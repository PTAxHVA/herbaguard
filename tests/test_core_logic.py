from __future__ import annotations

import unittest
from pathlib import Path

from models import ChatHistoryMessage
from services.chat_service import ChatService
from services.data_loader import load_database
from services.gemini_service import GeminiService
from services.graph_service import KnowledgeGraphService
from services.interaction_service import InteractionService
from services.normalize import deduplicate_inputs, normalize_ascii
from services.resolver import EntityResolver


class _FakeGeminiService:
    enabled = True

    def __init__(self) -> None:
        self.last_prompt = ""

    def generate_grounded_answer(self, prompt: str, system_instruction: str) -> str:
        self.last_prompt = prompt
        return "Đây là phản hồi Gemini grounded."


class CoreLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        db = load_database(Path("."))
        resolver = EntityResolver(db)

        cls.db = db
        cls.resolver = resolver
        cls.interaction_service = InteractionService(db, resolver)
        cls.graph_service = KnowledgeGraphService(db, resolver)
        cls.chat_service = ChatService(cls.graph_service, gemini_service=GeminiService(None))

    def test_normalize_ascii_vietnamese(self) -> None:
        self.assertEqual(normalize_ascii("Nhân Sâm"), "nhan sam")
        self.assertEqual(normalize_ascii("  BẠCH-QUẢ  "), "bach qua")

    def test_deduplicate_inputs_diacritics(self) -> None:
        items = ["nhân sâm", "nhan sam", "Warfarin", "warfarin"]
        self.assertEqual(deduplicate_inputs(items), ["nhân sâm", "Warfarin"])

    def test_resolver_handles_ascii_alias(self) -> None:
        match = self.resolver.resolve("nhan sam")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.entity_type, "herb")
        self.assertEqual(match.entity_id, 18)

    def test_graph_find_node_by_name(self) -> None:
        node = self.graph_service.find_node_by_name("nhân sâm")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.type, "herb")
        self.assertEqual(node.id, 18)

    def test_graph_find_node_by_alias(self) -> None:
        node = self.graph_service.find_node_by_alias("warfarin")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.type, "drug")

    def test_graph_check_interaction_pair(self) -> None:
        self.assertTrue(self.graph_service.check_interaction_pair("warfarin", "nhân sâm"))

    def test_graph_no_interaction_pair(self) -> None:
        self.assertFalse(self.graph_service.check_interaction_pair("warfarin", "bạc hà"))

    def test_chat_tool_identify_medical_entities_via_graph(self) -> None:
        entities, used_memory = self.chat_service.identify_medical_entities_via_graph(
            "Nhân sâm có tương tác với warfarin không?",
            [],
        )
        names = {(item.type, item.name) for item in entities}
        self.assertIn(("drug", "warfarin"), names)
        self.assertIn(("herb", "nhân sâm"), names)
        self.assertFalse(used_memory)

    def test_chat_tool_check_interaction_pair_via_graph(self) -> None:
        entities, _ = self.chat_service.identify_medical_entities_via_graph("warfarin và nhân sâm", [])
        drug = next(item for item in entities if item.type == "drug")
        herb = next(item for item in entities if item.type == "herb")
        rows = self.chat_service.check_interaction_pair_via_graph(drug, herb)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["drug_name"], "warfarin")

    def test_chat_tool_search_drug_info(self) -> None:
        entity = self.graph_service.resolve_entity("aspirin")
        self.assertIsNotNone(entity)
        assert entity is not None
        info = self.chat_service.search_drug_info(entity)
        self.assertEqual(info["type"], "drug")
        self.assertIn("aliases", info)

    def test_chat_tool_registry_contains_graph_agent_responsibilities(self) -> None:
        for name in [
            "detect_intents",
            "identify_medical_entities_via_graph",
            "resolve_follow_up_entities",
            "check_interaction_pair_via_graph",
            "search_drug_info",
            "build_response_plan",
            "build_grounded_prompt",
            "generate_gemini_response",
            "build_fallback_response",
        ]:
            self.assertIn(name, self.chat_service.tool_registry)

    def test_chat_build_grounded_prompt_includes_evidence_bundle(self) -> None:
        plan = self.chat_service.build_response_plan("Nhân sâm có tương tác với warfarin không?", [])
        prompt = self.chat_service.build_grounded_prompt(plan)
        self.assertIn("RESPONSE_PLAN_JSON", prompt)
        self.assertIn("warfarin", prompt.lower())

    def test_known_interaction_high(self) -> None:
        result = self.interaction_service.check_interactions(["warfarin", "bạch quả"])
        self.assertTrue(result.interaction_found)
        self.assertGreaterEqual(len(result.interaction_pairs), 1)
        self.assertEqual(result.summary.level, "danger")

    def test_known_interaction_medium(self) -> None:
        result = self.interaction_service.check_interactions(["warfarin", "nhân sâm"])
        self.assertTrue(result.interaction_found)
        self.assertGreaterEqual(len(result.interaction_pairs), 1)
        self.assertEqual(result.interaction_pairs[0].severity, "medium")
        self.assertEqual(result.summary.level, "warning")

    def test_no_interaction_path(self) -> None:
        result = self.interaction_service.check_interactions(["warfarin", "bạc hà"])
        self.assertFalse(result.interaction_found)
        self.assertEqual(result.summary.level, "safe")

    def test_chat_grounded_answer(self) -> None:
        response = self.chat_service.generate_response("Nhân sâm có tương tác với warfarin không?", [])
        self.assertTrue(response.fallback)
        self.assertGreaterEqual(len(response.grounding.entities), 2)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertIn("database/interaction.json", response.citations)

    def test_chat_follow_up_from_history(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="Warfarin và nhân sâm có tương tác không?"),
            ChatHistoryMessage(role="assistant", content="Có, cặp warfarin và nhân sâm có tương tác."),
        ]
        response = self.chat_service.generate_response("Tại sao nguy hiểm?", history)
        self.assertTrue(response.fallback)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        first = response.grounding.interactions[0]
        self.assertEqual(first.drug_name, "warfarin")
        self.assertEqual(first.herb_name, "nhân sâm")

    def test_chat_fallback_when_unknown(self) -> None:
        response = self.chat_service.generate_response("Xin tư vấn về thuốc không có trong hệ thống abcxyz", [])
        self.assertTrue(response.fallback)
        self.assertEqual(response.orchestrator, "local")

    def test_chat_greeting_intent(self) -> None:
        response = self.chat_service.generate_response("Xin chào", [])
        self.assertTrue(response.fallback)
        self.assertIn("xin chào", response.answer.lower())

    def test_chat_unknown_question_does_not_hallucinate_from_history(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="Nhân sâm có tương tác với warfarin không?"),
            ChatHistoryMessage(role="assistant", content="Có, cặp warfarin và nhân sâm có tương tác."),
        ]
        response = self.chat_service.generate_response("Thuốc abcxyz có tương tác với cây qqq không?", history)
        self.assertTrue(response.fallback)
        self.assertEqual(len(response.grounding.interactions), 0)

    def test_chat_recommendation_followup_keeps_previous_pair(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="Nhân sâm có tương tác với warfarin không?"),
            ChatHistoryMessage(role="assistant", content="Có, cặp warfarin và nhân sâm có tương tác."),
            ChatHistoryMessage(role="user", content="Tại sao nguy hiểm?"),
            ChatHistoryMessage(role="assistant", content="Do cơ chế tương tác trong dữ liệu local."),
        ]
        response = self.chat_service.generate_response("Tôi nên làm gì?", history)
        self.assertTrue(response.fallback)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        first = response.grounding.interactions[0]
        self.assertEqual(first.drug_name, "warfarin")
        self.assertEqual(first.herb_name, "nhân sâm")

    def test_multi_intent_greeting_plus_interaction(self) -> None:
        response = self.chat_service.generate_response(
            "xin chào bạn có biết warfarin với nhân sâm có tương tác không?",
            [],
        )
        self.assertIn("xin chào", response.answer.lower())
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue(response.fallback)

    def test_multi_intent_greeting_interaction_side_effects(self) -> None:
        response = self.chat_service.generate_response(
            "hello bạn ơi aspirin với nghệ có tác dụng phụ gì không?",
            [],
        )
        self.assertIn("xin chào", response.answer.lower())
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue("hậu quả" in response.answer.lower() or "tác dụng phụ" in response.answer.lower())

    def test_multi_intent_greeting_interaction_recommendation(self) -> None:
        response = self.chat_service.generate_response(
            "xin chào, nếu metformin với nhân sâm có tương tác thì tôi nên làm gì?",
            [],
        )
        self.assertIn("xin chào", response.answer.lower())
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue("khuyến nghị" in response.answer.lower() or "nên" in response.answer.lower())

    def test_multi_intent_classification_and_interaction(self) -> None:
        response = self.chat_service.generate_response(
            "warfarin là thuốc tây hay thảo dược? và có tương tác với bạch quả không?",
            [],
        )
        self.assertIn("thuốc tây", response.answer.lower())
        self.assertGreaterEqual(len(response.grounding.interactions), 1)

    def test_follow_up_side_effects_uses_memory_entities(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="warfarin với nhân sâm có tương tác không?"),
            ChatHistoryMessage(role="assistant", content="Có tương tác."),
        ]
        response = self.chat_service.generate_response("có tác dụng phụ gì?", history)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue("hậu quả" in response.answer.lower() or "tác dụng phụ" in response.answer.lower())
        self.assertTrue(response.fallback)

    def test_follow_up_generic_uses_memory_entities(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="warfarin với nhân sâm có tương tác không?"),
            ChatHistoryMessage(role="assistant", content="Có tương tác."),
        ]
        response = self.chat_service.generate_response("còn cái đó thì sao?", history)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue(response.fallback)

    def test_follow_up_brief_request_uses_memory_entities(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="warfarin với nhân sâm có tương tác không?"),
            ChatHistoryMessage(role="assistant", content="Có tương tác."),
        ]
        response = self.chat_service.generate_response("giải thích ngắn gọn hơn", history)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue(response.fallback)

    def test_clarification_when_missing_pair(self) -> None:
        response = self.chat_service.generate_response("nhân sâm có nguy hiểm không?", [])
        self.assertTrue(response.fallback)
        self.assertIn("nêu rõ 1 thuốc tây", response.answer.lower())

    def test_greeting_does_not_suppress_medical_answer(self) -> None:
        response = self.chat_service.generate_response(
            "xin chào bạn có biết warfarin với nhân sâm có tác dụng phụ gì không?",
            [],
        )
        self.assertIn("xin chào", response.answer.lower())
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertTrue("hậu quả" in response.answer.lower() or "tác dụng phụ" in response.answer.lower())

    def test_chat_runs_without_gemini_key(self) -> None:
        local_chat = ChatService(self.graph_service, gemini_service=GeminiService(None))
        response = local_chat.generate_response("Nhân sâm có tương tác với warfarin không?", [])
        self.assertEqual(response.orchestrator, "local")
        self.assertTrue(response.fallback)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)

    def test_chat_uses_gemini_orchestrator_when_available(self) -> None:
        fake_gemini = _FakeGeminiService()
        gemini_chat = ChatService(self.graph_service, gemini_service=fake_gemini)
        response = gemini_chat.generate_response("Nhân sâm có tương tác với warfarin không?", [])
        self.assertEqual(response.orchestrator, "gemini")
        self.assertIn("Gemini grounded", response.answer)
        self.assertIn("RESPONSE_PLAN_JSON", fake_gemini.last_prompt)


if __name__ == "__main__":
    unittest.main()
