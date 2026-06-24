# Automatische Fristen-Rettung: Frist naht + Dokument fehlt → Warnung + Kontakt
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

from core.aufgabe_erledigt import aufgabe_ist_erledigt
from core.frist_utils import tage_bis_frist
from modules.settings_manager import load_settings_for_store

log = logging.getLogger("kanzlei_frist_rettung")


def _bool_cfg(cfg: Dict[str, Any], key: str, default: bool = True) -> bool:
    v = cfg.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def finde_gefaehrdete_faelle(store) -> List[Dict[str, Any]]:
    """Aufgaben mit naher Frist und fehlenden Unterlagen beim Mandanten."""
    cfg = load_settings_for_store(store)
    warn_tage = int(cfg.get("frist_kritisch_tage") or 3)
    mandanten = store.hole_mandanten() or {}
    gefahr: List[Dict[str, Any]] = []
    heute = datetime.now().date()

    for aid, a in (store.hole_fristen() or {}).items():
        if not isinstance(a, dict) or aufgabe_ist_erledigt(a):
            continue
        mandant = (a.get("mandant") or "").strip()
        if not mandant:
            continue
        tage = tage_bis_frist(a.get("frist"), heute=heute)
        if tage is None or tage > warn_tage or tage < 0:
            continue
        m = mandanten.get(mandant) or {}
        fehl = m.get("fehlende_dokumente_liste") or []
        fehl_n = len(fehl) if isinstance(fehl, list) else 0
        if fehl_n == 0:
            continue
        gefahr.append({
            "aufgabe_id": aid,
            "mandant": mandant,
            "beschreibung": a.get("beschreibung") or "",
            "frist": a.get("frist"),
            "tage_bis_frist": tage,
            "fehlende_dokumente": fehl_n,
            "prioritaet": a.get("prioritaet") or "hoch",
        })
    gefahr.sort(key=lambda x: (x["tage_bis_frist"], -x["fehlende_dokumente"]))
    return gefahr


def run_frist_rettung_for_store(store) -> Dict[str, Any]:
    """Interne Warnaufgabe + Log — ohne automatische Massen-Mails."""
    cfg = load_settings_for_store(store)
    if not _bool_cfg(cfg, "auto_frist_rettung_aktiv", True):
        return {"geprueft": 0, "aktionen": 0, "deaktiviert": True}

    faelle = finde_gefaehrdete_faelle(store)
    aktionen = 0
    tag_key = datetime.now().strftime("%Y-%m-%d")

    for f in faelle[:25]:
        mandant = f["mandant"]
        marker = f"FRIST_RETTUNG|{f.get('aufgabe_id')}|{tag_key}"
        try:
            recent = store.hole_logs(limit=80) or []
            if any(marker in str(r.get("aktion") or "") for r in recent):
                continue
        except Exception:
            pass

        aufgabe_id = str(uuid.uuid4())
        store.aufgabe_speichern(aufgabe_id, {
            "id": aufgabe_id,
            "mandant": mandant,
            "beschreibung": (
                f"⚠ Frist-Rettung: {f['beschreibung'][:80]} — "
                f"noch {f['tage_bis_frist']} Tag(e), {f['fehlende_dokumente']} Unterlage(n) fehlen"
            ),
            "frist": (datetime.now() + timedelta(days=max(1, f["tage_bis_frist"]))).strftime("%Y-%m-%d"),
            "prioritaet": "kritisch",
            "kategorie": "frist_rettung",
            "erledigt": False,
            "erstellt_am": datetime.now().isoformat(),
            "quelle": "frist_rettung_auto",
        })
        store.log_eintrag(
            f"FRIST_RETTUNG | {mandant} | Frist in {f['tage_bis_frist']}d | "
            f"{f['fehlende_dokumente']} fehlend | {marker}"
        )
        aktionen += 1

    return {"geprueft": len(faelle), "aktionen": aktionen, "faelle": faelle[:10]}
