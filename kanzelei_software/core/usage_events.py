"""Leichtgewichtige Nutzungs-Events für ROI/Autopilot (pro Mandant)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

EVENT_KEY = "__usage_events_v1"
MAX_EVENTS = 3000
RETENTION_DAYS = 90


def track_usage(store, metric: str, delta: int = 1) -> None:
    try:
        events: List[Dict[str, Any]] = store.setting_holen(EVENT_KEY, []) or []
        events.append({
            "metric": str(metric),
            "ts": datetime.now().isoformat(),
            "delta": int(delta),
        })
        cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
        compact: List[Dict[str, Any]] = []
        for e in events[-MAX_EVENTS:]:
            ts_raw = e.get("ts") or e.get("t") or e.get("timestamp")
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo:
                    ts = ts.replace(tzinfo=None)
                if ts >= cutoff:
                    compact.append(e)
            except Exception:
                compact.append(e)
        store.setting_setzen(EVENT_KEY, compact)
    except Exception:
        pass


def count_events_in_range(
    store,
    von_datum: str,
    bis_datum: str,
    metric_prefix: str = "",
) -> int:
    try:
        events = store.setting_holen(EVENT_KEY, []) or []
    except Exception:
        events = []
    n = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ts = str(ev.get("ts") or ev.get("t") or ev.get("timestamp") or "")[:10]
        if not ts or ts < von_datum or ts > bis_datum:
            continue
        m = str(ev.get("metric") or ev.get("a") or "")
        if not metric_prefix or m.startswith(metric_prefix):
            n += int(ev.get("delta") or ev.get("count") or 1)
    return n
