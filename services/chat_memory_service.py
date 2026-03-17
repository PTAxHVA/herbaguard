from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from models import ChatHistoryMessage, ChatRole


@dataclass(frozen=True)
class StoredChatMessage:
    role: ChatRole
    content: str
    created_at: datetime
    grounding: dict[str, Any] | None
    citations: list[str]
    fallback: bool | None


class ChatMemoryService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    grounding_json TEXT,
                    citations_json TEXT,
                    fallback INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_session
                ON chat_messages (user_id, session_id, id)
                """
            )
            conn.commit()

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        cleaned = (session_id or "").strip()
        if cleaned:
            return cleaned[:80]
        return uuid.uuid4().hex

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        text = (value or "").strip()
        if not text:
            return datetime.now(timezone.utc)

        try:
            if "T" in text:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            else:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.now(timezone.utc)

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _decode_json_object(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    @staticmethod
    def _decode_json_list(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]

    @classmethod
    def _row_to_message(cls, row: sqlite3.Row) -> StoredChatMessage:
        return StoredChatMessage(
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=cls._parse_datetime(str(row["created_at"])),
            grounding=cls._decode_json_object(row["grounding_json"]),
            citations=cls._decode_json_list(row["citations_json"]),
            fallback=bool(row["fallback"]) if row["fallback"] is not None else None,
        )

    def ensure_session_id(self, session_id: str | None) -> str:
        return self._normalize_session_id(session_id)

    def get_latest_session_id(self, user_id: int) -> str | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT session_id
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["session_id"])

    def append_message(
        self,
        user_id: int,
        session_id: str,
        role: ChatRole,
        content: str,
        *,
        grounding: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        fallback: bool | None = None,
    ) -> StoredChatMessage:
        session = self._normalize_session_id(session_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Nội dung chat trống.")

        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (
                    user_id, session_id, role, content, grounding_json, citations_json, fallback
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    session,
                    role,
                    clean_content,
                    json.dumps(grounding, ensure_ascii=False) if grounding is not None else None,
                    json.dumps(citations or [], ensure_ascii=False),
                    None if fallback is None else int(bool(fallback)),
                ),
            )
            row = conn.execute(
                """
                SELECT role, content, grounding_json, citations_json, fallback, created_at
                FROM chat_messages
                WHERE id = last_insert_rowid()
                """
            ).fetchone()
            conn.commit()

        if row is None:
            raise ValueError("Không thể lưu lịch sử chat.")
        return self._row_to_message(row)

    def get_history(self, user_id: int, session_id: str, limit: int = 80) -> list[StoredChatMessage]:
        session = self._normalize_session_id(session_id)
        safe_limit = max(1, min(int(limit), 200))

        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content, grounding_json, citations_json, fallback, created_at
                FROM chat_messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, session, safe_limit),
            ).fetchall()

        # Convert to chronological order for rendering/context.
        return [self._row_to_message(row) for row in reversed(rows)]

    def clear_history(self, user_id: int, session_id: str) -> int:
        session = self._normalize_session_id(session_id)
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_messages WHERE user_id = ? AND session_id = ?",
                (user_id, session),
            )
            conn.commit()
        return int(cursor.rowcount)

    @staticmethod
    def to_history_messages(items: list[StoredChatMessage], limit: int = 20) -> list[ChatHistoryMessage]:
        output: list[ChatHistoryMessage] = []
        for item in items[-limit:]:
            output.append(ChatHistoryMessage(role=item.role, content=item.content))
        return output
