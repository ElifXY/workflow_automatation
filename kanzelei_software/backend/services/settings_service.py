from __future__ import annotations

from typing import Any, Dict, Optional


class SettingsService:
    def __init__(self, store):
        self.store = store

    def get_all(self) -> Dict[str, Any]:
        from modules.settings_manager import load_settings_for_store, FESTGESCHRIEBEN

        from core.email_sender import mask_secret_settings

        settings = mask_secret_settings(load_settings_for_store(self.store))
        return {
            **settings,
            "_festgeschrieben": list(FESTGESCHRIEBEN.keys()),
            "_meta": {
                "kategorien": ["ki", "workflow", "portal", "billing", "compliance", "schnittstellen", "email", "kanzlei"],
                "version": "3.1",
                "kanzlei_id": getattr(self.store, "kanzlei_id", "default"),
                "hinweis": "Werte in _festgeschrieben können nicht geändert werden (GoBD §147 AO)",
            },
        }

    def update_one(self, key: str, wert: Any) -> Dict[str, Any]:
        from modules.settings_manager import save_setting_for_store, FESTGESCHRIEBEN

        if key in FESTGESCHRIEBEN:
            raise PermissionError(f"'{key}' ist festgeschrieben (GoBD/Compliance) und kann nicht geändert werden.")
        erfolg = save_setting_for_store(self.store, key, wert)
        if not erfolg:
            raise ValueError(f"Ungültiger Key oder Wert: '{key}' = '{wert}'.")
        self.store.log_eintrag(f"SETTING_GEAENDERT | {key} = {wert}")
        return {"status": "ok", "key": key, "wert": wert}

    def update_batch(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        from modules.settings_manager import save_setting_for_store, FESTGESCHRIEBEN

        ergebnisse: Dict[str, bool] = {}
        for key, wert in updates.items():
            if key in FESTGESCHRIEBEN:
                ergebnisse[key] = False
                continue
            ergebnisse[key] = save_setting_for_store(self.store, key, wert)
        gespeichert = [k for k, ok in ergebnisse.items() if ok]
        fehler = [k for k, ok in ergebnisse.items() if not ok]
        if gespeichert:
            self.store.log_eintrag(
                f"SETTINGS_BATCH | {len(gespeichert)} gespeichert: {', '.join(gespeichert[:5])}"
            )
        return {"gespeichert": len(gespeichert), "fehler": fehler, "details": ergebnisse}

    def categories(self) -> Dict[str, Any]:
        from modules.settings_manager import settings_nach_kategorie

        return settings_nach_kategorie(self.store)

    def fixed(self) -> Dict[str, Any]:
        from modules.settings_manager import FESTGESCHRIEBEN

        return {
            "festgeschrieben": FESTGESCHRIEBEN,
            "begruendung": {
                "gobd_konform": "§ 147 AO — 10 Jahre Aufbewahrungspflicht, unveränderliche Buchungen",
                "audit_unveraenderbar": "§ 239 HGB — Buchungen dürfen nicht nachträglich gelöscht werden",
            },
            "hinweis": "Diese Werte schützen Sie als Softwareanbieter vor Haftungsrisiken.",
        }

    def reset(self, key: Optional[str] = None) -> Dict[str, Any]:
        from modules.settings_manager import reset_settings_for_store

        erfolg = reset_settings_for_store(self.store, key)
        self.store.log_eintrag(f"SETTINGS_RESET | {'key='+key if key else 'ALLE'}")
        return {"status": "ok" if erfolg else "fehler", "key": key or "alle"}
