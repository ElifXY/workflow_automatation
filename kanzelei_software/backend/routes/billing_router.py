"""
Billing router extracted from ``api.py``.

Uses wrappers to keep runtime behavior stable during gradual extraction.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from backend.deps import get_current_user

router = APIRouter(tags=["Billing"])


def _root():
    import api as root

    return root


@router.get("/billing/usage", summary="Aktuelle Nutzung vs Plan-Limits")
def billing_usage(_user: dict = Depends(get_current_user)):
    root = _root()
    return root.billing_usage(_user)


@router.get("/billing/stripe/config", summary="Öffentliche Stripe-Konfiguration (Publishable Key)")
def stripe_public_config():
    root = _root()
    return root.stripe_public_config()


@router.post("/billing/stripe/checkout-session", summary="Stripe Checkout Session (Upgrade)")
def stripe_create_checkout(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.StripeCheckoutRequest(**data)
    return root.stripe_create_checkout(payload, _user)


@router.post("/billing/stripe/portal-session", summary="Stripe Customer Portal (Abo verwalten)")
def stripe_billing_portal(
    data: Dict[str, Any] = Body(...),
    _user: dict = Depends(get_current_user),
):
    root = _root()
    payload = root.StripePortalRequest(**data)
    return root.stripe_billing_portal(payload, _user)


@router.post("/billing/stripe/webhook", summary="Stripe Webhook (Signaturpflicht)")
async def stripe_webhook(request: Request):
    root = _root()
    return await root.stripe_webhook(request)

