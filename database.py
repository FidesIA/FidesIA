"""
database.py - Base de données SQLite pour FidesIA
Tables : users, exchanges, password_reset_tokens, jwt_blacklist,
         analytics_events, ip_geo_cache
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                ip TEXT,
                user_agent TEXT,
                user_id INTEGER,
                session_id TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ip_geo_cache (
                ip TEXT PRIMARY KEY,
                country TEXT,
                city TEXT,
                region TEXT,
                resolved_at TEXT DEFAULT (datetime('now'))
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

        # Analytics indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ae_type ON analytics_events(event_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ae_created ON analytics_events(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ae_ip ON analytics_events(ip)")


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


# === Analytics Events ===

_VALID_EVENTS = {
    "page_view", "question_guest", "question_auth",
    "login", "register",
    "click_donate", "click_saint", "click_corpus",
    "click_profile", "click_share", "click_example",
}


def save_event(
    event_type: str,
    ip: str = "",
    user_agent: str = "",
    user_id: Optional[int] = None,
    session_id: str = "",
    metadata: Optional[Dict] = None,
):
    if event_type not in _VALID_EVENTS:
        return
    meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
    with _db() as conn:
        conn.execute(
            "INSERT INTO analytics_events (event_type, ip, user_agent, user_id, session_id, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (event_type, ip, user_agent, user_id, session_id, meta_json),
        )


def get_all_questions(days: int = 30) -> List[str]:
    """Retourne les textes des questions des N derniers jours."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT question FROM exchanges WHERE created_at >= datetime('now', ?) AND visible = 1",
            (f"-{days} days",),
        ).fetchall()
        return [r["question"] for r in rows]


def get_events_summary(days: int = 30) -> Dict[str, Any]:
    cutoff = f"-{days} days"
    with _db() as conn:
        # Questions par jour (guest vs auth)
        questions_per_day = conn.execute("""
            SELECT date(created_at) as day,
                   SUM(CASE WHEN event_type = 'question_guest' THEN 1 ELSE 0 END) as guest,
                   SUM(CASE WHEN event_type = 'question_auth' THEN 1 ELSE 0 END) as auth
            FROM analytics_events
            WHERE event_type IN ('question_guest', 'question_auth')
              AND created_at >= datetime('now', ?)
            GROUP BY day ORDER BY day
        """, (cutoff,)).fetchall()

        # Clicks par type
        click_stats = conn.execute("""
            SELECT event_type, COUNT(*) as cnt
            FROM analytics_events
            WHERE event_type LIKE 'click_%'
              AND created_at >= datetime('now', ?)
            GROUP BY event_type
        """, (cutoff,)).fetchall()

        # Top exemples cliqués
        top_examples = conn.execute("""
            SELECT json_extract(metadata, '$.label') as label, COUNT(*) as cnt
            FROM analytics_events
            WHERE event_type = 'click_example'
              AND created_at >= datetime('now', ?)
              AND metadata IS NOT NULL
            GROUP BY label ORDER BY cnt DESC LIMIT 5
        """, (cutoff,)).fetchall()

        # Sessions uniques par IP
        ip_connections = conn.execute("""
            SELECT ip, COUNT(*) as visits,
                   COUNT(DISTINCT session_id) as sessions,
                   MAX(created_at) as last_seen
            FROM analytics_events
            WHERE event_type = 'page_view'
              AND created_at >= datetime('now', ?)
              AND ip IS NOT NULL AND ip != ''
            GROUP BY ip ORDER BY visits DESC LIMIT 50
        """, (cutoff,)).fetchall()

        # Guest vs auth sessions
        guest_questions = conn.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = 'question_guest' AND created_at >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()["c"]
        auth_questions = conn.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = 'question_auth' AND created_at >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()["c"]

        # Total page views
        total_views = conn.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = 'page_view' AND created_at >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()["c"]

        # Logins & registers
        logins = conn.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = 'login' AND created_at >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()["c"]
        registers = conn.execute(
            "SELECT COUNT(*) as c FROM analytics_events WHERE event_type = 'register' AND created_at >= datetime('now', ?)",
            (cutoff,),
        ).fetchone()["c"]

        return {
            "questions_per_day": [dict(r) for r in questions_per_day],
            "click_stats": {r["event_type"]: r["cnt"] for r in click_stats},
            "top_examples": [{"label": r["label"] or "?", "count": r["cnt"]} for r in top_examples],
            "ip_connections": [dict(r) for r in ip_connections],
            "guest_questions": guest_questions,
            "auth_questions": auth_questions,
            "total_views": total_views,
            "logins": logins,
            "registers": registers,
        }


def get_unresolved_ips(days: int = 30) -> List[str]:
    """IPs des N derniers jours qui ne sont pas dans ip_geo_cache."""
    with _db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT ae.ip
            FROM analytics_events ae
            LEFT JOIN ip_geo_cache gc ON ae.ip = gc.ip
            WHERE gc.ip IS NULL
              AND ae.ip IS NOT NULL AND ae.ip != '' AND ae.ip != '127.0.0.1'
              AND ae.created_at >= datetime('now', ?)
        """, (f"-{days} days",)).fetchall()
        return [r["ip"] for r in rows]


def save_ip_geo(ip: str, country: str, city: str, region: str):
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ip_geo_cache (ip, country, city, region) VALUES (?, ?, ?, ?)",
            (ip, country, city, region),
        )


def get_ip_geo_map() -> Dict[str, Dict[str, str]]:
    """Retourne {ip: {country, city, region}} pour toutes les IPs cachées."""
    with _db() as conn:
        rows = conn.execute("SELECT ip, country, city, region FROM ip_geo_cache").fetchall()
        return {r["ip"]: {"country": r["country"], "city": r["city"], "region": r["region"]} for r in rows}


def get_reconnection_stats(days: int = 30) -> Dict[str, Any]:
    """Stats de reconnexion : users qui reviennent, taux, délai moyen."""
    cutoff = f"-{days} days"
    with _db() as conn:
        # Users avec au moins 2 sessions distinctes (jours différents)
        rows = conn.execute("""
            SELECT user_id, GROUP_CONCAT(DISTINCT date(created_at)) as dates
            FROM analytics_events
            WHERE event_type = 'page_view' AND user_id IS NOT NULL
              AND created_at >= datetime('now', ?)
            GROUP BY user_id
        """, (cutoff,)).fetchall()

        unique_users = len(rows)
        returning = 0
        total_gap_days = 0
        gap_count = 0

        for row in rows:
            dates = sorted(row["dates"].split(","))
            if len(dates) >= 2:
                returning += 1
                for i in range(1, len(dates)):
                    d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                    d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                    total_gap_days += (d2 - d1).days
                    gap_count += 1

        return {
            "unique_users": unique_users,
            "returning_users": returning,
            "return_rate": round(returning / unique_users * 100, 1) if unique_users > 0 else 0,
            "avg_days_between": round(total_gap_days / gap_count, 1) if gap_count > 0 else 0,
        }
