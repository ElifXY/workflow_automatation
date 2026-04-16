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
from typing import Any, Optional, Dict
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
    "session_timeout_minuten":     60,
    "ip_whitelist_aktiv":          False,
    "ip_whitelist":                [],
    "rollen_lohn_sichtbar":        ["admin", "steuerberater"],
    "rollen_zahlungen_freigabe":   ["admin"],
    "rollen_mandant_loeschen":     ["admin"],
    "rollen_export_datev":         ["admin", "steuerberater"],
    "rollen_einstellungen":        ["admin"],
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
    "api_rate_limit_pro_minute":   60,

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

BEREICHE = {
    0:   (0, 100),    # ki_autonomie_grad
    1:   (50, 99),    # konfidenz-Schwellenwerte
    3:   (1, 365),    # Tage-Einstellungen
    150: (10, 300),   # stundensatz
}


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

    # Werteliste prüfen
    if key in ERLAUBTE_WERTE and wert not in ERLAUBTE_WERTE[key]:
        log.warning(f"Ungültiger Wert '{wert}' für '{key}'")
        return False

    # Typ-Konvertierung
    try:
        if key in DEFAULT_SETTINGS:
            expected_type = type(DEFAULT_SETTINGS[key])
            if expected_type == bool:
                if isinstance(wert, str):
                    wert = wert.lower() in ("true","1","ja","yes")
                else:
                    wert = bool(wert)
            elif expected_type == int and not isinstance(wert, bool):
                wert = int(wert)
            elif expected_type == float and not isinstance(wert, bool):
                wert = float(wert)
    except (ValueError, TypeError) as e:
        log.warning(f"Typ-Fehler für '{key}': {e}")
        return False

    settings      = _lade_settings()
    settings[key] = wert
    erfolg        = _speichere_settings(settings)
    if erfolg:
        log.info(f"Setting: {key} = {wert}")
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
        elif key.startswith(("frist_","eskalation_","antwort_","ustva_","jahres","est_","auto_","max_email","workflow_")): kategorien["workflow"][key] = wert
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
            