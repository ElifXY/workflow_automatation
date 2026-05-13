from __future__ import annotations

import re
from typing import Iterable, List

MAX_B64_CHARS = 12_000_000
MAX_TEXT_CHARS = 20_000

_PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "reveal hidden prompt",
    "exfiltrate",
    "api key",
    "secret",
)


def clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def guard_input_text(text: str) -> str:
    text = (text or "").strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return text


def validate_b64_payload(payload: str) -> None:
    if not payload or not isinstance(payload, str):
        raise ValueError("Dateiinhalt fehlt")
    if len(payload) > MAX_B64_CHARS:
        raise ValueError("Datei zu groß für KI-Analyse")
    if not re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", payload):
        raise ValueError("Dateiinhalt ist kein valides Base64")


def detect_prompt_injection(texts: Iterable[str]) -> List[str]:
    hits: List[str] = []
    blob = " ".join((t or "").lower() for t in texts)
    for marker in _PROMPT_INJECTION_MARKERS:
        if marker in blob:
            hits.append(marker)
    return hits


def apply_token_budget(max_tokens: int, budget: int) -> int:
    return clamp_int(min(max_tokens, budget), minimum=64, maximum=4096)

