"""
Stripe: Checkout, Customer-Portal, Webhooks (Plan ``kanzleien.plan``).

Konfiguration ausschließlich über Umgebungsvariablen (keine Secrets in Git):
``STRIPE_SECRET_KEY``, ``STRIPE_WEBHOOK_SECRET``, optional ``STRIPE_PRICE_ID_PROFESSIONAL``,
``STRIPE_PRICE_ID_ENTERPRISE``, ``STRIPE_PUBLISHABLE_KEY``.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger("kanzlei_stripe")

_VALID_PLANS = frozenset({"starter", "professional", "enterprise"})


def _stripe_module():
    try:
        import stripe as stripe_mod  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Stripe-Paket fehlt: pip install stripe (siehe requirements.txt)."
        ) from e
    return stripe_mod


def stripe_secret_configured() -> bool:
    return bool((os.getenv("STRIPE_SECRET_KEY") or "").strip())


def stripe_webhook_secret_configured() -> bool:
    return bool((os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip())


def stripe_publishable_key() -> str:
    return (os.getenv("STRIPE_PUBLISHABLE_KEY") or "").strip()


def stripe_checkout_ready() -> bool:
    """True, wenn Checkout (Professional) mit den gesetzten ENV-Variablen möglich ist."""
    return bool(
        stripe_secret_configured()
        and stripe_publishable_key()
        and _price_id_for_plan("professional")
    )


def stripe_enterprise_price_configured() -> bool:
    return bool(_price_id_for_plan("enterprise"))


def _price_id_for_plan(target_plan: str) -> Optional[str]:
    p = (target_plan or "").strip().lower()
    if p == "professional":
        return (os.getenv("STRIPE_PRICE_ID_PROFESSIONAL") or "").strip() or None
    if p == "enterprise":
        return (os.getenv("STRIPE_PRICE_ID_ENTERPRISE") or "").strip() or None
    return None


def _configure_stripe() -> Any:
    stripe = _stripe_module()
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY ist nicht gesetzt.")
    stripe.api_key = key
    ver = (os.getenv("STRIPE_API_VERSION") or "2023-10-16").strip()
    stripe.api_version = ver
    return stripe


def create_checkout_session(
    *,
    kanzlei_id: str,
    success_url: str,
    cancel_url: str,
    target_plan: str,
    customer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stripe Checkout (Subscription). ``metadata`` / ``subscription_data.metadata``
    enthalten ``kanzlei_id`` und ``target_plan`` für Webhooks.
    """
    kid = (kanzlei_id or "").strip() or "default"
    plan = (target_plan or "professional").strip().lower()
    if plan not in _VALID_PLANS or plan == "starter":
        raise ValueError("target_plan muss professional oder enterprise sein")
    price_id = _price_id_for_plan(plan)
    if not price_id:
        raise ValueError(
            "Kein Stripe-Price für diesen Plan: STRIPE_PRICE_ID_PROFESSIONAL "
            "bzw. STRIPE_PRICE_ID_ENTERPRISE setzen (Dashboard → Produkte → Price-ID)."
        )
    if not success_url.startswith("http") or not cancel_url.startswith("http"):
        raise ValueError("success_url und cancel_url müssen mit http/https beginnen")

    stripe = _configure_stripe()
    params: Dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": kid,
        "metadata": {"kanzlei_id": kid, "target_plan": plan},
        "subscription_data": {
            "metadata": {"kanzlei_id": kid, "target_plan": plan},
        },
    }
    if customer_email and "@" in customer_email:
        params["customer_email"] = customer_email.strip()
    session = stripe.checkout.Session.create(**params)
    return {
        "id": session.get("id"),
        "url": session.get("url"),
    }


def create_billing_portal_session(*, customer_id: str, return_url: str) -> Dict[str, Any]:
    if not customer_id or not customer_id.startswith("cus_"):
        raise ValueError("Ungültige Stripe-Customer-ID")
    if not return_url.startswith("http"):
        raise ValueError("return_url muss mit http/https beginnen")
    stripe = _configure_stripe()
    ps = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return {"url": ps.get("url")}


