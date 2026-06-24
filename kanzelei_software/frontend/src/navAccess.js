/**
 * Navigation — Produktfokus: 5 Hauptbereiche + „Mehr“
 * Kanzlei Automation: Mandanten liefern rechtzeitig.
 */
import { canonicalRole } from "./components/PermissionGate";

export const NAV_EXTENDED_STORAGE_KEY = "kanzlei_nav_extended";
export const NAV_MORE_OPEN_KEY = "kanzlei_nav_more_open";

/** Standard-Hauptnavigation (90 % der Nutzer) — exakt 5 Bereiche */
export const NAV_MAIN_IDS = [
  "dashboard",
  "mandanten",
  "dokumente",
  "automation",
  "settings",
];

/** Sekundär — unter „Mehr“ */
export const NAV_MORE_IDS = [
  "aufgaben",
  "portalchat",
  "analytics",
  "profit",
  "rechnungen",
  "steuerbot",
  "empfehlungen",
  "neu",
];

/** Versteckt — nur per Direktlink / KI-Button */
export const NAV_HIDDEN_IDS = ["ki"];

/** Sidebar-Fuß (Benutzer / Admin-Links) */
export const NAV_ADMIN_IDS = [];

export const NAV_TAB_IDS = [
  ...NAV_MAIN_IDS,
  ...NAV_MORE_IDS,
  ...NAV_HIDDEN_IDS,
  ...NAV_ADMIN_IDS,
  "belege",
];

const DEFAULT_TEAMLEITER = new Set([
  "dashboard",
  "mandanten",
  "dokumente",
  "automation",
  "settings",
  "aufgaben",
  "portalchat",
]);

const DEFAULT_STEUERBERATER = new Set([
  "dashboard",
  "mandanten",
  "dokumente",
  "automation",
  "settings",
  "aufgaben",
  "portalchat",
  "analytics",
  "profit",
]);

const DEFAULT_MITARBEITER = new Set([
  "dashboard",
  "mandanten",
  "dokumente",
  "settings",
  "aufgaben",
  "portalchat",
]);

const DEFAULT_OWNER_ADMIN = null;

const NAV_TABS_ALWAYS = ["dashboard"];

