from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.data_loader import EntityRecord, InteractionRecord, LoadedDatabase
from services.normalize import normalize_ascii, normalize_pair
from services.resolver import EntityResolver, MatchResult

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

_AMBIGUOUS_SINGLE_TOKEN_ALIASES = {
    "toi",
    "con",
    "co",
    "la",
    "cay",
    "thuoc",
    "va",
    "voi",
    "khong",
    "nen",
    "lam",
    "gi",
    "tai",
    "sao",
    "nguy",
    "hiem",
    "tuong",
    "tac",
}


@dataclass(frozen=True)
class GraphNode:
    type: str
    id: int
    canonical_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class GraphEntity:
    type: str
    id: int
    name: str
    matched_alias: str
    confidence: float


class KnowledgeGraphService:
    def __init__(self, db: LoadedDatabase, resolver: EntityResolver) -> None:
        self.db = db
        self.resolver = resolver
        self._nodes = self._build_node_index()
        self._aliases = self._build_alias_index()
        self._canonical_index = self._build_canonical_index()
        self._alias_exact_index = self._build_alias_exact_index()

    def _build_node_index(self) -> dict[tuple[str, int], GraphNode]:
        nodes: dict[tuple[str, int], GraphNode] = {}
        for row in self.db.drugs.values():
            nodes[("drug", row.entity_id)] = GraphNode(
                type="drug",
                id=row.entity_id,
                canonical_name=row.canonical_name,
                aliases=row.aliases,
            )
        for row in self.db.herbs.values():
            nodes[("herb", row.entity_id)] = GraphNode(
                type="herb",
                id=row.entity_id,
                canonical_name=row.canonical_name,
                aliases=row.aliases,
            )
        return nodes

    def _build_alias_index(self) -> list[tuple[str, int, str, str, str, int]]:
        rows: list[tuple[str, int, str, str, str, int]] = []
        for (entity_type, entity_id), row in self._nodes.items():
            for alias in row.aliases:
                alias_norm, alias_ascii = normalize_pair(alias)
                if not alias_norm:
                    continue
                token_count = len([token for token in alias_ascii.split(" ") if token])
                rows.append((entity_type, entity_id, alias, alias_norm, alias_ascii, token_count))

        rows.sort(key=lambda item: len(item[3]), reverse=True)
        return rows

    def _build_canonical_index(self) -> dict[str, GraphNode]:
        index: dict[str, GraphNode] = {}
        for node in self._nodes.values():
            canon_norm, canon_ascii = normalize_pair(node.canonical_name)
            if canon_norm and canon_norm not in index:
                index[canon_norm] = node
            if canon_ascii and canon_ascii not in index:
                index[canon_ascii] = node
        return index

    def _build_alias_exact_index(self) -> dict[str, GraphNode]:
        index: dict[str, GraphNode] = {}
        for node in self._nodes.values():
            for alias in node.aliases:
                alias_norm, alias_ascii = normalize_pair(alias)
                if alias_norm and alias_norm not in index:
                    index[alias_norm] = node
                if alias_ascii and alias_ascii not in index:
                    index[alias_ascii] = node
        return index

    @staticmethod
    def infer_severity(interaction: InteractionRecord) -> str:
        joined = " ".join(
            [
                interaction.mechanism,
                " ".join(interaction.possible_consequences),
                interaction.recommendation,
            ]
        )
        text = normalize_ascii(joined)

        if any(keyword in text for keyword in _HIGH_KEYWORDS):
            return "high"
        if any(keyword in text for keyword in _MEDIUM_KEYWORDS):
            return "medium"
        return "medium"

    @staticmethod
    def _extract_from_match(match: MatchResult) -> GraphEntity:
        return GraphEntity(
            type=match.entity_type,
            id=match.entity_id,
            name=match.canonical_name,
            matched_alias=match.matched_alias,
            confidence=match.confidence,
        )

    @staticmethod
    def _looks_like_entity_phrase(query_ascii: str) -> bool:
        tokens = [token for token in query_ascii.split(" ") if token]
        if not tokens:
            return False

        if len(tokens) == 1:
            return len(tokens[0]) >= 3

        meaningful_tokens = [token for token in tokens if token not in _AMBIGUOUS_SINGLE_TOKEN_ALIASES]
        if not meaningful_tokens:
            return False

        return len(meaningful_tokens) / len(tokens) >= 0.5

    def _coerce_node(self, value: int | str | GraphNode | GraphEntity, expected_type: str | None = None) -> GraphNode | None:
        if isinstance(value, GraphNode):
            if expected_type is None or value.type == expected_type:
                return value
            return None

        if isinstance(value, GraphEntity):
            node = self._nodes.get((value.type, value.id))
            if node is None:
                return None
            if expected_type is None or node.type == expected_type:
                return node
            return None

        if isinstance(value, int):
            if expected_type == "drug":
                return self._nodes.get(("drug", value))
            if expected_type == "herb":
                return self._nodes.get(("herb", value))
            return self._nodes.get(("drug", value)) or self._nodes.get(("herb", value))

        resolved = self.resolve_entity(value)
        if resolved is None:
            return None
        node = self._nodes.get((resolved.type, resolved.id))
        if node is None:
            return None
        if expected_type is None or node.type == expected_type:
            return node
        return None

    def _collect_related_keys(self, node: GraphNode) -> list[tuple[str, int]]:
        related: set[tuple[str, int]] = set()
        if node.type == "drug":
            for drug_id, herb_id in self.db.interactions_by_pair:
                if drug_id == node.id:
                    related.add(("herb", herb_id))
        else:
            for drug_id, herb_id in self.db.interactions_by_pair:
                if herb_id == node.id:
                    related.add(("drug", drug_id))
        return sorted(related)

    def find_node_by_name(self, name: str) -> GraphNode | None:
        query_norm, query_ascii = normalize_pair(name)
        if not query_norm:
            return None
        return self._canonical_index.get(query_norm) or self._canonical_index.get(query_ascii)

    def find_node_by_alias(self, text: str) -> GraphNode | None:
        query_norm, query_ascii = normalize_pair(text)
        if not query_norm:
            return None
        return self._alias_exact_index.get(query_norm) or self._alias_exact_index.get(query_ascii)

    def resolve_entity(self, text: str) -> GraphEntity | None:
        match = self.resolver.resolve(text)
        if match is None:
            return None
        return self._extract_from_match(match)

    def resolve_term(self, text: str) -> GraphEntity | None:
        # Backward-compatible alias for older callers.
        return self.resolve_entity(text)

    def search_entities(self, query: str, limit: int = 10) -> list[GraphEntity]:
        return self.extract_entities(query, limit=limit)

    def extract_entities(self, text: str, limit: int = 6) -> list[GraphEntity]:
        query_norm, query_ascii = normalize_pair(text)
        if not query_norm:
            return []

        padded_norm = f" {query_norm} "
        padded_ascii = f" {query_ascii} "

        candidates: dict[tuple[str, int], GraphEntity] = {}
        query_token_count = len([token for token in query_ascii.split(" ") if token])

        for entity_type, entity_id, alias, alias_norm, alias_ascii, alias_token_count in self._aliases:
            if (
                alias_token_count == 1
                and alias_ascii in _AMBIGUOUS_SINGLE_TOKEN_ALIASES
                and query_ascii != alias_ascii
                and query_norm != alias_norm
                and query_token_count > 1
            ):
                # Prevent false positives such as "tôi" in natural Vietnamese sentence matching herb "tỏi".
                continue

            score = 0.0
            if f" {alias_norm} " in padded_norm:
                score = 1.0
            elif f" {alias_ascii} " in padded_ascii:
                score = 0.95
            elif alias_norm in query_norm:
                score = 0.9
            elif alias_ascii in query_ascii:
                score = 0.84
            if score <= 0:
                continue

            key = (entity_type, entity_id)
            node = self._nodes[key]
            current = candidates.get(key)
            candidate = GraphEntity(
                type=entity_type,
                id=entity_id,
                name=node.canonical_name,
                matched_alias=alias,
                confidence=round(score, 2),
            )
            if current is None or candidate.confidence > current.confidence:
                candidates[key] = candidate

        fuzzy_hits = self.resolver.extract_from_text(text, limit=max(8, limit * 2), threshold=0.6)
        for hit in fuzzy_hits:
            key = (hit.entity_type, hit.entity_id)
            current = candidates.get(key)
            candidate = self._extract_from_match(hit)
            if current is None or candidate.confidence > current.confidence:
                candidates[key] = candidate

        if not candidates and query_token_count <= 5 and self._looks_like_entity_phrase(query_ascii):
            search_hits = self.resolver.search(text, limit=max(limit, 6), threshold=0.6)
            for hit in search_hits:
                key = (hit.entity_type, hit.entity_id)
                current = candidates.get(key)
                candidate = self._extract_from_match(hit)
                if current is None or candidate.confidence > current.confidence:
                    candidates[key] = candidate

        output = sorted(candidates.values(), key=lambda item: (-item.confidence, item.name))
        return output[:limit]

    def _build_interaction_row(self, interaction: InteractionRecord) -> dict[str, object]:
        drug_node = self._nodes.get(("drug", interaction.drug_id))
        herb_node = self._nodes.get(("herb", interaction.herb_id))
        if drug_node is None or herb_node is None:
            return {}

        return {
            "drug_id": interaction.drug_id,
            "herb_id": interaction.herb_id,
            "drug_name": drug_node.canonical_name,
            "herb_name": herb_node.canonical_name,
            "severity": self.infer_severity(interaction),
            "mechanism": interaction.mechanism,
            "possible_consequences": list(interaction.possible_consequences),
            "recommendation": interaction.recommendation,
        }

    def get_interaction_evidence(
        self,
        drug_name_or_id: int | str | GraphNode | GraphEntity,
        herb_name_or_id: int | str | GraphNode | GraphEntity,
    ) -> list[dict[str, object]]:
        drug_node = self._coerce_node(drug_name_or_id, expected_type="drug")
        herb_node = self._coerce_node(herb_name_or_id, expected_type="herb")
        if drug_node is None or herb_node is None:
            return []

        rows: list[dict[str, object]] = []
        for interaction in self.db.interactions_by_pair.get((drug_node.id, herb_node.id), tuple()):
            row = self._build_interaction_row(interaction)
            if row:
                rows.append(row)

        rows.sort(key=lambda row: (0 if row["severity"] == "high" else 1, row["drug_name"], row["herb_name"]))
        return rows

    def check_interaction_pair(
        self,
        drug_name_or_id: int | str | GraphNode | GraphEntity,
        herb_name_or_id: int | str | GraphNode | GraphEntity,
    ) -> bool:
        return bool(self.get_interaction_evidence(drug_name_or_id, herb_name_or_id))

    def related_entities(
        self,
        name_or_id: int | str | GraphNode | GraphEntity,
        *,
        target_type: str | None = None,
        limit: int = 5,
    ) -> list[GraphNode]:
        node = self._coerce_node(name_or_id)
        if node is None:
            return []

        related_keys = self._collect_related_keys(node)
        output: list[GraphNode] = []
        for key in related_keys:
            related = self._nodes.get(key)
            if related is None:
                continue
            if target_type is not None and related.type != target_type:
                continue
            output.append(related)
            if len(output) >= limit:
                break
        return output

    def resolve_node(
        self,
        value: int | str | GraphNode | GraphEntity,
        *,
        expected_type: str | None = None,
    ) -> GraphNode | None:
        return self._coerce_node(value, expected_type=expected_type)

    def get_entity_aliases(
        self,
        value: int | str | GraphNode | GraphEntity,
        *,
        expected_type: str | None = None,
    ) -> tuple[str, ...]:
        node = self._coerce_node(value, expected_type=expected_type)
        if node is None:
            return tuple()
        return node.aliases

    def find_interactions(self, drug_ids: Iterable[int], herb_ids: Iterable[int]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []

        for drug_id in sorted(set(int(x) for x in drug_ids)):
            if ("drug", drug_id) not in self._nodes:
                continue

            for herb_id in sorted(set(int(x) for x in herb_ids)):
                if ("herb", herb_id) not in self._nodes:
                    continue

                rows.extend(self.get_interaction_evidence(drug_id, herb_id))

        rows.sort(key=lambda row: (0 if row["severity"] == "high" else 1, row["drug_name"], row["herb_name"]))
        return rows
