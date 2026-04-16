# Hardening Final Status

Stand: 2026-04-13

## Ergebnis (Kurzfassung)

- `_load/_save` in produktiven Core-Services: **0 Treffer**
- Runtime-JSON-Dateien unter `data/`: **0 Dateien**
- Repository-Policy-Check: **pass**
- Full-Hardening-Audit: **pass**

Damit ist die vorherige Hybrid-Problematik (`DB + JSON-File-Runtime`) im aktiven Core-Pfad entfernt.

## Was final gehärtet wurde

- `api.py`: direkte `_load/_save`-Nutzung entfernt und auf explizite Services/Settings umgestellt.
- Core-Services (`rechnungs_service`, `beleg_service`, `workflow_builder`, `team_service`, `proaktiver_bot`, `autonomer_steuerfall`, `finanzierung_service`, `lohn_service`, `profit_monitor`) auf explizite `DatenSpeicher`-Methoden refaktoriert.
- `core/daten_speicher.py`: explizite Domain-Methoden eingeführt (`*_liste`, `*_holen`, `*_speichern`) und `exportiere_json()` ohne `_load` umgesetzt.

## Verbleibende 1%-Restpunkte (technisch sauber, aber strategisch wichtig)

Diese Punkte sind **nicht** mehr JSON-File-Runtime, aber weiterhin als kompatible JSON-Payload in SQL gespeichert:

- `compat::belege`
- `compat::rechnungen`
- `compat::rechnungs_zaehler`
- `compat::bot_fragen`
- `compat::steuerfaelle`
- `compat::finanzierungen`
- `compat::workflow_regeln`
- `compat::workflow_runs`
- `compat::zeiterfassung`
- `compat::lohnabrechnung`

Bewertung:
- Kurzfristig stabil und produktiv nutzbar
- Mittelfristig für hohe Skalierung weniger ideal als eigene normalisierte Tabellen pro Domain

## Next Cut (empfohlen)

1. Eigene SQL-Tabellen für die zehn `compat::*`-Domänen anlegen.
2. `DatenSpeicher`-Methoden auf diese Tabellen umstellen (read/write).
3. Migrationsscript: `compat::*` Daten in neue Tabellen überführen.
4. Fallback-Reads für eine Übergangsphase (Feature-Flag), danach entfernen.
5. `compat::*`-Keys final löschen.

## Go-Live-Bewertung

- Architekturhärte gegenüber dem Ausgangszustand: **deutlich erhöht**
- Risiko "JSON-Dateien als Runtime-Datenquelle": **geschlossen**
- Nächste Engstelle für SaaS-Skalierung: **Domain-Normalisierung statt `compat::*` JSON in SQL**

