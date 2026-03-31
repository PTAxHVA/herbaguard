from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from models import ChatHistoryMessage, ChatRole
from services.mongo_helpers import normalize_datetime, parse_object_id, utc_now


@dataclass(frozen=True)
class StoredChatMessage:
    role: ChatRole
    content: str
    created_at: datetime
    grounding: dict[str, Any] | None
    citations: list[str]
    fallback: bool | None


class ChatMemoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.collection = db["chat_messages"]
        self._lock = Lock()
        self._init_indexes()

    def _init_indexes(self) -> None:
        self.collection.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING), ("_id", ASCENDING)],
            name="chat_messages_user_session_created",
        )
        self.collection.create_index(
            [("user_id", ASCENDING), ("session_id", ASCENDING), ("_id", DESCENDING)],
            name="chat_messages_user_session_desc",
        )

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        cleaned = (session_id or "").strip()
        if cleaned:
            return cleaned[:80]
        return uuid.uuid4().hex

    @staticmethod
    def _doc_to_message(doc: dict[str, Any]) -> StoredChatMessage:
        citations_raw = doc.get("citations")
        citations = [str(item) for item in citations_raw] if isinstance(citations_raw, list) else []

        grounding_raw = doc.get("grounding")
        grounding = grounding_raw if isinstance(grounding_raw, dict) else None

        fallback_raw = doc.get("fallback")
        fallback = bool(fallback_raw) if isinstance(fallback_raw, bool | int) else None

        role_value = str(doc.get("role") or "assistant")
        role: ChatRole = "assistant" if role_value != "user" else "user"

        return StoredChatMessage(
            role=role,
            content=str(doc.get("content") or ""),
            created_at=normalize_datetime(doc.get("created_at")),
            grounding=grounding,
            citations=citations,
            fallback=fallback,
        )

    def ensure_session_id(self, session_id: str | None) -> str:
        return self._normalize_session_id(session_id)

    def get_latest_session_id(self, user_id: str) -> str | None:
        user_oid = parse_object_id(user_id, field_name="user_id")
        row = self.collection.find_one(
            {"user_id": user_oid},
            sort=[("_id", DESCENDING)],
            projection={"session_id": 1},
        )
        if row is None:
            return None
        return str(row.get("session_id") or "") or None

    def append_message(
        self,
        user_id: str,
        session_id: str,
        role: ChatRole,
        content: str,
        *,
        grounding: dict[str, Any] | None = None,
        citations: list[str] | None = None,
        fallback: bool | None = None,
    ) -> StoredChatMessage:
        user_oid = parse_object_id(user_id, field_name="user_id")
        session = self._normalize_session_id(session_id)
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Nội dung chat trống.")

        with self._lock:
            doc = {
                "user_id": user_oid,
                "session_id": session,
                "role": "assistant" if role != "user" else "user",
                "content": clean_content,
                "grounding": grounding if isinstance(grounding, dict) else None,
                "citations": [str(item) for item in (citations or [])],
                "fallback": fallback if fallback is None else bool(fallback),
                "created_at": utc_now(),
            }
            insert_result = self.collection.insert_one(doc)
            stored = self.collection.find_one({"_id": insert_result.inserted_id})

        if stored is None:
            raise ValueError("Không thể lưu lịch sử chat.")
        return self._doc_to_message(stored)

    def get_history(self, user_id: str, session_id: str, limit: int = 80) -> list[StoredChatMessage]:
        user_oid = parse_object_id(user_id, field_name="user_id")
        session = self._normalize_session_id(session_id)
        safe_limit = max(1, min(int(limit), 200))

        cursor = self.collection.find(
            {"user_id": user_oid, "session_id": session},
            sort=[("_id", DESCENDING)],
            limit=safe_limit,
        )
        rows = list(cursor)

        return [self._doc_to_message(row) for row in reversed(rows)]

    def clear_history(self, user_id: str, session_id: str) -> int:
        user_oid = parse_object_id(user_id, field_name="user_id")
        session = self._normalize_session_id(session_id)
        with self._lock:
            result = self.collection.delete_many({"user_id": user_oid, "session_id": session})
        return int(result.deleted_count)

    @staticmethod
    def to_history_messages(items: list[StoredChatMessage], limit: int = 20) -> list[ChatHistoryMessage]:
        output: list[ChatHistoryMessage] = []
        for item in items[-limit:]:
            output.append(ChatHistoryMessage(role=item.role, content=item.content))
        return output
