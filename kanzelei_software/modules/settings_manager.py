# ============================================================
# KANZLEI AI — SETTINGS MANAGER v3.0 (MILLIARDEN-EDITION)
# Datei: modules/settings_manager.py
#
# 6 Kategorien = 6 Profitabilitäts-Hebel:
#   1. KI-Konfiguration      — Autonomiegrad + Lernkurve
#   2. Workflow-Designer     — Fristen-Radar + Eskalation
#   3. Mandanten-Self-Service — Sichtbarkeit + Validierung
#   4. Monetarisierung       — Billing-Regeln + Pakete
#   5. Compliance & Security — Rollen + GoBD + Audit
#   6. Schnittstellen        — Bank-Feeds + Drittsysteme
#
# FESTGESCHRIEBEN (nicht änderbar):
#   - GoBD-Konformität
#   - Steuerliche Grundregeln (SKR03/04)
#   - Datenmodell-Struktur (für Benchmarks)
# ============================================================

import logging
import ipaddress
import re
from typing import Any, Optional, Dict
from urllib.parse import urlparse
from core.daten_speicher import DatenSpeicher

log = logging.getLogger(__name__)

SETTINGS_KEY = "__settings_manager_v1"

# ============================================================
# VOLLSTÄNDIGE DEFAULT-SETTINGS (alle 6 Kategorien)
# ============================================================

