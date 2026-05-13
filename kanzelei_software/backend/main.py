"""
Kanonischer FastAPI-Einstiegspunkt für Uvicorn.

Beibehaltung der bestehenden Architektur:
- ``backend.application`` erstellt die einzige FastAPI-Instanz
- ``api.py`` registriert Routen auf dieser Instanz
"""
from __future__ import annotations

from backend.application import app

__all__ = ["app"]
