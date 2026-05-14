import sqlite3
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from core import tenant_postgres as tp
from core.daten_speicher import (
    DatenSpeicher,
    api_key_create,
    api_key_list,
    api_key_rotate,
    get_connection,
)
from core.pg_runtime import pg_primary_db

PLAENE = {
    "starter": {"name": "Starter", "preis_monat": 149, "mandanten_max": 20, "mitarbeiter_max": 3},
    "professional": {"name": "Professional", "preis_monat": 299, "mandanten_max": 100, "mitarbeiter_max": 10},
    "enterprise": {"name": "Enterprise", "preis_monat": 699, "mandanten_max": 999999, "mitarbeiter_max": 999999},
}


def _row_as_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


class TenantManager:
    """SaaS Tenant-Verwaltung — kanzleien in PostgreSQL (wenn DATABASE_URL=postgresql) sonst SQLite."""

    def __init__(self) -> None:
        self._pg = pg_primary_db()
        self.conn: Optional[sqlite3.Connection] = None if self._pg else get_connection()

    def _tenant_store(self, tenant_id: str) -> DatenSpeicher:
        return DatenSpeicher(kanzlei_id=tenant_id)

    def _fetch_tenant_row(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        if self._pg:
            return tp.tp_fetch_by_id(tenant_id)
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien WHERE id = ?",
            (tenant_id,),
        ).fetchone()
        return _row_as_dict(row) if row else None

    def _serialize_tenant(self, row: Any) -> Dict[str, Any]:
        if not row:
            raise ValueError("Tenant-Zeile fehlt")
        r = _row_as_dict(row)
        tenant_id = r["id"]
        ea = r.get("erstellt_am")
        if isinstance(ea, (datetime, date)):
            r = {**r, "erstellt_am": ea.isoformat()}
        profile = self._tenant_store(tenant_id).setting_holen("__tenant_profile__", {}) or {}
        data = {
            "id": r["id"],
            "kanzlei_name": r["name"],
            "inhaber_email": r.get("email") or "",
            "plan": r.get("plan") or "starter",
            "aktiv": bool(int(r.get("aktiv", 1) or 0)),
            "erstellt_am": r.get("erstellt_am"),
            "status": "aktiv" if bool(int(r.get("aktiv", 1) or 0)) else "gesperrt",
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
        pl = plan if plan in PLAENE else "starter"
        if self._pg:
            tp.tp_insert_kanzlei(tenant_id, kanzlei_name, inhaber_email, pl)
        else:
            assert self.conn is not None
            self.conn.execute(
                "INSERT INTO kanzleien (id, name, email, plan, aktiv) VALUES (?, ?, ?, ?, 1)",
                (tenant_id, kanzlei_name, inhaber_email, pl),
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
        if not row:
            raise RuntimeError(f"Tenant {tenant_id} nach Anlage nicht lesbar")
        out = self._serialize_tenant(row)
        out["api_key"] = key["key"]
        out["login_url"] = f"https://{subdomain}.kanzlei-ai.de"
        return out

    def alle_tenants(self) -> List[Dict[str, Any]]:
        if self._pg:
            rows = tp.tp_list_all()
            return [self._serialize_tenant(r) for r in rows]
        assert self.conn is not None
        rows = self.conn.execute(
            "SELECT id, name, email, plan, aktiv, erstellt_am FROM kanzleien ORDER BY erstellt_am DESC"
        ).fetchall()
        return [self._serialize_tenant(_row_as_dict(r)) for r in rows]

    def tenant_aktualisieren(self, tenant_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        row = self._fetch_tenant_row(tenant_id)
        if not row:
            raise ValueError(f"Tenant {tenant_id} nicht gefunden")
        current = self._serialize_tenant(row)

        name = updates.get("kanzlei_name", updates.get("name", current["kanzlei_name"]))
        email = updates.get("inhaber_email", updates.get("email", current.get("inhaber_email", "")))
        plan = updates.get("plan", current["plan"])
        aktiv = 1 if bool(updates.get("aktiv", current["aktiv"])) else 0
        pl = plan if plan in PLAENE else current["plan"]
        if self._pg:
            tp.tp_update_kanzlei(tenant_id, name, email or "", pl, aktiv)
        else:
            assert self.conn is not None
            self.conn.execute(
                "UPDATE kanzleien SET name = ?, email = ?, plan = ?, aktiv = ? WHERE id = ?",
                (name, email, pl, aktiv, tenant_id),
            )
            self.conn.commit()

        profile_keys = ["inhaber_name", "telefon", "adresse", "subdomain", "status", "sperr_grund"]
        profile = self._tenant_store(tenant_id).setting_holen("__tenant_profile__", {}) or {}
        for key in profile_keys:
            if key in updates:
                profile[key] = updates[key]
        self._tenant_store(tenant_id).setting_setzen("__tenant_profile__", profile)

        row2 = self._fetch_tenant_row(tenant_id)
        if not row2:
            raise ValueError(f"Tenant {tenant_id} nach Update nicht lesbar")
        return self._serialize_tenant(row2)

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
        gesamt_mrr = sum(
            PLAENE.get(t.get("plan", "starter"), PLAENE["starter"]).get("preis_monat", 0)
            for t in tenants
            if t.get("aktiv")
        )
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


_tenant_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager


def reset_tenant_manager() -> None:
    """Tests / Reload: TenantManager-Singleton zurücksetzen."""
    global _tenant_manager
    _tenant_manager = None
