# 13/13 SaaS Todo Status

## 1) Cleanup
- venv-Verzeichnisse entfernt
- `.gitignore` für `.venv/`, `venv/`, `__pycache__/`, `.env`, `node_modules/`, `*.log` gesetzt

## 2) JSON als Datenbank entfernen
- Produktive JSON-Runtime-Daten entfernt
- Settings auf DB-Storage umgestellt
- JSON nur noch für Konfig/Assets erlaubt

## 3) PostgreSQL einbauen
- Docker-Postgres Service vorhanden
- `DATABASE_URL` in prod erzwungen

## 4) DB-Struktur (Minimal Required)
- SQLAlchemy-Modelle vorhanden:
  - `organizations`
  - `users`
  - `mandanten`
  - `workflows`
  - `logs`

## 5) Multi-Tenant erzwingen
- globale Auth-Guard Middleware aktiv
- Cross-tenant Payload Checks blockieren Schreibzugriffe

## 6) Auth-System
- Login/Register vorhanden
- Passworthashing auf bcrypt umgestellt (mit Legacy-Fallback)

## 7) Rollen
- ADMIN/MITARBEITER Mapping vorhanden
- RBAC aktiv

## 8) API absichern
- globale Auth-Middleware plus Route-Dependencies

## 9) Server-Setup
- Bootstrap-Dateien für Hetzner/AWS vorhanden (`infra/`)

## 10) Deployment Setup
- Docker Compose + NGINX + SSL-Flow + Postgres angebunden

## 11) Stripe
- Billing/Stripe-Webhooks und Sperr-/Aktivlogik vorhanden

## 12) Frontend UX
- Dashboard/Mandanten/Automationen vorhanden
- Readiness-Header integriert

## 13) Logs sichtbar
- Audit- und Aktivitätslog-Endpunkte vorhanden
- Frontend nutzt Audit/Analytics Ansichten
