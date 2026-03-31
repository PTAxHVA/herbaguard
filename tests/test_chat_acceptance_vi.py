from __future__ import annotations

import importlib
import os
import sys
import unittest
import uuid

from fastapi.testclient import TestClient

from database.mongo import clear_mongo_client_cache
from services.normalize import normalize_ascii


class ChatAcceptanceVietnameseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_mongodb_uri = os.environ.get("MONGODB_URI")
        cls._saved_mongodb_db_name = os.environ.get("MONGODB_DB_NAME")
        cls._saved_mongodb_use_mock = os.environ.get("MONGODB_USE_MOCK")
        cls._saved_google_api_key = os.environ.pop("GOOGLE_API_KEY", None)
        cls._saved_gemini_model = os.environ.pop("GEMINI_MODEL", None)

        os.environ["MONGODB_URI"] = "mongodb://127.0.0.1:27017"
        os.environ["MONGODB_DB_NAME"] = f"herbaguard-test-acceptance-{uuid.uuid4().hex}"
        os.environ["MONGODB_USE_MOCK"] = "1"
        clear_mongo_client_cache()

        if "app" in sys.modules:
            del sys.modules["app"]
        app_module = importlib.import_module("app")
        cls.client = TestClient(app_module.app)
        cls.headers = cls._register_and_get_auth_header()

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
        email = f"accept-{uuid.uuid4().hex[:10]}@example.com"
        payload = {
            "full_name": "Acceptance Tester",
            "email": email,
            "password": "12345678",
        }
        response = cls.client.post("/api/auth/register", json=payload)
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def _new_session(self) -> str:
        return f"s-{uuid.uuid4().hex[:12]}"

    def _chat(self, session_id: str, message: str) -> dict:
        response = self.client.post(
            "/api/chat",
            headers=self.headers,
            json={"session_id": session_id, "message": message},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["session_id"], session_id)
        self.assertIn("answer", payload)
        self.assertIn("grounding", payload)
        self.assertIn("citations", payload)
        self.assertIn("fallback", payload)
        self.assertIn("used_memory", payload)
        return payload

    def _history(self, session_id: str, limit: int = 50) -> dict:
        response = self.client.get(
            "/api/chat/history",
            headers=self.headers,
            params={"session_id": session_id, "limit": limit},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _clear_history(self, session_id: str) -> dict:
        response = self.client.delete(
            "/api/chat/history",
            headers=self.headers,
            params={"session_id": session_id},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _assert_not_social_only(self, payload: dict) -> None:
        answer_ascii = normalize_ascii(payload["answer"])
        has_medical_marker = any(
            marker in answer_ascii
            for marker in [
                "tuong tac",
                "co che",
                "hau qua",
                "tac dung phu",
                "khuyen nghi",
                "thuoc tay",
                "thao duoc",
                "nguy co",
            ]
        )
        has_grounding_signal = bool(payload["grounding"].get("interactions")) or bool(payload["grounding"].get("entities"))
        self.assertTrue(has_medical_marker or has_grounding_signal, payload["answer"])

    def _assert_has_entities(self, payload: dict, expected_names: list[str]) -> None:
        names_ascii = {normalize_ascii(item["name"]) for item in payload["grounding"].get("entities", [])}
        for name in expected_names:
            self.assertIn(normalize_ascii(name), names_ascii)

    def _assert_interaction_grounded(self, payload: dict) -> None:
        interactions = payload["grounding"].get("interactions", [])
        self.assertGreaterEqual(len(interactions), 1, payload["answer"])
        self.assertIn("database/interaction.json", payload.get("citations", []))

    # A. Greeting only
    def test_a1_greeting_only_xin_chao(self) -> None:
        payload = self._chat(self._new_session(), "xin chào")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("xin chao", answer_ascii)
        self.assertEqual(payload["grounding"]["interactions"], [])

    def test_a2_greeting_only_chao_ban(self) -> None:
        payload = self._chat(self._new_session(), "chào bạn")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("chao", answer_ascii)
        self.assertEqual(payload["grounding"]["interactions"], [])

    # B. Greeting + interaction
    def test_b1_greeting_plus_interaction(self) -> None:
        payload = self._chat(self._new_session(), "xin chào, warfarin với nhân sâm có tương tác không?")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("xin chao", answer_ascii)
        self._assert_interaction_grounded(payload)
        self._assert_has_entities(payload, ["warfarin", "nhân sâm"])
        self._assert_not_social_only(payload)

    def test_b2_hello_plus_interaction(self) -> None:
        payload = self._chat(self._new_session(), "hello bạn ơi, aspirin với nghệ có tương tác không?")
        self._assert_interaction_grounded(payload)
        self._assert_has_entities(payload, ["aspirin", "nghệ"])
        self._assert_not_social_only(payload)

    # C. Greeting + side effects
    def test_c1_greeting_interaction_side_effects(self) -> None:
        payload = self._chat(
            self._new_session(),
            "xin chào bạn có biết warfarin với nhân sâm có tác dụng phụ gì không?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("tac dung phu" in answer_ascii or "hau qua" in answer_ascii)
        self._assert_not_social_only(payload)

    def test_c2_greeting_interaction_consequences(self) -> None:
        payload = self._chat(
            self._new_session(),
            "chào bạn, aspirin với gừng có hậu quả gì nếu dùng chung?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("hau qua" in answer_ascii or "tac dung phu" in answer_ascii)
        self._assert_not_social_only(payload)

    # D. Greeting + recommendation
    def test_d1_greeting_interaction_recommendation(self) -> None:
        payload = self._chat(
            self._new_session(),
            "xin chào, nếu warfarin với bạch quả có tương tác thì tôi nên làm gì?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("khuyen nghi" in answer_ascii or "nen" in answer_ascii)

    def test_d2_hello_interaction_recommendation(self) -> None:
        payload = self._chat(
            self._new_session(),
            "hello, metformin với nhân sâm có tương tác không và tôi nên xử lý sao?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("khuyen nghi" in answer_ascii or "nen" in answer_ascii or "xu ly" in answer_ascii)

    # E. Classification + interaction
    def test_e1_classification_and_interaction(self) -> None:
        payload = self._chat(
            self._new_session(),
            "warfarin là thuốc tây hay thảo dược, và có tương tác với nhân sâm không?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("thuoc tay", answer_ascii)
        self._assert_interaction_grounded(payload)

    def test_e2_classification_herb_and_interaction(self) -> None:
        payload = self._chat(
            self._new_session(),
            "nhân sâm là thuốc hay thảo dược, và nó có tương tác với warfarin không?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("thao duoc", answer_ascii)
        self._assert_interaction_grounded(payload)

    # F. Mechanism
    def test_f1_mechanism_question(self) -> None:
        payload = self._chat(self._new_session(), "warfarin và nhân sâm tương tác với nhau theo cơ chế gì?")
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue(
            "co che" in answer_ascii
            or bool((payload["grounding"].get("evidence") or {}).get("mechanism"))
        )

    def test_f2_mechanism_style_question(self) -> None:
        payload = self._chat(self._new_session(), "aspirin với nghệ tác động lẫn nhau như thế nào?")
        # Supported data should still produce grounded interaction response.
        self._assert_interaction_grounded(payload)

    # G. Direct interaction
    def test_g1_direct_interaction_warfarin_nhan_sam(self) -> None:
        payload = self._chat(self._new_session(), "warfarin với nhân sâm có tương tác không?")
        self._assert_interaction_grounded(payload)

    def test_g2_direct_interaction_aspirin_nghe(self) -> None:
        payload = self._chat(self._new_session(), "aspirin với nghệ có tương tác không?")
        self._assert_interaction_grounded(payload)

    def test_g3_direct_interaction_metformin_nhan_sam(self) -> None:
        payload = self._chat(self._new_session(), "metformin với nhân sâm có tương tác không?")
        self._assert_interaction_grounded(payload)

    # H. Follow-up using memory
    def test_h1_follow_up_side_effects(self) -> None:
        session = self._new_session()
        self._chat(session, "warfarin với nhân sâm có tương tác không?")
        payload = self._chat(session, "có tác dụng phụ gì?")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertTrue(payload["used_memory"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("hau qua" in answer_ascii or "tac dung phu" in answer_ascii)

    def test_h2_follow_up_recommendation(self) -> None:
        session = self._new_session()
        self._chat(session, "warfarin với bạch quả có tương tác không?")
        payload = self._chat(session, "nên làm gì?")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertTrue(payload["used_memory"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("khuyen nghi" in answer_ascii or "nen" in answer_ascii)

    def test_h3_follow_up_brief(self) -> None:
        session = self._new_session()
        self._chat(session, "aspirin với nghệ có tương tác không?")
        payload = self._chat(session, "giải thích ngắn gọn hơn")
        self.assertTrue(payload["used_memory"])
        self._assert_interaction_grounded(payload)

    def test_h4_follow_up_pronoun_resolution(self) -> None:
        session = self._new_session()
        self._chat(session, "warfarin là thuốc tây hay thảo dược?")
        payload = self._chat(session, "nó có tương tác với nhân sâm không?")
        self.assertTrue(payload["used_memory"])
        self._assert_interaction_grounded(payload)
        self._assert_has_entities(payload, ["warfarin", "nhân sâm"])

    # I. Clarification needed
    def test_i1_needs_pair_clarification(self) -> None:
        payload = self._chat(self._new_session(), "nhân sâm có nguy hiểm không?")
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertTrue(payload["fallback"])
        self.assertIn("neu ro 1 thuoc tay", answer_ascii)

    def test_i2_missing_entity_reference(self) -> None:
        payload = self._chat(self._new_session(), "thuốc đó có tương tác không?")
        self.assertTrue(payload["fallback"])
        self.assertIn("nêu rõ", payload["answer"].lower())

    def test_i3_missing_context_side_effects(self) -> None:
        payload = self._chat(self._new_session(), "có tác dụng phụ gì?")
        self.assertTrue(payload["fallback"])
        self.assertIn("nêu rõ", payload["answer"].lower())

    # J. Unknown / no evidence
    def test_j1_unknown_herb(self) -> None:
        payload = self._chat(self._new_session(), "lá abcxyz có tương tác với warfarin không?")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["grounding"]["interactions"], [])

    def test_j2_unknown_drug(self) -> None:
        payload = self._chat(self._new_session(), "thuốc qwerty có tương tác với nhân sâm không?")
        self.assertTrue(payload["fallback"])
        self.assertEqual(payload["grounding"]["interactions"], [])

    def test_j3_unspecific_herb(self) -> None:
        payload = self._chat(self._new_session(), "cây thuốc gia truyền nhà tôi có tương tác với aspirin không?")
        self.assertTrue(payload["fallback"])
        self.assertIn("nêu rõ", payload["answer"].lower())

    # K. Casual language + medical question
    def test_k1_casual_language_still_resolves(self) -> None:
        payload = self._chat(self._new_session(), "bạn ơi cho mình hỏi warfarin với nhân sâm uống chung có sao không?")
        self._assert_interaction_grounded(payload)

    def test_k2_casual_language_aspirin_nghe(self) -> None:
        payload = self._chat(self._new_session(), "ờ cho mình hỏi tí, aspirin với nghệ dùng chung ổn không?")
        self._assert_interaction_grounded(payload)

    def test_k3_greeting_concern_interaction(self) -> None:
        payload = self._chat(self._new_session(), "xin chào nha, mình hơi lo là warfarin và bạch quả có nguy hiểm không")
        self._assert_interaction_grounded(payload)
        self._assert_not_social_only(payload)

    # L. Multi-intent with many outputs
    def test_l1_interaction_side_effect_recommendation(self) -> None:
        payload = self._chat(
            self._new_session(),
            "warfarin với nhân sâm có tương tác không, có tác dụng phụ gì, và tôi nên làm gì?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self._assert_interaction_grounded(payload)
        self.assertTrue("hau qua" in answer_ascii or "tac dung phu" in answer_ascii)
        self.assertTrue("khuyen nghi" in answer_ascii or "nen" in answer_ascii)

    def test_l2_classification_and_mechanism(self) -> None:
        payload = self._chat(
            self._new_session(),
            "aspirin là thuốc tây đúng không, và nếu dùng cùng nghệ thì cơ chế tương tác là gì?",
        )
        answer_ascii = normalize_ascii(payload["answer"])
        self.assertIn("thuoc tay", answer_ascii)
        self._assert_interaction_grounded(payload)
        self.assertTrue("co che" in answer_ascii or bool((payload["grounding"].get("evidence") or {}).get("mechanism")))

    def test_l3_greeting_interaction_brief(self) -> None:
        payload = self._chat(
            self._new_session(),
            "xin chào, metformin với nhân sâm có tương tác không, nếu có thì giải thích ngắn gọn giúp mình",
        )
        self._assert_interaction_grounded(payload)
        self.assertIn("xin chào", payload["answer"].lower())

    # M. Session history APIs
    def test_m1_history_returns_turn_order(self) -> None:
        session = self._new_session()
        self._chat(session, "warfarin với nhân sâm có tương tác không?")
        self._chat(session, "có tác dụng phụ gì?")
        history_payload = self._history(session)
        messages = history_payload["messages"]
        self.assertEqual(history_payload["session_id"], session)
        self.assertGreaterEqual(len(messages), 4)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")

    def test_m2_clear_history(self) -> None:
        session = self._new_session()
        self._chat(session, "warfarin với bạch quả có tương tác không?")
        clear_payload = self._clear_history(session)
        self.assertGreaterEqual(clear_payload["deleted_count"], 1)
        history_payload = self._history(session)
        self.assertEqual(history_payload["messages"], [])

    def test_m3_no_history_leak_between_sessions(self) -> None:
        s1 = self._new_session()
        s2 = self._new_session()
        self._chat(s1, "warfarin với nhân sâm có tương tác không?")
        self._chat(s2, "aspirin với nghệ có tương tác không?")
        h1 = self._history(s1)["messages"]
        h2 = self._history(s2)["messages"]
        self.assertNotEqual(len(h1), 0)
        self.assertNotEqual(len(h2), 0)
        self.assertNotEqual(h1[0]["content"], h2[0]["content"])

    # N. Gemini unavailable fallback
    def test_n1_no_gemini_interaction_core(self) -> None:
        payload = self._chat(self._new_session(), "warfarin với nhân sâm có tương tác không?")
        self.assertEqual(payload["orchestrator"], "local")
        # Strict acceptance expectation: when Gemini absent, fallback flag should indicate fallback path.
        self.assertTrue(payload["fallback"])
        self._assert_interaction_grounded(payload)

    def test_n2_no_gemini_multi_intent(self) -> None:
        payload = self._chat(self._new_session(), "xin chào, warfarin với nhân sâm có tác dụng phụ gì không?")
        self.assertEqual(payload["orchestrator"], "local")
        self.assertTrue(payload["fallback"])
        self._assert_interaction_grounded(payload)
        self._assert_not_social_only(payload)

    def test_n3_no_gemini_follow_up_memory(self) -> None:
        session = self._new_session()
        first = self._chat(session, "warfarin với nhân sâm có tương tác không?")
        second = self._chat(session, "nên làm gì?")
        self.assertEqual(first["orchestrator"], "local")
        self.assertEqual(second["orchestrator"], "local")
        self.assertTrue(second["used_memory"])
        self._assert_interaction_grounded(second)


if __name__ == "__main__":
    unittest.main()