DEFAULT_SETTINGS: Dict[str, Any] = {

    # ── 1. KI-KONFIGURATION ──────────────────────────────────
    "ki_autonomie_grad":           75,      # 0-100: 0=alles manuell, 100=vollautonom
    "ki_auto_buchen_ab_konfidenz": 92,      # Ab % → automatisch buchen ohne Review
    "ki_review_ab_konfidenz":      75,      # Zwischen % → kurzer Review
    "ki_lernen_kanzleiweit":       True,    # Darf KI von Mandant A für B lernen?
    "ki_lernen_anonym":            True,    # Aggregiertes Lernen (anonym)
    "ki_anomalie_betrag_euro":     500,     # Ab €X → Mensch alarmieren
    "ki_anomalie_abweichung_pct":  30,      # Ab %X Abweichung → Mensch alarmieren
    "ki_modell":                   "gpt-4o-mini",
    "ki_max_tokens":               2048,
    "ki_temperature":              0.2,     # Niedrig = konservativ/zuverlässig
    "ki_steuer_autopilot_aktiv":   True,
    "ki_beleg_ocr_aktiv":          True,
    "ki_email_generierung_aktiv":  True,
    "ki_bot_proaktiv_aktiv":       True,
    "ki_bot_analyse_uhrzeit":      "07:00", # Wann Bot-Analyse läuft (Cron)

    # ── 2. WORKFLOW-DESIGNER ──────────────────────────────────
    "frist_warnung_tage":          14,      # Vorwarnung vor Frist
    "frist_kritisch_tage":         3,       # Kritische Warnung
    "antwort_warnung_tage":        7,       # Keine Antwort → Alarm
    "eskalation_stufe_1_tage":     7,       # Wer bei Stufe 1?
    "eskalation_stufe_1_empfaenger": "partner@kanzlei.de",
    "eskalation_stufe_2_tage":     14,
    "eskalation_stufe_2_empfaenger": "inhaber@kanzlei.de",
    "ustva_vorwarnung_tage":       5,       # USt-Voranmeldung
    "jahresabschluss_vorwarnung_tage": 30,
    "est_vorwarnung_tage":         45,
    "max_email_pro_tag":           1,
    "auto_workflow_monatsabschluss": True,
    "auto_workflow_lohn":           True,
    "workflow_batch_uhrzeit":       "06:00",
    "historie_erledigte_aufgaben_tage": 30,
    "historie_steuerfaelle_tage":       30,

    # ── 3. MANDANTEN SELF-SERVICE ─────────────────────────────
    "portal_aktiv":                True,
    "portal_sichtbarkeit_bwa":     True,    # Mandant sieht BWA
    "portal_sichtbarkeit_liquiditaet": True,
    "portal_sichtbarkeit_offene_posten": True,
    "portal_sichtbarkeit_benchmarks": False,  # Premium-Feature
    "portal_sichtbarkeit_steuerprognose": True,
    "portal_upload_pflichtfelder": ["kategorie"],  # JSON-Liste
    "portal_projektnummer_pflicht": False,
    "portal_upload_max_mb":        20,
    "portal_token_gueltig_stunden": 168,   # 7 Tage
    "portal_unterschrift_aktiv":   True,
    "portal_freigabe_aktiv":       True,
    "portal_simulation_aktiv":     True,
    "portal_nachrichten_aktiv":    True,

    # ── 4. MONETARISIERUNG & BILLING ──────────────────────────
    "billing_aktiv":               False,   # Eigene Abrechnung an Mandanten
    "billing_modell":              "pauschal",  # pauschal | pro_buchung | pro_mitarbeiter | value
    "billing_pauschal_euro":       299.0,   # Pauschalgebühr/Monat
    "billing_pro_buchung_euro":    0.20,    # Pro KI-Buchung
    "billing_pro_mitarbeiter_euro": 15.0,  # Pro Mitarbeiter-Zugang
    "billing_value_pricing_aktiv": False,   # Umsatz-basierte Preise
    "billing_value_tier_1_bis":    100000,  # Bis €100k Umsatz
    "billing_value_tier_1_euro":   199.0,
    "billing_value_tier_2_bis":    500000,
    "billing_value_tier_2_euro":   399.0,
    "billing_value_tier_3_euro":   699.0,
    "billing_ki_aufschlag_prozent": 20,     # KI-Features Aufschlag
    "billing_rechnung_auto":       False,   # Automatische Rechnungsstellung
    "billing_zahlungsziel_tage":   14,
    "billing_stripe_aktiv":        False,   # Stripe-Integration
    "billing_stripe_key":          "",      # Stripe API Key

    # ── 5. COMPLIANCE & SECURITY ──────────────────────────────
    "gobd_konform":                True,    # FESTGESCHRIEBEN — nicht änderbar!
    "gobd_aufbewahrung_jahre":     10,      # 10 Jahre (§ 147 AO)
    "audit_log_aktiv":             True,
    "audit_unveraenderbar":        True,    # FESTGESCHRIEBEN
    "dsgvo_aktiv":                 True,
    "datenschutz_beauftragter":    "",
    "server_standort":             "DE",    # DE | EU | CH | US
    "verschluesselung_aktiv":      True,
    "2fa_pflicht":                 False,
    "session_timeout_minuten":     0,
    "ip_whitelist_aktiv":          False,
    "ip_whitelist":                [],
    "rollen_lohn_sichtbar":        ["admin", "steuerberater"],
    "rollen_zahlungen_freigabe":   ["admin"],
    "rollen_mandant_loeschen":     ["admin"],
    "rollen_export_datev":         ["admin", "steuerberater"],
    "rollen_einstellungen":        ["admin"],
    # Sidebar: welche Hauptbereiche Steuerberater bzw. Mitarbeitende sehen (Owner/Admin konfigurierbar)
    "rollen_nav_steuerberater": [
        "dashboard", "mandanten", "aufgaben", "ki", "profit", "steuerbot",
        "dokumente", "belege", "rechnungen", "automation", "empfehlungen",
        "analytics", "neu", "settings",
    ],
    "rollen_nav_mitarbeiter": [
        "dashboard", "mandanten", "aufgaben", "ki", "dokumente", "belege",
        "rechnungen", "empfehlungen",
    ],
    "backup_aktiv":                True,
    "backup_interval_stunden":     24,
    "backup_anzahl_aufbewahren":   30,

    # ── 6. SCHNITTSTELLEN ─────────────────────────────────────
    "bank_fints_aktiv":            False,
    "bank_ebics_aktiv":            False,
    "bank_scraping_aktiv":         False,
    "bank_auto_import":            False,
    "bank_import_uhrzeit":         "08:00",
    "datev_export_aktiv":          True,
    "datev_import_aktiv":          False,   # Bidirektional (Premium)
    "datev_berater_nr":            "",
    "elster_aktiv":                True,
    "elster_direktversand":        False,   # ERiC SDK nötig
    "shopify_aktiv":               False,
    "shopify_api_key":             "",
    "amazon_seller_aktiv":         False,
    "amazon_api_key":              "",
    "personio_aktiv":              False,
    "personio_api_key":            "",
    "lexoffice_aktiv":             False,
    "lexoffice_api_key":           "",
    "webhook_url":                 "",      # Outgoing Webhooks
    "api_rate_limit_pro_minute":   300,

    # ── KANZLEI-STAMMDATEN ────────────────────────────────────
    "kanzlei_name":                "Steuerkanzlei",
    "kanzlei_adresse":             "",
    "kanzlei_steuernummer":        "",
    "kanzlei_iban":                "",
    "kanzlei_bic":                 "",
    "kanzlei_email":               "",
    "kanzlei_telefon":             "",
    "kanzlei_website":             "",
    "email_signatur":              "Mit freundlichen Grüßen\nIhre Steuerkanzlei",
    "stundensatz":                 150.0,
    "waehrung":                    "EUR",
    "sprache":                     "de",
    "automation_mode":             "halbautomatisch",
    "debug_mode":                  False,
}

