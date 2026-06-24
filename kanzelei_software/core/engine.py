# ============================================================
# KANZLEI AI — ENGINE v2.0
# Vollautomatischer Kanzlei-Motor
#
# Ziele:
#   ✓ Zeitersparnis durch Automatisierung aller Routineaufgaben
#   ✓ Fehlerreduktion durch intelligente Plausibilitätsprüfungen
#   ✓ Compliance / Rechtssicherheit: immer aktuelle Prüfungen
#   ✓ Mehr Mandanten pro Stunde: Engine arbeitet im Hintergrund
#   ✓ Revisionssichere Dokumentation aller Aktionen
#   ✓ Smart Learning: Muster erkennen, Empfehlungen verbessern
#   ✓ Predictive: Fristen, Cashflow, Steuerlasten vorausberechnen
# ============================================================

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from core.daten_speicher import DatenSpeicher
from core.decision_engine import analysiere_alle_mandanten as analysiere_alle
from core.ai_email import generate_ai_email, generiere_email_text

log = logging.getLogger("kanzlei_engine")

# ============================================================
# STEUER-FRISTEN KALENDER (Deutschland)
# Compliance: immer aktuelle gesetzliche Fristen
# ============================================================

def berechne_steuerfristen(jahr: int) -> List[Dict]:
    """
    Gesetzliche Steuerfristen für ein Jahr.
    Basis für automatische Fristenkontrolle & Erinnerungen.
    In Produktion: per API von FinanzAmt / DATEV aktualisieren.
    """
    fristen = [
        # Lohnsteuer-Anmeldungen (monatlich)
        {"typ": "Lohnsteuer-Anmeldung",   "monat": m, "tag": 10,  "kategorie": "lohnsteuer"}
        for m in range(1, 13)
    ] + [
        # Umsatzsteuer-Voranmeldungen (quartalsweise)
        {"typ": "USt-Voranmeldung Q1",    "monat": 4,  "tag": 10, "kategorie": "umsatzsteuer"},
        {"typ": "USt-Voranmeldung Q2",    "monat": 7,  "tag": 10, "kategorie": "umsatzsteuer"},
        {"typ": "USt-Voranmeldung Q3",    "monat": 10, "tag": 10, "kategorie": "umsatzsteuer"},
        {"typ": "USt-Voranmeldung Q4",    "monat": 1,  "tag": 10, "kategorie": "umsatzsteuer"},
        # Körperschaftsteuer
        {"typ": "Körperschaftsteuer",     "monat": 7,  "tag": 31, "kategorie": "koerperschaft"},
        # Einkommensteuer
        {"typ": "Einkommensteuererklärung","monat": 7, "tag": 31, "kategorie": "einkommensteuer"},
        # Gewerbesteuer
        {"typ": "Gewerbesteuervorauszahlung Q1", "monat": 2, "tag": 15, "kategorie": "gewerbesteuer"},
        {"typ": "Gewerbesteuervorauszahlung Q2", "monat": 5, "tag": 15, "kategorie": "gewerbesteuer"},
        {"typ": "Gewerbesteuervorauszahlung Q3", "monat": 8, "tag": 15, "kategorie": "gewerbesteuer"},
        {"typ": "Gewerbesteuervorauszahlung Q4", "monat": 11,"tag": 15, "kategorie": "gewerbesteuer"},
        # Jahresabschluss
        {"typ": "Jahresabschluss",        "monat": 12, "tag": 31, "kategorie": "jahresabschluss"},
    ]

    result = []
    for f in fristen:
        try:
            frist_monat = f["monat"]
            frist_jahr  = jahr if frist_monat >= datetime.now().month else jahr + 1
            datum = datetime(frist_jahr, frist_monat, f["tag"])
            result.append({**f, "datum": datum.strftime("%Y-%m-%d"), "jahr": frist_jahr})
        except ValueError:
            continue

    return sorted(result, key=lambda x: x["datum"])


# ============================================================
# PLAUSIBILITÄTSPRÜFUNGEN
# Fehlerreduktion: Erkennt unplausible Daten bevor sie Schaden anrichten
# ============================================================

