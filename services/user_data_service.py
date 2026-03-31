from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from models import CheckHistoryItem, DashboardAlert, DashboardData, MedicineItem, ReminderItem, UserSettings
from services.mongo_helpers import datetime_to_iso, parse_object_id, to_id_str, utc_now


class UserDataService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.medicines = db["medicines"]
        self.reminders = db["reminders"]
        self.user_settings = db["user_settings"]
        self.check_history = db["check_history"]
        self._lock = Lock()
        self._init_indexes()

    def _init_indexes(self) -> None:
        self.medicines.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)], name="medicines_user_updated")
        self.reminders.create_index(
            [("user_id", ASCENDING), ("is_enabled", DESCENDING), ("time_of_day", ASCENDING), ("_id", DESCENDING)],
            name="reminders_user_schedule",
        )
        self.reminders.create_index([("medicine_id", ASCENDING)], name="reminders_medicine_id")
        self.user_settings.create_index([("user_id", ASCENDING)], unique=True, name="user_settings_user_unique")
        self.check_history.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
            name="check_history_user_created",
        )

    @staticmethod
    def _next_due_iso(time_of_day: str, now: datetime | None = None) -> str:
        base = now or datetime.now()
        hour_text, minute_text = time_of_day.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)

        due = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due < base:
            due = due + timedelta(days=1)
        return due.isoformat()

    @staticmethod
    def _medicine_from_doc(doc: dict[str, Any]) -> MedicineItem:
        return MedicineItem(
            id=to_id_str(doc["_id"]),
            name=str(doc.get("name") or ""),
            dosage=str(doc.get("dosage") or ""),
            instructions=str(doc.get("instructions") or ""),
            stock_count=int(doc.get("stock_count") or 0),
            kind=str(doc.get("kind") or "unknown"),
            created_at=datetime_to_iso(doc.get("created_at")),
            updated_at=datetime_to_iso(doc.get("updated_at")),
        )

    @classmethod
    def _reminder_from_doc(cls, doc: dict[str, Any], medicine_name: str) -> ReminderItem:
        time_of_day = str(doc.get("time_of_day") or "00:00")
        return ReminderItem(
            id=to_id_str(doc["_id"]),
            medicine_id=to_id_str(doc.get("medicine_id") or ""),
            medicine_name=medicine_name,
            time_of_day=time_of_day,
            frequency_note=str(doc.get("frequency_note") or "Hằng ngày"),
            meal_note=str(doc.get("meal_note") or ""),
            is_enabled=bool(doc.get("is_enabled", True)),
            next_due_iso=cls._next_due_iso(time_of_day),
            created_at=datetime_to_iso(doc.get("created_at")),
            updated_at=datetime_to_iso(doc.get("updated_at")),
        )

    @staticmethod
    def _user_oid(user_id: str) -> ObjectId:
        return parse_object_id(user_id, field_name="user_id")

    @staticmethod
    def _medicine_oid(medicine_id: str) -> ObjectId:
        return parse_object_id(medicine_id, field_name="medicine_id")

    @staticmethod
    def _reminder_oid(reminder_id: str) -> ObjectId:
        return parse_object_id(reminder_id, field_name="reminder_id")

    def list_medicines(self, user_id: str) -> list[MedicineItem]:
        user_oid = self._user_oid(user_id)
        rows = list(
            self.medicines.find(
                {"user_id": user_oid},
                sort=[("updated_at", DESCENDING), ("_id", DESCENDING)],
            )
        )
        return [self._medicine_from_doc(row) for row in rows]

    def create_medicine(
        self,
        user_id: str,
        *,
        name: str,
        dosage: str,
        instructions: str,
        stock_count: int,
        kind: str,
    ) -> MedicineItem:
        user_oid = self._user_oid(user_id)
        now = utc_now()

        with self._lock:
            result = self.medicines.insert_one(
                {
                    "user_id": user_oid,
                    "name": name,
                    "dosage": dosage,
                    "instructions": instructions,
                    "stock_count": int(stock_count),
                    "kind": kind,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            row = self.medicines.find_one({"_id": result.inserted_id, "user_id": user_oid})

        if row is None:
            raise ValueError("Không thể tạo thuốc.")
        return self._medicine_from_doc(row)

    def update_medicine(
        self,
        user_id: str,
        medicine_id: str,
        *,
        name: str,
        dosage: str,
        instructions: str,
        stock_count: int,
        kind: str,
    ) -> MedicineItem | None:
        user_oid = self._user_oid(user_id)
        medicine_oid = self._medicine_oid(medicine_id)

        with self._lock:
            self.medicines.update_one(
                {"_id": medicine_oid, "user_id": user_oid},
                {
                    "$set": {
                        "name": name,
                        "dosage": dosage,
                        "instructions": instructions,
                        "stock_count": int(stock_count),
                        "kind": kind,
                        "updated_at": utc_now(),
                    }
                },
            )
            row = self.medicines.find_one({"_id": medicine_oid, "user_id": user_oid})

        if row is None:
            return None
        return self._medicine_from_doc(row)

    def delete_medicine(self, user_id: str, medicine_id: str) -> bool:
        user_oid = self._user_oid(user_id)
        medicine_oid = self._medicine_oid(medicine_id)

        with self._lock:
            self.reminders.delete_many({"user_id": user_oid, "medicine_id": medicine_oid})
            result = self.medicines.delete_one({"user_id": user_oid, "_id": medicine_oid})
        return result.deleted_count > 0

    def _medicine_owner_row(self, user_oid: ObjectId, medicine_oid: ObjectId) -> dict[str, Any] | None:
        return self.medicines.find_one(
            {"_id": medicine_oid, "user_id": user_oid},
            {"_id": 1, "name": 1},
        )

    def list_reminders(self, user_id: str) -> list[ReminderItem]:
        user_oid = self._user_oid(user_id)
        rows = list(
            self.reminders.find(
                {"user_id": user_oid},
                sort=[("is_enabled", DESCENDING), ("time_of_day", ASCENDING), ("_id", DESCENDING)],
            )
        )

        medicine_ids = [row.get("medicine_id") for row in rows if isinstance(row.get("medicine_id"), ObjectId)]
        medicine_map: dict[str, str] = {}
        if medicine_ids:
            medicines = self.medicines.find({"_id": {"$in": medicine_ids}}, {"_id": 1, "name": 1})
            medicine_map = {to_id_str(doc["_id"]): str(doc.get("name") or "Không rõ") for doc in medicines}

        reminders = [
            self._reminder_from_doc(row, medicine_map.get(to_id_str(row.get("medicine_id") or ""), "Không rõ"))
            for row in rows
        ]
        reminders.sort(key=lambda item: item.next_due_iso)
        return reminders

    def create_reminder(
        self,
        user_id: str,
        *,
        medicine_id: str,
        time_of_day: str,
        frequency_note: str,
        meal_note: str,
        is_enabled: bool,
    ) -> ReminderItem:
        user_oid = self._user_oid(user_id)
        medicine_oid = self._medicine_oid(medicine_id)

        medicine_doc = self._medicine_owner_row(user_oid, medicine_oid)
        if medicine_doc is None:
            raise ValueError("Thuốc được chọn không hợp lệ.")

        now = utc_now()
        with self._lock:
            result = self.reminders.insert_one(
                {
                    "user_id": user_oid,
                    "medicine_id": medicine_oid,
                    "time_of_day": time_of_day,
                    "frequency_note": frequency_note,
                    "meal_note": meal_note,
                    "is_enabled": bool(is_enabled),
                    "created_at": now,
                    "updated_at": now,
                }
            )
            row = self.reminders.find_one({"_id": result.inserted_id, "user_id": user_oid})

        if row is None:
            raise ValueError("Không thể tạo lịch nhắc.")

        return self._reminder_from_doc(row, str(medicine_doc.get("name") or "Không rõ"))

    def update_reminder(
        self,
        user_id: str,
        reminder_id: str,
        *,
        medicine_id: str,
        time_of_day: str,
        frequency_note: str,
        meal_note: str,
        is_enabled: bool,
    ) -> ReminderItem | None:
        user_oid = self._user_oid(user_id)
        reminder_oid = self._reminder_oid(reminder_id)
        medicine_oid = self._medicine_oid(medicine_id)

        medicine_doc = self._medicine_owner_row(user_oid, medicine_oid)
        if medicine_doc is None:
            raise ValueError("Thuốc được chọn không hợp lệ.")

        with self._lock:
            self.reminders.update_one(
                {"_id": reminder_oid, "user_id": user_oid},
                {
                    "$set": {
                        "medicine_id": medicine_oid,
                        "time_of_day": time_of_day,
                        "frequency_note": frequency_note,
                        "meal_note": meal_note,
                        "is_enabled": bool(is_enabled),
                        "updated_at": utc_now(),
                    }
                },
            )
            row = self.reminders.find_one({"_id": reminder_oid, "user_id": user_oid})

        if row is None:
            return None
        return self._reminder_from_doc(row, str(medicine_doc.get("name") or "Không rõ"))

    def delete_reminder(self, user_id: str, reminder_id: str) -> bool:
        user_oid = self._user_oid(user_id)
        reminder_oid = self._reminder_oid(reminder_id)
        with self._lock:
            result = self.reminders.delete_one({"user_id": user_oid, "_id": reminder_oid})
        return result.deleted_count > 0

    def get_settings(self, user_id: str) -> UserSettings:
        user_oid = self._user_oid(user_id)
        row = self.user_settings.find_one({"user_id": user_oid})

        if row is None:
            row = {
                "user_id": user_oid,
                "voice_enabled": False,
                "large_text": False,
                "theme": "light",
                "browser_notifications": False,
                "updated_at": utc_now(),
            }
            self.user_settings.insert_one(row)

        theme = str(row.get("theme") or "light")
        if theme not in {"light", "dark"}:
            theme = "light"

        return UserSettings(
            voice_enabled=bool(row.get("voice_enabled", False)),
            large_text=bool(row.get("large_text", False)),
            theme=theme,
            browser_notifications=bool(row.get("browser_notifications", False)),
        )

    def update_settings(self, user_id: str, updates: dict[str, Any]) -> UserSettings:
        user_oid = self._user_oid(user_id)
        current = self.get_settings(user_id)
        payload = current.model_dump()

        for key, value in updates.items():
            if value is not None and key in payload:
                payload[key] = value

        safe_theme = str(payload["theme"]) if str(payload["theme"]) in {"light", "dark"} else "light"

        self.user_settings.update_one(
            {"user_id": user_oid},
            {
                "$set": {
                    "voice_enabled": bool(payload["voice_enabled"]),
                    "large_text": bool(payload["large_text"]),
                    "theme": safe_theme,
                    "browser_notifications": bool(payload["browser_notifications"]),
                    "updated_at": utc_now(),
                },
                "$setOnInsert": {
                    "user_id": user_oid,
                },
            },
            upsert=True,
        )

        return UserSettings(**payload)

    def add_check_history(
        self,
        user_id: str,
        *,
        input_items: list[str],
        summary_level: str,
        summary_title: str,
        result_payload: dict[str, Any],
    ) -> None:
        user_oid = self._user_oid(user_id)
        with self._lock:
            self.check_history.insert_one(
                {
                    "user_id": user_oid,
                    "input_items": [str(item) for item in input_items],
                    "summary_level": summary_level,
                    "summary_title": summary_title,
                    "result_payload": result_payload,
                    "created_at": utc_now(),
                }
            )

    def list_check_history(self, user_id: str, limit: int = 10) -> list[CheckHistoryItem]:
        user_oid = self._user_oid(user_id)
        rows = list(
            self.check_history.find(
                {"user_id": user_oid},
                sort=[("created_at", DESCENDING), ("_id", DESCENDING)],
                limit=max(1, int(limit)),
            )
        )

        output: list[CheckHistoryItem] = []
        for row in rows:
            raw_items = row.get("input_items")
            if isinstance(raw_items, list):
                items = [str(item) for item in raw_items]
            else:
                items = []

            output.append(
                CheckHistoryItem(
                    id=to_id_str(row["_id"]),
                    input_items=items,
                    summary_level=str(row.get("summary_level") or "safe"),
                    summary_title=str(row.get("summary_title") or ""),
                    created_at=datetime_to_iso(row.get("created_at")),
                )
            )

        return output

    def get_dashboard_data(self, user_id: str) -> DashboardData:
        medicines = self.list_medicines(user_id)
        reminders = self.list_reminders(user_id)
        history = self.list_check_history(user_id, limit=1)

        low_stock = [item for item in medicines if item.stock_count <= 5]
        upcoming = [item for item in reminders if item.is_enabled]
        upcoming.sort(key=lambda item: item.next_due_iso)

        alerts: list[DashboardAlert] = []
        if upcoming:
            first = upcoming[0]
            alerts.append(
                DashboardAlert(
                    type="reminder",
                    title="Nhắc uống thuốc sắp tới",
                    message=f"{first.medicine_name} lúc {first.time_of_day}. {first.frequency_note}".strip(),
                    action_label="Mở tủ thuốc",
                )
            )

        for medicine in low_stock[:2]:
            alerts.append(
                DashboardAlert(
                    type="low_stock",
                    title=f"Sắp hết {medicine.name}",
                    message=f"Chỉ còn {medicine.stock_count} đơn vị trong tủ thuốc.",
                    action_label="Bổ sung ngay",
                )
            )

        if history:
            latest = history[0]
            if latest.summary_level in {"danger", "warning"}:
                alerts.append(
                    DashboardAlert(
                        type="interaction",
                        title="Lần kiểm tra gần nhất có cảnh báo",
                        message=f"{latest.summary_title} - {' + '.join(latest.input_items[:3])}",
                        action_label="Xem kết quả",
                    )
                )

        return DashboardData(
            alerts=alerts,
            upcoming_reminders=upcoming[:5],
            low_stock_medicines=low_stock[:5],
        )
