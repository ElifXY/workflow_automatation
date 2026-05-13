from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class AssistantResponse(BaseModel):
    content: str = ""
    tokens_used: int = 0
    modell: str = "gpt-4o-mini"
    trace_id: str = ""


class DocumentExtraction(BaseModel):
    doktyp: str = "sonstiges"
    ordner: str = "Sonstiges"
    datum: str = ""
    absender: str = ""
    empfaenger: str = ""
    betrag: float = 0.0
    mandant: str = ""
    aufgabe: str = ""
    frist: str = ""
    ki_zusammenfassung: str = ""
    konfidenz: float = Field(default=0.5, ge=0.0, le=1.0)
    unsichere_felder: List[str] = Field(default_factory=list)


class ReceiptExtraction(BaseModel):
    typ: str = "ausgabe"
    datum: str = ""
    betrag_brutto: float = 0.0
    betrag_netto: float = 0.0
    mwst_betrag: float = 0.0
    mwst_satz: int = 19
    waehrung: str = "EUR"
    lieferant: str = ""
    rechnungsnummer: str = ""
    kategorie: str = "sonstiges"
    skr03_soll: str = "4980"
    skr03_haben: str = "1200"
    buchungstext: str = ""
    vorsteuer_abzugsfaehig: bool = True
    notiz: str = ""
    vertrauens_score: float = Field(default=0.5, ge=0.0, le=1.0)
    unsichere_felder: List[str] = Field(default_factory=list)

