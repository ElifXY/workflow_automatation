#!/usr/bin/env python3
"""Pass 15: Berechnungen + Settings-Konsistenz."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("USE_POSTGRES_DATA", "0")
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    tmp = tempfile.mkdtemp(prefix=".tmp_pass15_")
    os.environ["DATA_DIR"] = tmp
    db = os.path.join(tmp, "kanzlei.db")
    os.environ["KANZLEI_DB_PATH"] = db

    import api  # noqa: WPS433
    from core.daten_speicher import DatenSpeicher  # noqa: WPS433
    from core.decision_engine import _berechne_risiko_daten  # noqa: WPS433
    from core.engine import Engine  # noqa: WPS433
    from core.profit_monitor import ProfitMonitor  # noqa: WPS433
    from core.tenant_settings import tenant_int  # noqa: WPS433
    from modules.settings_manager import save_setting_for_store  # noqa: WPS433

    tag = uuid.uuid4().hex[:8]
    pw = "StrongPass9!"
    c = TestClient(api.app)

    admin_user = f"p15_admin_{tag}"
    c.post(
        "/auth/registrieren",
        json={"benutzername": admin_user, "passwort": pw, "rolle": "admin", "email": f"p15_{tag}@example.com"},
    )
    r = c.post("/auth/login", json={"benutzername": admin_user, "passwort": pw})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token") or r.json().get("token")
    h = {"Authorization": f"Bearer {token}"}

    # Settings via API
    r = c.put("/settings", json={"key": "antwort_warnung_tage", "wert": 10}, headers=h)
    assert r.status_code == 200, r.text
    r = c.put("/settings", json={"key": "stundensatz", "wert": 200}, headers=h)
    assert r.status_code == 200, r.text
    r = c.put("/settings", json={"key": "auto_workflow_monatsabschluss", "wert": False}, headers=h)
    assert r.status_code == 200, r.text

    user = c.get("/auth/me", headers=h).json()
    kid = user.get("kanzlei_id") or user.get("tenant_id") or "default"
    store = DatenSpeicher(kanzlei_id=kid)

    assert tenant_int(store, "antwort_warnung_tage", 7) == 10
    assert tenant_int(store, "stundensatz", 150) == 200

    eng = Engine(store)
    assert eng._setting("antwort_warnung_tage", 7) == 10

    # Mandant ohne Umsatz-Falle im Profit
    name = f"Mandant P15 {tag}"
    c.post("/mandanten", json={"name": name, "email": f"m_{tag}@example.com", "umsatz": 500000}, headers=h)
    pm = ProfitMonitor(store)
    p = pm.berechne_profit(name, 30)
    assert p["honorar_netto"] == 0 or p.get("honorar_geschaetzt"), "Kein blindes Umsatz/12 als Honorar"
    assert p["status"] in ("keine_daten", "verlust", "warnung", "ok", "profitabel")

    # Risiko-Schwellen aus Settings
    m = store.hole_mandanten().get(name, {})
    from datetime import datetime, timedelta
    m["letzte_antwort"] = (datetime.now() - timedelta(days=11)).isoformat()
    store.mandant_speichern(name, m)
    risiko = _berechne_risiko_daten(name, m, store)
    assert risiko["tage_ohne_antwort"] >= 10

    # Scheduler-Flag aus Blob
    from core.tenant_settings import tenant_bool
    assert tenant_bool(store, "auto_workflow_monatsabschluss", True) is False

    print("PASS pass15: calculations + settings consistency")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
