# ============================================================
# KANZLEI AI — ML BUCHUNGSASSISTENT v1.0
# Datei: core/ml_buchung.py
#
# Nicht nur Beleg lesen — VERSTEHEN und LERNEN.
#
# Was anders ist als normaler OCR:
#
# Normal-OCR: "Rechnung von Amazon, €47,90"
#             → Kategorie: "sonstiges"
#
# ML-Assistent: "Rechnung von Amazon, €47,90"
#   Analysiert: Warenkorb-Inhalt (wenn sichtbar)
#   Kontext: Was kauft dieser Mandant bei Amazon?
#   Pattern: Letzten 5 Amazon-Belege dieser Kanzlei: 60% Bürobedarf
#   Mandant: Bäckerei → Amazon-Kauf = wahrscheinlich Verpackung/Küchengeräte
#   Entscheidung: "Büromaterial" mit 87% Konfidenz
#
# Lernmechanismus:
#   → Jede BESTÄTIGTE Buchung wird gespeichert (Trainings-Datum)
#   → Pattern-Matching: Gleicher Lieferant + ähnlicher Betrag → gleiche Kategorie
#   → Branchenspezifisch: Bäckerei-Patterns ≠ IT-Firma-Patterns
#   → Kanzleispezifisch: Jede Kanzlei hat eigene Muster
#
# KEIN Cloud-ML nötig — lokaler SQLite-basierter Pattern-Matcher
# ============================================================

import sqlite3
import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

log = logging.getLogger("kanzlei_ml_buchung")

ML_DB_PATH = os.path.join("data", "ml_buchungen.db")


