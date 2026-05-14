"""
SQLAlchemy-ORM: Tabelle ``users`` (parallel zur bestehenden Core-Auth ``benutzer``).

Hinweis: Das Paket ``backend/models/`` belegt den Importnamen ``backend.models`` —
ein separates ``backend/models.py`` ist in Python nicht neben dem Paket möglich.
Dieses Modul ist die kanonische ORM-Definition; ``init_postgres_sqlalchemy`` legt die Tabelle an.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, func, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative Base für optionale SQLAlchemy-Tabellen."""


class User(Base):
    """
    High-End SaaS-User (ORM-Schicht).

    Produktions-Login nutzt weiter ``core.auth`` / Tabelle ``benutzer``; diese Tabelle
    ist für Migrationen, Reporting oder zukünftige Vereinheitlichung gedacht.

    ``tenant_id`` entspricht der Mandanten-Kennung (wie ``kanzlei_id`` / UUID-String).
    Deprecated / nie wieder: ``tenant_id`` als Integer — bricht Multi-Tenant-UUIDs.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    tenant_id = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=False, server_default=text("'user'"), default="user")
    is_active = Column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
