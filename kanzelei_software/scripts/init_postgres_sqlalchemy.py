from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.db.sqlalchemy_models import Base  # noqa: E402


def main() -> int:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("DATABASE_URL fehlt.")
        return 2
    if not database_url.startswith("postgresql://"):
        print("DATABASE_URL muss mit postgresql:// beginnen.")
        return 2

    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        Base.metadata.create_all(engine)
    except Exception as e:
        print(f"SQLAlchemy create_all fehlgeschlagen: {e}")
        return 1
    print("SQLAlchemy schema created/verified for PostgreSQL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
