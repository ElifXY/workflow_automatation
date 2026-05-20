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


def _record_portal_sichtbar(store, mandant: str, row: Dict[str, Any]) -> bool:
    """False = Mandant sieht diese Chat-Zeile nicht im Portal."""
    meta = row.get("meta") or {}
    if meta.get("portal_sichtbar") is False:
        return False
    typ = row.get("typ") or ""
    refs = row.get("refs") or {}
    if typ == "upload" and refs.get("upload_id"):
        u = store.portal_holen("upload", refs["upload_id"]) or {}
        if u.get("mandant") == mandant and u.get("portal_sichtbar") is False:
            return False
    if typ == "unterschrift_anfrage" and refs.get("unterschrift_id"):
        u = store.portal_holen("unterschrift", refs["unterschrift_id"]) or {}
        if u.get("mandant") == mandant and u.get("portal_sichtbar") is False:
            return False
    if typ == "aufgabe" and refs.get("aufgabe_id"):
        alle = store.hole_fristen()
        a = alle.get(refs["aufgabe_id"]) if isinstance(alle, dict) else None
        if a and a.get("mandant") == mandant and (
            a.get("portal_sichtbar") is False or a.get("portal_sichtbar") == 0
        ):
            return False
    return True


def list_chat(
    store,
    mandant: str,
    *,
    limit: int = 200,
    seit_id: Optional[str] = None,
    nur_mandanten_portal: bool = False,
) -> List[Dict[str, Any]]:
    ensure_chat_migrated(store, mandant)
    rows = sorted(
        store.portal_liste("chat", mandant=mandant),
        key=lambda x: x.get("zeit") or x.get("erstellt_am") or "",
    )
    rows = [r for r in rows if not (r.get("meta") or {}).get("geloescht")]
    if nur_mandanten_portal:
        rows = [r for r in rows if _record_portal_sichtbar(store, mandant, r)]
    if seit_id:
        ids = [r.get("id") for r in rows]
        if seit_id in ids:
            rows = rows[ids.index(seit_id) + 1 :]
    enriched = [_enrich_message(store, mandant, dict(r)) for r in rows[-limit:]]
    return enriched


def _gelesen_key(reader: str) -> str:
    return "gelesen_von_mandant_am" if reader == "mandant" else "gelesen_von_kanzlei_am"


def _ist_ungelesen_fuer(row: Dict[str, Any], reader: str) -> bool:
    """reader = wer liest (kanzlei|mandant); ungelesen = Nachricht vom anderen ohne Lesebestätigung."""
    sender = row.get("sender") or ""
    if sender not in ("kanzlei", "mandant") or sender == reader:
        return False
    if (row.get("meta") or {}).get("geloescht"):
        return False
    return not (row.get("meta") or {}).get(_gelesen_key(reader))


def zaehle_ungelesen(store, mandant: str, reader: str) -> int:
    ensure_chat_migrated(store, mandant)
    return sum(
        1
        for r in store.portal_liste("chat", mandant=mandant)
        if _ist_ungelesen_fuer(r, reader)
    )


def mark_chat_gelesen(store, mandant: str, reader: str) -> int:
    """Alle Nachrichten des anderen als gelesen markieren. Gibt Anzahl zurück."""
    now = _now()
    gkey = _gelesen_key(reader)
    n = 0
    for row in store.portal_liste("chat", mandant=mandant):
        if not _ist_ungelesen_fuer(row, reader):
            continue
        mid = row.get("id")
        if not mid:
            continue
        meta = dict(row.get("meta") or {})
        meta[gkey] = now
        row = dict(row)
        row["meta"] = meta
        if store.portal_speichern("chat", mid, mandant, row):
            n += 1
    state_id = f"read_{mandant}"
    state = store.portal_holen("chat_state", state_id) or {"mandant": mandant}
    state[f"{reader}_last_read_at"] = now
    store.portal_speichern("chat_state", state_id, mandant, state)
    return n


def total_unread_kanzlei(store) -> Dict[str, Any]:
    alle = store.hole_mandanten() or {}
    per_mandant: Dict[str, int] = {}
    total = 0
    for name in sorted(alle.keys()):
        c = zaehle_ungelesen(store, name, "kanzlei")
        if c:
            per_mandant[name] = c
            total += c
    return {"total": total, "per_mandant": per_mandant}


