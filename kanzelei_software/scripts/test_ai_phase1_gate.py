from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(label: str) -> None:
    print(f"[OK] {label}")


def _fail(label: str) -> None:
    print(f"[FAIL] {label}")


def main() -> int:
    success = True

    for module_name in (
        "core.ai_service",
        "core.ai_guardrails",
        "core.ai_schemas",
        "core.ai_metrics",
    ):
        try:
            importlib.import_module(module_name)
            _ok(f"import {module_name}")
        except Exception as exc:  # noqa: BLE001
            _fail(f"import {module_name}: {exc}")
            success = False

    api_path = ROOT / "api.py"
    text = api_path.read_text(encoding="utf-8", errors="ignore")
    required_tokens = [
        "_require_tenant_feature(_user, \"ai_assistant\")",
        "_require_tenant_feature(_user, \"ai_document_scan\")",
        "_require_tenant_feature(_user, \"ai_receipt_scan\")",
        "assistant_chat(",
        "analyze_document(",
        "analyze_receipt(",
    ]
    for token in required_tokens:
        if token in text:
            _ok(f"api.py contains {token}")
        else:
            _fail(f"api.py missing {token}")
            success = False

    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())

