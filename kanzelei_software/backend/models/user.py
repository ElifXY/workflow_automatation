"""
Kanonisches Benutzer-Modell (API-Schicht).

Persistenz: Tabelle ``benutzer``. ``kanzlei_id`` = Tenant für Mandantenisolation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

# Kein EmailStr: vermeidet harten Import-Fehler ohne ``email-validator`` (schlanke venvs).
_EMAIL_SIMPLE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRead(BaseModel):
    """Antwort ohne Passwort — für /auth/me und Admin-Listen."""

    id: int
    benutzername: str
    email: Optional[str] = None
    kanzlei_id: str = Field(..., description="Tenant / Kanzlei")
    rolle: str
    aktiv: bool = True
    is_admin: bool = False

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "UserRead":
        r = dict(row)
        rid = r.get("id")
        rolle = (r.get("rolle") or "assistent").lower()
        return cls(
            id=int(rid) if rid is not None else 0,
            benutzername=r.get("benutzername") or "",
            email=(r.get("email") or None) or None,
            kanzlei_id=r.get("kanzlei_id") or "default",
            rolle=r.get("rolle") or "assistent",
            aktiv=bool(int(r.get("aktiv", 1) or 0)),
            is_admin=rolle == "admin",
        )

    @property
    def tenant_id(self) -> str:
        return self.kanzlei_id

    @property
    def role(self) -> str:
        return self.rolle

    @property
    def is_active(self) -> bool:
        return self.aktiv


class UserCreate(BaseModel):
    benutzername: str
    password: str = Field(..., min_length=8)
    email: Optional[str] = Field(None, max_length=254)
    kanzlei_id: str = "default"
    rolle: str = "assistent"

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        s = str(v).strip().lower()
        if not _EMAIL_SIMPLE.match(s):
            raise ValueError("invalid email")
        return s
