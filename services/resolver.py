from __future__ import annotations

from dataclasses import dataclass

from services.data_loader import EntityRecord, LoadedDatabase
from services.normalize import normalize_pair


@dataclass(frozen=True)
class MatchResult:
    entity_type: str
    entity_id: int
    canonical_name: str
    matched_alias: str
    confidence: float


@dataclass(frozen=True)
class _AliasRow:
    entity_type: str
    entity_id: int
    canonical_name: str
    alias: str
    alias_norm: str
    alias_ascii: str


class EntityResolver:
    def __init__(self, db: LoadedDatabase) -> None:
        self._alias_rows: tuple[_AliasRow, ...] = self._build_alias_rows(db)

    @staticmethod
    def _build_alias_rows(db: LoadedDatabase) -> tuple[_AliasRow, ...]:
        rows: list[_AliasRow] = []

        def append_entity(entity: EntityRecord) -> None:
            for alias in entity.aliases:
                alias_norm, alias_ascii = normalize_pair(alias)
                if not alias_norm:
                    continue
                rows.append(
                    _AliasRow(
                        entity_type=entity.entity_type,
                        entity_id=entity.entity_id,
                        canonical_name=entity.canonical_name,
                        alias=alias,
                        alias_norm=alias_norm,
                        alias_ascii=alias_ascii,
                    )
                )

        for entity in db.drugs.values():
            append_entity(entity)
        for entity in db.herbs.values():
            append_entity(entity)

        return tuple(rows)

    @staticmethod
    def _token_overlap_score(left: str, right: str) -> float:
        left_tokens = {token for token in left.split() if len(token) >= 2}
        right_tokens = {token for token in right.split() if len(token) >= 2}

        if not left_tokens or not right_tokens:
            return 0.0

        overlap = len(left_tokens.intersection(right_tokens))
        return overlap / len(left_tokens)

    @staticmethod
    def _contains_match(left: str, right: str) -> bool:
        if len(left) < 3 or len(right) < 3:
            return False
        return left in right or right in left

    def _score(self, query_norm: str, query_ascii: str, row: _AliasRow) -> float:
        if query_norm == row.alias_norm:
            return 1.0
        if query_ascii == row.alias_ascii:
            return 0.97

        if self._contains_match(query_norm, row.alias_norm):
            return 0.9 if query_norm in row.alias_norm else 0.87

        if self._contains_match(query_ascii, row.alias_ascii):
            return 0.84 if query_ascii in row.alias_ascii else 0.8

        overlap = self._token_overlap_score(query_ascii, row.alias_ascii)
        if overlap >= 1.0:
            return 0.76
        if overlap >= 0.6:
            return 0.72
        if overlap >= 0.45:
            return 0.66

        return 0.0

    @staticmethod
    def _better_candidate(candidate: MatchResult, current: MatchResult | None) -> bool:
        if current is None:
            return True
        if candidate.confidence != current.confidence:
            return candidate.confidence > current.confidence
        return len(candidate.matched_alias) < len(current.matched_alias)

    def resolve(self, raw_text: str, threshold: float = 0.66) -> MatchResult | None:
        query_norm, query_ascii = normalize_pair(raw_text)
        if not query_norm:
            return None

        best: MatchResult | None = None

        for row in self._alias_rows:
            score = self._score(query_norm, query_ascii, row)
            if score < threshold:
                continue

            candidate = MatchResult(
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                canonical_name=row.canonical_name,
                matched_alias=row.alias,
                confidence=round(score, 2),
            )
            if self._better_candidate(candidate, best):
                best = candidate

        return best

    def search(self, query: str, limit: int = 10, threshold: float = 0.6) -> list[MatchResult]:
        query_norm, query_ascii = normalize_pair(query)
        if not query_norm:
            return []

        best_by_entity: dict[tuple[str, int], MatchResult] = {}
        for row in self._alias_rows:
            score = self._score(query_norm, query_ascii, row)
            if score < threshold:
                continue

            key = (row.entity_type, row.entity_id)
            candidate = MatchResult(
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                canonical_name=row.canonical_name,
                matched_alias=row.alias,
                confidence=round(score, 2),
            )
            if self._better_candidate(candidate, best_by_entity.get(key)):
                best_by_entity[key] = candidate

        ranked = sorted(
            best_by_entity.values(),
            key=lambda item: (-item.confidence, item.canonical_name),
        )
        return ranked[:limit]
