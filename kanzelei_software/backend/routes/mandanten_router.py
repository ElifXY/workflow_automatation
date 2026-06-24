"""
Mandanten/Aufgaben/Dokumente Router extracted from ``api.py``.

Behavior stays identical by delegating to existing handlers in ``api.py``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, status

from backend.deps import get_current_user

router = APIRouter(tags=["Mandanten"])


def _root():
    import api as root

    return root


@router.get("/mandanten", summary="Alle Mandanten")
def get_mandanten(
    suche: Optional[str] = Query(None),
    branche: Optional[str] = Query(None),
    min_umsatz: Optional[float] = Query(None, ge=0),
    sortierung: Optional[str] = Query("name"),
    betreuer_email: Optional[str] = Query(None),
    nur_ohne_betreuer: bool = Query(False),
    nur_meine: bool = Query(False),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.get_mandanten(
        suche,
        branche,
        min_umsatz,
        sortierung,
        betreuer_email,
        nur_ohne_betreuer,
        nur_meine,
        _user,
    )


@router.get("/mandanten/{name}", summary="Einzelnen Mandanten lesen")
def get_mandant(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.get_mandant(name, _user)


@router.post("/mandanten", status_code=201, summary="Mandanten erstellen")
def create_mandant(data: Dict[str, Any] = Body(...), _user: dict = Depends(get_current_user)):
    root = _root()
    payload = root.MandantCreate(**data)
    return root.create_mandant(payload, _user)


@router.put("/mandanten/{name}", summary="Mandanten aktualisieren")
def update_mandant(name: str, data: Dict[str, Any] = Body(...), _user: dict = Depends(get_current_user)):
    root = _root()
    payload = root.MandantUpdate(**data)
    return root.update_mandant(name, payload, _user)


@router.delete("/mandanten/{name}", summary="Mandanten löschen")
def delete_mandant(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.delete_mandant(name, _user)


@router.post("/mandanten/{name}/antwort", summary="Mandantenantwort markieren")
def mandant_antwort_empfangen(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.mandant_antwort_empfangen(name, _user)


@router.get("/mandanten/{name}/aufgaben", tags=["Aufgaben"], summary="Aufgaben eines Mandanten")
def get_aufgaben(
    name: str,
    nur_offen: bool = Query(False),
    prioritaet: Optional[str] = Query(None),
    bereich: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.get_aufgaben(
        name,
        nur_offen=nur_offen,
        prioritaet=prioritaet,
        bereich=bereich,
        _user=_user,
    )


@router.post(
    "/mandanten/{name}/aufgaben",
    tags=["Aufgaben"],
    status_code=status.HTTP_201_CREATED,
    summary="Aufgabe anlegen",
)
def create_aufgabe(
    name: str,
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.AufgabeCreate(**data)
    return root.create_aufgabe(name, payload, _user)


@router.post("/mandanten/{name}/aufgaben/bulk", tags=["Aufgaben"], summary="Bulk-Aufgaben anlegen")
def create_aufgaben_bulk(
    name: str,
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.BulkAufgabeCreate(**data)
    return root.create_aufgaben_bulk(name, payload, _user)


@router.post("/aufgaben/{aufgabe_id}/erledigen", tags=["Aufgaben"], summary="Aufgabe toggeln")
def toggle_aufgabe(
    aufgabe_id: str,
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.toggle_aufgabe(aufgabe_id, _user)


@router.put("/aufgaben/{aufgabe_id}", tags=["Aufgaben"], summary="Aufgabe bearbeiten")
def update_aufgabe(
    aufgabe_id: str,
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.AufgabeUpdate(**data)
    return root.update_aufgabe(aufgabe_id, payload, _user)


@router.delete("/aufgaben/{aufgabe_id}", tags=["Aufgaben"], summary="Aufgabe löschen")
def delete_aufgabe(
    aufgabe_id: str,
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.delete_aufgabe(aufgabe_id, _user)


@router.get("/mandanten/{name}/dokumente", tags=["Dokumente"], summary="Dokumente eines Mandanten")
def get_dokumente(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.get_dokumente(name, _user)


@router.post("/mandanten/{name}/dokumente/anfordern", tags=["Dokumente"], summary="Dokument anfordern")
def dokument_anfordern(
    name: str,
    data: Dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = None,
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.DokumentAnforderung(**data)
    return root.dokument_anfordern(name, payload, background_tasks, _user)


@router.post("/mandanten/{name}/dokumente/erhalten", tags=["Dokumente"], summary="Dokument als erhalten markieren")
def dokument_erhalten(
    name: str,
    dokument_name: str = Query(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.dokument_erhalten(name, dokument_name, _user)


@router.post("/mandanten/{name}/simulation", tags=["Analyse"], summary="Steuersimulation")
def steuersimulation(
    name: str,
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.SimulationRequest(**data)
    return root.steuersimulation(name, payload, _user)


@router.get("/mandanten/{name}/report", tags=["Reporting"], summary="Mandantenreport")
def mandant_report(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.mandant_report(name, _user)

