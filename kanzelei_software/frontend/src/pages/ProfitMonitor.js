/**
 * Honorar-Radar — schlanke Profit-Ansicht (Pass 5)
 * Fokus: Verlust-Mandanten und Honoraranpassungen, kein Benchmark-Cockpit
 */
import { useState, useEffect, useCallback, useMemo } from "react";

const BASE = process.env.REACT_APP_API_URL || "/api";
const api = async (url) => {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE + url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

const STATUS_CFG = {
  profitabel: { color: "var(--green)", label: "OK" },
  ok: { color: "var(--blue)", label: "OK" },
  warnung: { color: "var(--orange)", label: "Warnung" },
  verlust: { color: "var(--red)", label: "Verlust" },
};

const fmt = (v) => `€${Number(v || 0).toLocaleString("de-DE", { minimumFractionDigits: 0 })}`;
const pct = (v) => `${Number(v || 0).toFixed(0)}%`;

function MandantenZeile({ daten, onEmail }) {
  const cfg = STATUS_CFG[daten.status] || STATUS_CFG.ok;
  const a = daten.honoraranpassung;

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "minmax(140px,1fr) auto auto",
      gap: 12,
      alignItems: "center",
      padding: "12px 14px",
      background: "var(--bg2)",
      border: `1px solid color-mix(in srgb, ${cfg.color} 20%, transparent)`,
      borderLeft: `3px solid ${cfg.color}`,
      borderRadius: 10,
    }}>
      <div>
        <div style={{ fontWeight: 600, color: "var(--text)", fontSize: 14 }}>{daten.mandant}</div>
        <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>
          {daten.aufwand_stunden}h · Marge {pct(daten.marge_prozent)}
        </div>
        {a ? (
          <div style={{ fontSize: 11, color: "var(--orange)", marginTop: 4 }}>
            Empfehlung: {fmt(a.empfohlenes_honorar)}/Monat (+{pct(a.differenz_prozent)})
          </div>
        ) : null}
      </div>
      <div style={{
        fontFamily: "var(--font-head)",
        fontSize: 18,
        color: daten.profit_euro >= 0 ? "var(--green)" : "var(--red)",
        textAlign: "right",
      }}>
        {daten.profit_euro >= 0 ? "+" : ""}{fmt(daten.profit_euro)}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
        {a?.email_vorlage ? (
          <button
            type="button"
            onClick={() => onEmail(daten.mandant, a.email_vorlage)}
            style={btnGhost}
          >
            Vorlage
          </button>
        ) : null}
      </div>
    </div>
  );
}

const btnGhost = {
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid var(--border2)",
  background: "transparent",
  color: "var(--text2)",
  fontSize: 12,
  cursor: "pointer",
};

