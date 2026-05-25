#!/usr/bin/env python3
"""
Installiert lokale Git-Hooks für dieses Repository.

Aktuell:
- pre-commit: führt ``scripts/repo_policy_check.py`` aus
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


PRE_COMMIT = """#!/usr/bin/env sh
set -e

# Monorepo (Git-Root über kanzelei_software): Policy nur im App-Ordner ausführen.
if [ -f kanzelei_software/scripts/repo_policy_check.py ]; then
  cd kanzelei_software
fi

if command -v py >/dev/null 2>&1; then
  py -3 scripts/repo_policy_check.py
elif command -v python3 >/dev/null 2>&1; then
  python3 scripts/repo_policy_check.py
elif command -v python >/dev/null 2>&1; then
  python scripts/repo_policy_check.py
else
  echo "ERROR: Python wurde nicht gefunden. Bitte Python installieren."
  exit 1
fi
"""


def _find_repo_root(start: Path) -> Path | None:
    cur = start.resolve()
    for p in (cur, *cur.parents):
        if (p / ".git").exists():
            return p
    return None


def main() -> int:
    start = Path(__file__).resolve().parents[1]
    repo_root = _find_repo_root(start)
    if repo_root is None:
        print("ERROR: .git Verzeichnis nicht gefunden.")
        return 2
    git_dir = repo_root / ".git"
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "pre-commit"
    hook_path.write_text(PRE_COMMIT, encoding="utf-8", newline="\n")
    try:
        current = hook_path.stat().st_mode
        hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        # Auf Windows optional; Git Bash führt Hook i. d. R. trotzdem aus.
        pass

    print(f"Installed hook: {hook_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

