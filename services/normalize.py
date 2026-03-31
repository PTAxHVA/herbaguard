from __future__ import annotations

import re
import unicodedata

_NON_WORD_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")

_CONTEXT_NOISE_TOKENS = {
    "thuoc",
    "thao",
    "duoc",
    "cay",
    "la",
    "loai",
    "uong",
    "dang",
    "toi",
    "minh",
    "ban",
    "cho",
    "hoi",
    "ve",
    "voi",
    "va",
    "co",
    "khong",
    "thi",
    "sao",
    "tuong",
    "tac",
    "kiem",
    "tra",
    "nhe",
    "a",
    "ha",
}


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


def tokenize_ascii(text: str) -> list[str]:
    cleaned = normalize_ascii(text)
    return [token for token in cleaned.split(" ") if token]


def strip_context_noise(text: str) -> str:
    tokens = tokenize_ascii(text)
    if not tokens:
        return ""

    filtered = [token for token in tokens if token not in _CONTEXT_NOISE_TOKENS]
    if not filtered:
        filtered = tokens
    return " ".join(filtered)


def phrase_windows(text: str, max_window: int = 4) -> list[str]:
    tokens = tokenize_ascii(text)
    if not tokens:
        return []

    windows: list[str] = []
    token_count = len(tokens)
    upper = max(1, min(max_window, token_count))

    for size in range(upper, 0, -1):
        for start in range(0, token_count - size + 1):
            chunk = tokens[start : start + size]
            if not chunk:
                continue
            windows.append(" ".join(chunk))

    seen: set[str] = set()
    unique: list[str] = []
    for item in windows:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


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