def list_inbox(store, mandanten_namen: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Übersicht aller Mandanten-Chats für die Kanzlei-Suite (WhatsApp-Liste)."""
    alle = store.hole_mandanten() or {}
    names = mandanten_namen if mandanten_namen is not None else sorted(alle.keys())
    inbox: List[Dict[str, Any]] = []
    for name in names:
        if not name or name not in alle:
            continue
        ensure_chat_migrated(store, name)
        rows = sorted(
            store.portal_liste("chat", mandant=name),
            key=lambda x: x.get("zeit") or "",
        )
        last = rows[-1] if rows else None
        preview = ""
        sender = ""
        zeit = ""
        if last:
            preview = (last.get("text") or "")[:120]
            sender = last.get("sender") or ""
            zeit = last.get("zeit") or ""
        inbox.append({
            "mandant": name,
            "letzte_nachricht": preview,
            "letzte_zeit": zeit,
            "letzter_sender": sender,
            "anzahl": len(rows),
            "hat_chat": bool(rows),
            "ungelesen": zaehle_ungelesen(store, name, "kanzlei"),
        })
    inbox.sort(
        key=lambda x: (x.get("ungelesen", 0) > 0, x.get("letzte_zeit") or ""),
        reverse=True,
    )
    return inbox


def erledige_dokument_anfrage(
    store,
    mandant: str,
    msg_id: str,
    *,
    upload_id: Optional[str] = None,
) -> bool:
    """Dokument-Anfrage im Chat als erledigt markieren."""
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant or row.get("typ") != "dokument_anfrage":
        return False
    row = dict(row)
    meta = dict(row.get("meta") or {})
    meta["dokument_offen"] = False
    meta["dokument_erledigt_am"] = _now()
    if upload_id:
        refs = dict(row.get("refs") or {})
        refs["upload_id"] = upload_id
        row["refs"] = refs
    row["meta"] = meta
    return store.portal_speichern("chat", msg_id, mandant, row)


def get_chat_message(store, mandant: str, msg_id: str) -> Optional[Dict[str, Any]]:
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant:
        return None
    return _enrich_message(store, mandant, dict(row))


def bearbeite_nachricht(
    store,
    mandant: str,
    msg_id: str,
    text: str,
    editor: str,
) -> Dict[str, Any]:
    """Textnachricht bearbeiten (nur eigener Sender)."""
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant:
        raise ValueError("Nachricht nicht gefunden")
    if row.get("meta", {}).get("geloescht"):
        raise ValueError("Nachricht wurde gelöscht")
    if row.get("sender") != editor:
        raise ValueError("Nur eigene Nachrichten bearbeiten")
    row = dict(row)
    row["text"] = (text or "").strip()
    meta = dict(row.get("meta") or {})
    meta["bearbeitet_am"] = _now()
    meta["bearbeitet_von"] = editor
    row["meta"] = meta
    if not store.portal_speichern("chat", msg_id, mandant, row):
        raise RuntimeError("Bearbeitung konnte nicht gespeichert werden")
    return _enrich_message(store, mandant, row)


def loesche_nachricht(store, mandant: str, msg_id: str, editor: str) -> bool:
    row = store.portal_holen("chat", msg_id)
    if not row or row.get("mandant") != mandant:
        raise ValueError("Nachricht nicht gefunden")
    if row.get("sender") != editor:
        raise ValueError("Nur eigene Nachrichten löschen")
    row = dict(row)
    meta = dict(row.get("meta") or {})
    meta["geloescht"] = True
    meta["geloescht_am"] = _now()
    meta["geloescht_von"] = editor
    row["meta"] = meta
    row["text"] = "(Nachricht gelöscht)"
    return store.portal_speichern("chat", msg_id, mandant, row)


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
        if meta.get("dokument_erledigt_am") or refs.get("upload_id"):
            meta["dokument_offen"] = False
        elif meta.get("dokument_offen") is False:
            meta["dokument_offen"] = False
        else:
            meta["dokument_offen"] = True

    if meta.get("geloescht"):
        row["text"] = "(Nachricht gelöscht)"
    elif meta.get("bearbeitet_am"):
        row["text"] = (row.get("text") or "").strip()

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
    portal_sichtbar: bool = True,
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
            "portal_sichtbar": portal_sichtbar,
        },
    )


def chat_dokument_anfrage(
    store,
    mandant: str,
    dokument_name: str,
    beschreibung: str = "",
    frist: str = "",
    *,
    portal_sichtbar: bool = True,
) -> Dict[str, Any]:
    return append_chat(
        store,
        mandant,
        "dokument_anfrage",
        beschreibung or f"Bitte reichen Sie ein: {dokument_name}",
        "kanzlei",
        refs={"dokument_name": dokument_name},
        meta={
            "dokument_name": dokument_name,
            "frist": frist,
            "dokument_offen": True,
            "portal_sichtbar": portal_sichtbar,
        },
    )


def chat_unterschrift_anfrage(
    store,
    mandant: str,
    unterschrift_id: str,
    dokumentname: str,
    betreff: str,
    hinweis: str = "",
    *,
    portal_sichtbar: bool = True,
) -> Dict[str, Any]:
    return append_chat(
        store,
        mandant,
        "unterschrift_anfrage",
        hinweis or betreff or f"Unterschrift: {dokumentname}",
        "kanzlei",
        refs={"unterschrift_id": unterschrift_id},
        meta={
            "dokumentname": dokumentname,
            "unterschrift_status": "ausstehend",
            "portal_sichtbar": portal_sichtbar,
        },
    )


def chat_upload(
    store,
    mandant: str,
    upload_id: str,
    dateiname: str,
    groesse_kb: float,
    sender: str = "mandant",
    *,
    portal_sichtbar: bool = True,
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
        meta={
            "dateiname": dateiname,
            "groesse_kb": groesse_kb,
            "portal_sichtbar": portal_sichtbar,
        },
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
