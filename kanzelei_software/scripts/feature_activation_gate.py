#!/usr/bin/env python3
"""
Feature Activation Gate

Erlaubt das Aktivieren erweiterter Features nur nach bestandenem Security-Baseline-Gate.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.feature_gate import evaluate_feature_gate  # noqa: E402


def _enabled(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    if not _enabled(os.getenv("ENABLE_ADVANCED_FEATURES")):
        print("Feature activation gate: advanced features disabled -> skip")
        return 0

    allowed, reason = evaluate_feature_gate()
    if not allowed:
        print(f"Feature activation blocked: {reason}")
        return 2

    print("Feature activation gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

