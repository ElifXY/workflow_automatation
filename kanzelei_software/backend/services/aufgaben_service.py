from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


class AufgabenService:
    def __init__(self, store):
        self.store = store

    def list_for_mandant(self, name: str, nur_offen: bool = False, prioritaet: Optional[str] = None) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        result = [a for a in aufgaben.values() if a.get("mandant") == name]

        if nur_offen:
            result = [a for a in result if not a.get("erledigt")]
        if prioritaet:
            result = [a for a in result if a.get("prioritaet") == prioritaet]

        jetzt = datetime.now()
        for a in result:
            try:
                frist_dt = datetime.strptime(a["frist"], "%Y-%m-%d")
                tage = (frist_dt - jetzt).days
                a["tage_bis_frist"] = tage
                a["ueberfaellig"] = tage < 0
                a["dringend"] = 0 <= tage <= 3
            except Exception:
                a["tage_bis_frist"] = None
                a["ueberfaellig"] = False
                a["dringend"] = False
        result.sort(key=lambda x: (x.get("erledigt", False), x.get("tage_bis_frist") or 9999))
        return {"count": len(result), "aufgaben": result}

    def create(self, name: str, data) -> Dict[str, Any]:
        aufgabe_id = str(uuid.uuid4())
        aufgabe = {
            "id": aufgabe_id,
            "mandant": name,
            "beschreibung": data.beschreibung,
            "frist": data.frist,
            "prioritaet": data.prioritaet,
            "kategorie": data.kategorie or "",
            "notiz": data.notiz or "",
            "erledigt": False,
            "erstellt_am": datetime.now().isoformat(),
        }
        self.store.aufgabe_speichern(aufgabe_id, aufgabe)
        self.store.log_eintrag(f"AUFGABE_ERSTELLT | {name} | {data.beschreibung} | Frist: {data.frist}")
        return {"status": "created", "id": aufgabe_id}

    def create_bulk(self, name: str, aufgaben_input: List[Any]) -> Dict[str, Any]:
        erstellte_ids: List[str] = []
        for item in aufgaben_input:
            aufgabe_id = str(uuid.uuid4())
            aufgabe = {
                "id": aufgabe_id,
                "mandant": name,
                "beschreibung": item.beschreibung,
                "frist": item.frist,
                "prioritaet": item.prioritaet,
                "kategorie": item.kategorie or "",
                "notiz": item.notiz or "",
                "erledigt": False,
                "erstellt_am": datetime.now().isoformat(),
            }
            self.store.aufgabe_speichern(aufgabe_id, aufgabe)
            erstellte_ids.append(aufgabe_id)
        self.store.log_eintrag(f"BULK_AUFGABEN | {name} | {len(erstellte_ids)} Aufgaben erstellt")
        return {"status": "created", "anzahl": len(erstellte_ids), "ids": erstellte_ids}

    def toggle(self, aufgabe_id: str) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        if aufgabe_id not in aufgaben:
            raise ValueError("Aufgabe nicht gefunden")
        a = aufgaben[aufgabe_id]
        a["erledigt"] = not a.get("erledigt", False)
        if a["erledigt"]:
            a["erledigt_am"] = datetime.now().isoformat()
        else:
            a.pop("erledigt_am", None)
        self.store.aufgabe_speichern(aufgabe_id, a)
        self.store.log_eintrag(f"AUFGABE_TOGGLE | {a.get('mandant')} | {aufgabe_id} | erledigt={a['erledigt']}")
        return {"status": "ok", "erledigt": a["erledigt"]}

    def delete(self, aufgabe_id: str) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        if aufgabe_id not in aufgaben:
            raise ValueError("Aufgabe nicht gefunden")
        self.store.aufgabe_loeschen(aufgabe_id)
        self.store.log_eintrag(f"AUFGABE_GELOESCHT | {aufgabe_id}")
        return {"status": "deleted", "id": aufgabe_id}
