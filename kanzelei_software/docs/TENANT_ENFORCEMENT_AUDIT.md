# Tenant Enforcement Audit

## Static Checks
- `auth_guard_middleware`: OK
- `_AUTH_EXEMPT_PREFIXES`: OK
- `X-Organization-Id`: OK
- `X-Kanzlei-Id`: OK
- `Cross-tenant Payload blockiert`: OK
- `Cross-tenant Query blockiert`: OK
- `Cross-tenant Header blockiert`: OK

## Runtime Checks
- runtime checks failed to execute: USE_POSTGRES_DATA ist gesetzt: DATABASE_URL muss postgresql://… oder postgres://… sein (Schema scripts/postgres_bootstrap.sql, Daten scripts/migrate_sqlite_to_postgres.py).
