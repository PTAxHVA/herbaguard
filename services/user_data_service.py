from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from models import CheckHistoryItem, DashboardAlert, DashboardData, MedicineItem, ReminderItem, UserSettings


class UserDataService:
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
                CREATE TABLE IF NOT EXISTS medicines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    dosage TEXT NOT NULL DEFAULT '',
                    instructions TEXT NOT NULL DEFAULT '',
                    stock_count INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL DEFAULT 'unknown',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    medicine_id INTEGER NOT NULL,
                    time_of_day TEXT NOT NULL,
                    frequency_note TEXT NOT NULL DEFAULT 'Hằng ngày',
                    meal_note TEXT NOT NULL DEFAULT '',
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(medicine_id) REFERENCES medicines(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    voice_enabled INTEGER NOT NULL DEFAULT 0,
                    large_text INTEGER NOT NULL DEFAULT 0,
                    theme TEXT NOT NULL DEFAULT 'light',
                    browser_notifications INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS check_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    input_items TEXT NOT NULL,
                    summary_level TEXT NOT NULL,
                    summary_title TEXT NOT NULL,
                    result_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    @staticmethod
    def _medicine_from_row(row: sqlite3.Row) -> MedicineItem:
        return MedicineItem(
            id=int(row["id"]),
            name=str(row["name"]),
            dosage=str(row["dosage"]),
            instructions=str(row["instructions"]),
            stock_count=int(row["stock_count"]),
            kind=str(row["kind"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
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

    def list_medicines(self, user_id: int) -> list[MedicineItem]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, dosage, instructions, stock_count, kind, created_at, updated_at
                FROM medicines
                WHERE user_id = ?
                ORDER BY datetime(updated_at) DESC, id DESC
                """,
                (user_id,),
            ).fetchall()

        return [self._medicine_from_row(row) for row in rows]

    def create_medicine(
        self,
        user_id: int,
        *,
        name: str,
        dosage: str,
        instructions: str,
        stock_count: int,
        kind: str,
    ) -> MedicineItem:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO medicines (user_id, name, dosage, instructions, stock_count, kind)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, name, dosage, instructions, stock_count, kind),
            )
            medicine_id = int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id, name, dosage, instructions, stock_count, kind, created_at, updated_at
                FROM medicines
                WHERE id = ? AND user_id = ?
                """,
                (medicine_id, user_id),
            ).fetchone()
            conn.commit()

        if row is None:
            raise ValueError("Không thể tạo thuốc.")
        return self._medicine_from_row(row)

    def update_medicine(
        self,
        user_id: int,
        medicine_id: int,
        *,
        name: str,
        dosage: str,
        instructions: str,
        stock_count: int,
        kind: str,
    ) -> MedicineItem | None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE medicines
                SET name = ?, dosage = ?, instructions = ?, stock_count = ?, kind = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (name, dosage, instructions, stock_count, kind, medicine_id, user_id),
            )
            row = conn.execute(
                """
                SELECT id, name, dosage, instructions, stock_count, kind, created_at, updated_at
                FROM medicines
                WHERE id = ? AND user_id = ?
                """,
                (medicine_id, user_id),
            ).fetchone()
            conn.commit()

        if row is None:
            return None
        return self._medicine_from_row(row)

    def delete_medicine(self, user_id: int, medicine_id: int) -> bool:
        with self._lock, self._connection() as conn:
            conn.execute(
                "DELETE FROM reminders WHERE user_id = ? AND medicine_id = ?",
                (user_id, medicine_id),
            )
            cursor = conn.execute(
                "DELETE FROM medicines WHERE user_id = ? AND id = ?",
                (user_id, medicine_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def _reminder_from_row(self, row: sqlite3.Row) -> ReminderItem:
        return ReminderItem(
            id=int(row["id"]),
            medicine_id=int(row["medicine_id"]),
            medicine_name=str(row["medicine_name"]),
            time_of_day=str(row["time_of_day"]),
            frequency_note=str(row["frequency_note"]),
            meal_note=str(row["meal_note"]),
            is_enabled=bool(row["is_enabled"]),
            next_due_iso=self._next_due_iso(str(row["time_of_day"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _check_medicine_owner(self, conn: sqlite3.Connection, user_id: int, medicine_id: int) -> bool:
        row = conn.execute(
            "SELECT id FROM medicines WHERE id = ? AND user_id = ?",
            (medicine_id, user_id),
        ).fetchone()
        return row is not None

    def list_reminders(self, user_id: int) -> list[ReminderItem]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.medicine_id, m.name AS medicine_name,
                       r.time_of_day, r.frequency_note, r.meal_note, r.is_enabled,
                       r.created_at, r.updated_at
                FROM reminders r
                JOIN medicines m ON m.id = r.medicine_id
                WHERE r.user_id = ?
                ORDER BY r.is_enabled DESC, r.time_of_day ASC, r.id DESC
                """,
                (user_id,),
            ).fetchall()

        reminders = [self._reminder_from_row(row) for row in rows]
        reminders.sort(key=lambda item: item.next_due_iso)
        return reminders

    def create_reminder(
        self,
        user_id: int,
        *,
        medicine_id: int,
        time_of_day: str,
        frequency_note: str,
        meal_note: str,
        is_enabled: bool,
    ) -> ReminderItem:
        with self._lock, self._connection() as conn:
            if not self._check_medicine_owner(conn, user_id, medicine_id):
                raise ValueError("Thuốc được chọn không hợp lệ.")

            cursor = conn.execute(
                """
                INSERT INTO reminders (user_id, medicine_id, time_of_day, frequency_note, meal_note, is_enabled)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, medicine_id, time_of_day, frequency_note, meal_note, int(is_enabled)),
            )
            reminder_id = int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT r.id, r.medicine_id, m.name AS medicine_name,
                       r.time_of_day, r.frequency_note, r.meal_note, r.is_enabled,
                       r.created_at, r.updated_at
                FROM reminders r
                JOIN medicines m ON m.id = r.medicine_id
                WHERE r.id = ? AND r.user_id = ?
                """,
                (reminder_id, user_id),
            ).fetchone()
            conn.commit()

        if row is None:
            raise ValueError("Không thể tạo lịch nhắc.")
        return self._reminder_from_row(row)

    def update_reminder(
        self,
        user_id: int,
        reminder_id: int,
        *,
        medicine_id: int,
        time_of_day: str,
        frequency_note: str,
        meal_note: str,
        is_enabled: bool,
    ) -> ReminderItem | None:
        with self._lock, self._connection() as conn:
            if not self._check_medicine_owner(conn, user_id, medicine_id):
                raise ValueError("Thuốc được chọn không hợp lệ.")

            conn.execute(
                """
                UPDATE reminders
                SET medicine_id = ?,
                    time_of_day = ?,
                    frequency_note = ?,
                    meal_note = ?,
                    is_enabled = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (medicine_id, time_of_day, frequency_note, meal_note, int(is_enabled), reminder_id, user_id),
            )
            row = conn.execute(
                """
                SELECT r.id, r.medicine_id, m.name AS medicine_name,
                       r.time_of_day, r.frequency_note, r.meal_note, r.is_enabled,
                       r.created_at, r.updated_at
                FROM reminders r
                JOIN medicines m ON m.id = r.medicine_id
                WHERE r.id = ? AND r.user_id = ?
                """,
                (reminder_id, user_id),
            ).fetchone()
            conn.commit()

        if row is None:
            return None
        return self._reminder_from_row(row)

    def delete_reminder(self, user_id: int, reminder_id: int) -> bool:
        with self._lock, self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM reminders WHERE user_id = ? AND id = ?",
                (user_id, reminder_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_settings(self, user_id: int) -> UserSettings:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT voice_enabled, large_text, theme, browser_notifications
                FROM user_settings
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO user_settings (user_id, voice_enabled, large_text, theme, browser_notifications)
                    VALUES (?, 0, 0, 'light', 0)
                    """,
                    (user_id,),
                )
                conn.commit()
                return UserSettings()

        return UserSettings(
            voice_enabled=bool(row["voice_enabled"]),
            large_text=bool(row["large_text"]),
            theme=str(row["theme"]),
            browser_notifications=bool(row["browser_notifications"]),
        )

    def update_settings(self, user_id: int, updates: dict[str, Any]) -> UserSettings:
        current = self.get_settings(user_id)
        payload = current.model_dump()

        for key, value in updates.items():
            if value is not None and key in payload:
                payload[key] = value

        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_settings (user_id, voice_enabled, large_text, theme, browser_notifications, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    voice_enabled = excluded.voice_enabled,
                    large_text = excluded.large_text,
                    theme = excluded.theme,
                    browser_notifications = excluded.browser_notifications,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    int(bool(payload["voice_enabled"])),
                    int(bool(payload["large_text"])),
                    str(payload["theme"]),
                    int(bool(payload["browser_notifications"])),
                ),
            )
            conn.commit()

        return UserSettings(**payload)

    def add_check_history(
        self,
        user_id: int,
        *,
        input_items: list[str],
        summary_level: str,
        summary_title: str,
        result_payload: dict[str, Any],
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO check_history (user_id, input_items, summary_level, summary_title, result_payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    json.dumps(input_items, ensure_ascii=False),
                    summary_level,
                    summary_title,
                    json.dumps(result_payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def list_check_history(self, user_id: int, limit: int = 10) -> list[CheckHistoryItem]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, input_items, summary_level, summary_title, created_at
                FROM check_history
                WHERE user_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        output: list[CheckHistoryItem] = []
        for row in rows:
            try:
                items = json.loads(str(row["input_items"]))
                if not isinstance(items, list):
                    items = []
            except json.JSONDecodeError:
                items = []

            output.append(
                CheckHistoryItem(
                    id=int(row["id"]),
                    input_items=[str(item) for item in items],
                    summary_level=str(row["summary_level"]),
                    summary_title=str(row["summary_title"]),
                    created_at=str(row["created_at"]),
                )
            )

        return output

    def get_dashboard_data(self, user_id: int) -> DashboardData:
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
