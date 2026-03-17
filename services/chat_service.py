from __future__ import annotations

import json
from dataclasses import dataclass

from models import (
    ChatGrounding,
    ChatHistoryMessage,
    ChatResponse,
    GroundingEntity,
    GroundingInteraction,
    InteractionDetail,
)
from services.chat_intent_service import ChatIntentService, IntentDetectionResult
from services.chat_memory_service import ChatMemoryService, StoredChatMessage
from services.gemini_service import GeminiService
from services.graph_service import GraphEntity, KnowledgeGraphService
from services.normalize import normalize_ascii

_CITATIONS = [
    "database/interaction.json",
    "database/herb.json",
    "database/drug.json",
]

_PRIMARY_INTENTS = {
    "interaction_query",
    "ask_side_effects",
    "ask_recommendation",
    "ask_mechanism",
    "entity_classification",
    "follow_up",
    "related_entities",
}


@dataclass(frozen=True)
class ResponsePlan:
    intents: set[str]
    message: str
    message_ascii: str
    history: list[ChatHistoryMessage]
    entities: list[GraphEntity]
    interactions: list[dict[str, object]]
    entity_infos: list[dict[str, object]]
    used_memory_for_entities: bool
    clarification_needed: bool
    response_parts: dict[str, bool]

    @property
    def interaction_found(self) -> bool:
        return bool(self.interactions)


