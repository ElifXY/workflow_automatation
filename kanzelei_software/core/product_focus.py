# ============================================================
# Produktfokus — was wir verkaufen vs. was noch nicht reif ist
# ============================================================
"""
Kanzlei AI = Mandanten-Orchestrierung + Portal + proaktiver Bot + Aufgaben.
DATEV bleibt System of Record (Buchführung).
"""

from __future__ import annotations

from typing import Any, Dict, List

PRODUCT_TAGLINE = (
    "Mandanten steuern, Nachfassen automatisieren — Buchführung bleibt in DATEV."
)

VALUE_PILLARS: List[Dict[str, str]] = [
    {
        "id": "portal",
        "title": "Mandanten-Portal & Chat",
        "desc": "Unterlagen, Unterschrift, Chat — weniger Telefonate.",
    },
    {
        "id": "bot",
        "title": "Proaktiver Bot",
        "desc": "System stellt Fragen, bevor die Kanzlei anruft.",
    },
    {
        "id": "aufgaben",
        "title": "Aufgaben & Überblick",
        "desc": "Wer ist überfällig, was fehlt — ein Dashboard.",
    },
    {
        "id": "datev_export",
        "title": "DATEV-Export",
        "desc": "EXTF v700 CSV — Übergabe an DATEV, kein Ersatz.",
    },
]

# Sidebar-Tabs: Kern vs. Erweitert (Beta)
NAV_CORE = [
    "dashboard",
    "mandanten",
    "portalchat",
    "aufgaben",
    "automation",
    "ki",
    "neu",
    "settings",
]

NAV_EXTENDED = [
    "profit",
    "steuerbot",
    "dokumente",
    "belege",
    "rechnungen",
    "empfehlungen",
    "analytics",
]

# Schnittstellen: produktiv vs. Roadmap (keine irreführenden Toggles)
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
        "desc": "CSV/Kontoauszug hochladen (POST /bank/import).",
        "always_on": True,
    },
]

INTEGRATION_ROADMAP = [
    {"key": "datev_api", "label": "DATEV Live-Sync", "icon": "🏛", "eta": "Roadmap"},
    {"key": "bank_live", "label": "FinTS / EBICS", "icon": "🏦", "eta": "Roadmap"},
    {"key": "elster_eric", "label": "ELSTER Direktversand", "icon": "⚖", "eta": "Roadmap"},
    {"key": "lexoffice", "label": "Lexoffice", "icon": "📊", "eta": "Roadmap"},
    {"key": "personio", "label": "Personio", "icon": "👥", "eta": "Roadmap"},
    {"key": "shopify", "label": "Shopify / Amazon", "icon": "🛍", "eta": "Roadmap"},
]

DATEV_EXPORT_HINWEIS = (
    "Export im DATEV-Format (EXTF v700). Buchungen basieren auf Mandantendaten und Aufgaben — "
    "für die Fibu bitte in DATEV prüfen und ggf. anpassen. DATEV bleibt führend."
)

DATEV_IMPORT_UNAVAILABLE = (
    "DATEV-Import (Live-Sync) ist in Entwicklung. Nutzen Sie den Export zu DATEV; "
    "Mandanten- und Prozessdaten liegen in Kanzlei AI."
)


def default_nav_for_role(role: str, fokus: bool = True) -> List[str]:
    """Fokus-Modus: nur Kern-Navigation (weniger Ablenkung beim Verkauf/Pilot)."""
    if not fokus:
        return list(NAV_CORE) + list(NAV_EXTENDED)
    if role == "mitarbeiter":
        return ["dashboard", "mandanten", "portalchat", "aufgaben", "ki", "settings"]
    return list(NAV_CORE)


def product_summary() -> Dict[str, Any]:
    return {
        "tagline": PRODUCT_TAGLINE,
        "pillars": VALUE_PILLARS,
        "nav_core": NAV_CORE,
        "nav_extended": NAV_EXTENDED,
        "integrations_live": INTEGRATION_LIVE,
        "integrations_roadmap": INTEGRATION_ROADMAP,
        "datev_hinweis": DATEV_EXPORT_HINWEIS,
    }
