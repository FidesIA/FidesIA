"""
database.py - Base de données SQLite pour FidesIA
Tables : users (inscription) + exchanges (conversations Q/R)
Thread-safe avec lock.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading

from config import DB_PATH

_db_lock = threading.Lock()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crée les tables au démarrage."""
    with _db_lock:
        conn = get_connection()
        try:
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
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_session ON exchanges(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_user ON exchanges(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_conv ON exchanges(conversation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_visible ON exchanges(visible)")
            conn.commit()
        finally:
            conn.close()


# === Users ===

def create_user(email: str, password_hash: str, display_name: str) -> int:
    """Crée un utilisateur. Retourne l'ID."""
    with _db_lock:
        conn = get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
                (email, password_hash, display_name)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retourne un utilisateur par email."""
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def update_last_login(user_id: int):
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), user_id)
            )
            conn.commit()
        finally:
            conn.close()


def update_user_password(user_id: int, password_hash: str):
    """Met à jour le mot de passe d'un utilisateur."""
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id)
            )
            conn.commit()
        finally:
            conn.close()


def save_reset_token(user_id: int, token: str, expires_at: str):
    """Sauvegarde un token de réinitialisation (supprime les anciens du même user)."""
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
            conn.execute(
                "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at)
            )
            conn.commit()
        finally:
            conn.close()


def get_reset_token(token: str) -> Optional[Dict[str, Any]]:
    """Retourne les infos d'un token de réinitialisation."""
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT user_id, expires_at FROM password_reset_tokens WHERE token = ?",
                (token,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def delete_reset_token(token: str):
    """Supprime un token après usage."""
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM password_reset_tokens WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()


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
    """Enregistre un échange Q/R. Retourne l'ID."""
    timestamp = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps(sources, ensure_ascii=False) if sources else None

    with _db_lock:
        conn = get_connection()
        try:
            cursor = conn.execute("""
                INSERT INTO exchanges
                (timestamp, session_id, user_id, conversation_id,
                 question, response, sources_json, rating,
                 age_group, knowledge_level, response_time_ms, model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, session_id, user_id, conversation_id,
                  question, response, sources_json, rating,
                  age_group, knowledge_level, response_time_ms, model))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def get_exchange_owner(exchange_id: int) -> Optional[Dict[str, Any]]:
    """Retourne user_id et session_id d'un échange."""
    with _db_lock:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT user_id, session_id FROM exchanges WHERE id = ?",
                (exchange_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def update_rating(exchange_id: int, rating: int) -> bool:
    if not 1 <= rating <= 5:
        raise ValueError("La note doit être entre 1 et 5")
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE exchanges SET rating = ? WHERE id = ?",
                (rating, exchange_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()


def get_user_conversations(user_id: int) -> List[Dict[str, Any]]:
    """Liste des conversations d'un utilisateur connecté."""
    with _db_lock:
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT
                    conversation_id,
                    MIN(timestamp) as created,
                    (SELECT question FROM exchanges e2
                     WHERE e2.conversation_id = e.conversation_id AND e2.user_id = e.user_id
                     ORDER BY e2.timestamp ASC LIMIT 1) as first_question,
                    COUNT(*) as message_count
                FROM exchanges e
                WHERE e.user_id = ? AND (e.visible = 1 OR e.visible IS NULL)
                GROUP BY e.conversation_id
                ORDER BY created DESC
            """, (user_id,)).fetchall()

            result = []
            for row in rows:
                first_q = row["first_question"] or ""
                title = first_q[:50] + "..." if len(first_q) > 50 else first_q
                result.append({
                    "id": row["conversation_id"],
                    "title": title or "Nouvelle conversation",
                    "created": row["created"],
                    "message_count": row["message_count"]
                })
            return result
        finally:
            conn.close()


def get_conversation_messages(conversation_id: str, user_id: int = None, session_id: str = None) -> List[Dict[str, Any]]:
    """Récupère les messages d'une conversation."""
    with _db_lock:
        conn = get_connection()
        try:
            if user_id:
                rows = conn.execute("""
                    SELECT id, question, response, rating, response_time_ms, sources_json
                    FROM exchanges
                    WHERE user_id = ? AND conversation_id = ?
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
                    "sources_with_scores": sources
                })
            return messages
        finally:
            conn.close()


def delete_conversation(conversation_id: str, user_id: int) -> bool:
    """Soft delete d'une conversation."""
    with _db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE exchanges SET visible = 0 WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()
