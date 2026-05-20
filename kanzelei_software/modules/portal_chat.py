# ============================================================
# Portal-Chat — einheitlicher Verlauf (Nachrichten, Aufgaben,
# Dokument-/Unterschrift-Anfragen, Uploads)
# ============================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.aufgabe_erledigt import aufgabe_ist_erledigt

CHAT_TYPEN = frozenset({
    "text",
    "aufgabe",
    "dokument_anfrage",
    "unterschrift_anfrage",
    "upload",
    "system",
    "aufgabe_status",
    "unterschrift_status",
    "dokument_status",
})

_LEGACY_KOMM_TYPEN = frozenset({
    "portal_nachricht",
    "kanzlei_antwort",
    "portal_upload",
    "dokument_unterschrieben",
    "unterschrift_anfrage",
    "unterschrift_abgelehnt",
    "freigabe_erteilt",
})


def _now() -> str:
    return datetime.now().isoformat()


def _msg_id() -> str:
    return str(uuid.uuid4())


def append_chat(
    store,
    mandant: str,
    typ: str,
    text: str,
    sender: str,
    *,
    refs: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Neue Chat-Zeile speichern."""
    if typ not in CHAT_TYPEN:
        typ = "text"
    mid = _msg_id()
    payload = {
        "id": mid,
        "mandant": mandant,
        "typ": typ,
        "sender": sender,
        "text": (text or "").strip(),
        "zeit": _now(),
        "refs": dict(refs or {}),
        "meta": dict(meta or {}),
    }
    if not store.portal_speichern("chat", mid, mandant, payload):
        raise RuntimeError("Chat-Nachricht konnte nicht gespeichert werden")
    return payload


def list_chat(
    store,
    mandant: str,
    *,
    limit: int = 200,
    seit_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    ensure_chat_migrated(store, mandant)
    rows = sorted(
        store.portal_liste("chat", mandant=mandant),
        key=lambda x: x.get("zeit") or x.get("erstellt_am") or "",
    )
    if seit_id:
        ids = [r.get("id") for r in rows]
        if seit_id in ids:
            rows = rows[ids.index(seit_id) + 1 :]
    enriched = [_enrich_message(store, mandant, dict(r)) for r in rows[-limit:]]
    return enriched


def get_chat_message(store, mandant: str, msg_id: str) -> Optional[Dict[str, Any]]:
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant:
        return None
    return _enrich_message(store, mandant, dict(row))


def update_chat_meta(store, mandant: str, msg_id: str, meta_patch: Dict[str, Any]) -> bool:
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant:
        return False
    meta = dict(row.get("meta") or {})
    meta.update(meta_patch)
    row["meta"] = meta
    return store.portal_speichern("chat", msg_id, mandant, row)


def ensure_chat_migrated(store, mandant: str) -> None:
    """Einmalig alte Kommunikationseinträge in den Chat-Verlauf übernehmen."""
    if store.portal_liste("chat", mandant=mandant):
        return
    komm = store.hole_kommunikation(mandant) or []
    for k in komm:
        typ = k.get("typ") or "text"
        if typ not in _LEGACY_KOMM_TYPEN:
            continue
        sender = "kanzlei" if typ in ("kanzlei_antwort", "unterschrift_anfrage") or k.get("richtung") == "ausgehend" else "mandant"
        chat_typ = "text"
        refs: Dict[str, Any] = {}
        if typ == "portal_upload":
            chat_typ = "upload"
        elif typ in ("dokument_unterschrieben", "unterschrift_abgelehnt"):
            chat_typ = "unterschrift_status"
        elif typ == "unterschrift_anfrage":
            chat_typ = "unterschrift_anfrage"
        append_chat(
            store,
            mandant,
            chat_typ,
            k.get("text") or "",
            sender,
            refs=refs,
            meta={"migriert": True, "legacy_typ": typ},
        )


def _enrich_message(store, mandant: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Live-Status für Aufgaben/Unterschriften anreichern."""
    refs = dict(row.get("refs") or {})
    meta = dict(row.get("meta") or {})
    typ = row.get("typ") or "text"

    if typ == "aufgabe" and refs.get("aufgabe_id"):
        aid = refs["aufgabe_id"]
        aufgaben = store.hole_fristen()
        a = aufgaben.get(aid) if isinstance(aufgaben, dict) else None
        if a and a.get("mandant") == mandant:
            meta["aufgabe_erledigt"] = aufgabe_ist_erledigt(a)
            meta["aufgabe_frist"] = a.get("frist")
            meta["aufgabe_beschreibung"] = a.get("beschreibung")

    if typ == "unterschrift_anfrage" and refs.get("unterschrift_id"):
        uid = refs["unterschrift_id"]
        u = store.portal_holen("unterschrift", uid) or {}
        if u:
            meta["unterschrift_status"] = u.get("status")
            meta["dokumentname"] = u.get("dokumentname")

    if typ == "dokument_anfrage":
        m = store.hole_mandanten().get(mandant, {}) or {}
        fehlend = list(m.get("fehlende_dokumente_liste") or [])
        doc = refs.get("dokument_name") or meta.get("dokument_name")
        meta["dokument_offen"] = bool(doc and any(doc.lower() in d.lower() or d.lower() in doc.lower() for d in fehlend))

    row["refs"] = refs
    row["meta"] = meta
    return row


def chat_text_nachricht(store, mandant: str, text: str, sender: str) -> Dict[str, Any]:
    return append_chat(store, mandant, "text", text, sender)


def chat_aufgabe(
    store,
    mandant: str,
    aufgabe_id: str,
    beschreibung: str,
    frist: str,
    *,
    hinweis: str = "",
) -> Dict[str, Any]:
    return append_chat(
        store,
        mandant,
        "aufgabe",
        hinweis or f"Aufgabe: {beschreibung}",
        "kanzlei",
        refs={"aufgabe_id": aufgabe_id},
        meta={
            "aufgabe_beschreibung": beschreibung,
            "aufgabe_frist": frist,
            "aufgabe_erledigt": False,
        },
    )


def chat_dokument_anfrage(
    store,
    mandant: str,
    dokument_name: str,
    beschreibung: str = "",
    frist: str = "",
) -> Dict[str, Any]:
    return append_chat(
        store,
        mandant,
        "dokument_anfrage",
        beschreibung or f"Bitte reichen Sie ein: {dokument_name}",
        "kanzlei",
        refs={"dokument_name": dokument_name},
        meta={"dokument_name": dokument_name, "frist": frist, "dokument_offen": True},
    )


def chat_unterschrift_anfrage(
    store,
    mandant: str,
    unterschrift_id: str,
    dokumentname: str,
    betreff: str,
    hinweis: str = "",
) -> Dict[str, Any]:
    return append_chat(
        store,
        mandant,
        "unterschrift_anfrage",
        hinweis or betreff or f"Unterschrift: {dokumentname}",
        "kanzlei",
        refs={"unterschrift_id": unterschrift_id},
        meta={"dokumentname": dokumentname, "unterschrift_status": "ausstehend"},
    )


def chat_upload(
    store,
    mandant: str,
    upload_id: str,
    dateiname: str,
    groesse_kb: float,
    sender: str = "mandant",
) -> Dict[str, Any]:
    von = "kanzlei" if sender == "kanzlei" else "mandant"
    label = "Kanzlei hat Dokument bereitgestellt" if von == "kanzlei" else "Dokument hochgeladen"
    return append_chat(
        store,
        mandant,
        "upload",
        f"{label}: {dateiname}",
        von,
        refs={"upload_id": upload_id},
        meta={"dateiname": dateiname, "groesse_kb": groesse_kb},
    )


def chat_system(store, mandant: str, text: str, meta: Optional[Dict] = None) -> Dict[str, Any]:
    return append_chat(store, mandant, "system", text, "system", meta=meta or {})


def chat_aufgabe_erledigt(store, mandant: str, aufgabe_id: str, beschreibung: str, erledigt: bool) -> Dict[str, Any]:
    status = "erledigt" if erledigt else "wieder_offen"
    return append_chat(
        store,
        mandant,
        "aufgabe_status",
        f"Aufgabe {'erledigt' if erledigt else 'wieder geöffnet'}: {beschreibung}",
        "mandant" if erledigt else "system",
        refs={"aufgabe_id": aufgabe_id},
        meta={"aufgabe_erledigt": erledigt, "status": status},
    )


def chat_unterschrift_status(
    store, mandant: str, unterschrift_id: str, dokumentname: str, status: str
) -> Dict[str, Any]:
    labels = {
        "unterschrieben": f"Unterschrieben: {dokumentname}",
        "abgelehnt": f"Abgelehnt: {dokumentname}",
        "abgelaufen": f"Frist abgelaufen: {dokumentname}",
    }
    return append_chat(
        store,
        mandant,
        "unterschrift_status",
        labels.get(status, dokumentname),
        "mandant" if status == "unterschrieben" else "system",
        refs={"unterschrift_id": unterschrift_id},
        meta={"unterschrift_status": status, "dokumentname": dokumentname},
    )