export default function ProfitMonitor() {
  const [uebersicht, setUebersicht] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tage, setTage] = useState(30);
  const [nurAuffaellig, setNurAuffaellig] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [emailModal, setEmailModal] = useState(null);

  const laden = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const d = await api(`/profit/kanzlei/uebersicht?tage=${tage}`);
      setUebersicht(d);
    } catch (e) {
      setUebersicht(null);
      setLoadError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [tage]);

  useEffect(() => { laden(); }, [laden]);

  const u = uebersicht;
  const liste = useMemo(() => {
    const ranking = u?.ranking || [];
    if (!nurAuffaellig) return ranking;
    return ranking.filter(
      (r) => r.status === "verlust" || r.status === "warnung" || r.honoraranpassung,
    );
  }, [u, nurAuffaellig]);

  return (
    <div style={{ background: "var(--bg)", minHeight: "100%", padding: "24px 32px 40px" }}>
      <header style={{ marginBottom: 24, maxWidth: 720 }}>
        <div style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text3)", textTransform: "uppercase" }}>
          Mehr · Honorar
        </div>
        <h1 style={{ fontFamily: "var(--font-head)", fontSize: 26, color: "var(--text)", margin: "8px 0 10px" }}>
          Honorar-Radar
        </h1>
        <p style={{ fontSize: 14, color: "var(--text3)", lineHeight: 1.55 }}>
          Welche Mandanten lohnen sich nicht? Nur Auffälligkeiten — kein Benchmark-Cockpit.
          Details pro Mandant: Mandanten → Profil → Honorar.
        </p>
      </header>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 20 }}>
        {[7, 30, 90].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTage(t)}
            style={{
              ...btnGhost,
              background: tage === t ? "var(--bg3)" : "transparent",
              borderColor: tage === t ? "var(--accent)" : "var(--border2)",
              color: tage === t ? "var(--accent)" : "var(--text2)",
            }}
          >
            {t} Tage
          </button>
        ))}
        <button type="button" onClick={() => setNurAuffaellig((v) => !v)} style={btnGhost}>
          {nurAuffaellig ? "Alle Mandanten" : "Nur Auffällige"}
        </button>
        <button type="button" onClick={laden} disabled={loading} style={btnGhost}>
          {loading ? "…" : "Aktualisieren"}
        </button>
      </div>

      {loading && !u ? (
        <div style={{ color: "var(--text3)", padding: 40 }}>Lade…</div>
      ) : null}

      {!loading && loadError ? (
        <div style={{
          padding: 20, borderRadius: 12,
          background: "color-mix(in srgb, var(--orange) 12%, var(--bg2))",
          border: "1px solid color-mix(in srgb, var(--orange) 30%, transparent)",
          fontSize: 14, color: "var(--text2)", maxWidth: 560,
        }}>
          Daten nicht verfügbar ({loadError}).{" "}
          <button type="button" onClick={laden} style={{ ...btnGhost, marginTop: 8 }}>Erneut</button>
        </div>
      ) : null}

      {u ? (
        <>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            gap: 12,
            marginBottom: 20,
          }}>
            {[
              { l: "Kanzlei-Profit", v: fmt(u.gesamt_profit), c: u.gesamt_profit >= 0 ? "var(--green)" : "var(--red)" },
              { l: "Marge", v: pct(u.gesamt_marge_prozent), c: u.gesamt_marge_prozent >= 40 ? "var(--green)" : "var(--orange)" },
              { l: "Verlust-Mandanten", v: u.verlust_mandanten, c: u.verlust_mandanten > 0 ? "var(--red)" : "var(--green)" },
              { l: "Potenzial/Jahr", v: fmt(u.potenzial_euro_jährlich), c: "var(--accent)" },
            ].map((s, i) => (
              <div key={i} style={{
                background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 16px",
              }}>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", marginBottom: 4 }}>{s.l}</div>
                <div style={{ fontFamily: "var(--font-head)", fontSize: 22, color: s.c }}>{s.v}</div>
              </div>
            ))}
          </div>

          {u.verlust_mandanten > 0 ? (
            <div style={{
              padding: "12px 14px", borderRadius: 10, marginBottom: 16,
              background: "color-mix(in srgb, var(--red) 10%, var(--bg3))",
              border: "1px solid color-mix(in srgb, var(--red) 22%, transparent)",
              fontSize: 13, color: "var(--red)", fontWeight: 600,
            }}>
              {u.verlust_mandanten} Mandant(en) im Verlust — Honorar prüfen
            </div>
          ) : null}

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {liste.length === 0 ? (
              <div style={{ fontSize: 14, color: "var(--green)", padding: 20 }}>
                {nurAuffaellig ? "Keine auffälligen Mandanten in diesem Zeitraum." : "Keine Daten."}
              </div>
            ) : (
              liste.map((r, i) => (
                <MandantenZeile
                  key={`${r.mandant}-${i}`}
                  daten={r}
                  onEmail={(mandant, vorlage) => setEmailModal({ mandant, vorlage })}
                />
              ))
            )}
          </div>
        </>
      ) : null}

      {emailModal ? (
        <div style={{
          position: "fixed", inset: 0, background: "var(--overlay-scrim)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 20,
        }}>
          <div style={{
            background: "var(--bg2)", border: "1px solid var(--border2)", borderRadius: 14,
            width: "min(560px,95vw)", padding: 20,
          }}>
            <div style={{ fontWeight: 600, marginBottom: 12, color: "var(--text)" }}>
              E-Mail-Vorlage: {emailModal.mandant}
            </div>
            <textarea
              readOnly
              value={emailModal.vorlage}
              rows={10}
              style={{
                width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)",
                borderRadius: 8, color: "var(--text)", padding: 10, fontSize: 13, resize: "vertical",
              }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(emailModal.vorlage);
                  setEmailModal(null);
                }}
                style={{ ...btnGhost, background: "var(--accent)", color: "var(--on-accent)", border: "none" }}
              >
                Kopieren
              </button>
              <button type="button" onClick={() => setEmailModal(null)} style={btnGhost}>Schließen</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
