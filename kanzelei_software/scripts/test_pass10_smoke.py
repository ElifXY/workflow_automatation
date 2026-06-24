#!/usr/bin/env python3
"""Pass 10 Smoke — Mandanten-Zugriff + M365 Mail-Helfer (offline)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mandant_access import (  # noqa: E402
    assert_mandant_access,
    user_may_access_mandant,
    user_sees_all_mandanten,
)
from core.m365_integration import _build_mandant_email_index, _sender_email  # noqa: E402


class _FakeStore:
    def hole_mandanten(self):
        return {
            "Alpha GmbH": {"email": "alpha@test.de", "betreuer_email": "a@kanzlei.de"},
            "Beta OHG": {"email": "beta@test.de", "betreuer_email": "b@kanzlei.de"},
            "Gamma": {"email": "", "betreuer_email": ""},
        }


def test_mandant_access() -> None:
    mitarbeiter = {"email": "a@kanzlei.de", "rolle": "mitarbeiter"}
    assert user_sees_all_mandanten({"rolle": "steuerberater"})
    assert user_may_access_mandant(mitarbeiter, {"betreuer_email": "a@kanzlei.de"})
    assert not user_may_access_mandant(mitarbeiter, {"betreuer_email": "b@kanzlei.de"})
    assert user_may_access_mandant(mitarbeiter, {"betreuer_email": ""})

    try:
        assert_mandant_access(mitarbeiter, {"betreuer_email": "b@kanzlei.de"}, "Beta")
        raise AssertionError("403 expected")
    except Exception as exc:
        if getattr(exc, "status_code", None) != 403:
            raise


def test_mail_matching() -> None:
    idx = _build_mandant_email_index(_FakeStore())
    assert idx.get("alpha@test.de") == "Alpha GmbH"
    msg = {"from": {"emailAddress": {"address": "Beta@test.de"}}}
    assert _sender_email(msg) == "beta@test.de"


def main() -> int:
    test_mandant_access()
    test_mail_matching()
    print("PASS pass10 smoke: mandant_access + m365 mail helpers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
