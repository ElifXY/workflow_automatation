"""Re-Export ORM (Tabelle ``users``) aus ``backend.db.sqlalchemy_models``."""
from __future__ import annotations

from backend.db.sqlalchemy_models import Base, User  # noqa: F401

__all__ = ["Base", "User"]
