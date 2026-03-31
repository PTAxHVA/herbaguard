from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_object_id(value: str, *, field_name: str) -> ObjectId:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} không hợp lệ.")
    try:
        return ObjectId(cleaned)
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"{field_name} không hợp lệ.") from exc


def to_id_str(value: Any) -> str:
    return str(value)


def normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return utc_now()

        try:
            if "T" in text:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            else:
                parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return utc_now()

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return utc_now()


def datetime_to_iso(value: Any) -> str:
    return normalize_datetime(value).isoformat()
