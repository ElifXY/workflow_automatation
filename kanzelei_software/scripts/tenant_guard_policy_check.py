#!/usr/bin/env python3
"""
Tenant Guard Policy Check

Blockiert Rückfälle bei Mandanten-Isolation:
- keine manuelle tenant_id-Extraktion aus ``admin.get(...)`` in API-Userpfaden
- ``/api/users`` Endpunkte sollen ``tenant_id_from_user(...)`` nutzen
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_FILE = ROOT / "api.py"

BAD_ADMIN_TENANT_EXTRACTION = re.compile(
    r"admin\.get\(\"tenant_id\"\)\s*or\s*admin\.get\(\"kanzlei_id\"\)"
)


def main() -> int:
    if not API_FILE.exists():
        print("tenant-guard: api.py not found")
        return 2
    src = API_FILE.read_text(encoding="utf-8")
    problems: list[str] = []

    if "from backend.tenant import tenant_id_from_user" not in src:
        problems.append("api.py must import tenant_id_from_user from backend.tenant")

    for m in BAD_ADMIN_TENANT_EXTRACTION.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        problems.append(
            f"Manual admin tenant extraction found in api.py:{line}; use tenant_id_from_user(admin)"
        )

    # Hard requirement for critical endpoint block in /api/users domain.
    critical_user_fns = (
        "api_users_list",
        "api_users_create",
        "api_users_invites_list",
        "api_users_create_invite",
        "api_users_invite_revoke",
        "api_users_patch_role",
        "api_users_delete",
    )
    for fn in critical_user_fns:
        marker = f"def {fn}("
        if marker not in src:
            continue
        snippet_start = src.find(marker)
        next_def = src.find("\ndef ", snippet_start + len(marker))
        snippet = src[snippet_start: next_def if next_def != -1 else len(src)]
        if "tenant_id_from_user(admin)" not in snippet:
            problems.append(f"{fn} must derive tenant via tenant_id_from_user(admin)")

    if problems:
        print("Tenant guard policy violations found:")
        for p in problems:
            print(f"- {p}")
        return 2

    print("Tenant guard policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

