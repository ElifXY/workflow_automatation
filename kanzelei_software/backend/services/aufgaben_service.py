from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, status

from core.aufgabe_erledigt import aufgabe_ist_erledigt, aufgabe_ist_offen
from core.kanzlei_historie import (
    aufgaben_historie_nach_purge,
    historie_erledigte_aufgaben_tage,
    purge_abgelaufene_erledigte_aufgaben,
)


class AufgabenService:
    def __init__(self, store):
        self.store = store

    def list_for_mandant(
        self,
        name: str,
        nur_offen: bool = False,
        prioritaet: Optional[str] = None,
        bereich: str = "alle",
    ) -> Dict[str, Any]:
        purge_abgelaufene_erledigte_aufgaben(self.store)

        if bereich == "historie":
            items, ttl = aufgaben_historie_nach_purge(self.store, name)
            if prioritaet:
                items = [a for a in items if a.get("prioritaet") == prioritaet]
            return {"count": len(items), "aufgaben": items, "historie_ttl_tage": ttl}

        # Direkte Mandanten-Abfrage (SQLite/PG konsistent mit Speicherpfad für Aufgaben)
        result = list(self.store.hole_aufgaben_fuer_mandant(name))

        if bereich in ("aktiv", "offen"):
            result = [a for a in result if aufgabe_ist_offen(a)]
        elif nur_offen:
            result = [a for a in result if aufgabe_ist_offen(a)]
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
        return {
            "count": len(result),
            "aufgaben": result,
            "historie_ttl_tage": historie_erledigte_aufgaben_tage(self.store),
        }

    def create(self, name: str, data) -> Dict[str, Any]:
        aufgabe_id = str(uuid.uuid4())
        aufgabe = {
            "id": aufgabe_id,
            "mandant": name,
            "beschreibung": data.beschreibung,
            "frist": data.frist,
            "frist_uhrzeit": data.frist_uhrzeit or "",
            "prioritaet": data.prioritaet,
            "kategorie": data.kategorie or "",
            "notiz": data.notiz or "",
            "erledigt": False,
            "erstellt_am": datetime.now().isoformat(),
        }
        if not self.store.aufgabe_speichern(aufgabe_id, aufgabe):
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Aufgabe konnte nicht gespeichert werden",
            )
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
                "frist_uhrzeit": item.frist_uhrzeit or "",
                "prioritaet": item.prioritaet,
                "kategorie": item.kategorie or "",
                "notiz": item.notiz or "",
                "erledigt": False,
                "erstellt_am": datetime.now().isoformat(),
            }
            if not self.store.aufgabe_speichern(aufgabe_id, aufgabe):
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Aufgabe konnte nicht gespeichert werden",
                )
            erstellte_ids.append(aufgabe_id)
        self.store.log_eintrag(f"BULK_AUFGABEN | {name} | {len(erstellte_ids)} Aufgaben erstellt")
        return {"status": "created", "anzahl": len(erstellte_ids), "ids": erstellte_ids}

    def toggle(self, aufgabe_id: str) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        if aufgabe_id not in aufgaben:
            raise ValueError("Aufgabe nicht gefunden")
        a = dict(aufgaben[aufgabe_id])
        war_erledigt = aufgabe_ist_erledigt(a)
        a["erledigt"] = 0 if war_erledigt else 1
        if a["erledigt"]:
            a["erledigt_am"] = datetime.now().isoformat()
        else:
            a["erledigt_am"] = None
        if not self.store.aufgabe_speichern(aufgabe_id, a):
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Aufgabe konnte nicht gespeichert werden",
            )
        self.store.log_eintrag(f"AUFGABE_TOGGLE | {a.get('mandant')} | {aufgabe_id} | erledigt={a['erledigt']}")
        return {"status": "ok", "erledigt": a["erledigt"]}

    def update(self, aufgabe_id: str, data) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        if aufgabe_id not in aufgaben:
            raise ValueError("Aufgabe nicht gefunden")
        a = dict(aufgaben[aufgabe_id])

        if data.beschreibung is not None:
            a["beschreibung"] = data.beschreibung.strip()
        if data.mandant is not None:
            m = (data.mandant or "").strip()
            if m:
                a["mandant"] = m
        if data.frist is not None:
            a["frist"] = data.frist
        if data.frist_uhrzeit is not None:
            a["frist_uhrzeit"] = data.frist_uhrzeit
        if data.prioritaet is not None:
            a["prioritaet"] = data.prioritaet
        if data.kategorie is not None:
            a["kategorie"] = data.kategorie or ""
        if data.notiz is not None:
            a["notiz"] = data.notiz or ""

        if not self.store.aufgabe_speichern(aufgabe_id, a):
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Aufgabe konnte nicht gespeichert werden",
            )
        self.store.log_eintrag(f"AUFGABE_UPDATED | {a.get('mandant')} | {aufgabe_id}")
        return {"status": "updated", "id": aufgabe_id}

    def delete(self, aufgabe_id: str) -> Dict[str, Any]:
        aufgaben = self.store.hole_fristen()
        if aufgabe_id not in aufgaben:
            raise ValueError("Aufgabe nicht gefunden")
        if not self.store.aufgabe_loeschen(aufgabe_id):
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Aufgabe konnte nicht gelöscht werden",
            )
        self.store.log_eintrag(f"AUFGABE_GELOESCHT | {aufgabe_id}")
        return {"status": "deleted", "id": aufgabe_id}
