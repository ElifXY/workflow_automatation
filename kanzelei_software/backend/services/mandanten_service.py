from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


class MandantenService:
    """Business logic layer for mandanten workflows."""

    def __init__(self, store):
        self.store = store

    def list_mandanten(
        self,
        *,
        suche: Optional[str] = None,
        branche: Optional[str] = None,
        min_umsatz: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        daten = self.store.hole_mandanten()
        result: List[Dict[str, Any]] = []
        for name, m in daten.items():
            if not isinstance(m, dict):
                continue
            if suche and suche.lower() not in name.lower():
                continue
            if branche and m.get("branche", "").lower() != branche.lower():
                continue
            if min_umsatz is not None and float(m.get("umsatz", 0) or 0) < min_umsatz:
                continue
            result.append({"name": name, **m})
        return result

    def create_mandant(self, data) -> Dict[str, Any]:
        mandanten = self.store.hole_mandanten()
        if data.name in mandanten:
            raise ValueError(f"Mandant '{data.name}' existiert bereits")

        mandant_daten = {
            "umsatz": data.umsatz,
            "email": data.email or "",
            "telefon": data.telefon or "",
            "branche": data.branche or "",
            "steuer_id": data.steuer_id or "",
            "notizen": data.notizen or "",
            "fehlende_dokumente_liste": [],
            "letzte_antwort": datetime.now().isoformat(),
            "letzte_email": None,
            "erstellt_am": datetime.now().isoformat(),
            "aktiv": True,
        }
        self.store.mandant_speichern(data.name, mandant_daten)
        self.store.log_eintrag(f"MANDANT_ERSTELLT | {data.name} | Umsatz: {data.umsatz}€")
        return {"status": "created", "name": data.name}

    def update_mandant(self, name: str, update_felder: Dict[str, Any]) -> Dict[str, Any]:
        m = self.store.hole_mandant(name)
        if not m:
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        m.update(update_felder)
        m["zuletzt_geaendert"] = datetime.now().isoformat()
        self.store.mandant_speichern(name, m)
        self.store.log_eintrag(f"MANDANT_AKTUALISIERT | {name} | {list(update_felder.keys())}")
        return {"status": "updated", "name": name, "geaenderte_felder": list(update_felder.keys())}

    def delete_mandant(self, name: str) -> Dict[str, Any]:
        if not self.store.hole_mandant(name):
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        self.store.mandant_loeschen(name)
        self.store.log_eintrag(f"MANDANT_GELOESCHT | {name}")
        return {"status": "deleted", "name": name}

    def mark_antwort(self, name: str) -> Dict[str, Any]:
        m = self.store.hole_mandant(name)
        if not m:
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        m["letzte_antwort"] = datetime.now().isoformat()
        self.store.mandant_speichern(name, m)
        self.store.log_eintrag(f"ANTWORT_EMPFANGEN | {name}")
        return {"status": "ok", "letzte_antwort": m["letzte_antwort"]}
