"""Kompatibilität: bitte ``python scripts/api_route_audit.py`` nutzen."""
from __future__ import annotations

import sys
from pathlib import Path

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "api_route_audit", Path(__file__).resolve().parent / "api_route_audit.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
sys.exit(_mod.main())
