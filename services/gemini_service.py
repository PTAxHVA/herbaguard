from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str
    model: str = "gemini-2.5-flash"
    timeout_seconds: float = 15.0


class GeminiService:
    def __init__(self, config: GeminiConfig | None) -> None:
        self._config = config

    @classmethod
    def from_env(cls) -> "GeminiService":
        api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
        if not api_key:
            return cls(None)

        model = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()
        timeout_raw = (os.environ.get("GEMINI_TIMEOUT_SECONDS") or "15").strip()
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 15.0

        return cls(
            GeminiConfig(
                api_key=api_key,
                model=model,
                timeout_seconds=max(5.0, min(timeout, 60.0)),
            )
        )

    @property
    def enabled(self) -> bool:
        return self._config is not None

    def generate_grounded_answer(self, prompt: str, system_instruction: str) -> str | None:
        config = self._config
        if config is None:
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent"
        params = {"key": config.api_key}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.9,
                "maxOutputTokens": 700,
            },
        }

        try:
            with httpx.Client(timeout=config.timeout_seconds) as client:
                response = client.post(url, params=params, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return None

        text = self._extract_text(data)
        return text.strip() if text else None

    @staticmethod
    def _extract_text(payload: dict) -> str | None:
        candidates = payload.get("candidates", [])
        if not isinstance(candidates, list):
            return None

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            parts = content.get("parts", [])
            if not isinstance(parts, list):
                continue

            chunks: list[str] = []
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
            if chunks:
                return "\n".join(chunks)

        return None
