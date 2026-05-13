"""Einheitliche Auswertung von Aufgaben.erledigt (SQLite 0/1, bool, Strings)."""
from __future__ import annotations

from typing import Any, Mapping


def aufgabe_ist_erledigt(a: Mapping[str, Any]) -> bool:
    """True, wenn die Aufgabe als erledigt gilt (nicht mehr in offenen Listen / Heute)."""
    e = a.get("erledigt")
    if e is None or e is False:
        return False
    if e is True:
        return True
    if isinstance(e, (int, float)):
        return e != 0
    if isinstance(e, str):
        s = e.strip().lower()
        if s in ("", "0", "false", "nein", "no", "none", "null"):
            return False
        if s in ("1", "true", "yes", "ja"):
            return True
        return False
    return bool(e)


def aufgabe_ist_offen(a: Mapping[str, Any]) -> bool:
    return not aufgabe_ist_erledigt(a)
