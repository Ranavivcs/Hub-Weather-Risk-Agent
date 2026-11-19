"""Conversation persistence: append-only message history per conversation, in SQLite."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create(conn: sqlite3.Connection) -> str:
    """Start a new conversation and return its id."""
    conversation_id = uuid.uuid4().hex
    conn.execute("INSERT INTO conversations (id, created_at) VALUES (?, ?)", (conversation_id, _now()))
    conn.commit()
    return conversation_id


def exists(conn: sqlite3.Connection, conversation_id: str) -> bool:
    return conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone() is not None


def load_messages(conn: sqlite3.Connection, conversation_id: str) -> list[dict]:
    """The full history in Messages API shape: [{"role": ..., "content": [...]}, ...]."""
    rows = conn.execute(
        "SELECT role, content_json FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
    )
    return [{"role": r["role"], "content": json.loads(r["content_json"])} for r in rows]


def append_turn(conn: sqlite3.Connection, conversation_id: str, messages: list[dict]) -> None:
    """Store all messages of one completed turn in a single transaction.

    Called only after a turn succeeds, so a failed turn (e.g. API error mid tool-loop) leaves no
    half-finished tool exchange in the history; the user can simply ask again.
    """
    now = _now()
    with conn:  # one transaction: all rows or none
        conn.executemany(
            "INSERT INTO messages (conversation_id, role, content_json, created_at) VALUES (?, ?, ?, ?)",
            [(conversation_id, m["role"], json.dumps(m["content"]), now) for m in messages],
        )
