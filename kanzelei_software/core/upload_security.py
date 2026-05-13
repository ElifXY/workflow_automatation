# ============================================================
# Upload-Validierung (Portal / API) — Magic Bytes + Größe
# ============================================================
from __future__ import annotations

import os
from typing import Optional, Tuple

_ALLOWED_PREFIXES: Tuple[bytes, ...] = (
    b"%PDF",
    b"\xff\xd8\xff",
    b"\x89PNG",
    b"GIF87a",
    b"GIF89a",
    b"PK\x03\x04",  # ZIP / Office Open XML
)


def max_upload_bytes() -> int:
    mb = int(os.getenv("UPLOAD_MAX_MB", os.getenv("PORTAL_UPLOAD_MAX_MB", "25")))
    return max(1, mb) * 1024 * 1024


def validate_binary_upload(raw: bytes, *, max_bytes: Optional[int] = None) -> None:
    """Wirft ValueError wenn Größe oder Dateityp unzulässig."""
    lim = max_bytes if max_bytes is not None else max_upload_bytes()
    if len(raw) > lim:
        raise ValueError(f"Datei zu groß (max. {lim // (1024 * 1024)} MB)")
    if len(raw) < 4:
        raise ValueError("Datei zu klein oder leer")
    if not any(raw.startswith(p) for p in _ALLOWED_PREFIXES):
        raise ValueError("Dateityp nicht erlaubt (nur PDF, PNG, JPEG, GIF, ZIP/Office)")


def sanitize_filename(name: str, *, max_len: int = 180) -> str:
    n = (name or "upload").replace("\\", "_").replace("/", "_").strip()
    n = "".join(c for c in n if c.isprintable() and c not in '<>:"|?*')
    return (n or "upload")[:max_len]
