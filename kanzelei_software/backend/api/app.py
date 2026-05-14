"""Alternativer Uvicorn-Pfad: ``uvicorn backend.api.app:app`` — dieselbe Instanz wie ``backend.api:app``."""
from __future__ import annotations

from backend.application import app  # noqa: F401

__all__ = ["app"]