def verify_webhook_event(payload: bytes, sig_header: str) -> Any:
    stripe = _stripe_module()
    wh = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not wh:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET ist nicht gesetzt.")
    if not sig_header:
        raise ValueError("Stripe-Signatur-Header fehlt")
    sk = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not sk:
        raise RuntimeError("STRIPE_SECRET_KEY ist nicht gesetzt.")
    stripe.api_key = sk
    return stripe.Webhook.construct_event(payload, sig_header, wh)


def _persist_stripe_customer(kanzlei_id: str, customer_id: Optional[str]) -> None:
    if not customer_id or not str(customer_id).startswith("cus_"):
        return
    from core.daten_speicher import DatenSpeicher

    store = DatenSpeicher(kanzlei_id=kanzlei_id)
    prof = store.setting_holen("__tenant_profile__", {}) or {}
    if not isinstance(prof, dict):
        prof = {}
    prof["stripe_customer_id"] = customer_id
    store.setting_setzen("__tenant_profile__", prof)


def _event_to_dict(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "to_dict"):
        return event.to_dict()  # type: ignore[no-any-return]
    return dict(event)


def handle_stripe_event(event: Any) -> Dict[str, Any]:
    """
    Idempotente Geschäftslogik. Nutzt ``TenantManager`` für ``kanzleien.plan``.
    """
    ev = _event_to_dict(event)
    et = ev.get("type") or ""
    obj = (ev.get("data") or {}).get("object") or {}
    out: Dict[str, Any] = {"event_type": et, "action": "ignored"}

    from core.multi_tenant import get_tenant_manager

    tm = get_tenant_manager()

    def _apply_plan(kid: str, plan: str) -> None:
        pl = plan if plan in _VALID_PLANS else "starter"
        tm.tenant_aktualisieren(kid, {"plan": pl})

    if et == "checkout.session.completed":
        md = obj.get("metadata") or {}
        kid = (md.get("kanzlei_id") or obj.get("client_reference_id") or "").strip()
        plan = (md.get("target_plan") or "professional").strip().lower()
        if kid and plan in _VALID_PLANS and plan != "starter":
            try:
                _apply_plan(kid, plan)
            except Exception as exc:  # noqa: BLE001
                log.warning("Stripe checkout: Plan-Update fehlgeschlagen kid=%s: %s", kid, exc)
                return {"action": "plan_update_failed", "kanzlei_id": kid, "error": str(exc)}
            cust = obj.get("customer")
            _persist_stripe_customer(kid, str(cust) if cust else None)
            log.info("Stripe checkout completed: kanzlei_id=%s plan=%s", kid, plan)
            return {"action": "plan_activated", "kanzlei_id": kid, "plan": plan}
        return {"action": "checkout_noop", "reason": "missing_metadata"}

    if et == "customer.subscription.updated":
        md = obj.get("metadata") or {}
        kid = (md.get("kanzlei_id") or "").strip()
        st = (obj.get("status") or "").strip()
        plan = (md.get("target_plan") or "professional").strip().lower()
        if kid and st == "active" and plan in _VALID_PLANS:
            try:
                _apply_plan(kid, plan)
            except Exception as exc:  # noqa: BLE001
                log.warning("Stripe subscription.updated: %s", exc)
                return {"action": "subscription_sync_failed", "error": str(exc)}
            log.info("Stripe subscription active: kanzlei_id=%s plan=%s", kid, plan)
            return {"action": "subscription_sync", "kanzlei_id": kid, "plan": plan}
        return {"action": "subscription_skipped", "status": st}

    if et == "customer.subscription.deleted":
        md = obj.get("metadata") or {}
        kid = (md.get("kanzlei_id") or "").strip()
        if kid:
            try:
                _apply_plan(kid, "starter")
            except Exception as exc:  # noqa: BLE001
                log.warning("Stripe subscription.deleted: %s", exc)
                return {"action": "downgrade_failed", "error": str(exc)}
            log.info("Stripe subscription ended: kanzlei_id=%s -> starter", kid)
            return {"action": "plan_downgraded", "kanzlei_id": kid, "plan": "starter"}
        return {"action": "subscription_delete_noop"}

    if et == "invoice.payment_failed":
        cust = obj.get("customer")
        log.warning("Stripe invoice.payment_failed customer=%s", cust)
        return {"action": "payment_failed_logged"}

    return out
