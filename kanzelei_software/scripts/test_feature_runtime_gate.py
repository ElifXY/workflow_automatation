#!/usr/bin/env python3
"""
Runtime gate verification:
- advanced path is blocked (503) when feature flag is off
- advanced path is reachable (auth then applies) when explicitly enabled + bootstrap
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402


def _new_client(enable_advanced: bool, bootstrap: bool) -> TestClient:
    os.environ["ENABLE_ADVANCED_FEATURES"] = "1" if enable_advanced else "0"
    os.environ["SECURITY_BASELINE_BOOTSTRAP"] = "1" if bootstrap else "0"
    import api  # noqa: WPS433,E402
    return TestClient(api.app)


def main() -> int:
    # 1) default hard block
    c1 = _new_client(enable_advanced=False, bootstrap=False)
    r1 = c1.get("/ki/chat")
    if r1.status_code != 503:
        print(f"expected 503 for locked advanced route, got {r1.status_code}: {r1.text}")
        return 1

    # Kern bleibt erreichbar (Auth, nicht Feature-Gate)
    r1b = c1.get("/mandanten")
    if r1b.status_code not in (401, 403):
        print(f"expected auth on /mandanten when gate locked, got {r1b.status_code}: {r1b.text}")
        return 1

    # 2) enabled+bootstrap => gate open; auth should answer (401 without token)
    c2 = _new_client(enable_advanced=True, bootstrap=True)
    r2 = c2.get("/ki/chat")
    if r2.status_code not in (401, 403):
        print(f"expected auth response after unlock (401/403), got {r2.status_code}: {r2.text}")
        return 1

    print("PASS: runtime feature gate lock/unlock behavior")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

