"""
Smoke test for settings reliability.

Checks:
- Every default setting key can be persisted round-trip.
- Safety rules reject known-invalid values.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.settings_manager import (
    DEFAULT_SETTINGS,
    FESTGESCHRIEBEN,
    alle_settings_holen,
    setting_holen,
    setting_setzen,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run() -> None:
    base = alle_settings_holen()
    failures = []

    # Round-trip each key with its current/default value.
    for key, default in DEFAULT_SETTINGS.items():
        if key in FESTGESCHRIEBEN:
            continue
        current = base.get(key, default)
        ok = setting_setzen(key, current)
        if not ok:
            failures.append(f"roundtrip rejected: {key}={current!r}")
            continue
        now = setting_holen(key)
        if now != current:
            failures.append(f"roundtrip mismatch: {key} expected={current!r} got={now!r}")

    # Guardrail checks (must be rejected).
    invalid_cases = [
        ("ki_review_ab_konfidenz", 99),        # likely >= auto threshold
        ("billing_modell", "invalid"),
        ("server_standort", "CN"),
        ("webhook_url", "not-a-url"),
        ("bank_import_uhrzeit", "25:99"),
        ("rollen_einstellungen", []),
        ("rollen_einstellungen", ["mitarbeiter"]),
        ("rollen_mandant_loeschen", ["steuerberater"]),
        ("rollen_zahlungen_freigabe", ["mitarbeiter"]),
    ]
    for key, val in invalid_cases:
        ok = setting_setzen(key, val)
        if ok:
            failures.append(f"invalid value accepted: {key}={val!r}")

    _assert(not failures, " | ".join(failures))
    print(f"[OK] settings integrity: {len(DEFAULT_SETTINGS)} keys round-tripped")


if __name__ == "__main__":
    run()
