# Go-Live Security Checklist

Diese Checkliste ist die verbindliche Reihenfolge fuer produktiven Rollout.

## 1) Basisschutz nachweisen (Pflicht vor Features)

- `python scripts/repo_policy_check.py`
- Erwartung: **pass**
- Enthaltene Pflicht-Gates:
  - Tenant Guard Policy
  - Tenant AST Policy
  - Security Baseline Gate (RBAC + Tenant-Isolation + Invite-Isolation + Runtime-Gate)
  - Feature Activation Gate

## 2) Daten-Trennung und Zugriff pruefen (Pflicht)

- `python scripts/security_baseline_gate.py`
- Erwartung: **pass**
- Nachweis-Artefakt wird erstellt:
  - `artifacts/security_baseline_pass.json`

## 2b) Login/JWT End-to-End pruefen (Pflicht)

- Login:
  - `curl -X POST http://localhost:8000/api/login -H "Content-Type: application/json" -d "{\"email\":\"test@test.de\",\"password\":\"123456\"}"`
- Erwartung:
  - `access_token` vorhanden
  - `token_type` = `bearer`
- Protected probe:
  - `curl http://localhost:8000/api/me -H "Authorization: Bearer <TOKEN>"`
- Erwartung:
  - `200` und Userdaten (`id`, `email`, `tenant_id`)

## 3) Advanced Features standardmaessig gesperrt lassen

- Standard: `ENABLE_ADVANCED_FEATURES` **nicht** setzen (oder `0`)
- Erwartung:
  - Advanced-Domaenen liefern `503` bis Baseline + Freigabe

## 4) Erst dann Features aktivieren

- Voraussetzung:
  - `artifacts/security_baseline_pass.json` vorhanden, valide, frisch
- Aktivierung:
  - `ENABLE_ADVANCED_FEATURES=1`
  - optional: `SECURITY_BASELINE_MAX_AGE_HOURS=24` (oder strenger)
- Verifikation:
  - `python scripts/feature_activation_gate.py`
  - Erwartung: **Feature activation gate passed.**

## 5) Produktiv-Sicherheitsmindeststandard

- `ENVIRONMENT=production`
- Starkes `JWT_SECRET` (>= 48 Zeichen, kein Dev-Muster)
- Starkes `API_GATEWAY_KEY` (>= 32 Zeichen)
- Keine Dev-Default-DB-Passwoerter
- TLS/HTTPS aktiv
- CORS nur erlaubte Origins

## 6) Release-Stop-Kriterien

Sofortiger Stopp, wenn eines zutrifft:

- irgendein Gate ist rot
- Tenant-Isolation testet nicht mehr sauber
- Auth/Role-Checks liefern unerwartete 2xx
- Feature-Gate laesst Advanced-Domaenen ohne Nachweis durch

