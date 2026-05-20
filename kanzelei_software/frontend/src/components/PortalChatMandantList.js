import { useMemo, useState } from "react";

/**
 * Mandanten-Auswahl in der Sidebar für den Portal-Chat.
 */
export default function PortalChatMandantList({
  mandanten = [],
  selected,
  onSelect,
  isCompact,
  isMobile,
}) {
  const [q, setQ] = useState("");

  const liste = useMemo(() => {
    const names = mandanten
      .map((m) => (typeof m === "string" ? m : m?.mandant))
      .filter(Boolean);
    const uniq = [...new Set(names)].sort((a, b) => a.localeCompare(b, "de"));
    const needle = q.trim().toLowerCase();
    if (!needle) return uniq;
    return uniq.filter((n) => n.toLowerCase().includes(needle));
  }, [mandanten, q]);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
      <div
        style={{
          fontSize: 10,
          color: "var(--text3)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          marginBottom: 8,
          padding: isCompact ? "0 4px" : "0 2px",
        }}
      >
        Chat mit Mandant
      </div>
      <input
        type="search"
        placeholder="Suchen…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{
          width: "100%",
          boxSizing: "border-box",
          padding: isMobile ? "10px 10px" : "8px 10px",
          marginBottom: 8,
          borderRadius: 8,
          border: "1px solid var(--border2)",
          background: "var(--bg3)",
          color: "var(--text)",
          fontSize: 13,
        }}
      />
      <div style={{ flex: 1, overflowY: "auto", minHeight: 80, WebkitOverflowScrolling: "touch" }}>
        {liste.length === 0 ? (
          <div style={{ fontSize: 12, color: "var(--text3)", padding: "8px 4px" }}>Keine Mandanten</div>
        ) : (
          liste.map((name) => {
            const active = selected === name;
            return (
              <button
                key={name}
                type="button"
                onClick={() => onSelect(name)}
                title={name}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: isMobile ? "11px 10px" : "9px 10px",
                  marginBottom: 4,
                  borderRadius: 8,
                  border: active ? "1px solid color-mix(in srgb, var(--accent) 40%, transparent)" : "1px solid transparent",
                  background: active ? "color-mix(in srgb, var(--accent) 12%, var(--bg3))" : "transparent",
                  color: active ? "var(--accent)" : "var(--text2)",
                  fontWeight: active ? 600 : 400,
                  fontSize: isCompact ? 12 : 13,
                  cursor: "pointer",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {active ? "💬 " : "◦ "}
                {name}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
