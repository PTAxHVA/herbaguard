from __future__ import annotations

from dataclasses import dataclass

from models import ChatHistoryMessage
from services.normalize import normalize_ascii


@dataclass(frozen=True)
class IntentDetectionResult:
    intents: set[str]
    message_ascii: str


class ChatIntentService:
    _GREETING_KEYWORDS = {
        "xin chao",
        "chao",
        "hello",
        "hi",
        "alo",
        "chao ban",
        "hey",
    }
    _HELP_KEYWORDS = {
        "help",
        "tro giup",
        "huong dan",
        "co the giup",
        "ban lam duoc gi",
        "cach dung",
    }
    _INTERACTION_KEYWORDS = {
        "tuong tac",
        "dung chung",
        "ket hop",
        "uong cung",
        "co anh huong",
        "co nguy hiem",
    }
    _SIDE_EFFECT_KEYWORDS = {
        "tac dung phu",
        "hau qua",
        "bien chung",
        "anh huong gi",
        "co hai gi",
        "co gay gi",
    }
    _RECOMMENDATION_KEYWORDS = {
        "nen lam gi",
        "khuyen nghi",
        "can lam gi",
        "xu ly",
        "co nen dung",
    }
    _MECHANISM_KEYWORDS = {
        "co che",
        "tai sao",
        "vi sao",
        "nguyen nhan",
    }
    _CLASSIFICATION_KEYWORDS = {
        "la thuoc tay hay thao duoc",
        "la thuoc tay",
        "la thao duoc",
        "phan loai",
        "thuoc hay thao duoc",
    }
    _RELATED_KEYWORDS = {
        "goi y",
        "lien quan",
        "thuoc nao khac",
        "thao duoc nao khac",
        "co the kiem tra them",
    }
    _FOLLOW_UP_MARKERS = {
        "cai do",
        "thuoc do",
        "thao duoc do",
        "cai nay",
        "thuoc nay",
        "thao duoc nay",
        "no",
        "con cai do thi sao",
        "con cai kia thi sao",
        "giai thich ngan gon hon",
        "ngan gon hon",
        "con thi sao",
    }

    @staticmethod
    def _contains_any(text_ascii: str, keywords: set[str]) -> bool:
        tokens = [token for token in text_ascii.split(" ") if token]
        token_set = set(tokens)
        padded = f" {text_ascii} "

        for keyword in keywords:
            key = keyword.strip()
            if not key:
                continue
            if " " in key:
                if f" {key} " in padded:
                    return True
            elif key in token_set:
                return True
        return False

    def _is_follow_up(self, text_ascii: str, history: list[ChatHistoryMessage]) -> bool:
        if self._contains_any(text_ascii, self._FOLLOW_UP_MARKERS):
            return True
        if not history:
            return False
        token_count = len([token for token in text_ascii.split(" ") if token])
        return 0 < token_count <= 4

    def detect_intents(self, message: str, history: list[ChatHistoryMessage]) -> IntentDetectionResult:
        text_ascii = normalize_ascii(message)
        intents: set[str] = set()

        if self._contains_any(text_ascii, self._GREETING_KEYWORDS):
            intents.add("greeting")

        if self._contains_any(text_ascii, self._HELP_KEYWORDS):
            intents.add("help")

        if self._contains_any(text_ascii, self._INTERACTION_KEYWORDS):
            intents.add("interaction_query")

        if self._contains_any(text_ascii, self._SIDE_EFFECT_KEYWORDS):
            intents.add("ask_side_effects")

        if self._contains_any(text_ascii, self._RECOMMENDATION_KEYWORDS):
            intents.add("ask_recommendation")

        if self._contains_any(text_ascii, self._MECHANISM_KEYWORDS):
            intents.add("ask_mechanism")

        if self._contains_any(text_ascii, self._CLASSIFICATION_KEYWORDS):
            intents.add("entity_classification")

        if self._contains_any(text_ascii, self._RELATED_KEYWORDS):
            intents.add("related_entities")

        if self._is_follow_up(text_ascii, history):
            intents.add("follow_up")

        return IntentDetectionResult(intents=intents, message_ascii=text_ascii)
