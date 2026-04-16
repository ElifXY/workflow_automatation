# Production Deployment (Hetzner/AWS)

## 1) Server vorbereiten

- Ubuntu 24.04 LTS
- Docker + Docker Compose Plugin installieren
- DNS setzen: `api.<domain>`, `<domain>`

## 2) Environment setzen

1. `.env.example` nach `.env` kopieren.
2. Produktionswerte setzen (`JWT_SECRET`, `STRIPE_*`, `POSTGRES_*`, `REDIS_PASSWORD`).
3. `ENVIRONMENT=production`, `FORCE_HTTPS=1`, `SECURITY_HEADERS=1`.

## 3) Stack starten

```bash
docker compose up -d --build
```

## 4) SSL aktivieren (optional über Profil)

```bash
docker compose --profile ssl up -d certbot
```

## 5) Verifikation

- `GET /health` muss `healthy` liefern
- `GET /ready` muss `ready=true` liefern
- Login testen, Dashboard testen, E-Mail-Outbox prüfen
- Go-Live Check ausführen:

```bash
python scripts/go_live_check.py --base-url http://127.0.0.1:8000 --token <JWT_TOKEN>
```

## 6) Betriebsroutinen

- Tägliche DB-Backups (PostgreSQL Dump)
- Error Monitoring (Sentry) aktivieren
- Log-Rotation für NGINX + API-Logs
- Quartalsweise Recovery-Test durchführen
- CI aktivieren: `.github/workflows/go-live-check.yml` muss bei jedem PR grün sein
