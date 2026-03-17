from __future__ import annotations

import re
import unicodedata

_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    if text is None:
        return ""

    normalized = unicodedata.normalize("NFKC", str(text)).strip().lower()
    normalized = _NON_WORD_RE.sub(" ", normalized)
    normalized = _MULTI_SPACE_RE.sub(" ", normalized)
    return normalized.strip()


def remove_diacritics(text: str) -> str:
    if not text:
        return ""

    base = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    stripped = stripped.replace("đ", "d").replace("Đ", "d")
    return unicodedata.normalize("NFC", stripped)


def normalize_ascii(text: str) -> str:
    return normalize_text(remove_diacritics(normalize_text(text)))


def normalize_pair(text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    return normalized, normalize_ascii(normalized)


def deduplicate_inputs(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for raw in items:
        cleaned = str(raw).strip()
        if not cleaned:
            continue
        key = normalize_ascii(cleaned)
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)

    return output
