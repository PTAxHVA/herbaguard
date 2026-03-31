#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import load_config
from database.mongo import get_mongo_database
from services.auth_service import AuthService
from services.chat_memory_service import ChatMemoryService
from services.mongo_helpers import normalize_datetime
from services.user_data_service import UserDataService


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return bool(_parse_int(value, 1 if default else 0))


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


def migrate(sqlite_path: Path, *, mongodb_uri: str, mongodb_db_name: str, use_mock: bool, verbose: bool) -> int:
    if not sqlite_path.exists():
        print(f"[ERROR] Không tìm thấy file SQLite: {sqlite_path}")
        return 1

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    try:
        db = get_mongo_database(mongodb_uri, mongodb_db_name, use_mock=use_mock)

        # Ensure indexes are initialized before migration writes.
        AuthService(db)
        ChatMemoryService(db)
        UserDataService(db)

        users_col = db["users"]
        sessions_col = db["sessions"]
        medicines_col = db["medicines"]
        reminders_col = db["reminders"]
        settings_col = db["user_settings"]
        check_history_col = db["check_history"]
        chat_col = db["chat_messages"]

        counts: dict[str, int] = {
            "users_inserted": 0,
            "users_updated": 0,
            "users_skipped": 0,
            "sessions_inserted": 0,
            "sessions_updated": 0,
            "sessions_skipped": 0,
            "medicines_inserted": 0,
            "medicines_updated": 0,
            "medicines_skipped": 0,
            "reminders_inserted": 0,
            "reminders_updated": 0,
            "reminders_skipped": 0,
            "settings_inserted": 0,
            "settings_updated": 0,
            "settings_skipped": 0,
            "check_history_inserted": 0,
            "check_history_updated": 0,
            "check_history_skipped": 0,
            "chat_inserted": 0,
            "chat_updated": 0,
            "chat_skipped": 0,
        }

        user_map: dict[int, Any] = {}
        medicine_map: dict[tuple[int, int], Any] = {}

        if _table_exists(conn, "users"):
            rows = conn.execute(
                "SELECT id, full_name, email, password_hash, created_at FROM users ORDER BY id ASC"
            ).fetchall()
            for row in rows:
                legacy_user_id = _parse_int(row["id"])
                email = str(row["email"] or "").strip().lower()
                if not email:
                    counts["users_skipped"] += 1
                    continue

                existing = users_col.find_one({"email": email}, {"_id": 1})
                payload = {
                    "full_name": str(row["full_name"] or "").strip(),
                    "password_hash": str(row["password_hash"] or ""),
                    "created_at": normalize_datetime(row["created_at"]),
                    "legacy_sqlite_id": legacy_user_id,
                }

                if existing is None:
                    result = users_col.insert_one({"email": email, **payload})
                    user_oid = result.inserted_id
                    counts["users_inserted"] += 1
                    _log(verbose, f"[users] insert email={email}")
                else:
                    user_oid = existing["_id"]
                    users_col.update_one({"_id": user_oid}, {"$set": payload})
                    counts["users_updated"] += 1
                    _log(verbose, f"[users] update email={email}")

                user_map[legacy_user_id] = user_oid

        if _table_exists(conn, "sessions"):
            rows = conn.execute(
                "SELECT token, user_id, created_at FROM sessions"
            ).fetchall()
            for row in rows:
                token = str(row["token"] or "").strip()
                legacy_user_id = _parse_int(row["user_id"])
                if not token:
                    counts["sessions_skipped"] += 1
                    continue

                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["sessions_skipped"] += 1
                        _log(verbose, f"[sessions] skip token={token[:8]}... (missing user)")
                        continue
                    user_oid = user_doc["_id"]

                token_hash = AuthService._hash_token(token)
                result = sessions_col.update_one(
                    {"token_hash": token_hash},
                    {
                        "$set": {
                            "user_id": user_oid,
                            "created_at": normalize_datetime(row["created_at"]),
                            "legacy_sqlite_token": token,
                        }
                    },
                    upsert=True,
                )
                if result.upserted_id is not None:
                    counts["sessions_inserted"] += 1
                elif result.modified_count > 0:
                    counts["sessions_updated"] += 1
                else:
                    counts["sessions_skipped"] += 1

        if _table_exists(conn, "medicines"):
            rows = conn.execute(
                """
                SELECT id, user_id, name, dosage, instructions, stock_count, kind, created_at, updated_at
                FROM medicines
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                legacy_id = _parse_int(row["id"])
                legacy_user_id = _parse_int(row["user_id"])
                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["medicines_skipped"] += 1
                        continue
                    user_oid = user_doc["_id"]

                filter_doc = {"user_id": user_oid, "legacy_sqlite_id": legacy_id}
                update_doc = {
                    "$set": {
                        "name": str(row["name"] or "").strip(),
                        "dosage": str(row["dosage"] or "").strip(),
                        "instructions": str(row["instructions"] or "").strip(),
                        "stock_count": _parse_int(row["stock_count"], 0),
                        "kind": str(row["kind"] or "unknown"),
                        "updated_at": normalize_datetime(row["updated_at"]),
                    },
                    "$setOnInsert": {
                        "created_at": normalize_datetime(row["created_at"]),
                    },
                }
                result = medicines_col.update_one(filter_doc, update_doc, upsert=True)
                med_doc = medicines_col.find_one(filter_doc, {"_id": 1})
                if med_doc is not None:
                    medicine_map[(legacy_user_id, legacy_id)] = med_doc["_id"]

                if result.upserted_id is not None:
                    counts["medicines_inserted"] += 1
                elif result.modified_count > 0:
                    counts["medicines_updated"] += 1
                else:
                    counts["medicines_skipped"] += 1

        if _table_exists(conn, "reminders"):
            rows = conn.execute(
                """
                SELECT id, user_id, medicine_id, time_of_day, frequency_note, meal_note,
                       is_enabled, created_at, updated_at
                FROM reminders
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                legacy_id = _parse_int(row["id"])
                legacy_user_id = _parse_int(row["user_id"])
                legacy_medicine_id = _parse_int(row["medicine_id"])

                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["reminders_skipped"] += 1
                        continue
                    user_oid = user_doc["_id"]

                medicine_oid = medicine_map.get((legacy_user_id, legacy_medicine_id))
                if medicine_oid is None:
                    med_doc = medicines_col.find_one(
                        {"user_id": user_oid, "legacy_sqlite_id": legacy_medicine_id},
                        {"_id": 1},
                    )
                    if med_doc is None:
                        counts["reminders_skipped"] += 1
                        continue
                    medicine_oid = med_doc["_id"]

                filter_doc = {"user_id": user_oid, "legacy_sqlite_id": legacy_id}
                update_doc = {
                    "$set": {
                        "medicine_id": medicine_oid,
                        "time_of_day": str(row["time_of_day"] or "08:00"),
                        "frequency_note": str(row["frequency_note"] or "Hằng ngày"),
                        "meal_note": str(row["meal_note"] or ""),
                        "is_enabled": _parse_bool(row["is_enabled"], True),
                        "updated_at": normalize_datetime(row["updated_at"]),
                    },
                    "$setOnInsert": {
                        "created_at": normalize_datetime(row["created_at"]),
                    },
                }
                result = reminders_col.update_one(filter_doc, update_doc, upsert=True)

                if result.upserted_id is not None:
                    counts["reminders_inserted"] += 1
                elif result.modified_count > 0:
                    counts["reminders_updated"] += 1
                else:
                    counts["reminders_skipped"] += 1

        if _table_exists(conn, "user_settings"):
            rows = conn.execute(
                """
                SELECT user_id, voice_enabled, large_text, theme, browser_notifications, updated_at
                FROM user_settings
                """
            ).fetchall()
            for row in rows:
                legacy_user_id = _parse_int(row["user_id"])
                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["settings_skipped"] += 1
                        continue
                    user_oid = user_doc["_id"]

                result = settings_col.update_one(
                    {"user_id": user_oid},
                    {
                        "$set": {
                            "voice_enabled": _parse_bool(row["voice_enabled"], False),
                            "large_text": _parse_bool(row["large_text"], False),
                            "theme": str(row["theme"] or "light"),
                            "browser_notifications": _parse_bool(row["browser_notifications"], False),
                            "updated_at": normalize_datetime(row["updated_at"]),
                            "legacy_sqlite_user_id": legacy_user_id,
                        },
                    },
                    upsert=True,
                )

                if result.upserted_id is not None:
                    counts["settings_inserted"] += 1
                elif result.modified_count > 0:
                    counts["settings_updated"] += 1
                else:
                    counts["settings_skipped"] += 1

        if _table_exists(conn, "check_history"):
            rows = conn.execute(
                """
                SELECT id, user_id, input_items, summary_level, summary_title, result_payload, created_at
                FROM check_history
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                legacy_id = _parse_int(row["id"])
                legacy_user_id = _parse_int(row["user_id"])
                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["check_history_skipped"] += 1
                        continue
                    user_oid = user_doc["_id"]

                result = check_history_col.update_one(
                    {"user_id": user_oid, "legacy_sqlite_id": legacy_id},
                    {
                        "$set": {
                            "input_items": [str(item) for item in _parse_json_list(row["input_items"])],
                            "summary_level": str(row["summary_level"] or "safe"),
                            "summary_title": str(row["summary_title"] or ""),
                            "result_payload": _parse_json_object(row["result_payload"]),
                            "created_at": normalize_datetime(row["created_at"]),
                        },
                    },
                    upsert=True,
                )

                if result.upserted_id is not None:
                    counts["check_history_inserted"] += 1
                elif result.modified_count > 0:
                    counts["check_history_updated"] += 1
                else:
                    counts["check_history_skipped"] += 1

        if _table_exists(conn, "chat_messages"):
            rows = conn.execute(
                """
                SELECT id, user_id, session_id, role, content,
                       grounding_json, citations_json, fallback, created_at
                FROM chat_messages
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                legacy_id = _parse_int(row["id"])
                legacy_user_id = _parse_int(row["user_id"])
                user_oid = user_map.get(legacy_user_id)
                if user_oid is None:
                    user_doc = users_col.find_one({"legacy_sqlite_id": legacy_user_id}, {"_id": 1})
                    if user_doc is None:
                        counts["chat_skipped"] += 1
                        continue
                    user_oid = user_doc["_id"]

                role_value = str(row["role"] or "assistant")
                role = "user" if role_value == "user" else "assistant"

                citations = [str(item) for item in _parse_json_list(row["citations_json"])]
                grounding = _parse_json_object(row["grounding_json"])

                result = chat_col.update_one(
                    {"user_id": user_oid, "legacy_sqlite_id": legacy_id},
                    {
                        "$set": {
                            "session_id": str(row["session_id"] or "").strip(),
                            "role": role,
                            "content": str(row["content"] or "").strip(),
                            "grounding": grounding if grounding else None,
                            "citations": citations,
                            "fallback": None if row["fallback"] is None else _parse_bool(row["fallback"], False),
                            "created_at": normalize_datetime(row["created_at"]),
                        },
                    },
                    upsert=True,
                )

                if result.upserted_id is not None:
                    counts["chat_inserted"] += 1
                elif result.modified_count > 0:
                    counts["chat_updated"] += 1
                else:
                    counts["chat_skipped"] += 1

        print("SQLite -> Mongo migration completed.")
        print(f"SQLite source: {sqlite_path}")
        print(f"Mongo target: {mongodb_db_name} @ {mongodb_uri}")
        for key in sorted(counts.keys()):
            print(f"- {key}: {counts[key]}")

        return 0
    finally:
        conn.close()


def main() -> int:
    config = load_config()

    parser = argparse.ArgumentParser(description="Migrate HerbaGuard SQLite data to MongoDB.")
    parser.add_argument(
        "--sqlite-path",
        default=str(PROJECT_ROOT / "herbaguard_auth.db"),
        help="Path to old SQLite database file.",
    )
    parser.add_argument(
        "--mongodb-uri",
        default=config.mongodb_uri,
        help="MongoDB URI (Atlas compatible).",
    )
    parser.add_argument(
        "--mongodb-db-name",
        default=config.mongodb_db_name,
        help="MongoDB database name.",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use mongomock instead of a real MongoDB connection.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-row migration logs.",
    )

    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).expanduser().resolve()
    return migrate(
        sqlite_path,
        mongodb_uri=args.mongodb_uri,
        mongodb_db_name=args.mongodb_db_name,
        use_mock=bool(args.use_mock or config.mongodb_use_mock),
        verbose=bool(args.verbose),
    )


if __name__ == "__main__":
    raise SystemExit(main())
