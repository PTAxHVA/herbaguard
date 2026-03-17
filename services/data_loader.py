from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EntityRecord:
    entity_type: str
    entity_id: int
    canonical_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class InteractionRecord:
    interaction_id: int
    drug_id: int
    herb_id: int
    mechanism: str
    possible_consequences: tuple[str, ...]
    recommendation: str


@dataclass(frozen=True)
class LoadedDatabase:
    herbs: dict[int, EntityRecord]
    drugs: dict[int, EntityRecord]
    interactions: tuple[InteractionRecord, ...]
    interactions_by_pair: dict[tuple[int, int], tuple[InteractionRecord, ...]]


def _load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Dữ liệu JSON tại {path} phải là dạng mảng.")
    return data


def _normalize_aliases(raw_aliases: Any) -> tuple[str, ...]:
    if not isinstance(raw_aliases, list):
        return tuple()

    output: list[str] = []
    seen: set[str] = set()
    for alias in raw_aliases:
        if not isinstance(alias, str):
            continue
        cleaned = alias.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)

    return tuple(output)


def _load_entities(path: Path, entity_type: str, id_field: str) -> dict[int, EntityRecord]:
    entities: dict[int, EntityRecord] = {}

    for item in _load_json(path):
        if id_field not in item:
            continue
        try:
            entity_id = int(item[id_field])
        except (TypeError, ValueError):
            continue

        aliases = _normalize_aliases(item.get("aliases", []))
        canonical_name = aliases[0] if aliases else f"{entity_type}-{entity_id}"
        entities[entity_id] = EntityRecord(
            entity_type=entity_type,
            entity_id=entity_id,
            canonical_name=canonical_name,
            aliases=aliases,
        )

    return entities


def _load_interactions(path: Path) -> tuple[InteractionRecord, ...]:
    records: list[InteractionRecord] = []

    for item in _load_json(path):
        try:
            interaction_id = int(item.get("interaction_id"))
            drug_id = int(item.get("drug_id"))
            herb_id = int(item.get("herb_id"))
        except (TypeError, ValueError):
            continue

        interaction_data = item.get("interaction", {})
        if not isinstance(interaction_data, dict):
            interaction_data = {}

        mechanism = str(interaction_data.get("mechanism", "")).strip()
        recommendation = str(interaction_data.get("recommendation", "")).strip()

        raw_consequences = interaction_data.get("possible_consequences", [])
        consequences: list[str] = []
        if isinstance(raw_consequences, list):
            for consequence in raw_consequences:
                if isinstance(consequence, str) and consequence.strip():
                    consequences.append(consequence.strip())

        records.append(
            InteractionRecord(
                interaction_id=interaction_id,
                drug_id=drug_id,
                herb_id=herb_id,
                mechanism=mechanism,
                possible_consequences=tuple(consequences),
                recommendation=recommendation,
            )
        )

    return tuple(records)


def load_database(base_dir: Path | None = None) -> LoadedDatabase:
    project_root = base_dir or Path(__file__).resolve().parent.parent
    db_dir = project_root / "database"

    herbs = _load_entities(db_dir / "herb.json", entity_type="herb", id_field="herb_id")
    drugs = _load_entities(db_dir / "drug.json", entity_type="drug", id_field="drug_id")
    interactions = _load_interactions(db_dir / "interaction.json")

    interaction_map: dict[tuple[int, int], list[InteractionRecord]] = {}
    for row in interactions:
        key = (row.drug_id, row.herb_id)
        interaction_map.setdefault(key, []).append(row)

    interactions_by_pair = {key: tuple(rows) for key, rows in interaction_map.items()}

    return LoadedDatabase(
        herbs=herbs,
        drugs=drugs,
        interactions=interactions,
        interactions_by_pair=interactions_by_pair,
    )
