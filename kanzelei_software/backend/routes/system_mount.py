"""System- und API-v1-Meta-Routen (aus ``api.py`` ausgelagert)."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI

from backend.deps import get_current_user


def attach_system_routes(app: FastAPI) -> None:
    """Wird erst aufgerufen, wenn ``api`` vollständig importiert ist (Lazy ``import api``)."""
    import api as root

    @app.get("/", tags=["System"])
    def root():
        """Öffentlicher Status — keine Mandanten- oder Aufgaben-Zahlen (Datenschutz)."""
        return {
            "name": "Kanzlei Automation API",
            "version": "3.0.0",
            "status": "running",
            "docs": "/docs",
            "intro": "/api/v1/introduction",
            "timestamp": datetime.now().isoformat(),
        }

    @app.get("/health", tags=["System"])
    def health():
        try:
            root.ds.hole_mandanten()
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            from fastapi import HTTPException

            raise HTTPException(503, f"Datenspeicher nicht erreichbar: {e}")

    @app.get("/ready", tags=["System"])
    def ready():
        """Readiness für Load-Balancer / go_live_check (ohne DB-Schreiblast)."""
        return {"status": "ready", "timestamp": datetime.now().isoformat()}

    @app.get("/api/v1/meta", tags=["System"])
    def api_v1_meta():
        return root.ok(
            {
                "version": "v1",
                "contract": {
                    "success": {"ok": True, "data": {}},
                    "error": {"ok": False, "error": "message", "code": 400},
                },
                "timestamp": datetime.now().isoformat(),
            }
        )

    @app.get("/api/v1/health", tags=["System"])
    def api_v1_health():
        return root.ok({"status": "healthy", "timestamp": datetime.now().isoformat()})

    @app.get("/api/v1/dashboard", tags=["System"])
    def api_v1_dashboard(_user: dict = Depends(get_current_user)):
        return root.get_dashboard(_user)

    @app.get("/api/v1/kpis", tags=["System"])
    def api_v1_kpis(_user: dict = Depends(get_current_user)):
        return root.get_kpis(_user)

    @app.get("/api/v1/settings/suggestions", tags=["System"])
    def api_v1_settings_suggestions(_user: dict = Depends(get_current_user)):
        return root.settings_suggestions(_user)

    @app.get("/api/v1/billing/usage", tags=["System"])
    def api_v1_billing_usage(_user: dict = Depends(get_current_user)):
        return root.billing_usage(_user)

    @app.get("/api/v1/compliance/status", tags=["System"])
    def api_v1_compliance_status(_user: dict = Depends(get_current_user)):
        return root.ok(root._compliance_status())

    @app.get("/api/v1/webhooks/verify-example", tags=["System"])
    def api_v1_webhook_verify_example():
        snippet = {
            "python": (
                "import hmac, hashlib\n"
                "def verify(sig_header, secret, raw_body_bytes):\n"
                "    # sig_header format: sha256=<hex>\n"
                "    got = (sig_header or '').split('=',1)[-1]\n"
                "    exp = hmac.new(secret.encode('utf-8'), raw_body_bytes, hashlib.sha256).hexdigest()\n"
                "    return hmac.compare_digest(got, exp)\n"
            ),
            "headers": {
                "X-Kanzlei-Event": "event type",
                "X-Kanzlei-Signature": "sha256=<hmac_hex>",
                "X-Kanzlei-Webhook-Id": "endpoint id",
            },
            "important": "Signatur immer gegen den RAW-Request-Body prüfen, nicht gegen re-serialisiertes JSON.",
        }
        return root.ok(snippet)

    @app.get("/api/v1/endpoints", tags=["System"])
    def api_v1_endpoints_catalog(_user: dict = Depends(get_current_user)):
        return root.ok(
            {
                "core": [
                    "/api/v1/health",
                    "/api/v1/meta",
                    "/api/v1/dashboard",
                    "/api/v1/kpis",
                    "/api/v1/settings/suggestions",
                    "/api/v1/billing/usage",
                    "/api/v1/compliance/status",
                    "/api/v1/ai/usecases",
                    "/api/v1/webhooks/verify-example",
                ],
                "saas_admin": [
                    "/saas/apikeys",
                    "/saas/apikeys/{key_id}",
                    "/saas/apikeys/{key_id}/rotate",
                    "/saas/webhooks",
                    "/saas/webhooks/{webhook_id}",
                    "/saas/webhooks/{webhook_id}/test",
                ],
            }
        )

    @app.get("/api/v1/introduction", tags=["System"])
    def api_v1_introduction():
        return root.ok(
            {
                "produkt": "Kanzlei Automation",
                "kurzbeschreibung": (
                    "Multi-Tenant Steuerkanzlei-SaaS mit Automatisierung, Decision Engine und Self-Service APIs."
                ),
                "wie_es_funktioniert": [
                    "1) Auth: Benutzer oder API-Key identifiziert eine Kanzlei (tenant).",
                    "2) Datenebene: Jeder Request wird tenant-spezifisch über kanzlei_id isoliert.",
                    "3) Automatisierung: Engine/Agent priorisiert Fälle, Email-Outbox versendet robust mit Retry.",
                    "4) SaaS Controls: Billing-Limits, RBAC, Usage-Metering und Audit-Policies schützen Betrieb und Umsatz.",
                    "5) Integrationen: Tenant-Webhooks und API-Keys für externe Systeme.",
                ],
                "empfohlener_start": [
                    "/api/v1/meta",
                    "/api/v1/health",
                    "/api/v1/endpoints",
                    "/api/v1/billing/usage",
                ],
            }
        )

    @app.get("/api/v1/ai/usecases", tags=["System"])
    def api_v1_ai_usecases(_user: dict = Depends(get_current_user)):
        return root.ok(
            {
                "usecases": [
                    {"id": "auto_reply", "name": "Automatische Antworten", "value_metric": "Antwortzeit sinkt"},
                    {"id": "doc_processing", "name": "Dokumentenverarbeitung", "value_metric": "Durchsatz steigt"},
                    {
                        "id": "deadline_detection",
                        "name": "Fristen-Erkennung",
                        "value_metric": "Fristversäumnisse sinken",
                    },
                ],
                "recommended_start": ["/dokumente/analysieren", "/prognose/fristen", "/bot/analyse"],
            }
        )
