#!/usr/bin/env python3
"""
Security Baseline Gate

Ziel:
- harte Verifikation für Tenant-Trennung + Zugriffskontrolle
- Features sollten erst nach bestandenem Baseline-Gate aktiviert werden
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_FILE = ARTIFACT_DIR / "security_baseline_pass.json"

TEST_SCRIPTS = [
    "scripts/test_feature_runtime_gate.py",
    "scripts/go_live_rbac_gate.py",
    "scripts/test_api_users_management.py",
    "scripts/test_api_users_invites.py",
    "scripts/tenant_enforcement_audit.py",
]


def _run(script_rel: str) -> tuple[int, str]:
    env = dict(os.environ)
    # Baseline suite runs with explicit controlled unlock.
    env["ENABLE_ADVANCED_FEATURES"] = "1"
    env["SECURITY_BASELINE_BOOTSTRAP"] = "1"
    proc = subprocess.run(
        [sys.executable, script_rel],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    joined = "\n".join([p for p in [out, err] if p]).strip()
    return proc.returncode, joined


def main() -> int:
    failures: list[str] = []
    for script in TEST_SCRIPTS:
        code, output = _run(script)
        if code != 0:
            failures.append(f"{script} failed with exit={code}\n{output}")
        else:
            print(f"PASS: {script}")

    if failures:
        print("Security baseline gate failed:")
        for item in failures:
            print(f"- {item}")
        return 2

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": TEST_SCRIPTS,
    }
    ARTIFACT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Security baseline gate passed. Artifact: {ARTIFACT_FILE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

