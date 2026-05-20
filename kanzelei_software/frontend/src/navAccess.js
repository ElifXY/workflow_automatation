/**
 * Sidebar-Navigation: Tab-IDs und effektive Sichtbarkeit pro Rolle + Tenant-Settings.
 * Server-RBAC bleibt unverändert; dies steuert nur die Menüführung (Orientierung).
 */
import { canonicalRole } from "./components/PermissionGate";

export const NAV_TAB_IDS = [
  "dashboard",
  "mandanten",
  "portalchat",
  "aufgaben",
  "ki",
  "profit",
  "steuerbot",
  "dokumente",
  "belege",
  "rechnungen",
  "automation",
  "empfehlungen",
  "analytics",
  "neu",
  "settings",
];

const DEFAULT_STEUERBERATER = new Set([
  "dashboard",
  "mandanten",
  "portalchat",
  "aufgaben",
  "ki",
  "profit",
  "steuerbot",
  "dokumente",
  "belege",
  "rechnungen",
  "automation",
  "empfehlungen",
  "analytics",
  "neu",
  "settings",
]);

/** Neue Menüpunkte: in bestehenden Tenant-Einstellungen automatisch sichtbar */
const NAV_TABS_AUTO_ENABLE = ["portalchat"];

const DEFAULT_MITARBEITER = new Set([
  "dashboard",
  "mandanten",
  "portalchat",
  "aufgaben",
  "ki",
  "dokumente",
  "belege",
  "rechnungen",
  "empfehlungen",
]);

/**
 * @param {string} role Rohrolle (inkl. Alias assistent → mitarbeiter im Gate)
 * @param {Record<string, unknown>|null|undefined} settings flaches Settings-Objekt von GET /settings
 * @returns {Set<string>|null} null = alle Tabs (Owner/Admin)
 */
export function effectiveTabSet(role, settings) {
  const c = canonicalRole(role);
  if (c === "owner" || c === "admin") return null;

  const key = c === "steuerberater" ? "rollen_nav_steuerberater" : "rollen_nav_mitarbeiter";
  const raw = settings && settings[key];
  if (Array.isArray(raw) && raw.length > 0) {
    const allowed = new Set(raw.map((x) => String(x).toLowerCase()));
    allowed.add("dashboard");
    for (const id of NAV_TABS_AUTO_ENABLE) allowed.add(id);
    return allowed;
  }
  if (c === "steuerberater") return DEFAULT_STEUERBERATER;
  return DEFAULT_MITARBEITER;
}

export function hasNavTab(role, tabId, settings) {
  const id = String(tabId || "").toLowerCase();
  // Mandanten-Portal/Chat: immer sichtbar für Steuerberater-Suite (auch alte Tenant-Nav-Listen)
  if (id === "portalchat") return true;
  const set = effectiveTabSet(role, settings);
  if (set == null) return true;
  return set.has(id);
}

export const NAV_TAB_LABELS = {
  dashboard: "Dashboard",
  mandanten: "Mandanten",
  portalchat: "Mandanten-Portal",
  aufgaben: "Aufgaben",
  ki: "KI-Assistent",
  profit: "Profit Monitor",
  steuerbot: "Steuer-Autopilot",
  dokumente: "Dokument-Scanner",
  belege: "Belegscanner",
  rechnungen: "Rechnungen",
  automation: "Automation",
  empfehlungen: "KI-Insights",
  analytics: "Analytics",
  neu: "Neu anlegen",
  settings: "Einstellungen",
};
