"""
database.py - Base de données SQLite pour FidesIA
Tables : users, exchanges, password_reset_tokens, jwt_blacklist
Thread-safe avec lock + thread-local connection pooling.
"""

import sqlite3
import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from config import DB_PATH

_db_lock = threading.Lock()
_thread_local = threading.local()


def _get_connection() -> sqlite3.Connection:
    """Thread-local cached connection. PRAGMAs set once per thread."""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _thread_local.conn = conn
    return conn


@contextmanager
def _db():
    """DRY context manager: acquires lock, yields connection, handles commit/rollback."""
    with _db_lock:
        conn = _get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_db():
    """Crée les tables et index au démarrage."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchanges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id INTEGER,
                conversation_id TEXT NOT NULL,
                question TEXT NOT NULL,
                response TEXT NOT NULL,
                sources_json TEXT,
                rating INTEGER CHECK(rating IS NULL OR (rating >= 1 AND rating <= 5)),
                age_group TEXT,
                knowledge_level TEXT,
                response_time_ms INTEGER,
                model TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                visible INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jwt_blacklist (
                jti TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Simple indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_session ON exchanges(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_user ON exchanges(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_conv ON exchanges(conversation_id)")

        # Composite indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_user_conv ON exchanges(user_id, conversation_id, visible)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_user_visible_ts ON exchanges(user_id, visible, timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_tokens(token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jwt_bl_exp ON jwt_blacklist(expires_at)")


# === Users ===

def create_user(email: str, password_hash: str, display_name: str) -> int:
    with _db() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
            (email, password_hash, display_name),
        )
        return cursor.lastrowid


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_last_login(user_id: int):
    with _db() as conn:
        conn.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )


def update_user_password(user_id: int, password_hash: str):
    with _db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )


# === Password Reset Tokens (hashed with SHA-256) ===

def save_reset_token(user_id: int, token_hash: str, expires_at: str):
    """Sauvegarde un token hashé (supprime les anciens du même user)."""
    with _db() as conn:
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, token_hash, expires_at),
        )


def get_reset_token(token_hash: str) -> Optional[Dict[str, Any]]:
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM password_reset_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None


def delete_reset_token(token_hash: str):
    with _db() as conn:
        conn.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))


def cleanup_expired_tokens():
    """Supprime les tokens expirés."""
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute("DELETE FROM password_reset_tokens WHERE expires_at < ?", (now,))


# === JWT Blacklist ===

def blacklist_jwt(jti: str, expires_at: str):
    """Ajoute un JTI à la blacklist (logout effectif)."""
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO jwt_blacklist (jti, expires_at) VALUES (?, ?)",
            (jti, expires_at),
        )


def is_jwt_blacklisted(jti: str) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT 1 FROM jwt_blacklist WHERE jti = ?", (jti,)).fetchone()
        return row is not None


def cleanup_expired_blacklist():
    """Supprime les JTI expirés."""
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute("DELETE FROM jwt_blacklist WHERE expires_at < ?", (now,))


# === Exchanges ===

def save_exchange(
    session_id: str,
    conversation_id: str,
    question: str,
    response: str,
    user_id: Optional[int] = None,
    sources: Optional[List[Dict]] = None,
    rating: Optional[int] = None,
    age_group: Optional[str] = None,
    knowledge_level: Optional[str] = None,
    response_time_ms: int = 0,
    model: Optional[str] = None,
) -> int:
    timestamp = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

    with _db() as conn:
        cursor = conn.execute("""
            INSERT INTO exchanges
            (timestamp, session_id, user_id, conversation_id,
             question, response, sources_json, rating,
             age_group, knowledge_level, response_time_ms, model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, session_id, user_id, conversation_id,
              question, response, sources_json, rating,
              age_group, knowledge_level, response_time_ms, model))
        return cursor.lastrowid


def check_conversation_owner(conversation_id: str, user_id: int) -> bool:
    """Vérifie qu'une conversation appartient bien à un utilisateur."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM exchanges WHERE conversation_id = ? AND user_id = ? LIMIT 1",
            (conversation_id, user_id),
        ).fetchone()
        return row is not None


def get_exchange_owner(exchange_id: int) -> Optional[Dict[str, Any]]:
    with _db() as conn:
        row = conn.execute(
            "SELECT user_id, session_id FROM exchanges WHERE id = ?",
            (exchange_id,),
        ).fetchone()
        return dict(row) if row else None


def update_rating(exchange_id: int, rating: int) -> bool:
    if not 1 <= rating <= 5:
        raise ValueError("La note doit être entre 1 et 5")
    with _db() as conn:
        conn.execute(
            "UPDATE exchanges SET rating = ? WHERE id = ?",
            (rating, exchange_id),
        )
        return True


def get_user_conversations(user_id: int) -> List[Dict[str, Any]]:
    """Liste des conversations d'un utilisateur connecté."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT
                e.conversation_id,
                MIN(e.timestamp) as created,
                COUNT(*) as message_count
            FROM exchanges e
            WHERE e.user_id = ? AND e.visible = 1
            GROUP BY e.conversation_id
            ORDER BY created DESC
        """, (user_id,)).fetchall()

        result = []
        for row in rows:
            first = conn.execute(
                "SELECT question FROM exchanges WHERE conversation_id = ? AND user_id = ? ORDER BY timestamp ASC LIMIT 1",
                (row["conversation_id"], user_id),
            ).fetchone()
            first_q = first["question"] if first else ""
            title = first_q[:50] + "..." if len(first_q) > 50 else first_q
            result.append({
                "id": row["conversation_id"],
                "title": title or "Nouvelle conversation",
                "created": row["created"],
                "message_count": row["message_count"],
            })
        return result


def get_conversation_messages(conversation_id: str, user_id: int = None, session_id: str = None) -> List[Dict[str, Any]]:
    with _db() as conn:
        if user_id:
            rows = conn.execute("""
                SELECT id, question, response, rating, response_time_ms, sources_json
                FROM exchanges
                WHERE user_id = ? AND conversation_id = ? AND visible = 1
                ORDER BY timestamp
            """, (user_id, conversation_id)).fetchall()
        elif session_id:
            rows = conn.execute("""
                SELECT id, question, response, rating, response_time_ms, sources_json
                FROM exchanges
                WHERE session_id = ? AND conversation_id = ? AND user_id IS NULL
                ORDER BY timestamp
            """, (session_id, conversation_id)).fetchall()
        else:
            return []

        messages = []
        for row in rows:
            messages.append({"role": "user", "content": row["question"]})
            sources = json.loads(row["sources_json"]) if row["sources_json"] else []
            messages.append({
                "role": "assistant",
                "content": row["response"],
                "exchange_id": row["id"],
                "rating": row["rating"],
                "response_time_ms": row["response_time_ms"],
                "sources_with_scores": sources,
            })
        return messages


def delete_exchange(exchange_id: int, user_id: int) -> bool:
    """Soft-delete un échange individuel (question + réponse)."""
    with _db() as conn:
        result = conn.execute(
            "UPDATE exchanges SET visible = 0 WHERE id = ? AND user_id = ?",
            (exchange_id, user_id),
        )
        return result.rowcount > 0


def delete_conversation(conversation_id: str, user_id: int) -> bool:
    with _db() as conn:
        conn.execute(
            "UPDATE exchanges SET visible = 0 WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        )
        return True