export function readNavExtended() {
  try {
    const v = localStorage.getItem(NAV_EXTENDED_STORAGE_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {}
  return false;
}

export function writeNavExtended(on) {
  try {
    localStorage.setItem(NAV_EXTENDED_STORAGE_KEY, on ? "1" : "0");
  } catch {}
}

export function readNavMoreOpen() {
  try {
    return localStorage.getItem(NAV_MORE_OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeNavMoreOpen(on) {
  try {
    localStorage.setItem(NAV_MORE_OPEN_KEY, on ? "1" : "0");
  } catch {}
}

/**
 * @param {string} role
 * @param {Record<string, unknown>|null|undefined} settings
 * @returns {Set<string>|null} null = alle Tabs (Owner/Admin)
 */
export function effectiveTabSet(role, settings) {
  const c = canonicalRole(role);
  if (c === "owner" || c === "admin") return DEFAULT_OWNER_ADMIN;

  const keyMap = {
    teamleiter: "rollen_nav_teamleiter",
    steuerberater: "rollen_nav_steuerberater",
    mitarbeiter: "rollen_nav_mitarbeiter",
  };
  const key = keyMap[c] || "rollen_nav_mitarbeiter";
  const raw = settings && settings[key];
  if (Array.isArray(raw) && raw.length > 0) {
    const allowed = new Set(raw.map((x) => String(x).toLowerCase()));
    for (const tid of NAV_TABS_ALWAYS) allowed.add(tid);
    if (allowed.has("dokumente")) allowed.add("belege");
    return allowed;
  }
  if (c === "teamleiter") return DEFAULT_TEAMLEITER;
  if (c === "steuerberater") return DEFAULT_STEUERBERATER;
  return DEFAULT_MITARBEITER;
}

export function isAdminRole(role) {
  const c = canonicalRole(role);
  return c === "owner" || c === "admin";
}

/**
 * Darf Tab in Sidebar erscheinen (Haupt, Mehr oder Admin)?
 */
export function hasNavTab(role, tabId, settings, opts = {}) {
  const id = String(tabId || "").toLowerCase();
  if (id === "ki") return false;
  if (id === "belege") return hasNavTab(role, "dokumente", settings, opts);

  const c = canonicalRole(role);
  const set = effectiveTabSet(role, settings);
  const allowed = set == null || set.has(id);

  if (!allowed) return false;

  if (NAV_ADMIN_IDS.includes(id)) {
    return isAdminRole(c);
  }

  if (NAV_MORE_IDS.includes(id)) {
    const extended = opts.extended !== undefined ? opts.extended : readNavExtended();
    return extended;
  }

  if (NAV_MAIN_IDS.includes(id)) return true;
  return false;
}

export function sidebarSections(role, settings, opts = {}) {
  const main = NAV_MAIN_IDS.filter((id) => hasNavTab(role, id, settings, opts));
  const more = NAV_MORE_IDS.filter((id) => hasNavTab(role, id, settings, opts));
  const admin = NAV_ADMIN_IDS.filter((id) => hasNavTab(role, id, settings, opts));
  return { main, more, admin };
}

export const NAV_TAB_LABELS = {
  dashboard: "Dashboard",
  mandanten: "Mandanten",
  dokumente: "Dokumente",
  automation: "Automationen",
  aufgaben: "Aufgaben",
  portalchat: "Portal-Chat",
  analytics: "Analytics",
  profit: "Honorar-Radar",
  steuerbot: "Steuer-Autopilot",
  belege: "Belege",
  rechnungen: "Rechnungen",
  automation_legacy: "Automation",
  empfehlungen: "Insights",
  ki: "KI fragen",
  neu: "Neu anlegen",
  settings: "Einstellungen",
};

export const NAV_TAB_ICONS = {
  dashboard: "◼",
  mandanten: "◉",
  dokumente: "📄",
  automation: "⚙",
  aufgaben: "▦",
  portalchat: "💬",
  analytics: "◎",
  profit: "📈",
  rechnungen: "🧾",
  steuerbot: "🤖",
  empfehlungen: "◈",
  neu: "＋",
  settings: "🔧",
};

export const PRODUCT_TAGLINE =
  "Mandanten liefern rechtzeitig — keine liegengebliebenen Fälle.";

export const PRODUCT_HEADLINE =
  "Mandanten liefern Unterlagen nicht rechtzeitig?";

export const PRODUCT_SUBLINE =
  "Kanzlei Automation fordert Dokumente automatisch an, erinnert Mandanten selbstständig und verhindert liegengebliebene Fälle.";

export const PRODUCT_NAME = "Kanzlei Automation";

/** Für Einstellungen → Team: Tabs gruppiert statt Feature-Wüste */
export const NAV_SETTINGS_GROUPS = [
  { id: "main", label: "Hauptbereiche", ids: NAV_MAIN_IDS },
  { id: "more", label: "Mehr (optional)", ids: NAV_MORE_IDS },
  { id: "admin", label: "Administration", ids: [...NAV_ADMIN_IDS, "neu"] },
];

/** Schnell-Presets für Rollen-Navigation (keine 30 Einzelrollen) */
export const ROLE_NAV_PRESETS = {
  mitarbeiter: {
    label: "Mitarbeiter",
    hint: "5 Hauptbereiche; Aufgaben unter „Mehr“",
    teamleiter: ["dashboard", "mandanten", "dokumente", "automation", "settings", "aufgaben"],
    steuerberater: ["dashboard", "mandanten", "dokumente", "automation", "settings", "aufgaben"],
    mitarbeiter: ["dashboard", "mandanten", "dokumente", "settings", "aufgaben"],
  },
  teamleiter: {
    label: "Teamleiter",
    hint: "5 Hauptbereiche + Automationen; Aufgaben unter „Mehr“",
    teamleiter: ["dashboard", "mandanten", "dokumente", "automation", "settings", "aufgaben", "portalchat"],
    steuerberater: ["dashboard", "mandanten", "dokumente", "automation", "settings", "aufgaben", "portalchat"],
    mitarbeiter: ["dashboard", "mandanten", "dokumente", "settings", "aufgaben", "portalchat"],
  },
  inhaber: {
    label: "Kanzleiinhaber / Steuerberater",
    hint: "5 Hauptbereiche + Analytics & Profit unter „Mehr“",
    teamleiter: ["dashboard", "mandanten", "dokumente", "automation", "settings", "aufgaben", "portalchat", "analytics", "profit"],
    steuerberater: [
      "dashboard", "mandanten", "dokumente", "automation", "settings",
      "aufgaben", "portalchat", "analytics", "profit", "rechnungen", "neu",
    ],
    mitarbeiter: ["dashboard", "mandanten", "dokumente", "settings", "aufgaben"],
  },
};

/** Feature-Berechtigungen (API/Backend, unabhängig von Sidebar) */
export const FEATURE_PERMISSION_KEYS = [
  { key: "rollen_lohn_sichtbar", label: "Löhne & Gehälter sehen", perm: "lohn:read" },
  { key: "rollen_zahlungen_freigabe", label: "Zahlungen freigeben", perm: "payments:release" },
  { key: "rollen_mandant_loeschen", label: "Mandanten löschen", perm: "mandanten:delete" },
  { key: "rollen_export_datev", label: "DATEV-Export", perm: "export:datev" },
  { key: "rollen_einstellungen", label: "Einstellungen ändern", perm: "settings:write" },
];

/** UI-Hilfe: darf Rolle laut Settings-Matrix die Aktion? (Owner/Admin immer ja) */
export function featureAllowed(settings, featureKey, role) {
  const canon = String(role || "").toLowerCase();
  if (canon === "owner" || canon === "admin") return true;
  const aliases = {
    teamleiter: "teamleiter",
    steuerberater: "steuerberater",
    selbststaendig: "steuerberater",
    mitarbeiter: "mitarbeiter",
    assistent: "mitarbeiter",
    user: "mitarbeiter",
  };
  const me = aliases[canon] || canon;
  const raw = settings?.[featureKey];
  const list = Array.isArray(raw) ? raw : [];
  return list.some((r) => (aliases[String(r).toLowerCase()] || String(r).toLowerCase()) === me);
}
