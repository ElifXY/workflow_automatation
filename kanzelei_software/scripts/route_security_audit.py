from __future__ import annotations

import re
import sys
from pathlib import Path


API_FILE = Path("api.py")
OUT_FILE = Path("docs/ROUTE_SECURITY_AUDIT.md")

PUBLIC_HINTS = (
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/registrieren",
    "/auth/setup-status",
    "/billing/stripe/webhook",
    "/api/v1/health",
    "/api/v1/meta",
    "/api/v1/introduction",
)


def main() -> int:
    if not API_FILE.exists():
        print("api.py not found")
        return 2

    src = API_FILE.read_text(encoding="utf-8")
    route_pattern = re.compile(r'@app\.(get|post|put|patch|delete)\("([^"]+)"')
    routes = route_pattern.findall(src)

    lines = [
        "# Route Security Audit",
        "",
        "| Method | Path | Classification |",
        "|---|---|---|",
    ]
    for method, path in routes:
        classification = "public" if any(path.startswith(p) for p in PUBLIC_HINTS) else "auth-guarded"
        lines.append(f"| `{method.upper()}` | `{path}` | `{classification}` |")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_FILE} with {len(routes)} routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
