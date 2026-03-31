from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    static_dir: Path
    mongodb_uri: str
    mongodb_db_name: str
    mongodb_use_mock: bool


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_static_dir(project_root: Path) -> Path:
    configured = (os.environ.get("HERBAGUARD_STATIC_DIR") or "frontend").strip() or "frontend"
    candidate = project_root / configured
    if candidate.exists():
        return candidate

    legacy_dir = project_root / "[herbaguard] app"
    if legacy_dir.exists():
        return legacy_dir

    return candidate


def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parent
    static_dir = _resolve_static_dir(project_root)

    mongodb_uri = (os.environ.get("MONGODB_URI") or "mongodb://127.0.0.1:27017").strip()
    mongodb_db_name = (os.environ.get("MONGODB_DB_NAME") or "herbaguard").strip() or "herbaguard"
    mongodb_use_mock = _is_truthy(os.environ.get("MONGODB_USE_MOCK"))

    return AppConfig(
        project_root=project_root,
        static_dir=static_dir,
        mongodb_uri=mongodb_uri,
        mongodb_db_name=mongodb_db_name,
        mongodb_use_mock=mongodb_use_mock,
    )