def pruefe_mandant_plausibilitaet(name: str, daten: Dict) -> List[Dict]:
    """
    Plausibilitätsprüfung für einen Mandanten.
    Erkennt Datenfehler, fehlende Pflichtfelder, Inkonsistenzen.

    Returns:
        Liste von Warnungen mit typ, text, schwere
    """
    warnungen = []

    # Pflichtfelder
    if not daten.get("email"):
        warnungen.append({
            "typ": "fehlend", "schwere": "mittel",
            "text": "Keine E-Mail-Adresse — automatische Kommunikation nicht möglich"
        })

    if not daten.get("steuer_id"):
        warnungen.append({
            "typ": "fehlend", "schwere": "niedrig",
            "text": "Keine Steuer-ID hinterlegt"
        })

    # Umsatz-Plausibilität
    umsatz = daten.get("umsatz", 0)
    if umsatz < 0:
        warnungen.append({
            "typ": "fehler", "schwere": "hoch",
            "text": f"Negativer Umsatz ({umsatz}€) — Datenfehler prüfen"
        })
    elif umsatz == 0:
        warnungen.append({
            "typ": "hinweis", "schwere": "niedrig",
            "text": "Umsatz ist 0€ — ggf. aktualisieren"
        })

    # Letzte Antwort prüfen
    letzte_antwort = daten.get("letzte_antwort")
    if letzte_antwort:
        try:
            dt = datetime.fromisoformat(letzte_antwort)
            tage = (datetime.now() - dt).days
            if tage > 90:
                warnungen.append({
                    "typ": "inaktiv", "schwere": "hoch",
                    "text": f"Kein Kontakt seit {tage} Tagen — Mandant aktiv?"
                })
        except ValueError:
            warnungen.append({
                "typ": "fehler", "schwere": "mittel",
                "text": f"Ungültiges Datum in letzte_antwort: {letzte_antwort}"
            })

    return warnungen


def pruefe_aufgabe_plausibilitaet(aufgabe: Dict) -> List[Dict]:
    """Plausibilitätsprüfung für eine einzelne Aufgabe."""
    warnungen = []

    # Frist in der Vergangenheit?
    try:
        frist = datetime.strptime(aufgabe["frist"], "%Y-%m-%d")
        tage  = (frist - datetime.now()).days

        if tage < -30 and not aufgabe.get("erledigt"):
            warnungen.append({
                "typ": "ueberfaellig", "schwere": "hoch",
                "text": f"Aufgabe seit {abs(tage)} Tagen überfällig und nicht erledigt: {aufgabe.get('beschreibung', '?')}"
            })
    except (ValueError, KeyError):
        warnungen.append({
            "typ": "fehler", "schwere": "hoch",
            "text": f"Ungültiges Frist-Datum in Aufgabe: {aufgabe.get('id', '?')}"
        })

    return warnungen


# ============================================================
# ENGINE KLASSE
# ============================================================