class MLBuchungsassistent:
    """
    Lokaler lernender Buchungsassistent.
    Kein Cloud-ML nötig — Pattern-Matching aus eigenen Buchungen.
    """

    def __init__(self):
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        os.makedirs("data", exist_ok=True)
        conn = sqlite3.connect(ML_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Datenbank initialisieren."""
        with self._conn() as conn:
            conn.executescript("""
            -- Bestätigte Buchungen (Trainingsdaten)
            CREATE TABLE IF NOT EXISTS buchungen (
                id            TEXT PRIMARY KEY,
                lieferant     TEXT NOT NULL,
                lieferant_norm TEXT NOT NULL,  -- normalisiert für Matching
                betrag        REAL,
                kategorie     TEXT NOT NULL,
                skr03_konto   TEXT,
                branche       TEXT,            -- Branche des Mandanten
                mandant       TEXT,
                inhalt_stichworte TEXT,         -- Stichworte aus Beleg-Inhalt (JSON)
                mwst_satz     INTEGER,
                vorsteuer     INTEGER,          -- 1/0
                bestaetigt_am TEXT,
                quelle        TEXT              -- 'manuell' | 'ki' | 'pattern'
            );

            -- Aggregierte Patterns (für schnelles Matching)
            CREATE TABLE IF NOT EXISTS patterns (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                lieferant_norm  TEXT NOT NULL,
                kategorie       TEXT NOT NULL,
                skr03_konto     TEXT,
                branche         TEXT,
                anzahl          INTEGER DEFAULT 1,
                letzte_nutzung  TEXT,
                konfidenz       REAL DEFAULT 0.5,
                UNIQUE(lieferant_norm, kategorie, branche)
            );

            -- Lieferant-Kontext (was kauft man typischerweise dort?)
            CREATE TABLE IF NOT EXISTS lieferant_kontext (
                lieferant_norm  TEXT PRIMARY KEY,
                stichworte      TEXT,   -- JSON: häufigste Stichworte
                kategorien      TEXT,   -- JSON: Kategorie → Anzahl
                aktualisiert_am TEXT
            );

            -- Branchenspezifische Regeln
            CREATE TABLE IF NOT EXISTS branchenregeln (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                branche     TEXT NOT NULL,
                lieferant   TEXT NOT NULL,  -- Teilstring reicht
                kategorie   TEXT NOT NULL,
                begruendung TEXT,
                UNIQUE(branche, lieferant)
            );

            CREATE INDEX IF NOT EXISTS idx_buchungen_lieferant ON buchungen(lieferant_norm);
            CREATE INDEX IF NOT EXISTS idx_patterns_lieferant  ON patterns(lieferant_norm);
            """)

            # Standard-Branchenregeln einspielen
            self._init_branchenregeln(conn)

    def _init_branchenregeln(self, conn):
        """Vordefinierte Branchenregeln — das Basis-Wissen."""
        regeln = [
            # Alle Branchen
            ("*",          "amazon",       "buero",         "Amazon Standard → Bürobedarf"),
            ("*",          "amazon",       "material",       "Amazon → auch Handelswaren möglich"),
            ("*",          "ebay",         "material",       "eBay → typisch Waren"),
            ("*",          "tankstelle",   "benzin",         "Tankstellen → Kraftstoff"),
            ("*",          "aral",         "benzin",         "Aral = Tankstelle"),
            ("*",          "shell",        "benzin",         "Shell = Tankstelle"),
            ("*",          "esso",         "benzin",         "Esso = Tankstelle"),
            ("*",          "bahn",         "reise",          "Deutsche Bahn → Reisekosten"),
            ("*",          "lufthansa",    "reise",          "Lufthansa → Reisekosten"),
            ("*",          "hotel",        "reise",          "Hotel → Reisekosten"),
            ("*",          "hilton",       "reise",          "Hilton = Hotel"),
            ("*",          "marriott",     "reise",          "Marriott = Hotel"),
            ("*",          "office",       "buero",          "Office-Produkte → Büro"),
            ("*",          "staples",      "buero",          "Staples = Bürobedarf"),
            ("*",          "telekom",      "telefon",        "Telekom → Telefon/Internet"),
            ("*",          "vodafone",     "telefon",        "Vodafone → Telefon"),
            ("*",          "o2",           "telefon",        "O2 → Telefon"),
            ("*",          "datev",        "software",       "DATEV → Softwarekosten"),
            ("*",          "microsoft",    "software",       "Microsoft → Software"),
            ("*",          "google",       "software",       "Google → Software/Werbung"),
            ("*",          "meta",         "werbung",        "Meta/Facebook → Werbung"),
            # Branchenspezifisch
            ("Gastronomie / Lebensmittel", "amazon",   "material",  "Bäckerei: Amazon → Verpackung/Geräte"),
            ("Gastronomie / Lebensmittel", "metro",    "material",  "Bäckerei: Metro → Lebensmittel"),
            ("Gastronomie / Lebensmittel", "rewe",     "material",  "Gastronomie: REWE → Handelswaren"),
            ("IT / Software",              "amazon",   "hardware",  "IT-Firma: Amazon → Hardware"),
            ("IT / Software",              "amazon web","software",  "IT-Firma: AWS → Cloud"),
            ("Immobilien",                 "amazon",   "buero",     "Immobilien: Amazon → Bürobedarf"),
            ("Kfz-Handel",                 "amazon",   "material",  "KFZ: Amazon → Ersatzteile/Material"),
        ]
        for branche, lieferant, kategorie, begruendung in regeln:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO branchenregeln (branche, lieferant, kategorie, begruendung)
                    VALUES (?, ?, ?, ?)""", (branche, lieferant, kategorie, begruendung))
            except Exception:
                pass

    def _normalisiere(self, text: str) -> str:
        """Lieferantennamen normalisieren für robustes Matching."""
        import re
        t = text.lower().strip()
        # Rechtliche Formen entfernen
        for suffix in [" gmbh", " ag", " kg", " ohg", " ug", " mbh", " co.", " & co", " se", " inc", " ltd", " llc"]:
            t = t.replace(suffix, "")
        # Sonderzeichen
        t = re.sub(r"[^\w\s]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t[:50]  # Max 50 Zeichen

    # ── Hauptfunktion: Buchungsvorschlag generieren ───────────
    def kategorisiere(
        self,
        lieferant:   str,
        betrag:      float,
        dateiname:   str = "",
        inhalt:      str = "",
        branche:     str = "",
        mandant:     str = "",
    ) -> Dict[str, Any]:
        """
        Generiert einen Buchungsvorschlag basierend auf:
        1. Branchenregeln (vordefiniert)
        2. Eigenen Buchungs-Patterns (aus bestätigten Buchungen)
        3. Lieferant-Kontext (Stichworte aus Beleg-Inhalt)
        4. Betrag-Analyse

        Returns:
            {kategorie, skr03_konto, konfidenz, methode, begruendung}
        """
        lieferant_norm = self._normalisiere(lieferant)
        if not lieferant_norm:
            lieferant_norm = self._normalisiere(dateiname)

        ergebnisse = []

        # 1. Branchenregeln prüfen
        branchenregel = self._prüfe_branchenregeln(lieferant_norm, branche)
        if branchenregel:
            ergebnisse.append({
                "kategorie":    branchenregel["kategorie"],
                "konfidenz":    0.75,
                "methode":      "branchenregel",
                "begruendung":  branchenregel["begruendung"],
            })

        # 2. Eigene Patterns
        pattern_result = self._prüfe_patterns(lieferant_norm, branche, mandant)
        if pattern_result:
            ergebnisse.append(pattern_result)

        # 3. Inhalts-Analyse (Stichworte)
        if inhalt:
            inhalt_result = self._analysiere_inhalt(inhalt, lieferant_norm)
            if inhalt_result:
                ergebnisse.append(inhalt_result)

        # 4. Betrag-basierte Hinweise
        betrag_hinweis = self._analysiere_betrag(betrag, lieferant_norm)
        if betrag_hinweis:
            ergebnisse.append(betrag_hinweis)

        # Bestes Ergebnis auswählen
        if not ergebnisse:
            return {
                "kategorie":   "sonstiges",
                "skr03_konto": "4980",
                "konfidenz":   0.3,
                "methode":     "fallback",
                "begruendung": "Keine Patterns gefunden — bitte manuell kategorisieren",
            }

        # Nach Konfidenz sortieren, Pattern-Ergebnisse bevorzugen
        ergebnisse.sort(key=lambda x: (
            1 if x["methode"] == "pattern_match" else 0,
            x["konfidenz"]
        ), reverse=True)

        bestes = ergebnisse[0]

        # SKR03-Konto aus Kategorie-Tabelle
        from core.beleg_service import SKR03_KATEGORIEN
        konto_info = SKR03_KATEGORIEN.get(bestes["kategorie"], SKR03_KATEGORIEN["sonstiges"])
        bestes["skr03_konto"]  = konto_info["soll"]
        bestes["skr03_haben"]  = konto_info["haben"]
        bestes["kategorie_name"] = konto_info["name"]

        return bestes

    def _prüfe_branchenregeln(self, lieferant_norm: str, branche: str) -> Optional[Dict]:
        with self._conn() as conn:
            # Branchenspezifische Regel zuerst
            row = conn.execute("""
                SELECT * FROM branchenregeln
                WHERE (branche = ? OR branche = '*')
                  AND ? LIKE '%' || lieferant || '%'
                ORDER BY CASE WHEN branche = ? THEN 0 ELSE 1 END
                LIMIT 1""", (branche, lieferant_norm, branche)).fetchone()
            return dict(row) if row else None

    def _prüfe_patterns(
        self, lieferant_norm: str, branche: str, mandant: str
    ) -> Optional[Dict]:
        """Pattern-Matching aus bestätigten Buchungen."""
        with self._conn() as conn:
            # Exakter Match zuerst, dann Teilmatch
            row = conn.execute("""
                SELECT kategorie, skr03_konto, SUM(anzahl) as gesamt, AVG(konfidenz) as konf
                FROM patterns
                WHERE (lieferant_norm = ? OR ? LIKE '%' || lieferant_norm || '%')
                  AND (branche = ? OR branche IS NULL OR branche = '')
                GROUP BY kategorie, skr03_konto
                ORDER BY gesamt DESC, konf DESC
                LIMIT 1""", (lieferant_norm, lieferant_norm, branche)).fetchone()

            if not row or row["gesamt"] == 0:
                return None

            # Konfidenz: mehr Buchungen = höhere Konfidenz
            basis_konfidenz = min(0.95, 0.5 + row["gesamt"] * 0.05)
            return {
                "kategorie":   row["kategorie"],
                "konfidenz":   basis_konfidenz,
                "methode":     "pattern_match",
                "begruendung": f"Gelernt aus {row['gesamt']} bestätigten Buchungen",
            }

    def _analysiere_inhalt(self, inhalt: str, lieferant_norm: str) -> Optional[Dict]:
        """Stichworte aus Beleg-Inhalt analysieren."""
        inhalt_lower = inhalt.lower()

        # Stichworte → Kategorien
        stichworte_mapping = {
            "büropapier":    ("buero",        0.88),
            "druckerpatronen": ("buero",      0.90),
            "toner":         ("buero",        0.90),
            "ordner":        ("buero",        0.85),
            "stift":         ("buero",        0.80),
            "laptop":        ("hardware",     0.92),
            "monitor":       ("hardware",     0.92),
            "tastatur":      ("hardware",     0.85),
            "server":        ("hardware",     0.90),
            "kraftstoff":    ("benzin",       0.95),
            "diesel":        ("benzin",       0.95),
            "super":         ("benzin",       0.80),
            "übernachtung":  ("reise",        0.92),
            "zimmer":        ("reise",        0.85),
            "flug":          ("reise",        0.92),
            "bahnticket":    ("reise",        0.95),
            "mehl":          ("material",     0.90),
            "zucker":        ("material",     0.90),
            "verpackung":    ("material",     0.85),
            "personal":      ("personal",     0.80),
            "gehalt":        ("personal",     0.90),
            "versicherung":  ("versicherung", 0.90),
            "miete":         ("miete",        0.92),
            "werbung":       ("werbung",      0.85),
            "anzeige":       ("werbung",      0.80),
            "schulung":      ("weiterbildung",0.88),
            "seminar":       ("weiterbildung",0.88),
        }

        for stichwort, (kategorie, konfidenz) in stichworte_mapping.items():
            if stichwort in inhalt_lower:
                return {
                    "kategorie":   kategorie,
                    "konfidenz":   konfidenz,
                    "methode":     "inhalts_analyse",
                    "begruendung": f"Stichwort '{stichwort}' im Beleg erkannt",
                }
        return None

    def _analysiere_betrag(self, betrag: float, lieferant_norm: str) -> Optional[Dict]:
        """Betrag-basierte Hinweise (z.B. sehr kleiner Betrag = wahrscheinlich Büro)."""
        if betrag <= 5.0:
            return {
                "kategorie":   "buero",
                "konfidenz":   0.55,
                "methode":     "betrag_analyse",
                "begruendung": f"Kleiner Betrag (€{betrag:.2f}) → wahrscheinlich Büroartikel",
            }
        elif betrag >= 1000.0 and "amazon" in lieferant_norm:
            return {
                "kategorie":   "hardware",
                "konfidenz":   0.65,
                "methode":     "betrag_analyse",
                "begruendung": f"Amazon-Kauf >€1000 → wahrscheinlich Hardware",
            }
        return None

    # ── Feedback-Loop: Bestätigte Buchung lernen ─────────────
    def buchung_bestätigt(
        self,
        lieferant:   str,
        betrag:      float,
        kategorie:   str,
        skr03_konto: str,
        branche:     str = "",
        mandant:     str = "",
        inhalt:      str = "",
        mwst_satz:   int = 19,
        vorsteuer:   bool = True,
    ):
        """
        Bestätigte Buchung als Trainingsdaten speichern.
        Das ist der Kern des Lernens — jede Bestätigung macht das System besser.
        """
        lieferant_norm = self._normalisiere(lieferant)
        buchung_id     = __import__("uuid").uuid4().hex

        # Stichworte aus Inhalt extrahieren
        stichworte = []
        if inhalt:
            words = [w for w in inhalt.lower().split() if len(w) > 4]
            stichworte = list(set(words))[:20]

        with self._conn() as conn:
            # Buchung speichern
            conn.execute("""
                INSERT OR REPLACE INTO buchungen
                (id, lieferant, lieferant_norm, betrag, kategorie, skr03_konto,
                 branche, mandant, inhalt_stichworte, mwst_satz, vorsteuer, bestaetigt_am, quelle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (buchung_id, lieferant, lieferant_norm, betrag, kategorie, skr03_konto,
                 branche, mandant, json.dumps(stichworte), mwst_satz, int(vorsteuer),
                 datetime.now().isoformat(), "benutzer")
            )

            # Pattern aktualisieren
            conn.execute("""
                INSERT INTO patterns (lieferant_norm, kategorie, skr03_konto, branche, anzahl, letzte_nutzung, konfidenz)
                VALUES (?, ?, ?, ?, 1, ?, 0.7)
                ON CONFLICT(lieferant_norm, kategorie, branche) DO UPDATE SET
                  anzahl         = anzahl + 1,
                  letzte_nutzung = excluded.letzte_nutzung,
                  konfidenz      = MIN(0.95, konfidenz + 0.03)""",
                (lieferant_norm, kategorie, skr03_konto, branche or "",
                 datetime.now().isoformat())
            )

            # Lieferant-Kontext aktualisieren
            existing = conn.execute(
                "SELECT * FROM lieferant_kontext WHERE lieferant_norm = ?",
                (lieferant_norm,)
            ).fetchone()

            if existing:
                kat_dict = json.loads(existing["kategorien"] or "{}")
                kat_dict[kategorie] = kat_dict.get(kategorie, 0) + 1
                stich_dict = json.loads(existing["stichworte"] or "[]")
                stich_dict = list(set(stich_dict + stichworte))[:50]
                conn.execute("""
                    UPDATE lieferant_kontext SET kategorien=?, stichworte=?, aktualisiert_am=?
                    WHERE lieferant_norm=?""",
                    (json.dumps(kat_dict), json.dumps(stich_dict),
                     datetime.now().isoformat(), lieferant_norm)
                )
            else:
                conn.execute("""
                    INSERT INTO lieferant_kontext (lieferant_norm, stichworte, kategorien, aktualisiert_am)
                    VALUES (?, ?, ?, ?)""",
                    (lieferant_norm, json.dumps(stichworte),
                     json.dumps({kategorie: 1}), datetime.now().isoformat())
                )

        log.info(f"ML-Training: {lieferant} → {kategorie} (gespeichert)")

    # ── Statistiken ───────────────────────────────────────────
    def statistiken(self) -> Dict:
        with self._conn() as conn:
            buchungen = conn.execute("SELECT COUNT(*) as n FROM buchungen").fetchone()["n"]
            patterns  = conn.execute("SELECT COUNT(*) as n FROM patterns").fetchone()["n"]
            lieferanten = conn.execute("SELECT COUNT(*) as n FROM lieferant_kontext").fetchone()["n"]

            top_lieferanten = conn.execute("""
                SELECT lieferant_norm, SUM(anzahl) as gesamt
                FROM patterns GROUP BY lieferant_norm
                ORDER BY gesamt DESC LIMIT 5""").fetchall()

        return {
            "trainings_buchungen": buchungen,
            "patterns":            patterns,
            "bekannte_lieferanten":lieferanten,
            "top_lieferanten":     [dict(r) for r in top_lieferanten],
            "lern_status":         "aktiv" if buchungen > 0 else "noch keine Trainingsdaten",
            "hinweis": f"Nach {buchungen} Buchungen mit {lieferanten} Lieferanten gelernt",
        }

    def top_lieferanten(self) -> List[Dict]:
        """Alle bekannten Lieferanten mit ihren häufigsten Kategorien."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT lk.lieferant_norm, lk.kategorien,
                       SUM(p.anzahl) as buchungen_gesamt
                FROM lieferant_kontext lk
                LEFT JOIN patterns p ON p.lieferant_norm = lk.lieferant_norm
                GROUP BY lk.lieferant_norm
                ORDER BY buchungen_gesamt DESC LIMIT 50""").fetchall()

        result = []
        for r in rows:
            try:
                kategorien = json.loads(r["kategorien"] or "{}")
                haupt_kat  = max(kategorien, key=kategorien.get) if kategorien else "?"
            except Exception:
                haupt_kat = "?"

            result.append({
                "lieferant":       r["lieferant_norm"],
                "hauptkategorie":  haupt_kat,
                "buchungen":       r["buchungen_gesamt"] or 0,
            })
        return result