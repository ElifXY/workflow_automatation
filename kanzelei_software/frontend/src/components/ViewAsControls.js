import {
  clearViewAsRole,
  getRealRole,
  getViewAsRole,
  hasRoleReal,
  setViewAsRole,
} from "./PermissionGate";

/**
 * Owner/Admin: Navigation & Gates wie eine andere Rolle **anzeigen** (Vorschau).
 * API-/JWT-Rechte bleiben die der echten Rolle.
 */
export default function ViewAsControls({ onChanged }) {
  if (!hasRoleReal(["owner", "admin"])) return null;

  const real = getRealRole();
  const view = getViewAsRole();

  const options = [];
  if (real === "owner") {
    options.push({ value: "", label: "Eigene Rolle (Owner)" });
    options.push({ value: "admin", label: "Als Admin (Vorschau)" });
    options.push({ value: "steuerberater", label: "Als Steuerberater/in" });
    options.push({ value: "mitarbeiter", label: "Als Mitarbeiter/in" });
  } else {
    options.push({ value: "", label: "Eigene Rolle (Admin)" });
    options.push({ value: "steuerberater", label: "Als Steuerberater/in" });
    options.push({ value: "mitarbeiter", label: "Als Mitarbeiter/in" });
  }

  const fire = () => {
    try {
      onChanged?.();
    } catch {}
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        flexWrap: "wrap",
        fontSize: 11,
        color: "var(--text2)",
      }}
      title="Nur Darstellung: Menü und sichtbare Funktionen wie die gewählte Rolle. Server prüft weiterhin Ihre echte Rolle."
    >
      <span style={{ color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Ansicht
      </span>
      <select
        value={view || ""}
        onChange={(e) => {
          const v = e.target.value;
          if (!v) clearViewAsRole();
          else setViewAsRole(v);
          fire();
        }}
        style={{
          maxWidth: 220,
          padding: "4px 8px",
          borderRadius: 8,
          border: "1px solid var(--border2)",
          background: "var(--bg3)",
          color: "var(--text)",
          fontSize: 12,
          fontFamily: "var(--font-body)",
        }}
      >
        {options.map((o) => (
          <option key={o.value || "self"} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {view ? (
        <span style={{ color: "var(--orange)", fontWeight: 600 }}>
          Vorschau aktiv
        </span>
      ) : null}
    </div>
  );
}
