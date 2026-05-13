"""
Domain-Router für die FastAPI-``app``.

Die schwere Geschäftslogik und die meisten Pydantic-Modelle liegen weiter in ``api.py``;
hier werden lesbar gruppierte Endpunkte an dieselbe App „angehängt“ (kein zweiter Uvicorn-Prozess).
"""

from backend.routes.register import mount_split_routers

__all__ = ["mount_split_routers"]
