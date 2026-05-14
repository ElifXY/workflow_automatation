"""
Pydantic-/Domain-Modelle für die API.

SQLAlchemy-ORM (``Base``, ``User``, Tabelle ``users``) wird **nicht** beim Paketimport
geladen — vermeidet Abhängigkeits- und Startreihenfolge-Probleme. Nutzung::

    from backend.db.sqlalchemy_models import Base, User

Oder::

    from backend.models import User  # lazy, lädt ORM erst bei Zugriff
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.models.user import UserCreate, UserRead

__all__ = ["UserCreate", "UserRead", "Base", "User"]

if TYPE_CHECKING:
    from backend.db.sqlalchemy_models import Base
    from backend.db.sqlalchemy_models import User


def __getattr__(name: str) -> Any:
    if name in ("Base", "User"):
        from backend.db import sqlalchemy_models as _orm

        return getattr(_orm, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

