#!/usr/bin/env python3
"""Pass 13 offline smoke — M365 Timeline Workflow-Aktion."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.m365_integration import run_m365_timeline_workflow_action  # noqa: E402


class _FakeStore:
    def __init__(self):
        self.settings = {}
        self.logs = []

    def setting_holen(self, key):
        return self.settings.get(key)

    def log_eintrag(self, msg):
        self.logs.append(msg)


def test_timeline_workflow_action_offline() -> None:
    store = _FakeStore()
    msg = run_m365_timeline_workflow_action(store, "Test Mandant", {"limit": 5})
    assert isinstance(msg, str)
    assert any("WORKFLOW_M365_TIMELINE" in x for x in store.logs)


def main() -> int:
    test_timeline_workflow_action_offline()
    print("PASS pass13 smoke: m365 timeline workflow action")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
