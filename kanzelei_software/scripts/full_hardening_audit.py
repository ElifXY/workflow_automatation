from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def check(condition: bool, ok: str, fail: str, out: list[str]) -> bool:
    if condition:
        out.append(f"[OK] {ok}")
        return True
    out.append(f"[FAIL] {fail}")
    return False


def main() -> int:
    out: list[str] = []
    root = Path(".").resolve()
    success = True

    # 1) venv cleanup
    venv_dirs = [p for p in root.iterdir() if p.is_dir() and (p.name.startswith(".venv") or p.name.startswith("venv"))]
    success &= check(len(venv_dirs) == 0, "No venv directories in project root", f"Found venv dirs: {[p.name for p in venv_dirs]}", out)

    # 2) no json runtime in data
    data_dir = root / "data"
    data_json = list(data_dir.rglob("*.json")) if data_dir.exists() else []
    success &= check(len(data_json) == 0, "No JSON runtime files in data/", f"Found JSON in data/: {[str(p.relative_to(root)) for p in data_json]}", out)

    # 3) backend structure
    required_paths = [
        "backend/api.py",
        "backend/services/__init__.py",
        "backend/models/sqlalchemy_models.py",
        "backend/db/init_postgres.py",
    ]
    for rel in required_paths:
        p = root / rel
        success &= check(p.exists(), f"{rel} exists", f"Missing required path: {rel}", out)

    # 4) SQLAlchemy minimum model file check
    model_file = root / "db" / "sqlalchemy_models.py"
    if model_file.exists():
        text = model_file.read_text(encoding="utf-8", errors="ignore")
        for token in ['__tablename__ = "organizations"', '__tablename__ = "users"', '__tablename__ = "mandanten"', '__tablename__ = "workflows"', '__tablename__ = "logs"']:
            success &= check(token in text, f"Model contains {token}", f"Model missing token: {token}", out)
    else:
        out.append("[FAIL] db/sqlalchemy_models.py missing")
        success = False

    # 5) sqlite table presence (local fallback schema sanity)
    db_file = root / "data" / "kanzlei.db"
    if db_file.exists():
        try:
            conn = sqlite3.connect(str(db_file))
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            conn.close()
            for t in ["kanzleien", "benutzer", "mandanten", "aufgaben", "audit_log"]:
                success &= check(t in tables, f"SQLite table {t} exists", f"SQLite table missing: {t}", out)
        except Exception as exc:
            out.append(f"[FAIL] SQLite inspect error: {exc}")
            success = False
    else:
        out.append("[FAIL] data/kanzlei.db missing")
        success = False

    print("=== FULL HARDENING AUDIT ===")
    for line in out:
        print(line)
    return 0 if success else 2


if __name__ == "__main__":
    sys.exit(main())
