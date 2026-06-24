/**
 * Globale Suche — Cmd/Ctrl+K über Mandanten & offene Aufgaben
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { globalSearch } from "../api";

export default function GlobalSearch({ onTab }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQ("");
      setRows([]);
    }
  }, [open]);

  const suche = useCallback(async (term) => {
    const t = String(term || "").trim();
    if (t.length < 1) {
      setRows([]);
      return;
    }
    setLoading(true);
    try {
      const r = await globalSearch(t);
      const list = r?.ergebnisse ?? r?.data?.ergebnisse ?? [];
      setRows(Array.isArray(list) ? list : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => suche(q), 180);
    return () => clearTimeout(t);
  }, [q, suche]);

  const waehle = (row) => {
    setOpen(false);
    if (row.tab && onTab) onTab(row.tab);
    if (row.pfad?.startsWith("/mandant/")) {
      navigate(row.pfad);
    } else if (row.typ === "mandant" && row.titel) {
      navigate(`/mandant/${encodeURIComponent(row.titel)}`);
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Globale Suche"
      style={{
        position: "fixed", inset: 0, zIndex: 9500,
        background: "color-mix(in srgb, var(--bg) 55%, transparent)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        padding: "max(12vh, 80px) 16px 16px",
      }}
      onClick={() => setOpen(false)}
    >
      <div
        style={{
          width: "min(560px, 100%)", background: "var(--bg2)",
          border: "1px solid var(--border2)", borderRadius: 14,
          boxShadow: "0 16px 48px color-mix(in srgb, var(--text) 18%, transparent)",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Mandanten oder Aufgaben suchen…"
            style={{
              width: "100%", padding: "10px 12px", borderRadius: 8,
              border: "1px solid var(--border2)", background: "var(--bg3)",
              color: "var(--text)", fontSize: 15,
            }}
          />
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 8 }}>
            Esc schließen · Strg+K öffnen
          </div>
        </div>
        <div style={{ maxHeight: 320, overflowY: "auto" }}>
          {loading ? (
            <div style={{ padding: 20, color: "var(--text3)", fontSize: 13 }}>Suche…</div>
          ) : rows.length === 0 ? (
            <div style={{ padding: 20, color: "var(--text3)", fontSize: 13 }}>
              {q.trim() ? "Keine Treffer" : "Suchbegriff eingeben"}
            </div>
          ) : (
            rows.map((row, i) => (
              <button
                key={`${row.typ}-${row.titel}-${i}`}
                type="button"
                onClick={() => waehle(row)}
                style={{
                  width: "100%", textAlign: "left", padding: "12px 16px",
                  border: "none", borderBottom: "1px solid var(--border)",
                  background: "transparent", cursor: "pointer", color: "var(--text)",
                }}
              >
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  {row.typ === "aufgabe" ? "Aufgabe" : "Mandant"}
                </div>
                <div style={{ fontWeight: 600, fontSize: 14, marginTop: 2 }}>{row.titel}</div>
                {row.untertitel ? (
                  <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>{row.untertitel}</div>
                ) : null}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
