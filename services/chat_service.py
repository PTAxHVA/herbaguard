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
from services.chat_memory_service import ChatMemoryService, StoredChatMessage
from services.gemini_service import GeminiService
from services.graph_service import GraphEntity, KnowledgeGraphService
from services.normalize import normalize_ascii

_CITATIONS = [
    "database/interaction.json",
    "database/herb.json",
    "database/drug.json",
]


@dataclass(frozen=True)
class GraphAgentContext:
    message: str
    message_ascii: str
    history: list[ChatHistoryMessage]
    entities: list[GraphEntity]
    interactions: list[dict[str, object]]
    entity_infos: list[dict[str, object]]
    wants_brief: bool


class ChatService:
    def __init__(
        self,
        graph: KnowledgeGraphService,
        memory_service: ChatMemoryService | None = None,
        gemini_service: GeminiService | None = None,
    ) -> None:
        self.graph = graph
        self.memory_service = memory_service
        self.gemini_service = gemini_service or GeminiService.from_env()
        self.tool_registry = {
            "greet_user": self.greet_user,
            "identify_medical_entities_via_graph": self.identify_medical_entities_via_graph,
            "check_interaction_pair_via_graph": self.check_interaction_pair_via_graph,
            "search_drug_info": self.search_drug_info,
            "build_grounded_prompt": self.build_grounded_prompt,
            "generate_gemini_response": self.generate_gemini_response,
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
    def _recent_user_messages(history: list[ChatHistoryMessage], limit: int = 8) -> list[ChatHistoryMessage]:
        users = [item for item in history if item.role == "user"]
        return users[-limit:]

    @staticmethod
    def _is_classification_question(text_ascii: str) -> bool:
        keywords = [
            "la thuoc tay hay thao duoc",
            "la thuoc tay",
            "la thao duoc",
            "phan loai",
            "thuoc hay thao duoc",
            "la gi",
        ]
        return any(keyword in text_ascii for keyword in keywords)

    @staticmethod
    def _is_reason_question(text_ascii: str) -> bool:
        keywords = ["tai sao", "vi sao", "co che", "nguy hiem", "hau qua"]
        return any(keyword in text_ascii for keyword in keywords)

    @staticmethod
    def _is_recommendation_question(text_ascii: str) -> bool:
        keywords = ["nen lam gi", "khuyen nghi", "can lam gi", "xu ly", "co nen dung"]
        return any(keyword in text_ascii for keyword in keywords)

    @staticmethod
    def _is_context_followup_question(text_ascii: str) -> bool:
        markers = [
            "tai sao",
            "vi sao",
            "co che",
            "nguy hiem",
            "hau qua",
            "nen lam gi",
            "khuyen nghi",
            "can lam gi",
            "co nen dung",
            "truong hop nay",
            "cap nay",
            "cai nay",
            "mon nay",
            "thuoc nay",
            "thao duoc nay",
            "thuoc do",
            "thao duoc do",
            "giai thich lai",
            "ngan gon hon",
            "con cai do thi sao",
            "con thuoc do thi sao",
        ]
        if any(marker in text_ascii for marker in markers):
            return True

        token_count = len([token for token in text_ascii.split(" ") if token])
        return 0 < token_count <= 4

    @staticmethod
    def _wants_brief_answer(text_ascii: str) -> bool:
        markers = ["ngan gon", "tom tat", "rut gon", "noi ngan", "ngan thoi"]
        return any(marker in text_ascii for marker in markers)

    @staticmethod
    def _contains_uncertainty_language(answer_ascii: str) -> bool:
        markers = [
            "chua du du lieu",
            "khong du bang chung",
            "chua tim thay",
            "du lieu local hien tai",
            "khong the ket luan",
        ]
        return any(marker in answer_ascii for marker in markers)

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

    def greet_user(self, message: str, message_ascii: str | None = None) -> str | None:
        text_ascii = message_ascii or normalize_ascii(message)
        greeting_keywords = {
            "xin chao",
            "chao",
            "hello",
            "hi",
            "alo",
            "chao ban",
            "tro giup",
            "help",
        }
        if text_ascii not in greeting_keywords and not text_ascii.startswith("xin chao"):
            return None

        return (
            "Xin chào, tôi là trợ lý HerbaGuard AI. "
            "Tôi có thể hỗ trợ kiểm tra tương tác giữa thuốc tây và thảo dược từ dữ liệu local, "
            "và giải thích ngắn gọn lý do, hậu quả, khuyến nghị."
        )

    def _extract_entities_from_context(self, history: list[ChatHistoryMessage]) -> list[GraphEntity]:
        user_messages = self._recent_user_messages(history, limit=8)
        if not user_messages:
            return []

        latest_entities = self.graph.extract_entities(user_messages[-1].content)
        if latest_entities:
            return latest_entities

        merged_text = " ".join(item.content for item in user_messages)
        return self.graph.extract_entities(merged_text)

    def identify_medical_entities_via_graph(self, message: str, history: list[ChatHistoryMessage]) -> list[GraphEntity]:
        message_ascii = normalize_ascii(message)
        extracted = self.graph.extract_entities(message, limit=8)
        if extracted:
            return self._deduplicate_entities(extracted)

        if history and self._is_context_followup_question(message_ascii):
            return self._deduplicate_entities(self._extract_entities_from_context(history))

        return []

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

    def _build_context(self, message: str, history: list[ChatHistoryMessage]) -> GraphAgentContext:
        message_ascii = normalize_ascii(message)
        entities = self.identify_medical_entities_via_graph(message, history)
        entities = self._deduplicate_entities(entities)

        drugs = [item for item in entities if item.type == "drug"]
        herbs = [item for item in entities if item.type == "herb"]

        interactions: list[dict[str, object]] = []
        for drug in drugs:
            for herb in herbs:
                interactions.extend(self.check_interaction_pair_via_graph(drug, herb))

        interactions.sort(key=lambda row: (0 if row["severity"] == "high" else 1, row["drug_name"], row["herb_name"]))
        entity_infos = [self.search_drug_info(item) for item in entities[:4]]

        return GraphAgentContext(
            message=message.strip(),
            message_ascii=message_ascii,
            history=history[-10:],
            entities=entities,
            interactions=interactions,
            entity_infos=entity_infos,
            wants_brief=self._wants_brief_answer(message_ascii),
        )

    def build_grounded_prompt(self, context: GraphAgentContext) -> str:
        history_lines = [f"{item.role}: {item.content}" for item in context.history[-8:]]
        bundle = {
            "entities": [item.__dict__ for item in context.entities],
            "interactions": context.interactions,
            "entity_infos": context.entity_infos,
        }

        response_style = "ngắn gọn 2-4 câu" if context.wants_brief else "rõ ràng, súc tích và có cấu trúc"
        return (
            f"Người dùng hỏi: {context.message}\n\n"
            "Lịch sử gần nhất:\n"
            + ("\n".join(history_lines) if history_lines else "(không có)")
            + "\n\nKHUNG_BANG_CHUNG_JSON:\n"
            + json.dumps(bundle, ensure_ascii=False, indent=2)
            + "\n\nYÊU CẦU TRẢ LỜI:\n"
            + "1) Chỉ dùng bằng chứng trong KHUNG_BANG_CHUNG_JSON.\n"
            + "2) Nếu không đủ bằng chứng, phải nói rõ không đủ dữ liệu local để kết luận.\n"
            + "3) Không bịa cơ chế, hậu quả, khuyến nghị ngoài dữ liệu.\n"
            + "4) Dùng tiếng Việt, giọng tư vấn an toàn.\n"
            + f"5) Trình bày {response_style}.\n"
            + "6) Nếu có tương tác, nêu mức độ + cơ chế + khuyến nghị.\n"
            + "7) Nếu chỉ có 1 thực thể, nêu đó là thuốc tây hay thảo dược và gợi ý thực thể liên quan.\n"
        )

    def generate_gemini_response(self, context: GraphAgentContext) -> str | None:
        prompt = self.build_grounded_prompt(context)
        system_instruction = (
            "Bạn là trợ lý HerbaGuard AI cho người dùng Việt Nam. "
            "Bạn chỉ được trả lời dựa trên bằng chứng đã cung cấp; không thêm kiến thức y khoa bên ngoài. "
            "Nếu dữ liệu thiếu, phải nói rõ thiếu dữ liệu local."
        )
        return self.gemini_service.generate_grounded_answer(prompt=prompt, system_instruction=system_instruction)

    def _generate_local_grounded_response(self, context: GraphAgentContext) -> tuple[str, bool]:
        entities = context.entities
        interactions = context.interactions
        drugs = [item for item in entities if item.type == "drug"]
        herbs = [item for item in entities if item.type == "herb"]

        if interactions:
            first = interactions[0]
            pair_label = f"{first['drug_name']} và {first['herb_name']}"
            severity_label = "cao" if str(first["severity"]) == "high" else "cần theo dõi"

            if self._is_reason_question(context.message_ascii):
                consequences = first.get("possible_consequences", [])
                top_cons = f" Hậu quả có thể gặp: {consequences[0]}." if consequences else ""
                return (
                    f"Dữ liệu local cho thấy {pair_label} có nguy cơ tương tác mức {severity_label}. "
                    f"Cơ chế chính: {first['mechanism']}.{top_cons}",
                    False,
                )

            if self._is_recommendation_question(context.message_ascii):
                return (
                    f"Với cặp {pair_label}, khuyến nghị trong dữ liệu là: {first['recommendation']}. "
                    "Bạn nên trao đổi trực tiếp với bác sĩ hoặc dược sĩ trước khi dùng chung.",
                    False,
                )

            interaction_lines = [
                f"- {item['drug_name']} + {item['herb_name']}: mức {('cao' if item['severity'] == 'high' else 'cần theo dõi')}"
                for item in interactions[:4]
            ]
            return (
                "Có, dữ liệu local ghi nhận tương tác thuốc tây - thảo dược:\n"
                + "\n".join(interaction_lines)
                + "\nBạn có thể hỏi thêm: 'Tại sao nguy hiểm?' hoặc 'Tôi nên làm gì?'.",
                False,
            )

        if drugs and herbs:
            return (
                "Hiện chưa tìm thấy tương tác giữa các cặp bạn hỏi trong cơ sở dữ liệu local hiện có. "
                "Điều này không thay thế tư vấn y khoa nếu bạn có triệu chứng bất thường.",
                False,
            )

        if len(entities) == 1:
            entity = entities[0]
            entity_info = self.search_drug_info(entity)
            related = [str(item) for item in entity_info.get("related_entities", [])]
            suggestion_text = f" Bạn có thể kiểm tra thêm với: {', '.join(related[:3])}." if related else ""
            return (
                f"Tôi đã nhận diện '{entity.name}' là {entity_info['label_vi']}, nhưng chưa đủ cặp thuốc tây + thảo dược để kết luận tương tác."
                + suggestion_text,
                False,
            )

        return (
            "Xin lỗi, tôi chưa tìm đủ bằng chứng trong dữ liệu local để trả lời chắc chắn câu hỏi này. "
            "Bạn hãy nêu rõ tên thuốc tây và thảo dược cụ thể (ví dụ: warfarin và nhân sâm).",
            True,
        )

    def _build_grounding(self, context: GraphAgentContext) -> ChatGrounding:
        interactions = self._as_grounding_interactions(context.interactions)
        primary_evidence = None
        if interactions:
            first = interactions[0]
            primary_evidence = InteractionDetail(
                mechanism=first.mechanism,
                possible_consequences=list(first.possible_consequences),
                recommendation=first.recommendation,
            )

        return ChatGrounding(
            entities=self._as_grounding_entities(context.entities),
            interactions=interactions,
            interaction_found=bool(interactions),
            evidence=primary_evidence,
        )

    def generate_response(self, message: str, history: list[ChatHistoryMessage]) -> ChatResponse:
        msg_clean = message.strip()
        text_ascii = normalize_ascii(msg_clean)

        greeting = self.greet_user(msg_clean, text_ascii)
        if greeting:
            return ChatResponse(
                answer=greeting,
                grounding=ChatGrounding(entities=[], interactions=[], interaction_found=False),
                citations=_CITATIONS,
                fallback=False,
                orchestrator="local",
            )

        context = self._build_context(msg_clean, history)
        grounding = self._build_grounding(context)

        used_gemini = False
        answer = None
        if self.gemini_enabled:
            answer = self.generate_gemini_response(context)
            if answer:
                used_gemini = True

        if answer and not context.entities and not context.interactions:
            # Keep unknown-answer path strictly honest to local evidence.
            if not self._contains_uncertainty_language(normalize_ascii(answer)):
                answer = None
                used_gemini = False

        local_answer, local_fallback = self._generate_local_grounded_response(context)
        if not answer:
            answer = local_answer

        fallback_flag = local_fallback
        orchestrator = "gemini" if used_gemini else "local"

        return ChatResponse(
            answer=answer,
            grounding=grounding,
            citations=_CITATIONS,
            fallback=fallback_flag,
            orchestrator=orchestrator,
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
        response.used_memory = used_memory

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
