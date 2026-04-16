# PostgreSQL Migration Guide

Diese Anleitung macht den Wechsel von SQLite auf PostgreSQL reproduzierbar.

## 1) Ziel-Datenbank vorbereiten

1. PostgreSQL Datenbank erstellen.
2. Schema bootstrap ausführen:

```bash
psql "postgresql://USER:PASS@HOST:5432/DB" -f scripts/postgres_bootstrap.sql
```

## 2) Abhaengigkeiten installieren

```bash
pip install -r requirements.txt
```

## 3) Daten migrieren

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite data/kanzlei.db \
  --pg "postgresql://USER:PASS@HOST:5432/DB"
```

## 4) Smoke-Checks

- Benutzerzahl und Mandantenzahl vergleichen.
- Letzte 20 Audit-Events vergleichen.
- Einloggen + Dashboard + E-Mail Queue testen.

## 5) Go-Live Empfehlung

- SQLite in Read-Only setzen.
- Finalen Delta-Import ausfuehren.
- App-Konfiguration auf PostgreSQL umstellen.
- Monitoring fuer `/health`, `/ready` und Fehlerquote aktivieren.
