from __future__ import annotations

import json
import os
import re
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

    def _call_model(
        self,
        *,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.2,
        max_output_tokens: int = 700,
    ) -> str | None:
        config = self._config
        if config is None:
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.model}:generateContent"
        params = {"key": config.api_key}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.9,
                "maxOutputTokens": max_output_tokens,
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

    def generate_grounded_answer(self, prompt: str, system_instruction: str) -> str | None:
        return self._call_model(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=700,
        )

    def rerank_entity_candidates(
        self,
        *,
        user_message: str,
        recent_history: list[str],
        candidates: list[dict[str, object]],
    ) -> dict[str, object] | None:
        if not self.enabled:
            return None
        if not candidates:
            return None

        history_lines = [f"- {line}" for line in recent_history[-5:] if line.strip()]
        payload = {
            "user_message": user_message,
            "recent_history": history_lines,
            "candidates": candidates,
            "rules": [
                "Chỉ được chọn ID có trong candidates.",
                "Không tạo tên thực thể ngoài danh sách candidates.",
                "Nếu mơ hồ thì đánh dấu needs_clarification=true và trả về options.",
                "Tối đa 1 thuốc tây và 1 thảo dược trong selected.",
            ],
        }

        prompt = (
            "Nhiệm vụ: rerank thực thể y khoa từ danh sách ứng viên đã truy xuất cục bộ.\n"
            "Trả về JSON hợp lệ, không markdown, không giải thích thêm.\n\n"
            "Schema bắt buộc:\n"
            "{\n"
            '  "selected": [{"type":"drug|herb","id":123}],\n'
            '  "needs_clarification": true|false,\n'
            '  "clarification_options": [{"type":"drug|herb","candidate_ids":[1,2,3]}]\n'
            "}\n\n"
            "Input:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

        system_instruction = (
            "Bạn là bộ chuẩn hóa thực thể cho HerbaGuard. "
            "Bạn chỉ được thao tác trên danh sách ứng viên đã cung cấp, tuyệt đối không tự tạo thực thể mới."
        )

        raw = self._call_model(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.0,
            max_output_tokens=300,
        )
        if not raw:
            return None

        parsed = self._try_parse_json(raw)
        if parsed is None:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _try_parse_json(raw_text: str) -> dict[str, object] | None:
        text = raw_text.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            snippet = text[start : end + 1]
            try:
                parsed = json.loads(snippet)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None

        return None

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
