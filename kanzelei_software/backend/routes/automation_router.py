"""
Automation router extracted from ``api.py``.

Contains workflow, bot and ML endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, status

from backend.deps import get_current_user

router = APIRouter(tags=["Automation"])


def _root():
    import api as root

    return root


@router.post("/workflow/monatsabschluss/{name}", summary="Monatsabschluss-Workflow starten")
def workflow_monatsabschluss(
    name: str,
    monat: int = Query(default=None, ge=1, le=12),
    jahr: int = Query(default=None, ge=2020, le=2099),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.workflow_monatsabschluss(name, monat, jahr, _user)


@router.post("/workflow/jahresabschluss/{name}", summary="Jahresabschluss-Workflow starten")
def workflow_jahresabschluss(
    name: str,
    jahr: int = Query(default=None, ge=2020, le=2099),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.workflow_jahresabschluss(name, jahr, _user)


@router.post("/workflow/onboarding/{name}", summary="Onboarding-Workflow für neuen Mandanten")
def workflow_onboarding(name: str, _user: dict = Depends(get_current_user)):
    root = _root()
    return root.workflow_onboarding(name, _user)


@router.post("/bot/frage", summary="Neue Bot-Frage an Mandant stellen")
def bot_frage_stellen(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.BotFrageCreate(**data)
    return root.bot_frage_stellen(payload, _user)


@router.post("/bot/frage/{frage_id}/antwort", summary="Antwort auf Bot-Frage erfassen")
def bot_antwort(
    frage_id: str,
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.BotAntwortRequest(**data)
    return root.bot_antwort(frage_id, payload, _user)


@router.get("/bot/fragen", summary="Alle Bot-Fragen")
def bot_alle_fragen(
    mandant: Optional[str] = Query(None),
    status_value: Optional[str] = Query(None, alias="status"),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.bot_alle_fragen(mandant, status_value, _user)


@router.get("/bot/fragen/{mandant}", summary="Bot-Fragen für einen Mandanten (für Portal)")
def bot_fragen_mandant(
    mandant: str,
    nur_offen: bool = Query(True),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    return root.bot_fragen_mandant(mandant, nur_offen, _user)


@router.post("/bot/analyse", summary="Automatische Bot-Analyse aller Mandanten starten")
def bot_analyse(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.bot_analyse(_user)


@router.get("/bot/statistiken", summary="Bot-Statistiken (gesparte Telefonate)")
def bot_statistiken(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.bot_statistiken(_user)


@router.post("/ml/kategorisieren", summary="Lieferant KI-gestützt kategorisieren")
def ml_kategorisieren(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.MLKategorisierungRequest(**data)
    return root.ml_kategorisieren(payload, _user)


@router.post("/ml/feedback", summary="Bestätigte Buchung als Training speichern")
def ml_feedback(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.MLFeedbackRequest(**data)
    return root.ml_feedback(payload, _user)


@router.get("/ml/statistiken", summary="ML-Statistiken (wie viel hat das System gelernt?)")
def ml_statistiken(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.ml_statistiken(_user)


@router.get("/ml/lieferanten", summary="Alle bekannten Lieferanten mit gelernten Kategorien")
def ml_lieferanten(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.ml_lieferanten(_user)