# ── FESTGESCHRIEBENE WERTE (dürfen NICHT geändert werden) ────
FESTGESCHRIEBEN = {
    "gobd_konform":        True,
    "audit_unveraenderbar": True,
}

# ── VALIDIERUNGSREGELN ────────────────────────────────────────
ERLAUBTE_WERTE = {
    "automation_mode":  ["manuell", "halbautomatisch", "auto"],
    "billing_modell":   ["pauschal", "pro_buchung", "pro_mitarbeiter", "value"],
    "server_standort":  ["DE", "EU", "CH", "US"],
    "ki_modell":        ["gpt-4o-mini", "gpt-4o"],
    "sprache":          ["de", "en"],
}

NUMERIC_RANGES = {
    "ki_autonomie_grad": (0, 100),
    "ki_auto_buchen_ab_konfidenz": (50, 99),
    "ki_review_ab_konfidenz": (50, 99),
    "ki_anomalie_betrag_euro": (0, 1_000_000),
    "ki_anomalie_abweichung_pct": (1, 100),
    "historie_erledigte_aufgaben_tage": (1, 3650),
    "historie_steuerfaelle_tage": (1, 3650),
    "portal_upload_max_mb": (1, 1024),
    "billing_pauschal_euro": (0, 1_000_000),
    "billing_pro_buchung_euro": (0, 10_000),
    "billing_pro_mitarbeiter_euro": (0, 100_000),
    "billing_value_tier_1_bis": (1, 100_000_000),
    "billing_value_tier_2_bis": (1, 100_000_000),
    "billing_value_tier_1_euro": (0, 1_000_000),
    "billing_value_tier_2_euro": (0, 1_000_000),
    "billing_value_tier_3_euro": (0, 1_000_000),
    "billing_ki_aufschlag_prozent": (0, 100),
    "billing_zahlungsziel_tage": (1, 365),
    "session_timeout_minuten": (5, 1440),
    "api_rate_limit_pro_minute": (1, 100_000),
    "stundensatz": (1, 10_000),
    "backup_interval_stunden": (1, 24 * 365),
    "backup_anzahl_aufbewahren": (1, 36500),
    "max_email_pro_tag": (0, 10_000),
    "portal_token_gueltig_stunden": (1, 24 * 365),
}

ROLE_KEYS = {
    "rollen_lohn_sichtbar",
    "rollen_zahlungen_freigabe",
    "rollen_mandant_loeschen",
    "rollen_export_datev",
    "rollen_einstellungen",
}
ALLOWED_ROLES = {"owner", "admin", "steuerberater", "mitarbeiter", "assistent"}
ALLOWED_NAV_TABS = {
    "dashboard", "mandanten", "aufgaben", "ki", "profit", "steuerbot",
    "dokumente", "belege", "rechnungen", "automation", "empfehlungen",
    "analytics", "neu", "settings",
}
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_KEYS = {
    "eskalation_stufe_1_empfaenger",
    "eskalation_stufe_2_empfaenger",
    "datenschutz_beauftragter",
}
URL_KEYS = {"webhook_url", "kanzlei_website"}
NAV_KEYS = {"rollen_nav_steuerberater", "rollen_nav_mitarbeiter"}


# ============================================================
# KERN-FUNKTIONEN
# ============================================================

def _lade_settings() -> Dict:
    store = DatenSpeicher()
    gespeichert = store.setting_holen(SETTINGS_KEY, None)
    if not isinstance(gespeichert, dict):
        _speichere_settings(DEFAULT_SETTINGS.copy())
        gespeichert = {}
    try:
        result = DEFAULT_SETTINGS.copy()
        result.update(gespeichert)
        # Festgeschriebene Werte immer erzwingen
        result.update(FESTGESCHRIEBEN)
        return result
    except Exception as e:
        log.error(f"Settings-Ladefehler: {e}")
        return DEFAULT_SETTINGS.copy()


def _speichere_settings(settings: Dict) -> bool:
    # Festgeschriebene Werte niemals überschreiben
    settings.update(FESTGESCHRIEBEN)
    try:
        return DatenSpeicher().setting_setzen(SETTINGS_KEY, settings)
    except Exception as e:
        log.error(f"Settings-Speicherfehler: {e}")
        return False


def setting_holen(key: str) -> Optional[Any]:
    return _lade_settings().get(key, DEFAULT_SETTINGS.get(key))


