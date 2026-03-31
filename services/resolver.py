from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from services.data_loader import EntityRecord, LoadedDatabase
from services.normalize import normalize_pair, phrase_windows, strip_context_noise, tokenize_ascii


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
    token_count: int


_AMBIGUOUS_SINGLE_TOKENS = {
    "toi",
    "co",
    "con",
    "la",
    "cay",
    "thuoc",
    "va",
    "voi",
    "khong",
    "nen",
    "lam",
    "gi",
    "sao",
    "thi",
    "tuong",
    "tac",
}


class EntityResolver:
    def __init__(self, db: LoadedDatabase) -> None:
        self._alias_rows: tuple[_AliasRow, ...] = self._build_alias_rows(db)
        self._single_token_frequency: dict[str, int] = self._build_single_token_frequency(self._alias_rows)

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
                        token_count=len([token for token in alias_ascii.split(" ") if token]),
                    )
                )

        for entity in db.drugs.values():
            append_entity(entity)
        for entity in db.herbs.values():
            append_entity(entity)

        return tuple(rows)

    @staticmethod
    def _build_single_token_frequency(rows: tuple[_AliasRow, ...]) -> dict[str, int]:
        frequency: dict[str, int] = {}
        for row in rows:
            for token in tokenize_ascii(row.alias_ascii):
                if len(token) < 3:
                    continue
                frequency[token] = frequency.get(token, 0) + 1
        return frequency

    @staticmethod
    def _token_overlap_score(left: str, right: str) -> float:
        left_tokens = {token for token in left.split() if len(token) >= 2}
        right_tokens = {token for token in right.split() if len(token) >= 2}

        if not left_tokens or not right_tokens:
            return 0.0

        overlap = len(left_tokens.intersection(right_tokens))
        union = len(left_tokens.union(right_tokens))
        if union == 0:
            return 0.0
        return overlap / union

    @staticmethod
    def _sequence_score(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right).ratio()

    @staticmethod
    def _contains_match(left: str, right: str) -> bool:
        if len(left) < 4 or len(right) < 4:
            return False
        return left in right or right in left

    def _score(self, query_norm: str, query_ascii: str, row: _AliasRow) -> float:
        if query_norm == row.alias_norm:
            return 1.0
        if query_ascii == row.alias_ascii:
            return 0.98

        score = 0.0
        if self._contains_match(query_norm, row.alias_norm):
            score = max(score, 0.92 if query_norm in row.alias_norm else 0.89)

        if self._contains_match(query_ascii, row.alias_ascii):
            score = max(score, 0.88 if query_ascii in row.alias_ascii else 0.84)

        similarity = self._sequence_score(query_ascii, row.alias_ascii)
        if similarity >= 0.95:
            score = max(score, 0.9)
        elif similarity >= 0.9:
            score = max(score, 0.84)
        elif similarity >= 0.84:
            score = max(score, 0.78)
        elif similarity >= 0.76:
            score = max(score, 0.71)

        overlap = self._token_overlap_score(query_ascii, row.alias_ascii)
        if overlap >= 1.0 and row.token_count >= 2:
            score = max(score, 0.82)
        elif overlap >= 0.67:
            score = max(score, 0.74)
        elif overlap >= 0.5:
            score = max(score, 0.68)

        query_tokens = tokenize_ascii(query_ascii)
        if (
            len(query_tokens) == 1
            and row.token_count == 1
            and len(query_ascii) >= 4
            and len(row.alias_ascii) >= 4
            and abs(len(query_ascii) - len(row.alias_ascii)) <= 2
            and similarity >= 0.75
        ):
            score = max(score, 0.74)

        if (
            row.token_count == 1
            and row.alias_ascii in _AMBIGUOUS_SINGLE_TOKENS
            and query_ascii != row.alias_ascii
            and len(tokenize_ascii(query_ascii)) > 1
        ):
            score *= 0.75

        return min(score, 0.99)

    @staticmethod
    def _better_candidate(candidate: MatchResult, current: MatchResult | None) -> bool:
        if current is None:
            return True
        if candidate.confidence != current.confidence:
            return candidate.confidence > current.confidence
        return len(candidate.matched_alias) < len(current.matched_alias)

    @staticmethod
    def _query_variants(raw_text: str) -> list[tuple[str, str]]:
        variants: list[tuple[str, str]] = []
        for text in [raw_text, strip_context_noise(raw_text)]:
            query_norm, query_ascii = normalize_pair(text)
            if not query_norm:
                continue
            if (query_norm, query_ascii) in variants:
                continue
            variants.append((query_norm, query_ascii))
        return variants

    @staticmethod
    def _is_noise_phrase(phrase: str) -> bool:
        tokens = tokenize_ascii(phrase)
        if not tokens:
            return True
        if len(tokens) == 1 and len(tokens[0]) < 3:
            return True
        return all(token in _AMBIGUOUS_SINGLE_TOKENS for token in tokens)

    def resolve(self, raw_text: str, threshold: float = 0.66) -> MatchResult | None:
        best: MatchResult | None = None

        for query_norm, query_ascii in self._query_variants(raw_text):
            if self._is_noise_phrase(query_ascii):
                continue
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

    def search(self, query: str, limit: int = 10, threshold: float = 0.58) -> list[MatchResult]:
        best_by_entity: dict[tuple[str, int], MatchResult] = {}

        for query_norm, query_ascii in self._query_variants(query):
            if self._is_noise_phrase(query_ascii):
                continue
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

    def extract_from_text(self, text: str, limit: int = 8, threshold: float = 0.62) -> list[MatchResult]:
        raw_tokens = tokenize_ascii(text)
        direct_single_query = len(raw_tokens) == 1
        raw_single_token = raw_tokens[0] if direct_single_query else ""

        phrases: list[str] = []
        base = strip_context_noise(text)
        if base:
            phrases.append(base)

        phrases.extend(phrase_windows(base or text, max_window=4))
        if not base:
            phrases.extend(phrase_windows(text, max_window=3))

        seen_phrases: set[str] = set()
        unique_phrases: list[str] = []
        for phrase in phrases:
            cleaned = phrase.strip()
            if not cleaned or cleaned in seen_phrases:
                continue
            seen_phrases.add(cleaned)
            unique_phrases.append(cleaned)

        best_by_entity: dict[tuple[str, int], MatchResult] = {}
        for phrase in unique_phrases:
            phrase_tokens = tokenize_ascii(phrase)
            if len(phrase_tokens) == 1:
                token = phrase_tokens[0]
                is_explicit_single_query = direct_single_query and token == raw_single_token
                if len(token) <= 3 and not is_explicit_single_query:
                    if token in _AMBIGUOUS_SINGLE_TOKENS:
                        continue
                    token_frequency = self._single_token_frequency.get(token, 0)
                    if token_frequency == 0 or token_frequency > 6:
                        continue

            if self._is_noise_phrase(phrase):
                continue
            hits = self.search(phrase, limit=6, threshold=threshold)
            phrase_token_count = len(phrase_tokens)
            for hit in hits:
                adjusted = hit.confidence
                if phrase_token_count >= 2:
                    adjusted = min(0.99, adjusted + 0.03)
                candidate = MatchResult(
                    entity_type=hit.entity_type,
                    entity_id=hit.entity_id,
                    canonical_name=hit.canonical_name,
                    matched_alias=hit.matched_alias,
                    confidence=round(adjusted, 2),
                )
                key = (candidate.entity_type, candidate.entity_id)
                if self._better_candidate(candidate, best_by_entity.get(key)):
                    best_by_entity[key] = candidate

        ranked = sorted(best_by_entity.values(), key=lambda item: (-item.confidence, item.canonical_name))
        return ranked[:limit]
