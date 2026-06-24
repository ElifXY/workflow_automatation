from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write_report(lines: list[str]) -> None:
    out = Path("docs/TENANT_ENFORCEMENT_AUDIT.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    os.environ.setdefault("ENABLE_ADVANCED_FEATURES", "1")
    os.environ.setdefault("SECURITY_BASELINE_BOOTSTRAP", "1")
    lines: list[str] = ["# Tenant Enforcement Audit", ""]
    ok = True

    api_path = Path("api.py")
    if not api_path.exists():
        print("api.py not found")
        return 2

    src = api_path.read_text(encoding="utf-8")
    required_tokens = [
        "auth_guard_middleware",
        "_AUTH_EXEMPT_PREFIXES",
        "X-Organization-Id",
        "X-Kanzlei-Id",
        "Cross-tenant Payload blockiert",
        "Cross-tenant Query blockiert",
        "Cross-tenant Header blockiert",
    ]
    lines.append("## Static Checks")
    for token in required_tokens:
        found = token in src
        lines.append(f"- `{token}`: {'OK' if found else 'MISSING'}")
        ok = ok and found

    lines.append("")
    lines.append("## Runtime Checks")
    try:
        from fastapi.testclient import TestClient
        import api
        client = TestClient(api.app)

        # 1) Auth required with real get_current_user
        resp = client.get("/mandanten")
        passed = resp.status_code == 401
        try:
            body = resp.json()
        except Exception:
            body = {}
        lines.append(
            f"- `auth_required`: status={resp.status_code}, expected=401, "
            f"result={'OK' if passed else 'FAIL'}, error={body.get('error')}"
        )
        ok = ok and passed

        # 2) Tenant enforcement with patched authenticated user
        original_get_current_user = api.get_current_user
        api.get_current_user = lambda **kwargs: {  # type: ignore[assignment]
            "benutzername": "audit",
            "rolle": "admin",
            "kanzlei_id": "default",
            "tenant_id": "default",
        }
        try:
            tests = [
                (
                    "header_mismatch",
                    lambda: client.get("/mandanten", headers={"X-Organization-Id": "evil"}),
                    403,
                ),
                (
                    "query_mismatch",
                    lambda: client.get("/mandanten?kanzlei_id=evil"),
                    403,
                ),
                (
                    "payload_mismatch_nested",
                    lambda: client.put(
                        "/settings",
                        json={"nested": {"organization_id": "evil"}, "key": "x", "wert": "y"},
                    ),
                    403,
                ),
            ]

            for name, fn, expected in tests:
                resp = fn()
                passed = resp.status_code == expected
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                lines.append(
                    f"- `{name}`: status={resp.status_code}, expected={expected}, "
                    f"result={'OK' if passed else 'FAIL'}, error={body.get('error')}"
                )
                ok = ok and passed
        finally:
            api.get_current_user = original_get_current_user
    except Exception as exc:
        ok = False
        lines.append(f"- runtime checks failed to execute: {exc}")

    _write_report(lines)
    print("Wrote docs/TENANT_ENFORCEMENT_AUDIT.md")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

