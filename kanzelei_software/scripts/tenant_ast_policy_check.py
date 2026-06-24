#!/usr/bin/env python3
"""
AST-basierter Tenant/Auth Policy Check für ``api.py``.

Blockiert FastAPI-Endpunkte, die:
- keinen ``Depends(get_current_user)`` / ``Depends(require_admin)`` / ``Depends(require_saas_master)`` nutzen
- und nicht explizit auf der Public-Whitelist stehen.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_FILE = ROOT / "api.py"

ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head"}
AUTH_DEP_NAMES = {"get_current_user", "require_admin", "require_saas_master"}
AUTH_FACTORY_NAMES = {"require_permission"}

# Public endpoints that are intentionally unauthenticated.
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/health",
    "/ready",
    "/api/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/login",
    "/api/login",
    "/api/auth/login",
    "/register",
    "/api/register",
    "/auth/setup-status",
    "/auth/refresh",
    "/auth/registrieren",
    "/api/auth/registrieren",
    "/api/auth/setup-status",
    "/billing/stripe/webhook",
    "/billing/stripe/config",
    "/api/v1/health",
    "/api/v1/meta",
    "/api/v1/introduction",
    "/api/v1/webhooks/verify-example",
}

# Bestehende Legacy-Endpunkte ohne explizite Depends(get_current_user).
# Guardrail: diese Liste darf nur kleiner werden; neue Verstöße failen.
BASELINE_ALLOWED_FUNCTIONS = {
    "auth_password_forgot",
    "auth_password_reset",
    "auth_email_verify",
    "auth_email_resend",
    "auth_oauth_start",
    "auth_oauth_callback",
    "auth_oauth_exchange",
    "api_auth_refresh_alias",
    "tenant_features_put",
}


def _is_depends_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Depends"


def _depends_target_name(node: ast.AST) -> str | None:
    if not _is_depends_call(node) or not node.args:
        return None
    target = node.args[0]
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Call) and isinstance(target.func, ast.Name):
        return target.func.id
    return None


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    router_ctor_names = {"APIRouter"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "fastapi":
            continue
        for alias in node.names:
            if alias.name == "APIRouter":
                router_ctor_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        is_router_ctor = False
        if isinstance(call.func, ast.Name) and call.func.id in router_ctor_names:
            is_router_ctor = True
        if isinstance(call.func, ast.Attribute) and call.func.attr == "APIRouter":
            is_router_ctor = True
        if not is_router_ctor:
            continue
        prefix = ""
        for kw in call.keywords or []:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value
                break
        if not prefix:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _join_route_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def _extract_paths_from_decorator(dec: ast.AST, prefixes: dict[str, str]) -> set[str]:
    paths: set[str] = set()
    if not isinstance(dec, ast.Call):
        return paths
    func = dec.func
    if not (isinstance(func, ast.Attribute) and func.attr in ROUTE_DECORATORS):
        return paths
    base_prefix = ""
    if isinstance(func.value, ast.Name):
        base_prefix = prefixes.get(func.value.id, "")
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        paths.add(_join_route_path(base_prefix, dec.args[0].value))
    for kw in dec.keywords or []:
        if kw.arg == "path" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            paths.add(_join_route_path(base_prefix, kw.value.value))
    return paths


def _function_has_auth_dep(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for arg in list(fn.args.args) + list(fn.args.kwonlyargs):
        default = None
        # map defaults to args (positional only)
        if arg in fn.args.args:
            idx = fn.args.args.index(arg)
            n_defaults = len(fn.args.defaults)
            first_default_idx = len(fn.args.args) - n_defaults
            if idx >= first_default_idx:
                default = fn.args.defaults[idx - first_default_idx]
        else:
            kw_idx = fn.args.kwonlyargs.index(arg)
            if kw_idx < len(fn.args.kw_defaults):
                default = fn.args.kw_defaults[kw_idx]
        name = _depends_target_name(default) if default is not None else None
        if name in AUTH_DEP_NAMES or name in AUTH_FACTORY_NAMES:
            return True
    return False


def main() -> int:
    if not API_FILE.exists():
        print("tenant-ast-policy: api.py not found")
        return 2
    src = API_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(API_FILE))
    router_prefixes = _router_prefixes(tree)
    problems: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_paths: set[str] = set()
        for dec in node.decorator_list:
            route_paths |= _extract_paths_from_decorator(dec, router_prefixes)
        if not route_paths:
            continue
        non_public = [p for p in route_paths if p not in PUBLIC_PATHS]
        if not non_public:
            continue
        if not _function_has_auth_dep(node):
            if node.name in BASELINE_ALLOWED_FUNCTIONS:
                continue
            problems.append(
                f"{node.name} (line {node.lineno}) missing explicit auth dependency for paths: {', '.join(sorted(non_public))}"
            )

    if problems:
        print("Tenant AST policy violations found:")
        for p in problems:
            print(f"- {p}")
        return 2

    print("Tenant AST policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

