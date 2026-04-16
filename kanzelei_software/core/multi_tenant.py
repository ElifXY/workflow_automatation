import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.daten_speicher import (
    DatenSpeicher,
    api_key_create,
    api_key_list,
    api_key_rotate,
    get_connection,
)

PLAENE = {
    "starter": {"name": "Starter", "preis_monat": 149, "mandanten_max": 20, "mitarbeiter_max": 3},
    "professional": {"name": "Professional", "preis_monat": 299, "mandanten_max": 100, "mitarbeiter_max": 10},
    "enterprise": {"name": "Enterprise", "preis_monat": 699, "mandanten_max": 999999, "mitarbeiter_max": 999999},
}


class TenantManager:
    """SaaS Tenant-Verwaltung auf SQL-Basis (keine JSON-Dateien)."""

    def __init__(self):
        self.conn = get_connection()

    def _tenant_store(self, tenant_id: str) -> DatenSpeicher:
        return DatenSpeicher(kanzlei_id=tenant_id)

    def _fetch_tenant_row(self, tenant_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien WHERE id = ?",
            (tenant_id,),
        ).fetchone()

    def _serialize_tenant(self, row: sqlite3.Row) -> Dict[str, Any]:
        tenant_id = row["id"]
        profile = self._tenant_store(tenant_id).setting_holen("__tenant_profile__", {}) or {}
        data = {
            "id": row["id"],
            "kanzlei_name": row["name"],
            "inhaber_email": row["email"] or "",
            "plan": row["plan"] or "starter",
            "aktiv": bool(row["aktiv"]),
            "erstellt_am": row["erstellt_am"],
            "status": "aktiv" if bool(row["aktiv"]) else "gesperrt",
        }
        data.update(profile if isinstance(profile, dict) else {})
        data["plan_details"] = PLAENE.get(data["plan"], PLAENE["starter"])
        return data

    def tenant_erstellen(
        self,
        kanzlei_name: str,
        inhaber_name: str,
        inhaber_email: str,
        plan: str = "starter",
        subdomain: str = None,
        telefon: str = "",
        adresse: str = "",
    ) -> Dict[str, Any]:
        tenant_id = str(uuid.uuid4())[:8]
        if not subdomain:
            subdomain = f"kanzlei-{tenant_id}"
        self.conn.execute(
            "INSERT INTO kanzleien (id, name, email, plan, aktiv) VALUES (?, ?, ?, ?, 1)",
            (tenant_id, kanzlei_name, inhaber_email, plan if plan in PLAENE else "starter"),
        )
        self.conn.commit()
        store = self._tenant_store(tenant_id)
        store.setting_setzen(
            "__tenant_profile__",
            {
                "inhaber_name": inhaber_name,
                "telefon": telefon,
                "adresse": adresse,
                "subdomain": subdomain,
                "created_via": "sql_tenant_manager",
            },
        )
        key = api_key_create(tenant_id, "default tenant key", permissions=["*"])
        row = self._fetch_tenant_row(tenant_id)
        out = self._serialize_tenant(row)
        out["api_key"] = key["key"]
        out["login_url"] = f"https://{subdomain}.kanzlei-ai.de"
        return out

    def alle_tenants(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien ORDER BY erstellt_am DESC"
        ).fetchall()
        return [self._serialize_tenant(r) for r in rows]

    def tenant_aktualisieren(self, tenant_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        row = self._fetch_tenant_row(tenant_id)
        if not row:
            raise ValueError(f"Tenant {tenant_id} nicht gefunden")
        current = self._serialize_tenant(row)

        name = updates.get("kanzlei_name", updates.get("name", current["kanzlei_name"]))
        email = updates.get("inhaber_email", updates.get("email", current.get("inhaber_email", "")))
        plan = updates.get("plan", current["plan"])
        aktiv = 1 if bool(updates.get("aktiv", current["aktiv"])) else 0
        self.conn.execute(
            "UPDATE kanzleien SET name = ?, email = ?, plan = ?, aktiv = ? WHERE id = ?",
            (name, email, plan if plan in PLAENE else current["plan"], aktiv, tenant_id),
        )
        self.conn.commit()

        profile_keys = ["inhaber_name", "telefon", "adresse", "subdomain", "status", "sperr_grund"]
        profile = self._tenant_store(tenant_id).setting_holen("__tenant_profile__", {}) or {}
        for key in profile_keys:
            if key in updates:
                profile[key] = updates[key]
        self._tenant_store(tenant_id).setting_setzen("__tenant_profile__", profile)

        return self._serialize_tenant(self._fetch_tenant_row(tenant_id))

    def tenant_sperren(self, tenant_id: str, grund: str = ""):
        self.tenant_aktualisieren(tenant_id, {"aktiv": False, "status": "gesperrt", "sperr_grund": grund})

    def api_key_erneuern(self, tenant_id: str) -> str:
        keys = [k for k in api_key_list(tenant_id) if k.get("aktiv")]
        if keys:
            rotated = api_key_rotate(tenant_id, keys[0]["id"])
            if rotated and rotated.get("key"):
                return rotated["key"]
        created = api_key_create(tenant_id, "rotated tenant key", permissions=["*"])
        return created["key"]

    def saas_statistiken(self) -> Dict[str, Any]:
        tenants = self.alle_tenants()
        gesamt_mrr = sum(PLAENE.get(t.get("plan", "starter"), PLAENE["starter"]).get("preis_monat", 0) for t in tenants if t.get("aktiv"))
        plan_verteilung: Dict[str, int] = {}
        for t in tenants:
            p = t.get("plan", "starter")
            plan_verteilung[p] = plan_verteilung.get(p, 0) + 1
        return {
            "tenants_gesamt": len(tenants),
            "tenants_aktiv": sum(1 for t in tenants if t.get("aktiv")),
            "tenants_gesperrt": sum(1 for t in tenants if not t.get("aktiv")),
            "mrr_euro": gesamt_mrr,
            "arr_euro": gesamt_mrr * 12,
            "plan_verteilung": plan_verteilung,
            "berechnet_am": datetime.now().isoformat(),
        }


_tenant_manager = None


def get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager
