/**
 * Dokumente — Scanner, Belege, fehlende Unterlagen (ein Tab)
 */
import { useState } from "react";
import DokumentScanner from "./DokumentScanner";
import BelegScanner from "./BelegScanner";

const TABS = [
  { id: "scanner", label: "Dokument-Scanner" },
  { id: "belege", label: "Belegscanner" },
];

export default function DokumenteHub({ isMobile = false }) {
  const [sub, setSub] = useState("scanner");
  const pad = isMobile ? "12px" : "24px 32px";

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
      <div style={{
        padding: `${pad.split(" ")[0]} ${pad.includes("32") ? "32px" : "12px"} 0`,
        borderBottom: "1px solid var(--border)",
        background: "var(--bg2)",
      }}>
        <div style={{ fontFamily: "var(--font-head)", fontSize: 22, color: "var(--text)", marginBottom: 4 }}>
          Dokumente
        </div>
        <div style={{ fontSize: 13, color: "var(--text3)", marginBottom: 14 }}>
          Upload, OCR und fehlende Unterlagen — kein separates Scanner-Produkt.
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingBottom: 12 }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setSub(t.id)}
              style={{
                padding: "8px 16px", borderRadius: 20, fontSize: 13, cursor: "pointer",
                border: sub === t.id ? "1px solid var(--accent)" : "1px solid var(--border2)",
                background: sub === t.id ? "color-mix(in srgb, var(--accent) 12%, var(--bg))" : "var(--bg3)",
                color: sub === t.id ? "var(--accent)" : "var(--text2)",
                fontWeight: sub === t.id ? 600 : 400,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {sub === "belege" ? <BelegScanner /> : <DokumentScanner />}
      </div>
    </div>
  );
}
