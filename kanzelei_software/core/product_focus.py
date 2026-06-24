# ============================================================
# Produktfokus — Kanzlei Automation
# ============================================================
"""
Kern: Mandanten liefern rechtzeitig — Dokumente, Erinnerungen, keine liegengebliebenen Fälle.
DATEV bleibt System of Record (Buchführung).
"""

from __future__ import annotations

from typing import Any, Dict, List

PRODUCT_NAME = "Kanzlei Automation"

PRODUCT_TAGLINE = (
    "Mandanten liefern rechtzeitig — keine liegengebliebenen Fälle."
)

PRODUCT_HEADLINE = "Mandanten liefern Unterlagen nicht rechtzeitig?"

PRODUCT_SUBLINE = (
    "Kanzlei Automation fordert Dokumente automatisch an, erinnert Mandanten "
    "selbstständig und verhindert liegengebliebene Fälle."
)

VALUE_PILLARS: List[Dict[str, str]] = [
    {
        "id": "workflow",
        "title": "Automatische Erinnerungen",
        "desc": "E-Mail, Portal, Eskalation — ohne manuelles Nachfassen.",
    },
    {
        "id": "dokumente",
        "title": "Fehlende Unterlagen",
        "desc": "Wer liefert nicht? Was fehlt? Grün, Gelb, Rot.",
    },
    {
        "id": "portal",
        "title": "Mandantenportal",
        "desc": "Upload, Unterschrift, Chat — Werkzeug, nicht Hauptprodukt.",
    },
    {
        "id": "datev_export",
        "title": "DATEV-Export",
        "desc": "EXTF v700 — Übergabe an DATEV, kein Ersatz.",
    },
]

NAV_MAIN = [
    "dashboard",
    "mandanten",
    "dokumente",
    "automation",
    "aufgaben",
]

NAV_MORE = [
    "portalchat",
    "analytics",
    "profit",
    "rechnungen",
    "steuerbot",
    "empfehlungen",
    "neu",
]

NAV_EXTENDED = NAV_MORE + ["belege"]

NAV_HIDDEN_FROM_MARKETING = [
    "ki",
    "analytics",
    "profit",
    "empfehlungen",
    "steuerbot",
]

SETTINGS_TABS = [
    "email",
    "workflow",
    "portal",
    "kanzlei",
    "compliance",
    "schnittstellen",
    "ki",
    "billing",
]

INTEGRATION_LIVE = [
    {
        "key": "datev_export",
        "label": "DATEV Export",
        "icon": "🏛",
        "setting": "datev_export_aktiv",
        "desc": "Buchungsstapel + Stammdaten (EXTF v700) für Import in DATEV.",
    },
    {
        "key": "elster_xml",
        "label": "ELSTER XML",
        "icon": "⚖",
        "setting": "elster_aktiv",
        "desc": "Steuer-XML erzeugen — Versand über ELSTER-Software der Kanzlei.",
    },
    {
        "key": "bank_csv",
        "label": "Kontoauszug-Import",
        "icon": "🏦",
        "setting": "bank_csv_import",
        "desc": "CSV-Import von Kontoauszügen.",
    },
]