def _is_valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _validate_invariants(settings: Dict[str, Any], key: str) -> bool:
    auto = int(settings.get("ki_auto_buchen_ab_konfidenz", 92))
    review = int(settings.get("ki_review_ab_konfidenz", 75))
    if review >= auto:
        log.warning(
            "Ungültige Konfidenz-Schwellenwerte: review (%s) muss kleiner als auto (%s) sein",
            review,
            auto,
        )
        return False
    if key == "billing_value_tier_2_bis":
        tier1 = int(settings.get("billing_value_tier_1_bis", 100000))
        tier2 = int(settings.get("billing_value_tier_2_bis", 500000))
        if tier2 <= tier1:
            log.warning("billing_value_tier_2_bis muss größer als billing_value_tier_1_bis sein")
            return False
    if bool(settings.get("ip_whitelist_aktiv")):
        whitelist = settings.get("ip_whitelist") or []
        if not isinstance(whitelist, list) or not whitelist:
            log.warning("ip_whitelist_aktiv benötigt mindestens einen gültigen IP/CIDR-Eintrag")
            return False
        for entry in whitelist:
            try:
                text = str(entry).strip()
                if not text:
                    raise ValueError("empty")
                if "/" in text:
                    ipaddress.ip_network(text, strict=False)
                else:
                    ipaddress.ip_address(text)
            except Exception:
                log.warning("Ungültiger IP-Whitelist-Eintrag: %r", entry)
                return False
    if bool(settings.get("elster_direktversand")) and not bool(settings.get("elster_aktiv")):
        log.warning("elster_direktversand benötigt elster_aktiv=true")
        return False
    if bool(settings.get("billing_stripe_aktiv")):
        if not bool(settings.get("billing_aktiv")):
            log.warning("billing_stripe_aktiv benötigt billing_aktiv=true")
            return False
        if not str(settings.get("billing_stripe_key") or "").strip():
            log.warning("billing_stripe_aktiv benötigt billing_stripe_key")
            return False
    restricted_admin_roles = {"owner", "admin"}
    settings_roles = {str(r).strip().lower() for r in (settings.get("rollen_einstellungen") or []) if str(r).strip()}
    if not settings_roles:
        log.warning("rollen_einstellungen darf nicht leer sein")
        return False
    if not settings_roles.issubset(restricted_admin_roles):
        log.warning("rollen_einstellungen darf nur owner/admin enthalten")
        return False
    for critical_key in ("rollen_mandant_loeschen", "rollen_zahlungen_freigabe"):
        roles = {str(r).strip().lower() for r in (settings.get(critical_key) or []) if str(r).strip()}
        if not roles:
            log.warning("%s darf nicht leer sein", critical_key)
            return False
        if not roles.issubset(restricted_admin_roles):
            log.warning("%s darf nur owner/admin enthalten", critical_key)
            return False
    return True


def _normalize_value(key: str, wert: Any, settings: Dict[str, Any]) -> tuple[bool, Any]:
    if key in ERLAUBTE_WERTE and wert not in ERLAUBTE_WERTE[key]:
        return False, wert
    try:
        if key in DEFAULT_SETTINGS:
            expected_type = type(DEFAULT_SETTINGS[key])
            if expected_type == bool:
                if isinstance(wert, str):
                    wert = wert.strip().lower() in ("true", "1", "ja", "yes")
                else:
                    wert = bool(wert)
            elif expected_type == int and not isinstance(wert, bool):
                wert = int(wert)
            elif expected_type == float and not isinstance(wert, bool):
                wert = float(wert)
            elif expected_type == str:
                wert = "" if wert is None else str(wert).strip()
            elif expected_type == list:
                if not isinstance(wert, list):
                    return False, wert
                wert = [str(v).strip() for v in wert if str(v).strip()]
    except (ValueError, TypeError):
        return False, wert

    if key in NUMERIC_RANGES:
        low, high = NUMERIC_RANGES[key]
        if not (low <= wert <= high):
            return False, wert

    if key in EMAIL_KEYS and wert and not EMAIL_PATTERN.match(str(wert)):
        return False, wert
    if key.endswith("_uhrzeit") and wert and not TIME_PATTERN.match(str(wert)):
        return False, wert
    if key in URL_KEYS and wert and not _is_valid_url(str(wert)):
        return False, wert
    if key in ROLE_KEYS:
        uniq = []
        seen = set()
        for role in wert:
            r = str(role).lower()
            if r in ALLOWED_ROLES and r not in seen:
                uniq.append(r)
                seen.add(r)
        if not uniq:
            return False, wert
        wert = uniq
    if key in NAV_KEYS:
        uniq = []
        seen = set()
        for tab in wert:
            t = str(tab).lower()
            if t in ALLOWED_NAV_TABS and t not in seen:
                uniq.append(t)
                seen.add(t)
        if "dashboard" not in seen:
            uniq.insert(0, "dashboard")
        if not uniq:
            return False, wert
        wert = uniq
    return True, wert


