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
        saved = self.store.mandant_speichern(data.name, mandant_daten)
        if not saved:
            raise RuntimeError("Mandant konnte nicht gespeichert werden")
        created = self.store.hole_mandant(data.name)
        if not created:
            raise RuntimeError("Mandant wurde nicht persistiert")
        betreuer = getattr(data, "betreuer_email", None)
        if betreuer:
            self._apply_betreuer(data.name, betreuer)
        self.store.log_eintrag(f"MANDANT_ERSTELLT | {data.name} | Umsatz: {data.umsatz}€")
        return {"status": "created", "name": data.name}

    def _apply_betreuer(self, name: str, betreuer_email: Optional[str]) -> None:
        if betreuer_email is None:
            return
        extra = self.store.mandant_extra_holen(name)
        extra["betreuer_email"] = str(betreuer_email or "").strip().lower()
        self.store.mandant_extra_setzen(name, extra)

    def update_mandant(self, name: str, update_felder: Dict[str, Any]) -> Dict[str, Any]:
        m = self.store.hole_mandant(name)
        if not m:
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        betreuer = update_felder.pop("betreuer_email", None)
        if betreuer is not None:
            self._apply_betreuer(name, betreuer)
        m.update(update_felder)
        m["zuletzt_geaendert"] = datetime.now().isoformat()
        saved = self.store.mandant_speichern(name, m)
        if not saved:
            raise RuntimeError("Mandant konnte nicht aktualisiert werden")
        self.store.log_eintrag(f"MANDANT_AKTUALISIERT | {name} | {list(update_felder.keys())}")
        return {"status": "updated", "name": name, "geaenderte_felder": list(update_felder.keys())}

    def delete_mandant(self, name: str) -> Dict[str, Any]:
        if not self.store.hole_mandant(name):
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        deleted = self.store.mandant_loeschen(name)
        if not deleted:
            raise RuntimeError("Mandant konnte nicht gelöscht werden")
        self.store.log_eintrag(f"MANDANT_GELOESCHT | {name}")
        return {"status": "deleted", "name": name, "papierkorb": True}

    def list_papierkorb(self) -> List[Dict[str, Any]]:
        daten = self.store.hole_mandanten_papierkorb()
        return [{"name": name, **m} for name, m in daten.items()]

    def restore_mandant(self, name: str) -> Dict[str, Any]:
        papier = self.store.hole_mandanten_papierkorb()
        if name not in papier:
            raise ValueError(f"Mandant '{name}' nicht im Papierkorb")
        restored = self.store.mandant_wiederherstellen(name)
        if not restored:
            raise RuntimeError("Mandant konnte nicht wiederhergestellt werden")
        self.store.log_eintrag(f"MANDANT_WIEDERHERGESTELLT | {name}")
        return {"status": "restored", "name": name}

    def mark_antwort(self, name: str) -> Dict[str, Any]:
        m = self.store.hole_mandant(name)
        if not m:
            raise ValueError(f"Mandant '{name}' nicht gefunden")
        m["letzte_antwort"] = datetime.now().isoformat()
        saved = self.store.mandant_speichern(name, m)
        if not saved:
            raise RuntimeError("Antwort konnte nicht gespeichert werden")
        self.store.log_eintrag(f"ANTWORT_EMPFANGEN | {name}")
        return {"status": "ok", "letzte_antwort": m["letzte_antwort"]}
