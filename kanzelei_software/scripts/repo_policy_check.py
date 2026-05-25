"""
Repository Policy Check

Verhindert Rückfälle in:
- venv-Ordner im Projekt
- produktive JSON-Daten im data/-Pfad
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import re


FORBIDDEN_DIR_PREFIXES = [".venv", "venv"]
ALLOWED_DATA_JSON = {"README.json"}
ALLOWED_DATA_FILES = {
    "kanzlei.db",
    "kanzlei.db-shm",
    "kanzlei.db-wal",
    "ml_buchungen.db",
    "api.log",
}
EXPLICIT_FORBIDDEN_RUNTIME_JSON = {
    "data/mandanten.json",
    "data/settings.json",
    "data/kanzlei_daten.json",
    "data/logs.json",
    "data/emails.json",
}
ALLOWED_JSON_PATHS = {
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/public/manifest.json",
    "artifacts/security_baseline_pass.json",
}
SOURCE_JSON_PATTERN = re.compile(r"(open\([^\n]*\.json|json\.dump\()")
SOURCE_DATA_FILE_PATTERN = re.compile(r"open\([^\n]*data[\\/]")
SOURCE_ALLOWED_FILES = {
    "scripts/repo_policy_check.py",
}
FORBIDDEN_IMPORTS = {
    "from core.auth import": {
        "allow": {
            "backend/auth.py",
            "core/auth.py",
            "core/auth_postgres.py",
        },
        "message": "Use backend.auth facade instead of direct core.auth import",
    },
    "import core.auth": {
        "allow": {
            "backend/auth.py",
            "core/auth.py",
            "core/auth_postgres.py",
        },
        "message": "Use backend.auth facade instead of direct core.auth import",
    },
    "from core.deps import": {
        "allow": {
            "core/deps_old.py",
        },
        "message": "Use backend.deps as single dependency source",
    },
    "from core.jwt_tokens import": {
        "allow": {
            "backend/auth.py",
            "core/jwt_tokens.py",
        },
        "message": "Use backend.auth for JWT helpers",
    },
    "import core.jwt_tokens": {
        "allow": {
            "backend/auth.py",
            "core/jwt_tokens.py",
        },
        "message": "Use backend.auth for JWT helpers",
    },
    "from core.jwt_config import": {
        "allow": {
            "backend/auth.py",
            "core/jwt_config.py",
            "core/jwt_tokens.py",
        },
        "message": "Use backend.auth for JWT configuration",
    },
    "import core.jwt_config": {
        "allow": {
            "core/jwt_config.py",
            "core/jwt_tokens.py",
        },
        "message": "Use backend.auth for JWT configuration",
    },
    "from core.auth_postgres import": {
        "allow": {
            "core/auth.py",
            "core/auth_postgres.py",
            "scripts/reset_password.py",
        },
        "message": "Use backend.auth facade instead of direct core.auth_postgres import",
    },
    "import core.auth_postgres": {
        "allow": {
            "core/auth.py",
            "core/auth_postgres.py",
            "scripts/reset_password.py",
        },
        "message": "Use backend.auth facade instead of direct core.auth_postgres import",
    },
}


def main() -> int:
    root = Path(".").resolve()
    problems: list[str] = []

    for entry in root.iterdir():
        if entry.is_dir() and any(entry.name.lower().startswith(p) for p in FORBIDDEN_DIR_PREFIXES):
            problems.append(f"Forbidden virtualenv directory: {entry.name}")

    data_dir = root / "data"
    if data_dir.exists():
        for path in data_dir.rglob("*"):
            rel_data = path.relative_to(root).as_posix()
            if rel_data.startswith("data/uploads/"):
                continue
            if path.name == "scheduler.log":
                continue
            if path.is_file() and path.name not in ALLOWED_DATA_FILES and path.name not in ALLOWED_DATA_JSON:
                problems.append(f"Forbidden file in data/: {rel_data}")
        for path in data_dir.rglob("*.json"):
            if path.name not in ALLOWED_DATA_JSON:
                problems.append(f"Forbidden JSON runtime data: {path.relative_to(root)}")

    for path in root.rglob("*.json"):
        rel = path.relative_to(root).as_posix()
        if "/node_modules/" in f"/{rel}" or rel.startswith("node_modules/"):
            continue
        if rel.startswith(".cursor/") or "/.cursor/" in f"/{rel}/":
            continue
        if rel.startswith("frontend/build/"):
            continue
        if rel in EXPLICIT_FORBIDDEN_RUNTIME_JSON or rel.startswith("data/backups/"):
            problems.append(f"Explicitly forbidden runtime JSON: {rel}")
            continue
        if rel.startswith("data/"):
            continue  # already checked above
        if rel not in ALLOWED_JSON_PATHS:
            problems.append(f"Forbidden JSON file in repo: {rel}")

    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in SOURCE_ALLOWED_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if SOURCE_JSON_PATTERN.search(text):
            problems.append(f"Forbidden JSON persistence pattern in source: {rel}")
        if SOURCE_DATA_FILE_PATTERN.search(text):
            problems.append(f"Forbidden file access to data/ in source: {rel}")
        for needle, cfg in FORBIDDEN_IMPORTS.items():
            if needle in text and rel not in cfg["allow"]:
                problems.append(f"{cfg['message']}: {rel} ({needle})")

    if problems:
        print("Repository policy violations found:")
        for p in problems:
            print(f"- {p}")
        return 2

    # Schwere Gates nur in CI / bei explizitem Full-Check (lokaler Pre-Commit ohne Postgres).
    run_extended = (os.getenv("CI") or "").lower() in ("1", "true", "yes") or (
        os.getenv("KANZLEI_POLICY_FULL") or ""
    ).strip() == "1"
    if not run_extended:
        print("Repository policy check passed (static only; set CI=1 or KANZLEI_POLICY_FULL=1 for full gates).")
        return 0

    # Tenant Guard Policy (separates Gate)
    tenant_check = Path("scripts/tenant_guard_policy_check.py")
    if tenant_check.exists():
        proc = subprocess.run(
            [sys.executable, str(tenant_check)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout.strip())
            print(proc.stderr.strip())
            return proc.returncode

    ast_check = Path("scripts/tenant_ast_policy_check.py")
    if ast_check.exists():
        proc = subprocess.run(
            [sys.executable, str(ast_check)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout.strip())
            print(proc.stderr.strip())
            return proc.returncode

    security_gate = Path("scripts/security_baseline_gate.py")
    if security_gate.exists():
        proc = subprocess.run(
            [sys.executable, str(security_gate)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout.strip())
            print(proc.stderr.strip())
            return proc.returncode

    feature_gate = Path("scripts/feature_activation_gate.py")
    if feature_gate.exists():
        proc = subprocess.run(
            [sys.executable, str(feature_gate)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout.strip())
            print(proc.stderr.strip())
            return proc.returncode

    print("Repository policy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
