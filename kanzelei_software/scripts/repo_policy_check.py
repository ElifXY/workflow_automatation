"""
Repository Policy Check

Verhindert Rückfälle in:
- venv-Ordner im Projekt
- produktive JSON-Daten im data/-Pfad
"""

from __future__ import annotations

import os
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
}
SOURCE_JSON_PATTERN = re.compile(r"(open\([^\n]*\.json|json\.dump\()")
SOURCE_DATA_FILE_PATTERN = re.compile(r"open\([^\n]*data[\\/]")
SOURCE_ALLOWED_FILES = {
    "scripts/repo_policy_check.py",
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
            if path.is_file() and path.name not in ALLOWED_DATA_FILES and path.name not in ALLOWED_DATA_JSON:
                problems.append(f"Forbidden file in data/: {path.relative_to(root)}")
        for path in data_dir.rglob("*.json"):
            if path.name not in ALLOWED_DATA_JSON:
                problems.append(f"Forbidden JSON runtime data: {path.relative_to(root)}")

    for path in root.rglob("*.json"):
        rel = path.relative_to(root).as_posix()
        if "/node_modules/" in f"/{rel}" or rel.startswith("node_modules/"):
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

    if problems:
        print("Repository policy violations found:")
        for p in problems:
            print(f"- {p}")
        return 2

    print("Repository policy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