def setting_setzen(key: str, wert: Any) -> bool:
    """
    Setting ändern mit vollständiger Validierung.
    Festgeschriebene Werte sind unveränderbar.
    """
    # Festgeschriebene Werte schützen
    if key in FESTGESCHRIEBEN:
        log.warning(f"Festgeschriebener Wert kann nicht geändert werden: {key}")
        return False

    # Key muss bekannt sein (offenes Schema über Prefix erlaubt)
    if key not in DEFAULT_SETTINGS and not key.startswith(("custom_", "ext_")):
        log.warning(f"Unbekannter Setting-Key: {key}")
        return False

    settings = _lade_settings()
    ok, normalized = _normalize_value(key, wert, settings)
    if not ok:
        log.warning(f"Ungültiger Wert '{wert}' für '{key}'")
        return False
    settings[key] = normalized
    if not _validate_invariants(settings, key):
        return False
    erfolg = _speichere_settings(settings)
    if erfolg:
        log.info(f"Setting: {key} = {normalized}")
    return erfolg


def settings_batch_setzen(updates: Dict[str, Any]) -> Dict[str, bool]:
    """Mehrere Settings auf einmal speichern."""
    results = {}
    for key, wert in updates.items():
        results[key] = setting_setzen(key, wert)
    return results


def alle_settings_holen() -> Dict:
    return _lade_settings()


def settings_nach_kategorie() -> Dict[str, Dict]:
    """Settings gruppiert nach Kategorie für das Frontend."""
    alle = _lade_settings()
    kategorien = {
        "ki":           {},
        "workflow":     {},
        "portal":       {},
        "billing":      {},
        "compliance":   {},
        "schnittstellen":{},
        "kanzlei":      {},
    }
    for key, wert in alle.items():
        if key.startswith("ki_"):                kategorien["ki"][key] = wert
        elif key.startswith(("frist_","eskalation_","antwort_","ustva_","jahres","est_","auto_","max_email","workflow_","historie_")): kategorien["workflow"][key] = wert
        elif key.startswith("portal_"):          kategorien["portal"][key] = wert
        elif key.startswith("billing_"):         kategorien["billing"][key] = wert
        elif key.startswith(("gobd_","audit_","dsgvo_","server_","verschlue","2fa","session","ip_","rollen_","backup_","datenschutz")): kategorien["compliance"][key] = wert
        elif key.startswith(("bank_","datev_","elster_","shopify_","amazon_","personio_","lexoffice_","webhook_","api_")): kategorien["schnittstellen"][key] = wert
        else:                                    kategorien["kanzlei"][key] = wert
    return kategorien


def settings_zuruecksetzen(key: Optional[str] = None) -> bool:
    if key:
        if key in FESTGESCHRIEBEN:
            return False
        return setting_setzen(key, DEFAULT_SETTINGS.get(key))
    base = DEFAULT_SETTINGS.copy()
    base.update(FESTGESCHRIEBEN)
    return _speichere_settings(base)


# ── CLI ───────────────────────────────────────────────────────
def settings_anzeigen() -> None:
    settings = _lade_settings()
    print("\n==============================")
    print("KANZLEI AI — EINSTELLUNGEN")
    print("==============================")
    for key, default in DEFAULT_SETTINGS.items():
        wert = settings.get(key, default)
        mark = " [FEST]" if key in FESTGESCHRIEBEN else (" *" if wert != default else "")
        if len(str(wert)) < 40:
            print(f"  {key:<40} : {wert}{mark}")
    print("==============================\n")


def settings_aendern() -> None:
    settings_anzeigen()
    key = input("Einstellung ändern (Enter = abbrechen): ").strip()
    if not key: return
    if key in FESTGESCHRIEBEN:
        print("Dieser Wert ist festgeschrieben und kann nicht geändert werden.")
        return
    if key not in DEFAULT_SETTINGS:
        print(f"Unbekannte Einstellung: '{key}'")
        return
    aktuell = setting_holen(key)
    print(f"Aktuell: {aktuell}")
    if key in ERLAUBTE_WERTE:
        print(f"Erlaubt: {', '.join(str(v) for v in ERLAUBTE_WERTE[key])}")
    wert = input("Neuer Wert: ").strip()
    if not wert: return
    if setting_setzen(key, wert):
        print(f"✓ Gespeichert: {key} = {setting_holen(key)}")
    else:
        print("Fehler. Wert überprüfen.")
            