from __future__ import annotations

from threading import Lock
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

try:
    import mongomock
except ImportError:  # pragma: no cover
    mongomock = None


_ClientT = Any

_LOCK = Lock()
_CLIENT_CACHE: dict[tuple[str, bool], _ClientT] = {}


def create_mongo_client(uri: str, *, use_mock: bool = False) -> _ClientT:
    if use_mock:
        if mongomock is None:
            raise RuntimeError("MONGODB_USE_MOCK=1 nhưng chưa cài mongomock.")
        return mongomock.MongoClient()

    return MongoClient(uri, tz_aware=True, connect=False)


def get_mongo_database(uri: str, db_name: str, *, use_mock: bool = False) -> Database:
    normalized_uri = (uri or "mongodb://127.0.0.1:27017").strip() or "mongodb://127.0.0.1:27017"
    normalized_name = (db_name or "herbaguard").strip() or "herbaguard"
    cache_key = (normalized_uri, bool(use_mock))

    with _LOCK:
        client = _CLIENT_CACHE.get(cache_key)
        if client is None:
            client = create_mongo_client(normalized_uri, use_mock=use_mock)
            _CLIENT_CACHE[cache_key] = client

    return client[normalized_name]


def clear_mongo_client_cache() -> None:
    with _LOCK:
        clients = list(_CLIENT_CACHE.values())
        _CLIENT_CACHE.clear()

    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            close()
