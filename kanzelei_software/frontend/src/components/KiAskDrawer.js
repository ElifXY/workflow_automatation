/**
 * KI unsichtbar — „KI fragen“ oben rechts, kein Hauptmenü
 */
import { useState } from "react";
import KIAssistent from "../pages/KIAssistent";

export default function KiAskDrawer() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="KI fragen"
        title="KI fragen"
        style={{
          position: "fixed",
          top: "max(16px, env(safe-area-inset-top))",
          right: "max(16px, env(safe-area-inset-right))",
          zIndex: 9000,
          padding: "12px 18px",
          borderRadius: 999,
          border: "1px solid color-mix(in srgb, var(--accent) 35%, var(--border))",
          background: "var(--bg2)",
          color: "var(--text)",
          fontSize: 13,
          fontWeight: 600,
          cursor: "pointer",
          boxShadow: "0 4px 24px color-mix(in srgb, var(--text) 12%, transparent)",
        }}
      >
        ✦ KI fragen
      </button>

      {open ? (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9100,
            background: "color-mix(in srgb, var(--bg) 40%, transparent)",
            display: "flex",
            justifyContent: "flex-end",
          }}
          onClick={() => setOpen(false)}
        >
          <div
            style={{
              width: "min(480px, 100vw)",
              height: "100%",
              background: "var(--bg)",
              borderLeft: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              boxShadow: "-8px 0 32px color-mix(in srgb, var(--text) 8%, transparent)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "14px 16px", borderBottom: "1px solid var(--border)", background: "var(--bg2)",
            }}>
              <span style={{ fontWeight: 600, fontSize: 15 }}>KI fragen</span>
              <button type="button" onClick={() => setOpen(false)} style={{
                border: "none", background: "transparent", fontSize: 22, cursor: "pointer", color: "var(--text2)",
              }}>
                ×
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
              <KIAssistent />
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