class ChatService:
    def __init__(
        self,
        graph: KnowledgeGraphService,
        memory_service: ChatMemoryService | None = None,
        gemini_service: GeminiService | None = None,
        intent_service: ChatIntentService | None = None,
    ) -> None:
        self.graph = graph
        self.memory_service = memory_service
        self.gemini_service = gemini_service or GeminiService.from_env()
        self.intent_service = intent_service or ChatIntentService()
        self.tool_registry = {
            "detect_intents": self.detect_intents,
            "identify_medical_entities_via_graph": self.identify_medical_entities_via_graph,
            "resolve_follow_up_entities": self.resolve_follow_up_entities,
            "check_interaction_pair_via_graph": self.check_interaction_pair_via_graph,
            "search_drug_info": self.search_drug_info,
            "build_response_plan": self.build_response_plan,
            "build_grounded_prompt": self.build_grounded_prompt,
            "generate_gemini_response": self.generate_gemini_response,
            "build_fallback_response": self.build_fallback_response,
        }

    @property
    def gemini_enabled(self) -> bool:
        return self.gemini_service.enabled

    @staticmethod
    def _deduplicate_entities(items: list[GraphEntity]) -> list[GraphEntity]:
        output: list[GraphEntity] = []
        seen: set[tuple[str, int]] = set()
        for item in items:
            key = (item.type, item.id)
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    @staticmethod
    def _as_grounding_entities(items: list[GraphEntity]) -> list[GroundingEntity]:
        return [GroundingEntity(type=item.type, id=item.id, name=item.name) for item in items]

    @staticmethod
    def _as_grounding_interactions(items: list[dict[str, object]]) -> list[GroundingInteraction]:
        output: list[GroundingInteraction] = []
        for item in items:
            output.append(
                GroundingInteraction(
                    drug_id=int(item["drug_id"]),
                    herb_id=int(item["herb_id"]),
                    drug_name=str(item["drug_name"]),
                    herb_name=str(item["herb_name"]),
                    severity=str(item["severity"]),
                    mechanism=str(item["mechanism"]),
                    possible_consequences=[str(x) for x in item.get("possible_consequences", [])],
                    recommendation=str(item["recommendation"]),
                )
            )
        return output

    @staticmethod
    def _recent_user_messages(history: list[ChatHistoryMessage], limit: int = 8) -> list[ChatHistoryMessage]:
        users = [item for item in history if item.role == "user"]
        return users[-limit:]

    @staticmethod
    def _history_has_entities(history: list[ChatHistoryMessage]) -> bool:
        return any(item.role == "user" and len(item.content.strip()) >= 3 for item in history)

    @staticmethod
    def _contains_any(text_ascii: str, keywords: set[str]) -> bool:
        return any(keyword in text_ascii for keyword in keywords)

    @staticmethod
    def _merge_histories(
        persisted: list[ChatHistoryMessage],
        client_history: list[ChatHistoryMessage],
        limit: int = 30,
    ) -> list[ChatHistoryMessage]:
        if not persisted:
            return client_history[-limit:]
        if not client_history:
            return persisted[-limit:]

        merged = list(persisted)
        for item in client_history:
            if merged and merged[-1].role == item.role and merged[-1].content == item.content:
                continue
            merged.append(item)
        return merged[-limit:]

    def detect_intents(self, message: str, history: list[ChatHistoryMessage]) -> IntentDetectionResult:
        return self.intent_service.detect_intents(message, history)

    def resolve_follow_up_entities(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        current_entities: list[GraphEntity],
    ) -> tuple[list[GraphEntity], bool]:
        if not history:
            return current_entities, False

        user_messages = self._recent_user_messages(history, limit=8)
        if not user_messages:
            return current_entities, False

        latest_entities = self.graph.extract_entities(user_messages[-1].content, limit=8)
        if not latest_entities:
            merged_text = " ".join(item.content for item in user_messages)
            latest_entities = self.graph.extract_entities(merged_text, limit=8)

        if not latest_entities:
            return current_entities, False

        combined = self._deduplicate_entities(current_entities + latest_entities)
        if len(combined) == len(current_entities):
            return current_entities, False
        return combined, True

    def identify_medical_entities_via_graph(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        intents: set[str] | None = None,
    ) -> tuple[list[GraphEntity], bool]:
        current = self.graph.extract_entities(message, limit=8)
        entities = self._deduplicate_entities(current)
        used_memory = False

        intents = intents or set()
        asks_pair_logic = bool({"interaction_query", "ask_side_effects", "ask_recommendation", "ask_mechanism"} & intents)
        token_count = len([token for token in normalize_ascii(message).split(" ") if token])
        short_elliptical_question = token_count <= 6
        needs_context = (
            "follow_up" in intents
            or (asks_pair_logic and len(entities) == 1)
            or (asks_pair_logic and len(entities) == 0 and short_elliptical_question)
        )

        if needs_context and self._history_has_entities(history):
            entities, used_memory = self.resolve_follow_up_entities(message, history, entities)

        return self._deduplicate_entities(entities), used_memory

    def check_interaction_pair_via_graph(self, drug: GraphEntity, herb: GraphEntity) -> list[dict[str, object]]:
        return self.graph.get_interaction_evidence(drug, herb)

    def search_drug_info(self, entity: GraphEntity) -> dict[str, object]:
        node = self.graph.resolve_node(entity)
        aliases = list(node.aliases[:8]) if node is not None else [entity.name]
        related = [item.canonical_name for item in self.graph.related_entities(entity, limit=6)]
        return {
            "type": entity.type,
            "id": entity.id,
            "canonical_name": entity.name,
            "aliases": aliases,
            "related_entities": related,
            "label_vi": "Thuốc Tây" if entity.type == "drug" else "Thảo Dược",
        }

    def _enrich_intents(self, intents: set[str], entities: list[GraphEntity], message_ascii: str) -> set[str]:
        enriched = set(intents)
        has_drug = any(item.type == "drug" for item in entities)
        has_herb = any(item.type == "herb" for item in entities)

        if has_drug and has_herb:
            if {"ask_side_effects", "ask_recommendation", "ask_mechanism"}.intersection(enriched):
                enriched.add("interaction_query")
            if "interaction_query" not in enriched and "co" in message_ascii and "khong" in message_ascii:
                enriched.add("interaction_query")

        if not enriched:
            enriched.add("clarification_needed")

        return enriched

    def build_response_plan(self, message: str, history: list[ChatHistoryMessage]) -> ResponsePlan:
        detection = self.detect_intents(message, history)
        intents = set(detection.intents)
        entities, used_memory = self.identify_medical_entities_via_graph(message, history, intents=intents)

        intents = self._enrich_intents(intents, entities, detection.message_ascii)
        drugs = [item for item in entities if item.type == "drug"]
        herbs = [item for item in entities if item.type == "herb"]

        interactions: list[dict[str, object]] = []
        for drug in drugs:
            for herb in herbs:
                interactions.extend(self.check_interaction_pair_via_graph(drug, herb))
        interactions.sort(key=lambda row: (0 if row["severity"] == "high" else 1, row["drug_name"], row["herb_name"]))

        clarification_needed = False
        asks_pair_logic = bool({"interaction_query", "ask_side_effects", "ask_recommendation", "ask_mechanism"} & intents)
        if asks_pair_logic and not (drugs and herbs):
            clarification_needed = True
            intents.add("clarification_needed")

        entity_infos = [self.search_drug_info(item) for item in entities[:4]]
        primary_medical_present = bool(_PRIMARY_INTENTS.intersection(intents))
        has_explicit_primary = bool(
            {
                "interaction_query",
                "ask_side_effects",
                "ask_recommendation",
                "ask_mechanism",
                "entity_classification",
                "related_entities",
            }
            & intents
        )

        response_parts = {
            "include_greeting": "greeting" in intents,
            "include_help": "help" in intents and not primary_medical_present,
            "include_interaction_answer": (
                ("interaction_query" in intents and not clarification_needed)
                or ("follow_up" in intents and not has_explicit_primary and bool(interactions))
            ),
            "include_side_effects": "ask_side_effects" in intents and bool(interactions) and not clarification_needed,
            "include_recommendation": "ask_recommendation" in intents and bool(interactions) and not clarification_needed,
            "include_mechanism": "ask_mechanism" in intents and bool(interactions) and not clarification_needed,
            "include_classification": "entity_classification" in intents and bool(entities),
            "include_related_entities": "related_entities" in intents and bool(entities),
        }

        return ResponsePlan(
            intents=intents,
            message=message.strip(),
            message_ascii=detection.message_ascii,
            history=history[-10:],
            entities=entities,
            interactions=interactions,
            entity_infos=entity_infos,
            used_memory_for_entities=used_memory,
            clarification_needed=clarification_needed,
            response_parts=response_parts,
        )

    def _plan_as_json(self, plan: ResponsePlan) -> dict[str, object]:
        primary_evidence = None
        if plan.interactions:
            first = plan.interactions[0]
            primary_evidence = {
                "mechanism": first.get("mechanism", ""),
                "possible_consequences": first.get("possible_consequences", []),
                "recommendation": first.get("recommendation", ""),
            }

        return {
            "intents": sorted(plan.intents),
            "entities": [item.__dict__ for item in plan.entities],
            "interaction_found": bool(plan.interactions),
            "evidence": primary_evidence,
            "used_memory": plan.used_memory_for_entities,
            "clarification_needed": plan.clarification_needed,
            "response_parts": plan.response_parts,
            "interactions": plan.interactions,
            "entity_infos": plan.entity_infos,
        }

    def build_grounded_prompt(self, plan: ResponsePlan) -> str:
        history_lines = [f"{item.role}: {item.content}" for item in plan.history[-8:]]
        plan_json = self._plan_as_json(plan)
        return (
            f"Người dùng: {plan.message}\n\n"
            "Lịch sử gần nhất:\n"
            + ("\n".join(history_lines) if history_lines else "(không có)")
            + "\n\nRESPONSE_PLAN_JSON:\n"
            + json.dumps(plan_json, ensure_ascii=False, indent=2)
            + "\n\nYÊU CẦU:\n"
            + "1) Trả lời bằng tiếng Việt.\n"
            + "2) Bắt buộc xử lý tất cả phần `response_parts` được bật true.\n"
            + "3) Nếu include_greeting=true thì chào ngắn gọn 1 câu.\n"
            + "4) Nếu có câu hỏi y khoa hợp lệ thì không được trả lời social-only.\n"
            + "5) Chỉ dùng dữ liệu trong RESPONSE_PLAN_JSON, không bịa kiến thức ngoài.\n"
            + "6) Nếu clarification_needed=true thì yêu cầu người dùng nêu rõ 1 thuốc tây + 1 thảo dược.\n"
            + "7) Nếu include_side_effects=true thì nêu hậu quả/tác dụng phụ từ evidence.\n"
            + "8) Nếu include_recommendation=true thì nêu khuyến nghị từ evidence.\n"
            + "9) Tránh dài dòng, rõ ràng, an toàn.\n"
        )

    def generate_gemini_response(self, plan: ResponsePlan) -> str | None:
        system_instruction = (
            "Bạn là trợ lý HerbaGuard AI. Bạn chỉ được dùng dữ liệu cung cấp trong plan để trả lời. "
            "Không suy diễn ngoài dữ liệu local. Không bỏ sót intent quan trọng."
        )
        prompt = self.build_grounded_prompt(plan)
        return self.gemini_service.generate_grounded_answer(prompt=prompt, system_instruction=system_instruction)

    @staticmethod
    def _answer_has_greeting(answer_ascii: str) -> bool:
        return "xin chao" in answer_ascii or "chao" in answer_ascii or "hello" in answer_ascii

    def _postprocess_answer(self, answer: str, plan: ResponsePlan) -> str:
        text = answer.strip()
        ascii_text = normalize_ascii(text)

        if plan.response_parts["include_greeting"] and not self._answer_has_greeting(ascii_text):
            text = "Xin chào bạn. " + text
            ascii_text = normalize_ascii(text)

        if plan.response_parts["include_interaction_answer"] and plan.interactions:
            first = plan.interactions[0]
            pair_hint = f"{first['drug_name']} và {first['herb_name']}"
            if normalize_ascii(str(first["drug_name"])) not in ascii_text or normalize_ascii(str(first["herb_name"])) not in ascii_text:
                text += f"\nDữ liệu local ghi nhận cặp {pair_hint} có tương tác."
                ascii_text = normalize_ascii(text)

        if plan.response_parts["include_interaction_answer"] and not plan.interactions:
            drugs = [item for item in plan.entities if item.type == "drug"]
            herbs = [item for item in plan.entities if item.type == "herb"]
            if drugs and herbs and "chua tim thay tuong tac" not in ascii_text:
                text += "\nHiện chưa tìm thấy tương tác giữa các cặp bạn hỏi trong dữ liệu local hiện có."
                ascii_text = normalize_ascii(text)

        if plan.response_parts["include_classification"]:
            if "thuoc tay" not in ascii_text and "thao duoc" not in ascii_text:
                chunks = []
                for entity in plan.entities[:2]:
                    label = "thuốc tây" if entity.type == "drug" else "thảo dược"
                    chunks.append(f"'{entity.name}' là {label}")
                if chunks:
                    text += "\n" + "; ".join(chunks) + "."
                    ascii_text = normalize_ascii(text)

        if plan.clarification_needed and "nêu rõ" not in ascii_text:
            text += "\nMình cần bạn nêu rõ 1 thuốc tây và 1 thảo dược để kiểm tra chính xác."

        if plan.response_parts["include_side_effects"] and plan.interactions:
            if "tac dung phu" not in ascii_text and "hau qua" not in ascii_text:
                consequences = plan.interactions[0].get("possible_consequences", [])
                if consequences:
                    text += f"\nHậu quả có thể gặp: {consequences[0]}."

        if plan.response_parts["include_recommendation"] and plan.interactions:
            if "khuyen nghi" not in ascii_text and "nen" not in ascii_text:
                text += f"\nKhuyến nghị: {plan.interactions[0].get('recommendation', '')}".rstrip()

        return text.strip()

    def build_fallback_response(self, plan: ResponsePlan) -> tuple[str, bool]:
        lines: list[str] = []
        fallback = False

        if plan.response_parts["include_greeting"]:
            lines.append("Xin chào bạn.")

        if plan.clarification_needed:
            names = ", ".join(item.name for item in plan.entities[:2]) if plan.entities else ""
            if names:
                lines.append(f"Mình đã nhận diện: {names}.")
            lines.append("Bạn vui lòng nêu rõ 1 thuốc tây và 1 thảo dược để mình kiểm tra tương tác chính xác.")
            return " ".join(lines).strip(), True

        if plan.response_parts["include_classification"] and plan.entities:
            for entity in plan.entities[:2]:
                label = "thuốc tây" if entity.type == "drug" else "thảo dược"
                lines.append(f"'{entity.name}' được phân loại là {label}.")

        if plan.response_parts["include_interaction_answer"]:
            if plan.interactions:
                if len(plan.interactions) == 1:
                    first = plan.interactions[0]
                    level = "cao" if str(first["severity"]) == "high" else "cần theo dõi"
                    lines.append(
                        f"Dữ liệu local cho thấy {first['drug_name']} và {first['herb_name']} có nguy cơ tương tác mức {level}."
                    )
                else:
                    pair_lines = [
                        f"- {row['drug_name']} + {row['herb_name']}: mức {'cao' if row['severity'] == 'high' else 'cần theo dõi'}"
                        for row in plan.interactions[:4]
                    ]
                    lines.append("Có các tương tác được ghi nhận:\n" + "\n".join(pair_lines))
            else:
                drugs = [item for item in plan.entities if item.type == "drug"]
                herbs = [item for item in plan.entities if item.type == "herb"]
                if drugs and herbs:
                    lines.append("Hiện chưa tìm thấy tương tác giữa các cặp bạn hỏi trong dữ liệu local hiện có.")

        if plan.interactions:
            first = plan.interactions[0]
            if plan.response_parts["include_mechanism"]:
                lines.append(f"Cơ chế: {first['mechanism']}")
            if plan.response_parts["include_side_effects"]:
                consequences = first.get("possible_consequences", [])
                if consequences:
                    lines.append("Hậu quả/tác dụng phụ có thể gặp: " + "; ".join(str(item) for item in consequences[:3]) + ".")
            if plan.response_parts["include_recommendation"]:
                lines.append("Khuyến nghị: " + str(first["recommendation"]))

        if plan.response_parts["include_related_entities"] and plan.entity_infos:
            related = []
            for info in plan.entity_infos[:2]:
                related.extend(info.get("related_entities", [])[:3])
            unique_related = []
            seen = set()
            for item in related:
                key = normalize_ascii(str(item))
                if key in seen or not key:
                    continue
                seen.add(key)
                unique_related.append(str(item))
            if unique_related:
                lines.append("Bạn có thể kiểm tra thêm với: " + ", ".join(unique_related[:5]) + ".")

        if plan.response_parts["include_help"]:
            lines.append(
                "Mình có thể giúp kiểm tra tương tác thuốc tây - thảo dược. "
                "Ví dụ: 'warfarin và nhân sâm có tương tác không?'."
            )

        if not lines:
            fallback = True
            lines.append(
                "Xin lỗi, mình chưa đủ dữ liệu local để kết luận câu hỏi này. "
                "Bạn hãy nêu rõ tên thuốc tây và thảo dược cụ thể."
            )

        return " ".join(lines).strip(), fallback

    def _build_grounding(self, plan: ResponsePlan) -> ChatGrounding:
        interactions = self._as_grounding_interactions(plan.interactions)
        primary_evidence = None
        if interactions:
            first = interactions[0]
            primary_evidence = InteractionDetail(
                mechanism=first.mechanism,
                possible_consequences=list(first.possible_consequences),
                recommendation=first.recommendation,
            )

        return ChatGrounding(
            entities=self._as_grounding_entities(plan.entities),
            interactions=interactions,
            interaction_found=bool(interactions),
            evidence=primary_evidence,
        )

    def generate_response(self, message: str, history: list[ChatHistoryMessage]) -> ChatResponse:
        plan = self.build_response_plan(message, history)
        grounding = self._build_grounding(plan)

        answer_text = None
        used_gemini = False

        if self.gemini_enabled:
            gemini_answer = self.generate_gemini_response(plan)
            if gemini_answer:
                answer_text = self._postprocess_answer(gemini_answer, plan)
                used_gemini = True

        fallback_answer, fallback_flag = self.build_fallback_response(plan)
        if not answer_text:
            answer_text = fallback_answer

        # Contract:
        # - `fallback=True` when chatbot does not use Gemini orchestrator (local grounded path),
        #   or when evidence is insufficient and clarification fallback is required.
        # - `fallback=False` only when Gemini path is used successfully without fallback content.
        effective_fallback = fallback_flag or (not used_gemini)

        return ChatResponse(
            answer=answer_text,
            grounding=grounding,
            citations=_CITATIONS,
            fallback=effective_fallback,
            orchestrator="gemini" if used_gemini else "local",
        )

    def chat_with_memory(
        self,
        *,
        user_id: int,
        session_id: str,
        message: str,
        history: list[ChatHistoryMessage] | None = None,
    ) -> ChatResponse:
        client_history = history or []
        if self.memory_service is None:
            response = self.generate_response(message, client_history)
            response.session_id = session_id
            response.used_memory = bool(client_history)
            return response

        stored_messages = self.memory_service.get_history(user_id, session_id, limit=60)
        persisted_history = ChatMemoryService.to_history_messages(stored_messages, limit=24)
        merged_history = self._merge_histories(persisted_history, client_history, limit=30)
        used_memory = len(persisted_history) > 0

        response = self.generate_response(message, merged_history)
        response.session_id = session_id
        response.used_memory = used_memory or ("follow_up" in self.detect_intents(message, merged_history).intents)

        self.memory_service.append_message(
            user_id,
            session_id,
            "user",
            message,
        )
        self.memory_service.append_message(
            user_id,
            session_id,
            "assistant",
            response.answer,
            grounding=response.grounding.model_dump(),
            citations=response.citations,
            fallback=response.fallback,
        )

        return response

    def get_history(self, *, user_id: int, session_id: str, limit: int = 80) -> list[StoredChatMessage]:
        if self.memory_service is None:
            return []
        return self.memory_service.get_history(user_id, session_id, limit=limit)

    def clear_history(self, *, user_id: int, session_id: str) -> int:
        if self.memory_service is None:
            return 0
        return self.memory_service.clear_history(user_id, session_id)
