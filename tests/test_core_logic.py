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


class _FakeRerankGemini:
    enabled = True

    def __init__(self) -> None:
        self.called = False

    def rerank_entity_candidates(
        self,
        *,
        user_message: str,
        recent_history: list[str],
        candidates: list[dict[str, object]],
    ) -> dict[str, object] | None:
        self.called = True
        pick_drug = None
        pick_herb = None

        for row in candidates:
            if row.get("type") == "drug" and str(row.get("name", "")).lower() == "warfarin":
                pick_drug = int(row["id"])
            if row.get("type") == "herb" and normalize_ascii(str(row.get("name", ""))) == "nhan sam":
                pick_herb = int(row["id"])

        selected: list[dict[str, object]] = []
        if pick_drug is not None:
            selected.append({"type": "drug", "id": pick_drug})
        if pick_herb is not None:
            selected.append({"type": "herb", "id": pick_herb})

        return {
            "selected": selected,
            "needs_clarification": False,
            "clarification_options": [],
        }

    def generate_grounded_answer(self, prompt: str, system_instruction: str) -> str | None:
        return None


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

    def test_resolver_exact_entity_resolution(self) -> None:
        match = self.resolver.resolve("warfarin")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.entity_type, "drug")
        self.assertEqual(normalize_ascii(match.canonical_name), "warfarin")

    def test_resolver_accent_insensitive_resolution(self) -> None:
        match = self.resolver.resolve("nhan sam")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.entity_type, "herb")
        self.assertEqual(normalize_ascii(match.canonical_name), "nhan sam")

    def test_resolver_typo_near_match_resolution(self) -> None:
        match = self.resolver.resolve("aspirn")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.entity_type, "drug")
        self.assertEqual(normalize_ascii(match.canonical_name), "aspirin")

    def test_ambiguous_term_behavior(self) -> None:
        hits = self.graph_service.extract_entities("sam", limit=6)
        herb_names = {normalize_ascii(item.name) for item in hits if item.type == "herb"}
        self.assertIn("nhan sam", herb_names)
        self.assertIn("dan sam", herb_names)

    def test_extract_entities_from_noisy_sentence(self) -> None:
        hits = self.graph_service.extract_entities("warfarin voi nhan sam thi sao", limit=8)
        names = {(item.type, normalize_ascii(item.name)) for item in hits}
        self.assertIn(("drug", "warfarin"), names)
        self.assertIn(("herb", "nhan sam"), names)

    def test_assistant_does_not_ask_missing_entities_when_pair_present(self) -> None:
        response = self.chat_service.generate_response("warfarin với nhân sâm thì sao?", [])
        answer_ascii = normalize_ascii(response.answer)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertNotIn("ban muon kiem tra", answer_ascii)
        self.assertNotIn("chua khop duoc ten", answer_ascii)

    def test_clarification_when_only_one_entity_resolved(self) -> None:
        response = self.chat_service.generate_response("tôi đang uống warfarn", [])
        answer_ascii = normalize_ascii(response.answer)
        names = {normalize_ascii(item.name) for item in response.grounding.entities}
        self.assertIn("warfarin", names)
        self.assertTrue("thao duoc nao" in answer_ascii or "ban muon kiem tra" in answer_ascii)

    def test_grounded_answer_generation_uses_local_data(self) -> None:
        response = self.chat_service.generate_response("warfarin với nhân sâm có tương tác không?", [])
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        self.assertIn("database/interaction.json", response.citations)
        self.assertIn("nguồn dữ liệu nội bộ", response.answer.lower())

    def test_entity_identification_question(self) -> None:
        response = self.chat_service.generate_response("gừng là loại gì?", [])
        answer_ascii = normalize_ascii(response.answer)
        names = {normalize_ascii(item.name) for item in response.grounding.entities}
        self.assertIn("gung", names)
        self.assertIn("thao duoc", answer_ascii)
        self.assertEqual(len(response.grounding.interactions), 0)

    def test_follow_up_uses_memory_entities(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="Warfarin và nhân sâm có tương tác không?"),
            ChatHistoryMessage(role="assistant", content="Có, cặp warfarin và nhân sâm có tương tác."),
        ]
        response = self.chat_service.generate_response("Tại sao nguy hiểm?", history)
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        first = response.grounding.interactions[0]
        self.assertEqual(normalize_ascii(first.drug_name), "warfarin")
        self.assertEqual(normalize_ascii(first.herb_name), "nhan sam")

    def test_unknown_question_does_not_hallucinate_from_history(self) -> None:
        history = [
            ChatHistoryMessage(role="user", content="Nhân sâm có tương tác với warfarin không?"),
            ChatHistoryMessage(role="assistant", content="Có, cặp warfarin và nhân sâm có tương tác."),
        ]
        response = self.chat_service.generate_response("Thuốc abcxyz có tương tác với cây qqq không?", history)
        self.assertEqual(len(response.grounding.interactions), 0)
        self.assertTrue(response.fallback)

    def test_gemini_role_is_candidate_reranker_only(self) -> None:
        fake_gemini = _FakeRerankGemini()
        chat_service = ChatService(self.graph_service, gemini_service=fake_gemini)
        response = chat_service.generate_response("warfarin voi sam co tuong tac khong?", [])
        self.assertTrue(fake_gemini.called)
        self.assertEqual(response.orchestrator, "gemini")
        self.assertGreaterEqual(len(response.grounding.interactions), 1)
        entity_names = {normalize_ascii(item.name) for item in response.grounding.entities}
        self.assertIn("warfarin", entity_names)
        self.assertIn("nhan sam", entity_names)


if __name__ == "__main__":
    unittest.main()
