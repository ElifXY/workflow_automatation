"""
API-Request-Schemas (Tutorial-Vorlagen werden hier produktionsreif ausgeführt).

- Kein hartes ``EmailStr`` (schlanke venvs ohne ``email-validator``).
- Mandanten-Bindung passiert **nicht** im Body, sondern ausschließlich über ``require_admin`` → ``tenant_id``.
"""
from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.IGNORECASE)

# Sichtbare API-Rollen; intern mappt ``core.auth.erstelle_benutzer`` weiter (z. B. user → assistent).
_CREATE_USER_ROLES: Final[frozenset[str]] = frozenset(
    {"user", "mitarbeiter", "assistent", "steuerberater", "admin"}
)


class CreateUserRequest(BaseModel):
    """
    Admin legt einen Mitarbeiter für **dieselbe** Kanzlei an (``kanzlei_id`` kommt nur aus dem Token).
    """

    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=500)
    role: str = Field(
        "user",
        description="user | mitarbeiter | assistent | steuerberater | admin",
    )

    @field_validator("email")
    @classmethod
    def _email_norm(cls, v: str) -> str:
        s = (v or "").strip().lower()
        if not _EMAIL_RE.match(s):
            raise ValueError("invalid email")
        return s

    @field_validator("role")
    @classmethod
    def _role_norm(cls, v: str) -> str:
        r = (v or "user").strip().lower()
        if r not in _CREATE_USER_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(_CREATE_USER_ROLES))}")
        return r
