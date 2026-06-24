/**
 * Analytics — reduziert auf Problemlösung (kein Cockpit)
 * Blockierung, Autopilot, ROI, kurzes Audit
 */
import { useEffect, useState, useCallback } from "react";
import {
  getBlockierung,
  getAutopilotStats,
  getDashboardRoi,
  getAuditLog,
  getAutomationAudit,
} from "../api";

function Card({ title, children, style = {} }) {
  return (
    <div style={{
      background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14,
      padding: 18, marginBottom: 14, ...style,
    }}>
      {title ? (
        <div style={{ fontFamily: "var(--font-head)", fontSize: 16, color: "var(--text)", marginBottom: 12 }}>
          {title}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export default function Analytics() {
  const [loading, setLoading] = useState(true);
  const [block, setBlock] = useState(null);
  const [auto, setAuto] = useState(null);
  const [roi, setRoi] = useState(null);
  const [audit, setAudit] = useState([]);
  const [autoLog, setAutoLog] = useState([]);

  const laden = useCallback(async () => {
    setLoading(true);
    try {
      const [b, a, r, al, au] = await Promise.all([
        getBlockierung().catch(() => null),
        getAutopilotStats().catch(() => null),
        getDashboardRoi().catch(() => null),
        getAuditLog(15).catch(() => ({ logs: [] })),
        getAutomationAudit(12).catch(() => ({ eintraege: [] })),
      ]);
      setBlock(b);
      setAuto(a);
      setRoi(r);
      setAudit(al?.logs || al?.data?.logs || []);
      setAutoLog(au?.eintraege || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { laden(); }, [laden]);

  const nerv = block?.nervfaktoren || {};
  const heute = auto?.heute || {};

  return (
    <div style={{ background: "var(--bg)", minHeight: "100%", padding: "24px 32px 40px" }}>
      <header style={{ marginBottom: 24, maxWidth: 720 }}>
        <div style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text3)", textTransform: "uppercase" }}>
          Berichte
        </div>
        <h1 style={{ fontFamily: "var(--font-head)", fontSize: 26, color: "var(--text)", margin: "8px 0 10px" }}>
          Was blockiert — und was Automation leistet
        </h1>
        <p style={{ fontSize: 14, color: "var(--text3)", lineHeight: 1.55 }}>
          Keine Diagramm-Wüste. Nur Blockierungen, Autopilot-Ergebnisse und Nachvollziehbarkeit.
          Detaillierte Automation-Logs: Tab <strong style={{ color: "var(--text2)" }}>Automationen → Protokoll</strong>.
        </p>
      </header>

      {loading ? (
        <div style={{ color: "var(--text3)", padding: 40 }}>Lade…</div>
      ) : (
        <>
          <Card title="Kanzlei-Stau-Radar">
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--orange)", marginBottom: 10 }}>
              {nerv.headline || block?.headline || "Keine Blockierungen"}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {(block?.eintraege || []).slice(0, 8).map((row, i) => (
                <div key={`${row.mandant}-${i}`} style={{
                  padding: "10px 12px", background: "var(--bg3)", borderRadius: 8,
                  borderLeft: "3px solid var(--orange)", fontSize: 13,
                }}>
                  <strong>{row.mandant}</strong> — {row.titel || row.detail}
                </div>
              ))}
              {(block?.eintraege || []).length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--green)" }}>Keine offenen Blockierungen.</div>
              ) : null}
            </div>
          </Card>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
            <Card title="Autopilot (heute)">
              <div style={{ display: "grid", gap: 8, fontSize: 14 }}>
                <div>Erinnerungen: <strong>{heute.erinnerungen_gesendet ?? 0}</strong></div>
                <div>Dokumente: <strong>{heute.dokumente_eingesammelt ?? 0}</strong></div>
                <div>Automationen: <strong>{heute.automationen_ausgefuehrt ?? 0}</strong></div>
                <div style={{ color: "var(--accent)" }}>
                  Geschätzt gespart: <strong>{heute.geschaetzte_stunden_gespart ?? 0} Std.</strong>
                </div>
              </div>
            </Card>
            <Card title="ROI (Monat)">
              {roi ? (
                <div style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text2)" }}>
                  {roi.text}
                  <div style={{ marginTop: 8, fontSize: 12, color: "var(--text3)" }}>
                    Monat: {roi.monat}
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 13, color: "var(--text3)" }}>—</div>
              )}
            </Card>
          </div>

          <Card title="Letzte Automationen">
            {autoLog.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text3)" }}>Noch keine Einträge.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {autoLog.map((r, i) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--text2)", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ color: "var(--text3)", marginRight: 8 }}>
                      {r.zeit ? new Date(r.zeit).toLocaleString("de-DE") : "—"}
                    </span>
                    {r.text}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="System-Audit (kurz)">
            {audit.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text3)" }}>Keine Einträge.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {audit.slice(0, 10).map((r, i) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--text2)" }}>
                    {r.zeit ? new Date(r.zeit).toLocaleString("de-DE") : ""} — {r.text}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      <button type="button" onClick={laden} style={{
        marginTop: 8, padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
        background: "var(--bg2)", cursor: "pointer", fontSize: 13,
      }}>
        Aktualisieren
      </button>
    </div>
  );
}
