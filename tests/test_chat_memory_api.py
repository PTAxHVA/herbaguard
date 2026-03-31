from __future__ import annotations

import importlib
import os
import sys
import unittest
import uuid

import mongomock
from bson import ObjectId
from fastapi.testclient import TestClient

from database.mongo import clear_mongo_client_cache
from services.chat_memory_service import ChatMemoryService


class ChatMemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = mongomock.MongoClient()
        self.db = self.client[f"chat-memory-{uuid.uuid4().hex}"]
        self.memory = ChatMemoryService(self.db)
        self.user_id = str(ObjectId())

    def tearDown(self) -> None:
        self.client.close()

    def test_append_list_clear_roundtrip(self) -> None:
        session_id = "unit-session-1"
        self.memory.append_message(self.user_id, session_id, "user", "Xin chào")
        self.memory.append_message(
            self.user_id,
            session_id,
            "assistant",
            "Tôi có thể hỗ trợ kiểm tra tương tác.",
            citations=["database/interaction.json"],
            fallback=False,
        )

        history = self.memory.get_history(self.user_id, session_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].role, "user")
        self.assertEqual(history[1].role, "assistant")
        self.assertEqual(history[1].citations, ["database/interaction.json"])

        deleted = self.memory.clear_history(self.user_id, session_id)
        self.assertEqual(deleted, 2)
        self.assertEqual(self.memory.get_history(self.user_id, session_id), [])


class ChatApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_mongodb_uri = os.environ.get("MONGODB_URI")
        cls._saved_mongodb_db_name = os.environ.get("MONGODB_DB_NAME")
        cls._saved_mongodb_use_mock = os.environ.get("MONGODB_USE_MOCK")
        cls._saved_google_api_key = os.environ.pop("GOOGLE_API_KEY", None)
        cls._saved_gemini_model = os.environ.pop("GEMINI_MODEL", None)

        os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:27017"
        os.environ["MONGODB_DB_NAME"] = f"herbaguard-test-api-{uuid.uuid4().hex}"
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
        if cls._saved_google_api_key is not None:
            os.environ["GOOGLE_API_KEY"] = cls._saved_google_api_key
        if cls._saved_gemini_model is not None:
            os.environ["GEMINI_MODEL"] = cls._saved_gemini_model

    @classmethod
    def _register_and_get_auth_header(cls) -> dict[str, str]:
        email = f"chat-{uuid.uuid4().hex[:10]}@example.com"
        payload = {
            "full_name": "Test User",
            "email": email,
            "password": "12345678",
        }
        response = cls.client.post("/api/auth/register", json=payload)
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_chat_follow_up_uses_memory_and_history_endpoints(self) -> None:
        headers = self._register_and_get_auth_header()
        session_id = f"s-{uuid.uuid4().hex[:12]}"

        first = self.client.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": session_id,
                "message": "Nhân sâm có tương tác với warfarin không?",
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        first_payload = first.json()
        self.assertEqual(first_payload["session_id"], session_id)
        self.assertEqual(first_payload["orchestrator"], "local")

        second = self.client.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": session_id,
                "message": "Tại sao nguy hiểm?",
            },
        )
        self.assertEqual(second.status_code, 200, second.text)
        second_payload = second.json()
        self.assertTrue(second_payload["used_memory"])
        self.assertEqual(second_payload["orchestrator"], "local")
        self.assertGreaterEqual(len(second_payload["grounding"]["interactions"]), 1)

        history = self.client.get(
            "/api/chat/history",
            headers=headers,
            params={"session_id": session_id, "limit": 20},
        )
        self.assertEqual(history.status_code, 200, history.text)
        history_payload = history.json()
        self.assertEqual(history_payload["session_id"], session_id)
        self.assertGreaterEqual(len(history_payload["messages"]), 4)

        cleared = self.client.delete(
            "/api/chat/history",
            headers=headers,
            params={"session_id": session_id},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertGreaterEqual(cleared.json()["deleted_count"], 1)

        history_after_clear = self.client.get(
            "/api/chat/history",
            headers=headers,
            params={"session_id": session_id, "limit": 20},
        )
        self.assertEqual(history_after_clear.status_code, 200, history_after_clear.text)
        self.assertEqual(history_after_clear.json()["messages"], [])

    def test_chat_unknown_question_fallback(self) -> None:
        headers = self._register_and_get_auth_header()
        session_id = f"s-{uuid.uuid4().hex[:12]}"

        response = self.client.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": session_id,
                "message": "Thuốc abcxyz có tương tác với cây qqq không?",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["orchestrator"], "local")

    def test_chat_multi_intent_greeting_and_medical_not_suppressed(self) -> None:
        headers = self._register_and_get_auth_header()
        session_id = f"s-{uuid.uuid4().hex[:12]}"
        response = self.client.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": session_id,
                "message": "xin chào bạn có biết warfarin với nhân sâm có tác dụng phụ gì không?",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("xin chào", payload["answer"].lower())
        self.assertGreaterEqual(len(payload["grounding"]["interactions"]), 1)

    def test_interaction_api_still_works(self) -> None:
        headers = self._register_and_get_auth_header()
        response = self.client.post(
            "/api/check-interaction",
            headers=headers,
            json={"items": ["warfarin", "nhân sâm"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["interaction_found"])


if __name__ == "__main__":
    unittest.main()