class Engine:
    """
    Vollautomatischer Kanzlei-Motor.

    Führt aus:
    1. Daily Checks: Fristen, Antworten, Dokumente für alle Mandanten
    2. Plausibilitätsprüfungen: Datenfehler erkennen
    3. Automatische Emails: nach Automation-Mode (manuell/halbautomatisch/auto)
    4. Workflow-Automatisierung: Standardaufgaben mit einem Schritt
    5. Predictive Analysis: kommende Belastungen vorausberechnen
    6. Compliance-Check: gesetzliche Fristen überwachen
    7. Smart Reporting: automatische Tagesberichte
    """

    def __init__(self, ds: Optional[DatenSpeicher] = None):
        self.ds = ds or DatenSpeicher()

    def _setting(self, key: str, default: Any) -> Any:
        from core.tenant_settings import tenant_setting
        return tenant_setting(self.ds, key, default)

    # ────────────────────────────────────────────────────────
    # HAUPT-EINSTIEGSPUNKTE
    # ────────────────────────────────────────────────────────

    def run_daily_checks(self) -> Dict[str, Any]:
        """
        Vollständiger Tages-Check für alle Mandanten.
        BUGFIX: hole_mandanten / hole_fristen wurden ohne () aufgerufen.
        BUGFIX: _check_fristen wurde doppelt aufgerufen.
        BUGFIX: _entscheidungen() existierte nicht → _entscheidung().

        Returns:
            Zusammenfassung aller Aktionen und Warnungen
        """
        start = time.time()
        log.info("=" * 50)
        log.info("ENGINE DAILY CHECK STARTET")
        log.info("=" * 50)

        # Settings laden
        antwort_grenze = self._setting("antwort_warnung_tage", 7)
        frist_grenze = self._setting("frist_warnung_tage", 3)
        automation_mode = self._setting("automation_mode", "manuell")

        # Daten laden (BUGFIX: () fehlte)
        mandanten = self.ds.hole_mandanten()
        aufgaben  = self.ds.hole_fristen()

        ergebnis = {
            "mandanten_geprueft":   0,
            "emails_vorgeschlagen":  0,
            "emails_gesendet":       0,
            "warnungen":            [],
            "aktionen":             [],
            "plausibilitaet":       [],
            "compliance":           [],
            "start":                datetime.now().isoformat(),
        }

        if not mandanten:
            log.info("Keine Mandanten vorhanden.")
            return ergebnis

        # ── Pro Mandant ────────────────────────────────────
        for name, mandant_daten in mandanten.items():
            ergebnis["mandanten_geprueft"] += 1

            # 1. Plausibilitätsprüfung
            plausibilitaet = pruefe_mandant_plausibilitaet(name, mandant_daten)
            if plausibilitaet:
                ergebnis["plausibilitaet"].extend([
                    {"mandant": name, **p} for p in plausibilitaet
                ])

            # 2. Aufgaben-Plausibilität
            for aufgabe in aufgaben.values():
                if aufgabe.get("mandant") == name:
                    ap = pruefe_aufgabe_plausibilitaet(aufgabe)
                    ergebnis["plausibilitaet"].extend([
                        {"mandant": name, **p} for p in ap
                    ])

            # 3. Keine-Antwort Check
            aktion = self._check_keine_antwort(name, antwort_grenze, automation_mode)
            if aktion:
                ergebnis["aktionen"].append(aktion)
                if aktion.get("email_gesendet"):
                    ergebnis["emails_gesendet"] += 1
                else:
                    ergebnis["emails_vorgeschlagen"] += 1

            # 4. Dokumente Check (BUGFIX: wurde in alter Engine nie aufgerufen)
            aktion = self._check_dokumente(name, mandant_daten, automation_mode)
            if aktion:
                ergebnis["aktionen"].append(aktion)

            # 5. Fristen Check (BUGFIX: doppelter Aufruf entfernt)
            aktionen = self._check_fristen(name, aufgaben, frist_grenze, automation_mode)
            ergebnis["aktionen"].extend(aktionen)

        # 6. Compliance Check
        ergebnis["compliance"] = self._check_compliance_fristen()

        # 7. Tages-Report loggen
        dauer = round(time.time() - start, 2)
        ergebnis["dauer_sekunden"] = dauer
        ergebnis["ende"]           = datetime.now().isoformat()

        self.ds.log_eintrag(
            f"ENGINE_DAILY_CHECK | {ergebnis['mandanten_geprueft']} Mandanten | "
            f"{ergebnis['emails_gesendet']} Emails | "
            f"{len(ergebnis['warnungen'])} Warnungen | {dauer}s"
        )

        log.info(
            f"ENGINE FERTIG — {ergebnis['mandanten_geprueft']} Mandanten, "
            f"{ergebnis['emails_gesendet']} Emails, {dauer}s"
        )

        return ergebnis

    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Vollständige KI-Analyse aller Mandanten.
        Für Dashboard-Übersicht und strategische Planung.
        """
        mandanten = analysiere_alle(self.ds)
        return {
            "mandanten":     mandanten,
            "anzahl":        len(mandanten),
            "kritisch":      sum(1 for m in mandanten if m.get("status") == "KRITISCH"),
            "wichtig":       sum(1 for m in mandanten if m.get("status") == "WICHTIG"),
            "generiert_am":  datetime.now().isoformat(),
        }

    # ────────────────────────────────────────────────────────
    # EINZEL-CHECKS
    # ────────────────────────────────────────────────────────

    def _check_keine_antwort(self, mandant: str, grenze: int,
                              mode: str) -> Optional[Dict]:
        """
        Prüft ob ein Mandant zu lange nicht geantwortet hat.
        Eskalations-System: 7 Tage → Erinnerung, 14 Tage → Nachdrücklich, 21+ → Kritisch.
        """
        try:
            tage = self.ds.berechne_tage_ohne_antwort(mandant)

            if tage < grenze:
                return None

            # Eskalationsstufe bestimmen
            if tage >= 21:
                grund = "KEINE_ANTWORT_KRITISCH"
            elif tage >= 14:
                grund = "KEINE_ANTWORT_DRINGEND"
            else:
                grund = "KEINE_ANTWORT"

            email_text = generiere_email_text(mandant, "KEINE_ANTWORT")

            aktion = {
                "mandant": mandant,
                "typ":     "keine_antwort",
                "grund":   grund,
                "tage":    tage,
                "email_gesendet": False,
            }

            gesendet = self._entscheidung(mandant, grund, email_text, mode)
            aktion["email_gesendet"] = gesendet

            log.info(f"Keine-Antwort Check | {mandant} | {tage}d | gesendet={gesendet}")
            return aktion

        except Exception as e:
            log.error(f"Keine-Antwort Check Fehler für {mandant}: {e}")
            return None

    def _check_dokumente(self, mandant: str, daten: Dict,
                          mode: str) -> Optional[Dict]:
        """
        Prüft fehlende Dokumente und sendet Anforderungs-Email.
        Priorisiert nach Anzahl fehlender Dokumente.
        """
        try:
            docs = daten.get("fehlende_dokumente_liste", [])

            if not docs:
                return None

            email_text = generiere_email_text(mandant, "DOKUMENTE_FEHLEN", docs)
            grund      = "DOKUMENTE_FEHLEN"

            aktion = {
                "mandant":          mandant,
                "typ":              "dokumente",
                "grund":            grund,
                "fehlende_docs":    docs,
                "anzahl":           len(docs),
                "email_gesendet":   False,
            }

            gesendet = self._entscheidung(mandant, grund, email_text, mode)
            aktion["email_gesendet"] = gesendet

            return aktion

        except Exception as e:
            log.error(f"Dokumente Check Fehler für {mandant}: {e}")
            return None

    def _check_fristen(self, mandant: str, aufgaben: Dict,
                        grenze: int, mode: str) -> List[Dict]:
        """
        Prüft alle Fristen eines Mandanten.
        Eskalation nach Dringlichkeit: überfällig > morgen > N Tage.

        BUGFIX: Alter Code:
          - wurde doppelt aufgerufen (Verschwendung)
          - rief self._entscheidungen() auf (existiert nicht)
          - brach nach erstem Treffer ab (andere dringende Fristen ignoriert)
        """
        aktionen = []
        jetzt    = datetime.now()

        # Alle relevanten Aufgaben sammeln und sortieren
        relevante = []

        for aufgabe_id, a in aufgaben.items():
            if a.get("mandant") != mandant or a.get("erledigt"):
                continue
            try:
                frist      = datetime.strptime(a["frist"], "%Y-%m-%d")
                tage_bis   = (frist - jetzt).days

                if tage_bis <= grenze:
                    relevante.append((tage_bis, aufgabe_id, a))
            except (ValueError, KeyError):
                # Aufgabe mit ungültigem Datum loggen
                self.ds.log_eintrag(
                    f"WARNUNG | Ungültiges Datum in Aufgabe {aufgabe_id} für {mandant}"
                )
                continue

        # Nach Dringlichkeit sortieren (überfälligste zuerst)
        relevante.sort(key=lambda x: x[0])

        # Maximal 3 Fristen-Emails pro Mandant pro Check
        for tage_bis, aufgabe_id, a in relevante[:3]:
            try:
                if tage_bis < 0:
                    grund = "FRIST_UEBERFAELLIG"
                elif tage_bis == 0:
                    grund = "FRIST_HEUTE"
                elif tage_bis <= 1:
                    grund = "FRIST_MORGEN"
                else:
                    grund = "FRIST"

                email_text = generiere_email_text(mandant, "FRIST")

                aktion = {
                    "mandant":        mandant,
                    "typ":            "frist",
                    "grund":          grund,
                    "aufgabe_id":     aufgabe_id,
                    "beschreibung":   a.get("beschreibung", "?"),
                    "frist_datum":    a.get("frist"),
                    "tage_bis_frist": tage_bis,
                    "email_gesendet": False,
                }

                gesendet = self._entscheidung(mandant, grund, email_text, mode)
                aktion["email_gesendet"] = gesendet
                aktionen.append(aktion)

            except Exception as e:
                log.error(f"Fristen Check Fehler für {mandant} / {aufgabe_id}: {e}")
                continue

        return aktionen

    def _check_compliance_fristen(self) -> List[Dict]:
        """
        Prüft gesetzliche Steuerfristen für das aktuelle Jahr.
        Warnt wenn Fristen in den nächsten 14 Tagen anstehen.
        """
        jetzt    = datetime.now()
        warnungen = []
        fristen  = berechne_steuerfristen(jetzt.year)

        for f in fristen:
            try:
                datum = datetime.strptime(f["datum"], "%Y-%m-%d")
                tage  = (datum - jetzt).days

                if 0 <= tage <= 14:
                    warnungen.append({
                        "typ":       "compliance",
                        "frist_typ": f["typ"],
                        "datum":     f["datum"],
                        "tage":      tage,
                        "kategorie": f["kategorie"],
                        "warnung":   f"Gesetzliche Frist in {tage} Tagen: {f['typ']}"
                    })
                elif tage < 0:
                    warnungen.append({
                        "typ":       "compliance_ueberfaellig",
                        "frist_typ": f["typ"],
                        "datum":     f["datum"],
                        "tage":      tage,
                        "kategorie": f["kategorie"],
                        "warnung":   f"ÜBERFÄLLIG ({abs(tage)}d): {f['typ']}"
                    })
            except ValueError:
                continue

        return warnungen

    # ────────────────────────────────────────────────────────
    # ENTSCHEIDUNGS-LOGIK
    # ────────────────────────────────────────────────────────

    def _entscheidung(self, mandant: str, grund: str,
                       email_text: str, mode: str) -> bool:
        """
        Entscheidet basierend auf Automation-Mode ob/wie eine Aktion ausgeführt wird.

        Modi:
        - manuell:           Nur loggen, kein Auto-Versand
        - halbautomatisch:   Email vorbereiten + in Queue stellen
        - auto:              Direkt senden (wenn Email-Adresse vorhanden)

        BUGFIX: Alter Code fragte per input() — blockiert API-Betrieb komplett.
        BUGFIX: Methode hieß manchmal _entscheidungen() (Tippfehler).
        """
        try:
            # Email-Adresse prüfen
            mandanten = self.ds.hole_mandanten()
            m         = mandanten.get(mandant, {})
            hat_email  = bool(m.get("email"))

            if mode == "auto" and hat_email:
                # Direkt speichern + loggen (SMTP-Versand übernimmt api.py Auto-Agent)
                self._email_speichern(mandant, grund, email_text)
                log.info(f"AUTO | Email Queue | {mandant} | {grund}")
                return True

            elif mode == "halbautomatisch":
                # In Email-Queue stellen (Steuerberater genehmigt manuell)
                self._email_speichern(mandant, grund, email_text, status="wartend")
                log.info(f"HALB-AUTO | Email Queue | {mandant} | {grund}")
                return False  # Noch nicht gesendet

            else:  # manuell
                # Nur loggen — Steuerberater entscheidet selbst
                log.info(f"MANUELL | Vorschlag | {mandant} | {grund}")
                self.ds.log_eintrag(f"VORSCHLAG | {mandant} | {grund}")
                return False

        except Exception as e:
            log.error(f"Entscheidungs-Fehler für {mandant}: {e}")
            return False

    def _email_speichern(self, mandant: str, grund: str,
                          email_text: str, status: str = "gesendet") -> bool:
        """Email revisionssicher archivieren."""
        try:
            email_id = f"auto_{int(datetime.now().timestamp() * 1000)}"

            self.ds.email_speichern(email_id, {
                "id":      email_id,
                "mandant": mandant,
                "inhalt":  email_text,
                "zeit":    datetime.now().isoformat(),
                "typ":     grund,
                "status":  status,
                "auto":    True,
            })

            # Timeline-Eintrag
            self.ds.timeline_speichern(mandant, {
                "typ":    "auto_email",
                "grund":  grund,
                "inhalt": email_text[:200] + "..." if len(email_text) > 200 else email_text,
                "status": status,
            })

            # Kommunikations-Historie
            self.ds.kommunikation_hinzufuegen(mandant, {
                "typ":    "auto_email",
                "grund":  grund,
                "inhalt": email_text,
                "zeit":   datetime.now().isoformat(),
                "status": status,
            })

            self.ds.log_eintrag(f"EMAIL_ARCHIVIERT | {mandant} | {grund} | {status}")
            return True

        except Exception as e:
            log.error(f"Email-Speicher-Fehler für {mandant}: {e}")
            return False

    # ────────────────────────────────────────────────────────
    # WORKFLOW-AUTOMATISIERUNG (One-Click Workflows)
    # ────────────────────────────────────────────────────────

    def workflow_monatsabschluss(self, mandant: str, monat: int,
                                  jahr: int) -> Dict[str, Any]:
        """
        One-Click Monatsabschluss-Workflow.
        Erstellt alle Standardaufgaben für einen Monatsabschluss automatisch.
        """
        import uuid
        log.info(f"Workflow Monatsabschluss | {mandant} | {monat}/{jahr}")

        monat_str = f"{monat:02d}/{jahr}"
        erstellt  = []

        aufgaben_templates = [
            ("Belege vollständig prüfen",        14),
            ("Bankabstimmung durchführen",         7),
            ("Offene Posten klären",              10),
            ("Umsatzsteuer-Voranmeldung prüfen",   5),
            ("Lohnabrechnung prüfen",              7),
            ("Monatsabschluss buchen",             3),
            ("Report erstellen & versenden",       2),
        ]

        # Frist: letzter Tag des nächsten Monats
        if monat == 12:
            frist_dt = datetime(jahr + 1, 1, 31)
        else:
            import calendar
            letzter_tag = calendar.monthrange(jahr, monat + 1)[1]
            frist_dt    = datetime(jahr, monat + 1, letzter_tag)

        for beschreibung, puffer_tage in aufgaben_templates:
            aufgabe_frist = frist_dt - timedelta(days=puffer_tage)
            aufgabe_id    = str(uuid.uuid4())

            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": f"[{monat_str}] {beschreibung}",
                "frist":        aufgabe_frist.strftime("%Y-%m-%d"),
                "prioritaet":   "hoch",
                "kategorie":    "monatsabschluss",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "workflow":     "monatsabschluss",
            })
            erstellt.append(beschreibung)

        self.ds.log_eintrag(
            f"WORKFLOW_MONATSABSCHLUSS | {mandant} | {monat_str} | "
            f"{len(erstellt)} Aufgaben erstellt"
        )

        return {
            "status":          "ok",
            "mandant":         mandant,
            "zeitraum":        monat_str,
            "aufgaben_erstellt": len(erstellt),
            "aufgaben":        erstellt,
        }

    def workflow_jahresabschluss(self, mandant: str, jahr: int) -> Dict[str, Any]:
        """
        One-Click Jahresabschluss-Workflow.
        Automatisch alle Jahresabschluss-Aufgaben anlegen.
        """
        import uuid
        log.info(f"Workflow Jahresabschluss | {mandant} | {jahr}")

        aufgaben_templates = [
            ("Jahresinventur & Bestandsaufnahme",   "01-31"),
            ("Alle Belege prüfen & archivieren",     "02-15"),
            ("Abschreibungen berechnen",              "02-28"),
            ("Rückstellungen bilden",                 "03-15"),
            ("Jahresabschluss buchen",                "03-31"),
            ("Bilanz & GuV erstellen",                "04-15"),
            ("Steuererklärung vorbereiten",           "05-31"),
            ("Steuererklärung einreichen",            "07-31"),
            ("Jahresbericht an Mandanten",            "04-30"),
        ]

        erstellt = []
        folgejahr = jahr + 1

        for beschreibung, mm_dd in aufgaben_templates:
            aufgabe_id = str(uuid.uuid4())
            frist      = f"{folgejahr}-{mm_dd}"

            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": f"[JA {jahr}] {beschreibung}",
                "frist":        frist,
                "prioritaet":   "hoch",
                "kategorie":    "jahresabschluss",
                "erledigt":     False,
                "erstellt_am":  datetime.now().isoformat(),
                "workflow":     "jahresabschluss",
            })
            erstellt.append(beschreibung)

        self.ds.log_eintrag(
            f"WORKFLOW_JAHRESABSCHLUSS | {mandant} | {jahr} | "
            f"{len(erstellt)} Aufgaben erstellt"
        )

        return {
            "status":            "ok",
            "mandant":           mandant,
            "jahr":              jahr,
            "aufgaben_erstellt": len(erstellt),
            "aufgaben":          erstellt,
        }

    def workflow_neuer_mandant(self, mandant: str) -> Dict[str, Any]:
        """
        Onboarding-Workflow für neuen Mandanten.
        Alle Standard-Erstaufgaben automatisch anlegen.
        """
        import uuid
        log.info(f"Workflow Neuer Mandant | {mandant}")

        jetzt = datetime.now()

        aufgaben_templates = [
            ("Erstgespräch & Bedarfsanalyse",       7,  "hoch"),
            ("Vollmacht & Datenschutz unterzeichnen",14, "kritisch"),
            ("Steuerunterlagen Vorjahr anfordern",   21, "hoch"),
            ("DATEV-Stammdaten anlegen",             14, "hoch"),
            ("Bankverbindung hinterlegen",           14, "normal"),
            ("Bestehende Verträge prüfen",           30, "normal"),
            ("Erstberatung Steuerstrategie",         30, "hoch"),
            ("Mandantenportal Zugangsdaten senden",   7, "hoch"),
        ]

        erstellt = []

        for beschreibung, tage, prioritaet in aufgaben_templates:
            aufgabe_id  = str(uuid.uuid4())
            frist       = (jetzt + timedelta(days=tage)).strftime("%Y-%m-%d")

            self.ds.aufgabe_speichern(aufgabe_id, {
                "id":           aufgabe_id,
                "mandant":      mandant,
                "beschreibung": f"[Onboarding] {beschreibung}",
                "frist":        frist,
                "prioritaet":   prioritaet,
                "kategorie":    "onboarding",
                "erledigt":     False,
                "erstellt_am":  jetzt.isoformat(),
                "workflow":     "onboarding",
            })
            erstellt.append(beschreibung)

        # Willkommens-Email vorbereiten
        mandanten  = self.ds.hole_mandanten()
        m_daten    = mandanten.get(mandant, {})
        willkommen = (
            f"Sehr geehrte/r {mandant},\n\n"
            f"herzlich willkommen in unserer Kanzlei! Wir freuen uns, Sie als "
            f"neuen Mandanten begrüßen zu dürfen.\n\n"
            f"In den nächsten Tagen werden wir uns mit Ihnen in Verbindung "
            f"setzen, um alle notwendigen Unterlagen zu besprechen.\n\n"
            f"Mit freundlichen Grüßen\nIhre Steuerkanzlei"
        )

        self._email_speichern(mandant, "ONBOARDING_WILLKOMMEN", willkommen, "wartend")
        self.ds.log_eintrag(f"WORKFLOW_ONBOARDING | {mandant} | {len(erstellt)} Aufgaben")

        return {
            "status":            "ok",
            "mandant":           mandant,
            "aufgaben_erstellt": len(erstellt),
            "aufgaben":          erstellt,
            "email_vorbereitet": True,
        }

    # ────────────────────────────────────────────────────────
    # PREDICTIVE ANALYTICS
    # ────────────────────────────────────────────────────────

    def predictive_fristenbelastung(self, tage_vorschau: int = 30) -> Dict[str, Any]:
        """
        Vorausberechnung: Wie viele Fristen kommen in den nächsten N Tagen?
        Hilft dem Steuerberater, die Kapazität zu planen.
        """
        jetzt     = datetime.now()
        grenze    = jetzt + timedelta(days=tage_vorschau)
        aufgaben  = self.ds.hole_fristen()

        belastung_pro_woche: Dict[str, int] = {}
        kritische_fristen = []

        for a in aufgaben.values():
            if a.get("erledigt"):
                continue
            try:
                frist = datetime.strptime(a["frist"], "%Y-%m-%d")
                if jetzt <= frist <= grenze:
                    # Woche bestimmen
                    kw  = frist.isocalendar()[1]
                    key = f"KW{kw:02d}/{frist.year}"
                    belastung_pro_woche[key] = belastung_pro_woche.get(key, 0) + 1

                    tage = (frist - jetzt).days
                    if tage <= 3:
                        kritische_fristen.append({
                            "mandant":      a.get("mandant", "?"),
                            "beschreibung": a.get("beschreibung", "?"),
                            "frist":        a["frist"],
                            "tage":         tage,
                        })
            except (ValueError, KeyError):
                continue

        kritische_fristen.sort(key=lambda x: x["tage"])

        return {
            "vorschau_tage":       tage_vorschau,
            "gesamt_fristen":      sum(belastung_pro_woche.values()),
            "belastung_pro_woche": belastung_pro_woche,
            "kritische_fristen":   kritische_fristen,
            "generiert_am":        jetzt.isoformat(),
        }

    def predictive_umsatz_prognose(self) -> Dict[str, Any]:
        """
        Umsatz-Prognose basierend auf aktuellen Mandanten.
        Basis für Cashflow-Planung.
        """
        mandanten  = self.ds.hole_mandanten()
        aufgaben   = self.ds.hole_fristen()
        jetzt      = datetime.now()

        gesamt_umsatz  = sum(m.get("umsatz", 0) for m in mandanten.values())
        aktive         = sum(1 for m in mandanten.values() if m.get("aktiv", True))
        durchschnitt   = round(gesamt_umsatz / aktive, 2) if aktive else 0

        # Offene Aufgaben → ausstehende Arbeit → Umsatz-Risiko
        offene_aufgaben = sum(1 for a in aufgaben.values() if not a.get("erledigt"))
        ueberfaellig    = sum(
            1 for a in aufgaben.values()
            if not a.get("erledigt") and _ist_ueberfaellig(a, jetzt)
        )

        risiko_score = round(ueberfaellig / max(1, offene_aufgaben) * 100, 1)

        return {
            "gesamt_jahresumsatz":     round(gesamt_umsatz, 2),
            "monatsumsatz_erwartet":   round(gesamt_umsatz / 12, 2),
            "aktive_mandanten":        aktive,
            "durchschnittsumsatz":     durchschnitt,
            "offene_aufgaben":         offene_aufgaben,
            "ueberfaellige_aufgaben":  ueberfaellig,
            "risiko_score_prozent":    risiko_score,
            "hinweis": (
                "Hohes Risiko — Überfällige Aufgaben prüfen!" if risiko_score > 30
                else "Risiko im normalen Bereich"
            ),
            "generiert_am": jetzt.isoformat(),
        }

    # ────────────────────────────────────────────────────────
    # REPORTING
    # ────────────────────────────────────────────────────────

    def erstelle_tagesbericht(self) -> str:
        """
        Automatischer Tagesbericht für den Steuerberater.
        Zusammenfassung aller wichtigen Ereignisse des Tages.
        """
        mandanten = self.ds.hole_mandanten()
        aufgaben  = self.ds.hole_fristen()
        jetzt     = datetime.now()

        analyse   = self.run_full_analysis()
        prognose  = self.predictive_fristenbelastung(7)

        kritisch  = [m for m in analyse.get("mandanten", []) if m.get("status") == "KRITISCH"]
        wichtig   = [m for m in analyse.get("mandanten", []) if m.get("status") == "WICHTIG"]

        bericht = f"""
