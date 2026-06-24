#!/usr/bin/env python3
"""
API-Route-Audit: Auth-Whitelist (auth_guard) vs. Gateway-Whitelist vs. echte FastAPI-Routen.

Ausführung vom Projektroot:
  python scripts/api_route_audit.py
  python scripts/api_route_audit.py --markdown-out docs/ROUTE_SECURITY_AUDIT.md

Hinweis: Routen ohne explizite Auth-Dependency sind trotzdem oft durch den
auth_guard_middleware geschützt (Session oder X-API-Key). Spalte „explizite Auth-Dep“:
``get_current_user`` oder ``require_saas_master``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Iterable, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]


def _walk_routes(routes: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    for r in routes:
        children = getattr(r, "routes", None)
        if children:
            out.extend(_walk_routes(children))
        out.append(r)
    return out


def _is_get_current_user_call(call: Any, get_current_user: Any) -> bool:
    if call is None:
        return False
    if call is get_current_user:
        return True
    return getattr(call, "__name__", "") == "get_current_user"


def _is_require_saas_master_call(call: Any, require_saas_master: Any) -> bool:
    if call is None:
        return False
    if call is require_saas_master:
        return True
    return getattr(call, "__name__", "") == "require_saas_master"


def _dependant_has_auth_deps(
    dependant: Any, get_current_user: Any, require_saas_master: Any
) -> bool:
    if dependant is None:
        return False
    stack = [dependant]
    seen: Set[int] = set()
    while stack:
        d = stack.pop()
        i = id(d)
        if i in seen:
            continue
        seen.add(i)
        call = getattr(d, "call", None)
        if _is_get_current_user_call(call, get_current_user) or _is_require_saas_master_call(
            call, require_saas_master
        ):
            return True
        for sub in getattr(d, "dependencies", None) or []:
            stack.append(sub)
    return False


def _endpoint_has_explicit_auth_dep(
    route: Any, get_current_user: Any, require_saas_master: Any
) -> bool:
    dep = getattr(route, "dependant", None)
    if _dependant_has_auth_deps(dep, get_current_user, require_saas_master):
        return True
    import inspect

    try:
        sig = inspect.signature(route.endpoint)
    except (TypeError, ValueError):
        return False
    for p in sig.parameters.values():
        d = p.default
        dep_fn = getattr(d, "dependency", None)
        if dep_fn is get_current_user or dep_fn is require_saas_master:
            return True
    return False


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API-Route-Audit")
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional: Markdown-Tabelle schreiben (sonst nur stdout)",
    )
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("ENVIRONMENT", "development")

    import api as api_mod  # noqa: E402

    app = api_mod.app
    get_current_user = api_mod.get_current_user
    require_saas_master = api_mod.require_saas_master
    auth_pref = api_mod._AUTH_EXEMPT_PREFIXES
    gw_pref = api_mod._API_GATEWAY_EXEMPT_PREFIXES
    gw_exact = api_mod._API_GATEWAY_EXACT

    def auth_exempt(path: str) -> bool:
        return path == "/" or path.startswith(auth_pref)

    def gateway_exempt(path: str) -> bool:
        return path in gw_exact or path.startswith(gw_pref)

    rows: List[Tuple[str, str, str, str, str]] = []
    for route in _walk_routes(app.routes):
        cls = route.__class__.__name__
        if cls != "APIRoute":
            continue
        methods = ",".join(sorted(route.methods - {"HEAD"})) if route.methods else ""
        path = route.path or ""
        aex = "ja" if auth_exempt(path) else "nein"
        gex = "ja" if gateway_exempt(path) else "nein"
        udep = (
            "ja"
            if _endpoint_has_explicit_auth_dep(route, get_current_user, require_saas_master)
            else "nein"
        )
        rows.append((methods, path, aex, gex, udep))

    rows.sort(key=lambda x: (x[1], x[0]))

    lines = [
        f"# API Route Audit ({len(rows)} HTTP-Routen)",
        "",
        "| Methods | Path | auth_guard exempt | gateway exempt | explizite Auth-Dep (User/SaaS) |",
        "|---|---|---|---|---|",
    ]
    for m, p, a, g, u in rows:
        lines.append(f"| `{m}` | `{p}` | {a} | {g} | {u} |")

    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(text, encoding="utf-8")
        print(f"Written: {args.markdown_out}", file=sys.stderr)

    # Kurz-Summary
    no_auth_mw = [r for r in rows if r[2] == "nein"]
    no_gw = [r for r in rows if r[3] == "nein"]
    no_expl = [r for r in rows if r[4] == "nein"]
    print(
        f"\n---\nZusammenfassung: {len(no_auth_mw)} Routen → Auth-Middleware; "
        f"{len(no_gw)} Routen → API_GATEWAY_KEY bei aktivem Gateway; "
        f"{len(no_expl)} ohne explizite User-/SaaS-Dependency (nur Middleware / öffentlich).\n",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
