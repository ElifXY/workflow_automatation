from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("kanzlei_ai_metrics")


def log_ai_metric(
    *,
    event: str,
    trace_id: str,
    endpoint: str,
    model: str,
    latency_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_code: str = "",
    extra: Dict[str, Any] | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "event": event,
        "trace_id": trace_id,
        "endpoint": endpoint,
        "model": model,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error_code": error_code or "",
    }
    if extra:
        payload.update(extra)
    log.info("AI_METRIC %s", payload)

