from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from threading import Lock

from bson import ObjectId
from pymongo import ASCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from services.mongo_helpers import to_id_str, utc_now


@dataclass(frozen=True)
class AuthUserRecord:
    id: str
    full_name: str
    email: str


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.users = db["users"]
        self.sessions = db["sessions"]
        self._lock = Lock()
        self._init_indexes()

    def _init_indexes(self) -> None:
        self.users.create_index([("email", ASCENDING)], unique=True, name="users_email_unique")
        self.sessions.create_index([("token_hash", ASCENDING)], unique=True, name="sessions_token_hash_unique")
        self.sessions.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)], name="sessions_user_created_at")

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return f"{salt.hex()}${pwd_hash.hex()}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            salt_hex, pwd_hash_hex = stored_hash.split("$", 1)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(pwd_hash_hex)
        except ValueError:
            return False

        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(candidate, expected)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_user(doc: dict[str, object]) -> AuthUserRecord:
        return AuthUserRecord(
            id=to_id_str(doc["_id"]),
            full_name=str(doc.get("full_name") or ""),
            email=str(doc.get("email") or ""),
        )

    def register(self, full_name: str, email: str, password: str) -> tuple[AuthUserRecord, str]:
        clean_name = full_name.strip()
        normalized_email = email.strip().lower()
        pwd_hash = self._hash_password(password)

        with self._lock:
            try:
                result = self.users.insert_one(
                    {
                        "full_name": clean_name,
                        "email": normalized_email,
                        "password_hash": pwd_hash,
                        "created_at": utc_now(),
                    }
                )
            except DuplicateKeyError as exc:
                raise ValueError("Email đã tồn tại. Vui lòng dùng email khác.") from exc

            user_doc = {
                "_id": result.inserted_id,
                "full_name": clean_name,
                "email": normalized_email,
            }

            token = secrets.token_urlsafe(32)
            self.sessions.insert_one(
                {
                    "token_hash": self._hash_token(token),
                    "user_id": result.inserted_id,
                    "created_at": utc_now(),
                }
            )

        return self._build_user(user_doc), token

    def login(self, email: str, password: str) -> tuple[AuthUserRecord, str]:
        normalized_email = email.strip().lower()

        with self._lock:
            doc = self.users.find_one(
                {"email": normalized_email},
                {
                    "_id": 1,
                    "full_name": 1,
                    "email": 1,
                    "password_hash": 1,
                },
            )
            if doc is None or not self._verify_password(password, str(doc.get("password_hash") or "")):
                raise ValueError("Email hoặc mật khẩu không đúng.")

            token = secrets.token_urlsafe(32)
            self.sessions.insert_one(
                {
                    "token_hash": self._hash_token(token),
                    "user_id": doc["_id"],
                    "created_at": utc_now(),
                }
            )

        return self._build_user(doc), token

    def get_user_by_token(self, token: str) -> AuthUserRecord | None:
        token_hash = self._hash_token(token)
        session = self.sessions.find_one({"token_hash": token_hash}, {"user_id": 1})
        if session is None:
            return None

        user_id = session.get("user_id")
        if not isinstance(user_id, ObjectId):
            return None

        doc = self.users.find_one({"_id": user_id}, {"_id": 1, "full_name": 1, "email": 1})
        if doc is None:
            return None

        return self._build_user(doc)

    def logout(self, token: str) -> None:
        token_hash = self._hash_token(token)
        self.sessions.delete_one({"token_hash": token_hash})
