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
- `auth_required`: status=401, expected=401, result=OK, error=Login erforderlich
- `header_mismatch`: status=403, expected=403, result=OK, error=Cross-tenant Header blockiert
- `query_mismatch`: status=403, expected=403, result=OK, error=Cross-tenant Query blockiert
- `payload_mismatch_nested`: status=403, expected=403, result=OK, error=Cross-tenant Payload blockiert
