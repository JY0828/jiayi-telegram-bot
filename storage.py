from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    chat_type TEXT NOT NULL,
    title TEXT,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER,
    username TEXT,
    text TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id)
);
"""


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_chat(
        self,
        *,
        chat_id: int,
        chat_type: str,
        title: str | None,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        is_active: bool = True,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO chats (
                    chat_id, chat_type, title, username, first_name, last_name, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_type = excluded.chat_type,
                    title = excluded.title,
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    is_active = excluded.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chat_id,
                    chat_type,
                    title,
                    username,
                    first_name,
                    last_name,
                    1 if is_active else 0,
                ),
            )

    def set_active(self, chat_id: int, is_active: bool) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE chats SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                (1 if is_active else 0, chat_id),
            )

    def save_message(
        self,
        *,
        chat_id: int,
        user_id: int | None,
        username: str | None,
        text: str | None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO messages (chat_id, user_id, username, text) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, username, text),
            )

    def active_chat_ids(self) -> list[int]:
        with self.connect() as connection:
            rows: Iterable[sqlite3.Row] = connection.execute(
                "SELECT chat_id FROM chats WHERE is_active = 1 ORDER BY created_at"
            )
            return [int(row["chat_id"]) for row in rows]
