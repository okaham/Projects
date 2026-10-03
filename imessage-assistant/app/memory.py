"""Conversation memory stored in SQLite (a single file, data/assistant.db).

Each text you send and each reply the bot sends is one row. Before calling Claude,
we load the last HISTORY_LIMIT rows for that chat so Claude can see the conversation.

Inspect it any time with:  sqlite3 data/assistant.db "SELECT * FROM messages ORDER BY id DESC LIMIT 10"
"""

import os
import sqlite3

from app.config import settings


def _connect() -> sqlite3.Connection:
    # A new connection per call: simple, and safe because each background task runs
    # in its own thread (one sqlite3 connection must not be shared between threads).
    return sqlite3.connect(settings.db_path)


def init_db() -> None:
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_guid    TEXT NOT NULL,
                role         TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content      TEXT NOT NULL,
                message_guid TEXT,                        -- BlueBubbles id of your text (NULL for bot replies)
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))   -- UTC
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_guid, id)")
        conn.commit()
    finally:
        conn.close()


def save_exchange(chat_guid: str, user_text: str, assistant_text: str, message_guid: str | None) -> None:
    """Save your text and the bot's reply together.

    Both rows are written in one transaction: either both are saved or neither is.
    That keeps history strictly alternating user/assistant, which is what Claude expects.
    """
    conn = _connect()
    try:
        with conn:  # commits at the end of the block, or rolls back if an error happens inside
            conn.execute(
                "INSERT INTO messages (chat_guid, role, content, message_guid) VALUES (?, 'user', ?, ?)",
                (chat_guid, user_text, message_guid),
            )
            conn.execute(
                "INSERT INTO messages (chat_guid, role, content) VALUES (?, 'assistant', ?)",
                (chat_guid, assistant_text),
            )
    finally:
        conn.close()


def get_recent(chat_guid: str, limit: int) -> list[dict]:
    """Last `limit` messages for this chat, oldest first, in the format Claude's API takes."""
    conn = _connect()
    try:
        # Inner query: newest N rows. Outer query: flip them back to oldest-first.
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                WHERE chat_guid = ?
                ORDER BY id DESC
                LIMIT ?
            )
            ORDER BY id ASC
            """,
            (chat_guid, limit),
        ).fetchall()
    finally:
        conn.close()

    history = [{"role": role, "content": content} for role, content in rows]

    # Claude's conversation has to start with a user message. With an odd limit, the
    # window can begin on a bot reply, so drop it.
    while history and history[0]["role"] == "assistant":
        history.pop(0)
    return history
