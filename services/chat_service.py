from __future__ import annotations

import json
from dataclasses import dataclass, field

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

_PAIR_REQUIRED_INTENTS = {
    "interaction_query",
    "ask_side_effects",
    "ask_recommendation",
    "ask_mechanism",
}

_PAIR_HINT_KEYWORDS = {
    "tuong tac",
    "dung chung",
    "uong cung",
    "ket hop",
}


@dataclass
class ResolutionState:
    candidates: list[GraphEntity] = field(default_factory=list)
    selected: list[GraphEntity] = field(default_factory=list)
    ambiguous: dict[str, list[GraphEntity]] = field(default_factory=dict)
    used_memory: bool = False
    used_gemini: bool = False


@dataclass(frozen=True)
class ResponsePlan:
    intents: set[str]
    message: str
    message_ascii: str
    history: list[ChatHistoryMessage]
    pair_hint: bool
    candidates: list[GraphEntity]
    entities: list[GraphEntity]
    ambiguous_options: dict[str, list[GraphEntity]]
    interactions: list[dict[str, object]]
    clarification_needed: bool
    clarification_reason: str | None
    used_memory_for_entities: bool
    used_gemini_for_resolution: bool

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
    def _group_by_type(items: list[GraphEntity]) -> dict[str, list[GraphEntity]]:
        grouped: dict[str, list[GraphEntity]] = {"drug": [], "herb": []}
        for item in items:
            grouped.setdefault(item.type, []).append(item)
        for key in grouped:
            grouped[key].sort(key=lambda row: (-row.confidence, row.name))
        return grouped

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

    @staticmethod
    def _is_pair_hint(message_ascii: str) -> bool:
        padded = f" {message_ascii} "
        if " + " in padded:
            return True
        if " voi " in padded or " va " in padded:
            return True
        return any(keyword in message_ascii for keyword in _PAIR_HINT_KEYWORDS)

    @staticmethod
    def _entity_label_vi(entity_type: str) -> str:
        return "Thuốc Tây" if entity_type == "drug" else "Thảo dược"

    @staticmethod
    def _normalize_names(items: list[GraphEntity]) -> str:
        chunks = [f"{item.name} ({ChatService._entity_label_vi(item.type)})" for item in items]
        return ", ".join(chunks)

    @staticmethod
    def _has_both_types(items: list[GraphEntity]) -> bool:
        has_drug = any(item.type == "drug" for item in items)
        has_herb = any(item.type == "herb" for item in items)
        return has_drug and has_herb

    @staticmethod
    def _pick_best_per_type(items: list[GraphEntity]) -> list[GraphEntity]:
        best: dict[str, GraphEntity] = {}
        for item in items:
            current = best.get(item.type)
            if current is None or item.confidence > current.confidence:
                best[item.type] = item
        output = list(best.values())
        output.sort(key=lambda row: row.type)
        return output

    def detect_intents(self, message: str, history: list[ChatHistoryMessage]) -> IntentDetectionResult:
        return self.intent_service.detect_intents(message, history)

    def _extract_history_entities(self, history: list[ChatHistoryMessage]) -> list[GraphEntity]:
        user_messages = self._recent_user_messages(history, limit=6)
        if not user_messages:
            return []

        collected: list[GraphEntity] = []
        for row in reversed(user_messages[-4:]):
            collected.extend(self.graph.extract_entities(row.content, limit=8))

        merged_text = " ".join(item.content for item in user_messages[-4:])
        if merged_text.strip():
            collected.extend(self.graph.extract_entities(merged_text, limit=8))

        return self._deduplicate_entities(collected)

    def _should_use_history(
        self,
        *,
        intents: set[str],
        message_ascii: str,
        current_candidates: list[GraphEntity],
        history: list[ChatHistoryMessage],
        pair_hint: bool,
    ) -> bool:
        if not history:
            return False

        if "follow_up" in intents:
            return True

        has_pair = self._has_both_types(current_candidates)
        token_count = len([token for token in message_ascii.split(" ") if token])

        if ({"ask_side_effects", "ask_recommendation", "ask_mechanism"} & intents) and not has_pair:
            return token_count <= 8

        if (pair_hint or bool(_PAIR_REQUIRED_INTENTS & intents)) and not has_pair:
            return token_count <= 6

        return False

    @staticmethod
    def _select_entities_deterministic(
        grouped: dict[str, list[GraphEntity]],
    ) -> tuple[list[GraphEntity], dict[str, list[GraphEntity]]]:
        selected: list[GraphEntity] = []
        ambiguous: dict[str, list[GraphEntity]] = {}

        for entity_type in ["drug", "herb"]:
            rows = grouped.get(entity_type, [])
            if not rows:
                continue

            top = rows[0]
            second = rows[1] if len(rows) > 1 else None

            if second is None:
                if top.confidence >= 0.72:
                    selected.append(top)
                elif top.confidence >= 0.62:
                    ambiguous[entity_type] = rows[:4]
                continue

            gap = round(top.confidence - second.confidence, 3)
            if top.confidence >= 0.86 and gap >= 0.07:
                selected.append(top)
                continue

            if top.confidence >= 0.76 and gap >= 0.12:
                selected.append(top)
                continue

            if top.confidence >= 0.66:
                ambiguous[entity_type] = rows[:4]

        return selected, ambiguous

    def _needs_gemini_rerank(
        self,
        *,
        intents: set[str],
        pair_hint: bool,
        grouped: dict[str, list[GraphEntity]],
        selected: list[GraphEntity],
        ambiguous: dict[str, list[GraphEntity]],
    ) -> bool:
        if not self.gemini_enabled:
            return False

        if ambiguous:
            return True

        pair_expected = pair_hint or bool(_PAIR_REQUIRED_INTENTS & intents)
        if not pair_expected:
            return False

        if self._has_both_types(selected):
            return False

        for rows in grouped.values():
            if len(rows) < 2:
                continue
            if rows[0].confidence < 0.82 and (rows[0].confidence - rows[1].confidence) <= 0.08:
                return True

        return False

    def _rerank_with_gemini(
        self,
        *,
        message: str,
        history: list[ChatHistoryMessage],
        grouped: dict[str, list[GraphEntity]],
    ) -> tuple[list[GraphEntity], dict[str, list[GraphEntity]], bool]:
        candidate_pool: list[GraphEntity] = []
        for entity_type in ["drug", "herb"]:
            candidate_pool.extend(grouped.get(entity_type, [])[:4])

        if not candidate_pool:
            return [], {}, False

        candidate_payload = [
            {
                "type": item.type,
                "id": item.id,
                "name": item.name,
                "matched_alias": item.matched_alias,
                "confidence": item.confidence,
            }
            for item in candidate_pool
        ]

        recent_history = [item.content for item in self._recent_user_messages(history, limit=5)]
        result = self.gemini_service.rerank_entity_candidates(
            user_message=message,
            recent_history=recent_history,
            candidates=candidate_payload,
        )
        if not isinstance(result, dict):
            return [], {}, False

        candidate_map = {(item.type, item.id): item for item in candidate_pool}

        selected: list[GraphEntity] = []
        for row in result.get("selected", []):
            if not isinstance(row, dict):
                continue
            entity_type = str(row.get("type") or "").strip()
            try:
                entity_id = int(row.get("id"))
            except (TypeError, ValueError):
                continue

            candidate = candidate_map.get((entity_type, entity_id))
            if candidate is None:
                continue

            if any(item.type == candidate.type for item in selected):
                continue
            selected.append(candidate)

        ambiguous: dict[str, list[GraphEntity]] = {}
        for row in result.get("clarification_options", []):
            if not isinstance(row, dict):
                continue
            entity_type = str(row.get("type") or "").strip()
            if entity_type not in {"drug", "herb"}:
                continue

            ids = row.get("candidate_ids", [])
            if not isinstance(ids, list):
                continue

            options: list[GraphEntity] = []
            for value in ids:
                try:
                    option_id = int(value)
                except (TypeError, ValueError):
                    continue
                candidate = candidate_map.get((entity_type, option_id))
                if candidate is None:
                    continue
                if any(item.id == candidate.id and item.type == candidate.type for item in options):
                    continue
                options.append(candidate)
                if len(options) >= 4:
                    break

            if options:
                ambiguous[entity_type] = options

        return selected, ambiguous, bool(selected or ambiguous)

    def _resolve_entities(
        self,
        *,
        message: str,
        history: list[ChatHistoryMessage],
        intents: set[str],
        message_ascii: str,
        pair_hint: bool,
        allow_gemini: bool,
    ) -> ResolutionState:
        candidates = self.graph.extract_entities(message, limit=12)
        used_memory = False

        if self._should_use_history(
            intents=intents,
            message_ascii=message_ascii,
            current_candidates=candidates,
            history=history,
            pair_hint=pair_hint,
        ):
            from_history = self._extract_history_entities(history)
            if from_history:
                candidates = self._deduplicate_entities(candidates + from_history)
                used_memory = True

        grouped = self._group_by_type(candidates)
        selected, ambiguous = self._select_entities_deterministic(grouped)
        used_gemini = False

        if allow_gemini and self._needs_gemini_rerank(
            intents=intents,
            pair_hint=pair_hint,
            grouped=grouped,
            selected=selected,
            ambiguous=ambiguous,
        ):
            gemini_selected, gemini_ambiguous, gemini_applied = self._rerank_with_gemini(
                message=message,
                history=history,
                grouped=grouped,
            )
            if gemini_applied:
                merged_selected = self._pick_best_per_type(selected + gemini_selected)
                selected = merged_selected
                if gemini_ambiguous:
                    ambiguous = gemini_ambiguous
                used_gemini = True

        selected = self._pick_best_per_type(selected)

        return ResolutionState(
            candidates=self._deduplicate_entities(candidates),
            selected=selected,
            ambiguous=ambiguous,
            used_memory=used_memory,
            used_gemini=used_gemini,
        )

    def resolve_follow_up_entities(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        current_entities: list[GraphEntity],
    ) -> tuple[list[GraphEntity], bool]:
        if not history:
            return current_entities, False

        history_entities = self._extract_history_entities(history)
        if not history_entities:
            return current_entities, False

        combined = self._deduplicate_entities(current_entities + history_entities)
        return combined, len(combined) > len(current_entities)

    def identify_medical_entities_via_graph(
        self,
        message: str,
        history: list[ChatHistoryMessage],
        intents: set[str] | None = None,
    ) -> tuple[list[GraphEntity], bool]:
        detection = self.detect_intents(message, history)
        merged_intents = set(intents or set()) | set(detection.intents)
        pair_hint = self._is_pair_hint(detection.message_ascii)

        state = self._resolve_entities(
            message=message,
            history=history,
            intents=merged_intents,
            message_ascii=detection.message_ascii,
            pair_hint=pair_hint,
            allow_gemini=False,
        )
        return state.selected, state.used_memory

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
            "label_vi": self._entity_label_vi(entity.type),
        }

    def _is_pair_required(
        self,
        *,
        intents: set[str],
        pair_hint: bool,
        message_ascii: str,
        candidates: list[GraphEntity],
    ) -> bool:
        if bool({"entity_identification", "entity_classification"} & intents) and not pair_hint:
            if not (_PAIR_REQUIRED_INTENTS & intents):
                return False
        if pair_hint:
            return True
        if bool(_PAIR_REQUIRED_INTENTS & intents):
            return True
        interaction_context_markers = [" dang uong ", " uong ", " su dung ", " dung ", " ket hop "]
        padded = f" {message_ascii} "
        if candidates and any(marker in padded for marker in interaction_context_markers):
            return True
        return self._has_both_types(candidates)

    def _decide_clarification_reason(
        self,
        *,
        pair_required: bool,
        selected_entities: list[GraphEntity],
        ambiguous: dict[str, list[GraphEntity]],
    ) -> tuple[bool, str | None]:
        if not pair_required:
            return False, None

        has_drug = any(item.type == "drug" for item in selected_entities)
        has_herb = any(item.type == "herb" for item in selected_entities)

        if has_drug and has_herb:
            return False, None

        if ambiguous.get("drug") or ambiguous.get("herb"):
            return True, "ambiguous"

        if has_drug and not has_herb:
            return True, "missing_herb"

        if has_herb and not has_drug:
            return True, "missing_drug"

        return True, "unmatched"

    def build_response_plan(self, message: str, history: list[ChatHistoryMessage]) -> ResponsePlan:
        detection = self.detect_intents(message, history)
        intents = set(detection.intents)
        pair_hint = self._is_pair_hint(detection.message_ascii)
        if pair_hint:
            intents.add("interaction_query")

        state = self._resolve_entities(
            message=message,
            history=history,
            intents=intents,
            message_ascii=detection.message_ascii,
            pair_hint=pair_hint,
            allow_gemini=True,
        )

        entities = state.selected
        drug = next((item for item in entities if item.type == "drug"), None)
        herb = next((item for item in entities if item.type == "herb"), None)

        interactions: list[dict[str, object]] = []
        if drug is not None and herb is not None:
            interactions = self.check_interaction_pair_via_graph(drug, herb)

        pair_required = self._is_pair_required(
            intents=intents,
            pair_hint=pair_hint,
            message_ascii=detection.message_ascii,
            candidates=state.candidates,
        )
        clarification_needed, clarification_reason = self._decide_clarification_reason(
            pair_required=pair_required,
            selected_entities=entities,
            ambiguous=state.ambiguous,
        )

        if clarification_needed:
            intents.add("clarification")

        return ResponsePlan(
            intents=intents,
            message=message.strip(),
            message_ascii=detection.message_ascii,
            history=history[-10:],
            pair_hint=pair_hint,
            candidates=state.candidates,
            entities=entities,
            ambiguous_options=state.ambiguous,
            interactions=interactions,
            clarification_needed=clarification_needed,
            clarification_reason=clarification_reason,
            used_memory_for_entities=state.used_memory,
            used_gemini_for_resolution=state.used_gemini,
        )

    def _plan_as_json(self, plan: ResponsePlan) -> dict[str, object]:
        return {
            "intents": sorted(plan.intents),
            "pair_hint": plan.pair_hint,
            "entities": [item.__dict__ for item in plan.entities],
            "candidates": [item.__dict__ for item in plan.candidates[:8]],
            "ambiguous_options": {
                key: [item.__dict__ for item in value]
                for key, value in plan.ambiguous_options.items()
            },
            "interaction_found": bool(plan.interactions),
            "interactions": plan.interactions,
            "clarification_needed": plan.clarification_needed,
            "clarification_reason": plan.clarification_reason,
            "used_memory": plan.used_memory_for_entities,
            "used_gemini_for_resolution": plan.used_gemini_for_resolution,
        }

    def build_grounded_prompt(self, plan: ResponsePlan) -> str:
        history_lines = [f"{item.role}: {item.content}" for item in plan.history[-8:]]
        return (
            f"Người dùng: {plan.message}\n\n"
            "Lịch sử gần nhất:\n"
            + ("\n".join(history_lines) if history_lines else "(không có)")
            + "\n\nRESPONSE_PLAN_JSON:\n"
            + json.dumps(self._plan_as_json(plan), ensure_ascii=False, indent=2)
            + "\n\nYÊU CẦU:\n"
            + "- Chỉ dùng dữ liệu trong RESPONSE_PLAN_JSON.\n"
            + "- Trả lời ngắn gọn, rõ ràng bằng tiếng Việt.\n"
            + "- Không bịa thực thể ngoài danh sách cục bộ.\n"
        )

    def generate_gemini_response(self, plan: ResponsePlan) -> str | None:
        if not self.gemini_enabled:
            return None

        system_instruction = (
            "Bạn là trợ lý HerbaGuard AI. Trả lời ngắn gọn, rõ ràng, và chỉ dựa trên dữ liệu local được cung cấp."
        )
        prompt = self.build_grounded_prompt(plan)
        return self.gemini_service.generate_grounded_answer(prompt=prompt, system_instruction=system_instruction)

    @staticmethod
    def _line_or_default(value: str, default: str) -> str:
        cleaned = str(value or "").strip()
        return cleaned if cleaned else default

    def _build_interaction_answer(self, plan: ResponsePlan) -> str:
        greeting = "Xin chào bạn.\n\n" if "greeting" in plan.intents else ""

        drug = next((item for item in plan.entities if item.type == "drug"), None)
        herb = next((item for item in plan.entities if item.type == "herb"), None)
        if drug is None or herb is None:
            return greeting + "Mình chưa đủ thông tin để kết luận tương tác cho cặp bạn hỏi."

        if plan.interactions:
            first = plan.interactions[0]
            consequences = first.get("possible_consequences", [])
            if not isinstance(consequences, list):
                consequences = []
            consequence_text = "; ".join(str(item).strip() for item in consequences if str(item).strip())
            if not consequence_text:
                consequence_text = "Chưa có mô tả chi tiết trong bộ dữ liệu hiện tại."

            lines = [
                f"Kết luận: Có ghi nhận tương tác giữa {drug.name} và {herb.name} trong dữ liệu nội bộ.",
                f"Cơ chế: {self._line_or_default(str(first.get('mechanism', '')), 'Chưa có mô tả cơ chế chi tiết.')}",
                f"Hậu quả có thể gặp: {consequence_text}",
                f"Khuyến nghị: {self._line_or_default(str(first.get('recommendation', '')), 'Nên trao đổi bác sĩ/dược sĩ trước khi phối hợp.')}",
                f"Thực thể đã chuẩn hóa: {self._normalize_names([drug, herb])}",
                "Nguồn dữ liệu nội bộ: " + ", ".join(_CITATIONS),
            ]
            return greeting + "\n".join(lines)

        lines = [
            f"Kết luận: Chưa ghi nhận tương tác trực tiếp giữa {drug.name} và {herb.name} trong dữ liệu nội bộ hiện có.",
            "Khuyến nghị: Nếu bạn vẫn cần dùng đồng thời, nên theo dõi triệu chứng và hỏi bác sĩ/dược sĩ để xác nhận lâm sàng.",
            f"Thực thể đã chuẩn hóa: {self._normalize_names([drug, herb])}",
            "Nguồn dữ liệu nội bộ: " + ", ".join(_CITATIONS),
        ]
        return greeting + "\n".join(lines)

    def _build_entity_answer(self, plan: ResponsePlan) -> str:
        greeting = "Xin chào bạn.\n\n" if "greeting" in plan.intents else ""
        entity = plan.entities[0]
        info = self.search_drug_info(entity)
        related = [str(item).strip() for item in info.get("related_entities", []) if str(item).strip()]

        lines = [
            f"Kết luận: {entity.name} được nhận diện là {info['label_vi'].lower()} trong cơ sở dữ liệu nội bộ.",
            f"Thực thể đã chuẩn hóa: {entity.name} ({info['label_vi']}).",
        ]

        if related:
            lines.append("Gợi ý kiểm tra thêm: " + ", ".join(related[:4]))

        lines.append("Nguồn dữ liệu nội bộ: " + ", ".join(_CITATIONS[1:]))
        return greeting + "\n".join(lines)

    @staticmethod
    def _names_from_candidates(items: list[GraphEntity], limit: int = 4) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = normalize_ascii(item.name)
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item.name)
            if len(output) >= limit:
                break
        return output

    def _build_clarification_answer(self, plan: ResponsePlan) -> str:
        greeting = "Xin chào bạn.\n\n" if "greeting" in plan.intents else ""
        reason = plan.clarification_reason or "unmatched"

        if reason == "ambiguous":
            lines = ["Mình chưa chắc tên bạn nhập đang trỏ tới thực thể nào trong dữ liệu nội bộ."]
            for entity_type in ["drug", "herb"]:
                options = self._names_from_candidates(plan.ambiguous_options.get(entity_type, []), limit=4)
                if not options:
                    continue
                label = "thuốc" if entity_type == "drug" else "thảo dược"
                lines.append(f"Bạn chọn giúp {label}: " + ", ".join(options) + ".")
            lines.append("Nguồn dữ liệu nội bộ: " + ", ".join(_CITATIONS))
            return greeting + "\n".join(lines)

        selected_drug = next((item for item in plan.entities if item.type == "drug"), None)
        selected_herb = next((item for item in plan.entities if item.type == "herb"), None)

        if reason == "missing_herb" and selected_drug is not None:
            suggestions = [node.canonical_name for node in self.graph.related_entities(selected_drug, target_type="herb", limit=4)]
            lines = [
                f"Mình đã chuẩn hóa được thuốc tây: {selected_drug.name}.",
                f"Bạn muốn kiểm tra {selected_drug.name} với thảo dược nào?",
            ]
            if suggestions:
                lines.append("Bạn có thể chọn nhanh: " + ", ".join(suggestions) + ".")
            return greeting + "\n".join(lines)

        if reason == "missing_drug" and selected_herb is not None:
            suggestions = [node.canonical_name for node in self.graph.related_entities(selected_herb, target_type="drug", limit=4)]
            lines = [
                f"Mình đã chuẩn hóa được thảo dược: {selected_herb.name}.",
                f"Bạn muốn kiểm tra {selected_herb.name} với thuốc tây nào?",
            ]
            if suggestions:
                lines.append("Bạn có thể chọn nhanh: " + ", ".join(suggestions) + ".")
            return greeting + "\n".join(lines)

        hint_names = self._names_from_candidates(plan.candidates, limit=4)
        lines = [
            "Mình chưa khớp được tên thuốc/thảo dược của bạn với dữ liệu nội bộ hiện có.",
            "Bạn thử nhập lại tên gần đúng hoặc đầy đủ hơn.",
        ]
        if hint_names:
            lines.append("Ví dụ có trong hệ thống: " + ", ".join(hint_names) + ".")
        return greeting + "\n".join(lines)

    def _build_help_answer(self, plan: ResponsePlan) -> str:
        greeting = "Xin chào bạn.\n\n" if "greeting" in plan.intents else ""
        return (
            greeting
            + "Mình có thể giúp kiểm tra tương tác thuốc tây - thảo dược dựa trên dữ liệu nội bộ.\n"
            + "Ví dụ: 'warfarin với nhân sâm có tương tác không?'."
        )

    def build_fallback_response(self, plan: ResponsePlan) -> tuple[str, bool]:
        if plan.clarification_needed:
            return self._build_clarification_answer(plan), True

        if self._has_both_types(plan.entities):
            return self._build_interaction_answer(plan), True

        entity_info_intent = bool({"entity_identification", "entity_classification"} & plan.intents)
        if entity_info_intent and plan.entities:
            return self._build_entity_answer(plan), True

        if "related_entities" in plan.intents and plan.entities:
            return self._build_entity_answer(plan), True

        if plan.entities and not plan.clarification_needed and not self._is_pair_required(
            intents=plan.intents,
            pair_hint=plan.pair_hint,
            message_ascii=plan.message_ascii,
            candidates=plan.candidates,
        ):
            return self._build_entity_answer(plan), True

        if "help" in plan.intents or "greeting" in plan.intents:
            return self._build_help_answer(plan), True

        return self._build_clarification_answer(plan), True

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

        answer_text, _ = self.build_fallback_response(plan)
        used_gemini = plan.used_gemini_for_resolution

        return ChatResponse(
            answer=answer_text,
            grounding=grounding,
            citations=_CITATIONS,
            fallback=not used_gemini,
            orchestrator="gemini" if used_gemini else "local",
        )

    def chat_with_memory(
        self,
        *,
        user_id: str,
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

    def get_history(self, *, user_id: str, session_id: str, limit: int = 80) -> list[StoredChatMessage]:
        if self.memory_service is None:
            return []
        return self.memory_service.get_history(user_id, session_id, limit=limit)

    def clear_history(self, *, user_id: str, session_id: str) -> int:
        if self.memory_service is None:
            return 0
        return self.memory_service.clear_history(user_id, session_id)
