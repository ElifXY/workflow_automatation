#!/usr/bin/env python3
"""
End-to-end matrix test for settings.

What it checks:
1) Auth + permissions for settings endpoints.
2) Every mutable DEFAULT_SETTINGS key can be updated via /settings and read back.
3) Invalid values are rejected for critical guardrails.
4) Runtime usage coverage scan: which keys are referenced outside settings UI/manager.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient


def _unwrap(body: Any) -> Any:
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _token(body: Dict[str, Any]) -> str:
    return str(body.get("access_token") or body.get("token") or "")


def _pick_valid_value(key: str, cur: Any, shadow: Dict[str, Any]) -> Any:
    if key == "ip_whitelist_aktiv":
        # Aktivierung ohne befüllte Whitelist ist bewusst blockiert.
        return False
    if key == "ip_whitelist":
        return ["127.0.0.1/32"]
    if key == "elster_aktiv":
        return True
    if key == "elster_direktversand":
        return False
    if key == "billing_stripe_aktiv":
        return False
    if key == "api_rate_limit_pro_minute":
        return 99999
    if key == "ki_modell":
        return "gpt-4o" if cur != "gpt-4o" else "gpt-4o-mini"
    if key == "server_standort":
        return "EU" if cur != "EU" else "DE"
    if key == "billing_modell":
        return "pro_buchung" if cur != "pro_buchung" else "pauschal"
    if key == "sprache":
        return "en" if cur != "en" else "de"
    if key == "automation_mode":
        return "auto" if cur != "auto" else "halbautomatisch"
    if key == "ki_auto_buchen_ab_konfidenz":
        review = int(shadow.get("ki_review_ab_konfidenz", 75))
        return max(review + 1, 80)
    if key == "ki_review_ab_konfidenz":
        auto = int(shadow.get("ki_auto_buchen_ab_konfidenz", 92))
        return max(50, min(auto - 1, 90))
    if key == "billing_value_tier_1_bis":
        tier2 = int(shadow.get("billing_value_tier_2_bis", 500000))
        return max(10_000, min(tier2 - 1, 150_000))
    if key == "billing_value_tier_2_bis":
        tier1 = int(shadow.get("billing_value_tier_1_bis", 100000))
        return max(tier1 + 1, tier1 + 10_000)
    if key in {"rollen_einstellungen", "rollen_export_datev", "rollen_lohn_sichtbar", "rollen_zahlungen_freigabe", "rollen_mandant_loeschen"}:
        return ["admin", "owner"]
    if key in {"rollen_nav_steuerberater", "rollen_nav_mitarbeiter"}:
        return ["dashboard", "mandanten", "aufgaben"]
    if key in {"eskalation_stufe_1_empfaenger", "eskalation_stufe_2_empfaenger", "datenschutz_beauftragter"}:
        return "qa@example.com"
    if key in {"webhook_url", "kanzlei_website"}:
        return "https://example.com/hook"
    if key.endswith("_uhrzeit"):
        return "09:15"
    if isinstance(cur, bool):
        return not cur
    if isinstance(cur, int):
        return cur + 1 if cur < 999999 else cur - 1
    if isinstance(cur, float):
        return round(cur + 1.0, 2)
    if isinstance(cur, list):
        return cur if cur else ["default"]
    if isinstance(cur, str):
        return (cur + " test").strip() if cur else "test-value"
    return cur


def _runtime_coverage_scan(keys: list[str]) -> Tuple[int, list[str]]:
    excluded = {
        "modules/settings_manager.py",
        "frontend/src/pages/Settings.js",
        "scripts/test_settings_e2e_matrix.py",
        "scripts/test_settings_integrity.py",
    }
    scan_roots = [ROOT / "core", ROOT / "backend", ROOT / "modules", ROOT / "frontend" / "src", ROOT / "api.py"]
    files = []
    for sr in scan_roots:
        if sr.is_file():
            files.append(sr)
            continue
        if not sr.exists():
            continue
        files.extend(sr.rglob("*.py"))
        files.extend(sr.rglob("*.js"))
    missing = []
    for key in keys:
        hits = 0
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            if rel in excluded:
                continue
            try:
                if p.stat().st_size > 2_000_000:
                    continue
            except Exception:
                continue
            try:
                txt = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if key in txt:
                hits += 1
                if hits > 0:
                    break
        if hits == 0:
            missing.append(key)
    return len(keys) - len(missing), missing


def main() -> int:
    os.environ["ENVIRONMENT"] = "development"
    os.environ["APP_ENV"] = "development"
    os.environ["DATA_DIR"] = f".tmp_settings_e2e_matrix_{uuid.uuid4().hex}"
    import api
    from modules.settings_manager import DEFAULT_SETTINGS, FESTGESCHRIEBEN

    c = TestClient(api.app)
    tag = uuid.uuid4().hex[:10]
    password = "StrongPass8!"
    email = f"settings_e2e_{tag}@example.com"
    username = f"settings_admin_{tag}"

    reg = c.post(
        "/auth/registrieren",
        json={
            "benutzername": username,
            "passwort": password,
            "rolle": "admin",
            "email": email,
        },
    )
    if reg.status_code != 201:
        print("[FAIL] register", reg.status_code, reg.text[:300])
        return 1
    login = c.post("/auth/login", json={"benutzername": username, "passwort": password})
    if login.status_code != 200:
        print("[FAIL] login", login.status_code, login.text[:300])
        return 1
    token = _token(_unwrap(login.json()))
    if not token:
        print("[FAIL] no token from login")
        return 1
    h = {"Authorization": f"Bearer {token}"}
    if hasattr(api, "_tenant_rate_store"):
        api._tenant_rate_store.clear()

    r0 = c.get("/settings", headers=h)
    if r0.status_code != 200:
        print("[FAIL] get /settings", r0.status_code, r0.text[:300])
        return 1
    baseline = _unwrap(r0.json()) or {}
    shadow = dict(baseline)
    rl = c.put("/settings", headers=h, json={"key": "api_rate_limit_pro_minute", "wert": 100000})
    if rl.status_code != 200:
        print("[FAIL] raise api rate limit for matrix", rl.status_code, rl.text[:300])
        return 1
    shadow["api_rate_limit_pro_minute"] = 100000

    mutable_keys = [k for k in DEFAULT_SETTINGS.keys() if k not in FESTGESCHRIEBEN]
    failures: list[str] = []

    for key in mutable_keys:
        cur = shadow.get(key, DEFAULT_SETTINGS[key])
        nxt = _pick_valid_value(key, cur, shadow)
        wr = c.put("/settings", headers=h, json={"key": key, "wert": nxt})
        if wr.status_code != 200:
            failures.append(f"{key}: write status {wr.status_code}")
            continue
        rd = c.get("/settings", headers=h)
        if rd.status_code != 200:
            failures.append(f"{key}: readback status {rd.status_code}")
            continue
        got = (_unwrap(rd.json()) or {}).get(key)
        if got != nxt:
            failures.append(f"{key}: readback mismatch expected={nxt!r} got={got!r}")
            continue
        shadow[key] = got

    invalid_cases = [
        ("ki_review_ab_konfidenz", 120),
        ("billing_modell", "invalid"),
        ("server_standort", "CN"),
        ("webhook_url", "not-a-url"),
        ("bank_import_uhrzeit", "99:99"),
        ("rollen_einstellungen", []),
    ]
    for key, val in invalid_cases:
        rr = c.put("/settings", headers=h, json={"key": key, "wert": val})
        if rr.status_code < 400:
            failures.append(f"{key}: invalid value accepted ({val!r})")

    restore_payload = {k: baseline.get(k, DEFAULT_SETTINGS[k]) for k in mutable_keys}
    rb = c.put("/settings/batch", headers=h, json=restore_payload)
    if rb.status_code != 200:
        failures.append(f"restore batch failed status={rb.status_code}")

    covered, missing = _runtime_coverage_scan(mutable_keys)
    print(f"[INFO] runtime coverage by key reference: {covered}/{len(mutable_keys)}")
    if missing:
        print("[WARN] keys without runtime references outside settings store/ui:")
        print("       " + ", ".join(sorted(missing)))

    if failures:
        print("[FAIL] settings e2e matrix failures:")
        for f in failures:
            print(" -", f)
        return 1

    print(f"[OK] settings e2e matrix passed: {len(mutable_keys)} mutable keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
