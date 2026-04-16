from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine

from db.sqlalchemy_models import Base


def main() -> int:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("DATABASE_URL fehlt.")
        return 2
    if not database_url.startswith("postgresql://"):
        print("DATABASE_URL muss mit postgresql:// beginnen.")
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    print("SQLAlchemy schema created/verified for PostgreSQL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
