/**
 * PermissionGate
 *
 * UI-only Sichtbarkeits-/Aktivierungs-Steuerung. Trifft KEINE
 * Sicherheitsentscheidungen — die Wahrheit liegt server-seitig in
 * ``core/rbac.py`` und ``api.py:require_permission``.
 *
 * Beispiele::
 *
 *   <PermissionGate roles={["owner", "admin"]}>
 *     <button onClick={...}>Mandanten löschen</button>
 *   </PermissionGate>
 *
 *   <PermissionGate roles={["owner", "admin", "steuerberater"]} fallback={<Hint />}>
 *     <DangerButton />
 *   </PermissionGate>
 */

const ROLE_ALIASES = {
  owner: "owner",
  admin: "admin",
  steuerberater: "steuerberater",
  selbststaendig: "steuerberater",
  mitarbeiter: "mitarbeiter",
  assistent: "mitarbeiter",
  user: "mitarbeiter",
  worker: "mitarbeiter",
};

/** Nur UI-Vorschau: echte JWT-/API-Rolle bleibt unverändert. */
export const VIEW_AS_ROLE_KEY = "kanzlei_view_as_role";

export function getRealRole() {
  if (typeof window === "undefined") return "";
  try {
    const raw =
      window.localStorage.getItem("kanzlei_rolle") ||
      window.localStorage.getItem("role") ||
      "";
    return canonicalRole(raw);
  } catch {
    return "";
  }
}

/** @deprecated — bitte getRealRole / getEffectiveRole verwenden */
export function getCurrentRole() {
  return getRealRole();
}

export function getViewAsRole() {
  if (typeof window === "undefined") return "";
  try {
    const raw = (window.localStorage.getItem(VIEW_AS_ROLE_KEY) || "").trim();
    if (!raw) return "";
    return canonicalRole(raw);
  } catch {
    return "";
  }
}

export function setViewAsRole(role) {
  if (typeof window === "undefined") return;
  try {
    if (!role) {
      window.localStorage.removeItem(VIEW_AS_ROLE_KEY);
      return;
    }
    window.localStorage.setItem(VIEW_AS_ROLE_KEY, canonicalRole(String(role)));
  } catch {}
}

export function clearViewAsRole() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(VIEW_AS_ROLE_KEY);
  } catch {}
}

function _canPreviewAsOther() {
  const r = getRealRole();
  return r === "owner" || r === "admin";
}

function _allowedPreviewTargets() {
  const r = getRealRole();
  if (r === "owner") return new Set(["steuerberater", "mitarbeiter", "admin"]);
  if (r === "admin") return new Set(["steuerberater", "mitarbeiter"]);
  return new Set();
}

/** Für Navigation & PermissionGate: Vorschau-Rolle, falls Owner/Admin eine Zielrolle wählt. */
export function getEffectiveRole() {
  const real = getRealRole();
  const view = getViewAsRole();
  if (!view || !_canPreviewAsOther()) return real;
  if (!_allowedPreviewTargets().has(view)) return real;
  return view;
}

export function canonicalRole(role) {
  if (!role) return "";
  const key = String(role).trim().toLowerCase();
  return ROLE_ALIASES[key] || key;
}

export function hasRole(allowed) {
  const list = (Array.isArray(allowed) ? allowed : [allowed])
    .filter(Boolean)
    .map(canonicalRole);
  if (list.length === 0) return true;
  const me = getEffectiveRole();
  return list.includes(me) || list.includes("*");
}

/** Für Routen-Schutz & Admin-Aktionen: immer die echte Login-Rolle (ignoriert Vorschau). */
export function hasRoleReal(allowed) {
  const list = (Array.isArray(allowed) ? allowed : [allowed])
    .filter(Boolean)
    .map(canonicalRole);
  if (list.length === 0) return true;
  const me = getRealRole();
  return list.includes(me) || list.includes("*");
}

export default function PermissionGate({ roles, children, fallback = null, mode = "hide" }) {
  const allowed = hasRole(roles);
  if (allowed) return children ?? null;
  if (mode === "disable") {
    return (
      <span aria-disabled="true" style={{ opacity: 0.5, pointerEvents: "none" }}>
        {children}
      </span>
    );
  }
  return fallback;
}