KANZLEI AI — TAGESBERICHT
{jetzt.strftime('%A, %d. %B %Y')}
{'=' * 40}

ÜBERSICHT
  Mandanten gesamt:    {len(mandanten)}
  Kritische Mandanten: {len(kritisch)}
  Wichtige Mandanten:  {len(wichtig)}
  Fristen diese Woche: {prognose['gesamt_fristen']}

"""
        if kritisch:
            bericht += "SOFORTIGER HANDLUNGSBEDARF\n"
            for m in kritisch[:5]:
                bericht += f"  ▶ {m['mandant']} (Score: {int(m.get('score', 0)):,})\n"
                for e in m.get("entscheidungen", [])[:2]:
                    bericht += f"    → {e.get('text', '')}\n"
            bericht += "\n"

        if prognose["kritische_fristen"]:
            bericht += "KRITISCHE FRISTEN (nächste 3 Tage)\n"
            for f in prognose["kritische_fristen"][:5]:
                bericht += f"  ▶ {f['mandant']}: {f['beschreibung']} ({f['tage']}d)\n"
            bericht += "\n"

        bericht += f"{'=' * 40}\nGeneriert: {jetzt.strftime('%H:%M Uhr')}\n"

        self.ds.log_eintrag("TAGESBERICHT_ERSTELLT")
        return bericht.strip()


# ────────────────────────────────────────────────────────────
# HILFSFUNKTIONEN (Modul-Level)
# ────────────────────────────────────────────────────────────

def _ist_ueberfaellig(aufgabe: Dict, jetzt: datetime) -> bool:
    """Prüft ob eine Aufgabe überfällig ist."""
    try:
        frist = datetime.strptime(aufgabe["frist"], "%Y-%m-%d")
        return frist < jetzt
    except (ValueError, KeyError):
        return False