"""Einheitliches Parsen von Aufgaben-Fristen (ISO, DE, EN)."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional


def parse_frist(frist: Any) -> Optional[date]:
    if frist is None:
        return None
    s = str(frist).strip()
    if not s:
        return None
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 else s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def tage_bis_frist(frist: Any, *, heute: Optional[date] = None) -> Optional[int]:
    d = parse_frist(frist)
    if d is None:
        return None
    ref = heute or datetime.now().date()
    return (d - ref).days
