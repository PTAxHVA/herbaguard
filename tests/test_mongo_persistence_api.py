from __future__ import annotations

import importlib
import os
import sys
import unittest
import uuid

from fastapi.testclient import TestClient

from database.mongo import clear_mongo_client_cache


class MongoPersistenceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_mongodb_uri = os.environ.get("MONGODB_URI")
        cls._saved_mongodb_db_name = os.environ.get("MONGODB_DB_NAME")
        cls._saved_mongodb_use_mock = os.environ.get("MONGODB_USE_MOCK")

        os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:27017"
        os.environ["MONGODB_DB_NAME"] = f"herbaguard-test-persist-{uuid.uuid4().hex}"
        os.environ["MONGODB_USE_MOCK"] = "1"
        clear_mongo_client_cache()

        if "app" in sys.modules:
            del sys.modules["app"]
        app_module = importlib.import_module("app")
        cls.client = TestClient(app_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        clear_mongo_client_cache()

        if cls._saved_mongodb_uri is None:
            os.environ.pop("MONGODB_URI", None)
        else:
            os.environ["MONGODB_URI"] = cls._saved_mongodb_uri

        if cls._saved_mongodb_db_name is None:
            os.environ.pop("MONGODB_DB_NAME", None)
        else:
            os.environ["MONGODB_DB_NAME"] = cls._saved_mongodb_db_name

        if cls._saved_mongodb_use_mock is None:
            os.environ.pop("MONGODB_USE_MOCK", None)
        else:
            os.environ["MONGODB_USE_MOCK"] = cls._saved_mongodb_use_mock

    @classmethod
    def _register(cls) -> tuple[str, dict[str, str]]:
        email = f"persist-{uuid.uuid4().hex[:10]}@example.com"
        response = cls.client.post(
            "/api/auth/register",
            json={
                "full_name": "Persistence User",
                "email": email,
                "password": "12345678",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        token = payload["token"]
        headers = {"Authorization": f"Bearer {token}"}
        return token, headers

    def test_auth_me_logout_flow(self) -> None:
        token, headers = self._register()
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 10)

        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        me_payload = me.json()
        self.assertIsInstance(me_payload["id"], str)
        self.assertEqual(me_payload["email"].endswith("@example.com"), True)

        logout = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logout.status_code, 200, logout.text)

        me_after = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_after.status_code, 401, me_after.text)

    def test_settings_medicines_reminders_dashboard_history_persistence(self) -> None:
        _, headers = self._register()

        settings_get = self.client.get("/api/settings", headers=headers)
        self.assertEqual(settings_get.status_code, 200, settings_get.text)
        self.assertEqual(settings_get.json()["theme"], "light")

        settings_put = self.client.put(
            "/api/settings",
            headers=headers,
            json={
                "voice_enabled": True,
                "large_text": True,
                "theme": "dark",
                "browser_notifications": True,
            },
        )
        self.assertEqual(settings_put.status_code, 200, settings_put.text)
        self.assertEqual(settings_put.json()["theme"], "dark")

        med_create = self.client.post(
            "/api/medicines",
            headers=headers,
            json={
                "name": "Vitamin C",
                "dosage": "500mg",
                "instructions": "Sau ăn",
                "stock_count": 3,
                "kind": "drug",
            },
        )
        self.assertEqual(med_create.status_code, 200, med_create.text)
        med_payload = med_create.json()
        medicine_id = med_payload["id"]
        self.assertIsInstance(medicine_id, str)

        meds_list = self.client.get("/api/medicines", headers=headers)
        self.assertEqual(meds_list.status_code, 200, meds_list.text)
        self.assertGreaterEqual(len(meds_list.json()), 1)

        med_update = self.client.put(
            f"/api/medicines/{medicine_id}",
            headers=headers,
            json={
                "name": "Vitamin C Plus",
                "dosage": "1000mg",
                "instructions": "Sau ăn sáng",
                "stock_count": 2,
                "kind": "drug",
            },
        )
        self.assertEqual(med_update.status_code, 200, med_update.text)
        self.assertEqual(med_update.json()["name"], "Vitamin C Plus")

        reminder_create = self.client.post(
            "/api/reminders",
            headers=headers,
            json={
                "medicine_id": medicine_id,
                "time_of_day": "08:30",
                "frequency_note": "Hằng ngày",
                "meal_note": "Sau ăn",
                "is_enabled": True,
            },
        )
        self.assertEqual(reminder_create.status_code, 200, reminder_create.text)
        reminder_id = reminder_create.json()["id"]
        self.assertIsInstance(reminder_id, str)

        reminders_list = self.client.get("/api/reminders", headers=headers)
        self.assertEqual(reminders_list.status_code, 200, reminders_list.text)
        reminders_payload = reminders_list.json()
        self.assertGreaterEqual(len(reminders_payload), 1)
        self.assertEqual(reminders_payload[0]["medicine_name"], "Vitamin C Plus")

        dashboard = self.client.get("/api/dashboard", headers=headers)
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        dashboard_payload = dashboard.json()
        self.assertIn("upcoming_reminders", dashboard_payload)
        self.assertIn("low_stock_medicines", dashboard_payload)

        check = self.client.post(
            "/api/check-interaction",
            headers=headers,
            json={"items": ["warfarin", "nhân sâm"]},
        )
        self.assertEqual(check.status_code, 200, check.text)

        history = self.client.get("/api/check-history", headers=headers)
        self.assertEqual(history.status_code, 200, history.text)
        history_payload = history.json()
        self.assertGreaterEqual(len(history_payload), 1)
        self.assertIsInstance(history_payload[0]["id"], str)

        reminder_delete = self.client.delete(f"/api/reminders/{reminder_id}", headers=headers)
        self.assertEqual(reminder_delete.status_code, 200, reminder_delete.text)

        med_delete = self.client.delete(f"/api/medicines/{medicine_id}", headers=headers)
        self.assertEqual(med_delete.status_code, 200, med_delete.text)


if __name__ == "__main__":
    unittest.main()
