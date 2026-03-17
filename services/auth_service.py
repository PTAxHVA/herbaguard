from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class AuthUserRecord:
    id: int
    full_name: str
    email: str


class AuthService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            conn.commit()

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
    def _build_user(row: sqlite3.Row) -> AuthUserRecord:
        return AuthUserRecord(id=int(row["id"]), full_name=str(row["full_name"]), email=str(row["email"]))

    def register(self, full_name: str, email: str, password: str) -> tuple[AuthUserRecord, str]:
        pwd_hash = self._hash_password(password)

        with self._lock, self._connection() as conn:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing is not None:
                raise ValueError("Email đã tồn tại. Vui lòng dùng email khác.")

            cursor = conn.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (full_name, email, pwd_hash),
            )
            user_id = int(cursor.lastrowid)
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
            conn.commit()

            user = AuthUserRecord(id=user_id, full_name=full_name, email=email)
            return user, token

    def login(self, email: str, password: str) -> tuple[AuthUserRecord, str]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT id, full_name, email, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if row is None or not self._verify_password(password, str(row["password_hash"])):
                raise ValueError("Email hoặc mật khẩu không đúng.")

            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, int(row["id"])))
            conn.commit()

            return self._build_user(row), token

    def get_user_by_token(self, token: str) -> AuthUserRecord | None:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.full_name, u.email
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None
            return self._build_user(row)

    def logout(self, token: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
