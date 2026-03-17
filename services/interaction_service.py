from __future__ import annotations

from services.data_loader import LoadedDatabase
from services.normalize import deduplicate_inputs, normalize_ascii
from services.resolver import EntityResolver
from models import (
    CheckInteractionResponse,
    InteractionDetail,
    InteractionEntityRef,
    InteractionPair,
    ResolvedItem,
    Summary,
)

_HIGH_KEYWORDS = [
    "xuat huyet",
    "soc",
    "nghiem trong",
    "khong nen dung chung",
    "suy gan",
    "qua lieu",
    "nguy hiem cao",
    "ngung tim",
    "tu vong",
    "hon me",
    "suy than cap",
]

_MEDIUM_KEYWORDS = [
    "theo doi",
    "than trong",
    "co the lam tang",
    "co the lam giam",
    "han che",
    "dieu chinh lieu",
    "bao cao voi bac si",
]


class InteractionService:
    def __init__(self, db: LoadedDatabase, resolver: EntityResolver) -> None:
        self.db = db
        self.resolver = resolver

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _infer_severity(self, detail: InteractionDetail) -> str:
        combined_text = " ".join(
            [
                detail.mechanism,
                " ".join(detail.possible_consequences),
                detail.recommendation,
            ]
        )
        normalized = normalize_ascii(combined_text)

        if self._contains_any(normalized, _HIGH_KEYWORDS):
            return "high"
        if self._contains_any(normalized, _MEDIUM_KEYWORDS):
            return "medium"
        return "medium"

    def _resolve_items(self, items: list[str]) -> tuple[list[str], list[ResolvedItem], list[str]]:
        deduplicated = deduplicate_inputs(items)

        resolved: list[ResolvedItem] = []
        unresolved: list[str] = []

        for user_input in deduplicated:
            match = self.resolver.resolve(user_input)
            if match is None:
                unresolved.append(user_input)
                continue

            resolved.append(
                ResolvedItem(
                    input=user_input,
                    type=match.entity_type,
                    id=match.entity_id,
                    canonical_name=match.canonical_name,
                    matched_alias=match.matched_alias,
                    confidence=match.confidence,
                )
            )

        # Dedupe entities (same herb/drug can be entered with multiple aliases)
        by_entity: dict[tuple[str, int], ResolvedItem] = {}
        for item in resolved:
            key = (item.type, item.id)
            existing = by_entity.get(key)
            if existing is None or item.confidence > existing.confidence:
                by_entity[key] = item

        unique_resolved = list(by_entity.values())
        unique_resolved.sort(key=lambda row: (row.type, row.canonical_name))

        return deduplicated, unique_resolved, unresolved

    def _find_pairs(self, resolved_items: list[ResolvedItem]) -> list[InteractionPair]:
        drug_items = {item.id: item for item in resolved_items if item.type == "drug"}
        herb_items = {item.id: item for item in resolved_items if item.type == "herb"}

        results: list[InteractionPair] = []

        for drug_id, drug_item in drug_items.items():
            for herb_id, herb_item in herb_items.items():
                rows = self.db.interactions_by_pair.get((drug_id, herb_id), tuple())
                for row in rows:
                    detail = InteractionDetail(
                        mechanism=row.mechanism,
                        possible_consequences=list(row.possible_consequences),
                        recommendation=row.recommendation,
                    )

                    severity = self._infer_severity(detail)
                    results.append(
                        InteractionPair(
                            drug=InteractionEntityRef(
                                id=drug_item.id,
                                canonical_name=drug_item.canonical_name,
                            ),
                            herb=InteractionEntityRef(
                                id=herb_item.id,
                                canonical_name=herb_item.canonical_name,
                            ),
                            severity=severity,
                            interaction=detail,
                        )
                    )

        results.sort(key=lambda row: (0 if row.severity == "high" else 1, row.drug.id, row.herb.id))
        return results

    @staticmethod
    def _build_summary(interaction_pairs: list[InteractionPair]) -> Summary:
        if not interaction_pairs:
            return Summary(
                level="safe",
                title="CHƯA GHI NHẬN TƯƠNG TÁC",
                message="Chưa phát hiện tương tác thuốc tây - thảo dược trong cơ sở dữ liệu hiện có.",
                recommendation="Nếu bạn vẫn lo lắng hoặc có triệu chứng bất thường, hãy tham khảo bác sĩ hoặc dược sĩ.",
            )

        has_high = any(pair.severity == "high" for pair in interaction_pairs)
        if has_high:
            return Summary(
                level="danger",
                title="NGUY CƠ TƯƠNG TÁC CAO",
                message="Phát hiện tương tác giữa thuốc tây và thảo dược. Không nên tự ý dùng cùng nhau.",
                recommendation="Tham khảo bác sĩ hoặc dược sĩ trước khi tiếp tục sử dụng.",
            )

        return Summary(
            level="warning",
            title="CÓ NGUY CƠ TƯƠNG TÁC",
            message="Phát hiện tương tác có thể ảnh hưởng hiệu quả hoặc độ an toàn khi dùng cùng nhau.",
            recommendation="Nên theo dõi chặt chẽ và trao đổi với bác sĩ hoặc dược sĩ để được điều chỉnh phù hợp.",
        )

    def check_interactions(self, items: list[str]) -> CheckInteractionResponse:
        input_items, resolved_items, unresolved_items = self._resolve_items(items)
        interaction_pairs = self._find_pairs(resolved_items)
        summary = self._build_summary(interaction_pairs)

        return CheckInteractionResponse(
            success=True,
            input_items=input_items,
            resolved_items=resolved_items,
            interaction_found=bool(interaction_pairs),
            interaction_pairs=interaction_pairs,
            summary=summary,
            unresolved_items=unresolved_items,
        )
