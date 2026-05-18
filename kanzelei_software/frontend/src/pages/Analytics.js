// ============================================================
// KANZLEI AI — ANALYTICS & REPORTING
// KPIs, Prognosen, Benchmarking, Audit-Log, Engine-Tools, Live-WS
// ============================================================

import { useState, useEffect, useCallback } from "react";
import {
  getKpis,
  getDashboard,
  getBenchmarking,
  getPrognoseFristen,
  getPrognoseUmsatz,
  getPrsteuerfristen,
  getAuditLog,
  engineRun,
  engineAnalyse,
  engineBericht,
} from "../api";

const FONTS = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
`;

const fmt = (v) =>
  `€${Number(v || 0).toLocaleString("de-DE", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

const unwrapData = (res) => {
  if (!res) return null;
  if (res.data !== undefined) return res.data;
  return res;
};

const unwrapArray = (res) => {
  const d = unwrapData(res);
  if (Array.isArray(d)) return d;
  if (d && typeof d === "object") return Object.values(d);
  return [];
};

const TabBtn = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    style={{
      padding: "8px 14px",
      borderRadius: 10,
      border: active ? "1px solid color-mix(in srgb, var(--accent) 45%, transparent)" : "1px solid var(--border)",
      background: active ? "color-mix(in srgb, var(--accent) 18%, var(--bg3))" : "transparent",
      color: active ? "var(--accent)" : "var(--text2)",
      fontSize: 13,
      fontWeight: 500,
      cursor: "pointer",
      fontFamily: "var(--font-body)",
    }}
  >
    {children}
  </button>
);

const Card = ({ title, children, style = {} }) => (
  <div
    style={{
      background: "var(--bg2)",
      border: "1px solid var(--border)",
      borderRadius: 14,
      padding: 18,
      marginBottom: 14,
      ...style,
    }}
  >
    {title && (
      <div
        style={{
          fontFamily: "var(--font-head)",
          fontSize: 17,
          color: "var(--text)",
          marginBottom: 12,
        }}
      >
        {title}
      </div>
    )}
    {children}
  </div>
);

// ── Übersicht ───────────────────────────────────────────────
function UebersichtTab({ kpis, dashboard, liveData, loading }) {
  const kpiList = Array.isArray(kpis) ? kpis : [];
  const dKpis = dashboard?.kpis || {};

  return (
    <>
      <Card title="Kennzahlen (Dashboard)">
        {loading && !dashboard ? (
          <div style={{ color: "var(--text3)" }}>Lade …</div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill,minmax(140px,1fr))",
              gap: 12,
            }}
          >
            {[
              ["Mandanten", dKpis.mandanten_gesamt],
              ["Umsatz Σ", fmt(dKpis.total_umsatz)],
              ["Aufgaben offen", dKpis.aufgaben_offen],
              ["Erledigt", dKpis.aufgaben_erledigt],
              ["Überfällig", dKpis.aufgaben_ueberfaellig],
            ].map(([k, v]) => (
              <div
                key={k}
                style={{
                  background: "var(--bg3)",
                  borderRadius: 10,
                  padding: "12px 14px",
                }}
              >
                <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4 }}>{k}</div>
                <div style={{ fontSize: 18, fontWeight: 600, color: "var(--text)" }}>{v ?? "—"}</div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {liveData && (
        <Card title="Live (WebSocket)">
          <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.6 }}>
            <div>Mandanten: {liveData.mandanten_gesamt ?? "—"}</div>
            <div>Aufgaben offen: {liveData.aufgaben_offen ?? "—"}</div>
            <div>Kritisch (≤2 Tage): {liveData.aufgaben_kritisch ?? "—"}</div>
            <div>Timer aktiv: {liveData.timer_laufend ?? "—"}</div>
            <div>Bot-Fragen offen: {liveData.bot_fragen_offen ?? "—"}</div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 8 }}>
              {liveData.zeitpunkt || ""}
            </div>
          </div>
        </Card>
      )}

      <Card title="Mandanten-Risiko (KPIs)">
        {loading && !kpiList.length ? (
          <div style={{ color: "var(--text3)" }}>Lade …</div>
        ) : !kpiList.length ? (
          <div style={{ color: "var(--text3)" }}>Keine KPI-Daten.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: "var(--text3)", textAlign: "left" }}>
                  <th style={{ padding: "8px 6px" }}>Mandant</th>
                  <th style={{ padding: "8px 6px" }}>Status</th>
                  <th style={{ padding: "8px 6px" }}>Score</th>
                  <th style={{ padding: "8px 6px" }}>Umsatz</th>
                </tr>
              </thead>
              <tbody>
                {kpiList.slice(0, 25).map((row, i) => (
                  <tr
                    key={i}
                    style={{ borderTop: `1px solid var(--border)` }}
                  >
                    <td style={{ padding: "10px 6px", color: "var(--text)" }}>
                      {row.mandant || row.name || "—"}
                    </td>
                    <td style={{ padding: "10px 6px", color: "var(--accent)" }}>
                      {row.status || "—"}
                    </td>
                    <td style={{ padding: "10px 6px" }}>{row.score ?? "—"}</td>
                    <td style={{ padding: "10px 6px" }}>{fmt(row.umsatz)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ── Prognose ────────────────────────────────────────────────
function PrognoseTab() {
  const [fristen, setFristen] = useState(null);
  const [umsatz, setUmsatz] = useState(null);
  const [steuer, setSteuer] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const [a, b, c] = await Promise.allSettled([
          getPrognoseFristen(30),
          getPrognoseUmsatz(),
          getPrsteuerfristen(),
        ]);
        if (!cancel) {
          if (a.status === "fulfilled") setFristen(unwrapData(a.value));
          if (b.status === "fulfilled") setUmsatz(unwrapData(b.value));
          if (c.status === "fulfilled") setSteuer(unwrapData(c.value));
        }
      } catch (e) {
        if (!cancel) setErr(String(e.message || e));
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, []);

  if (loading) return <div style={{ color: "var(--text3)" }}>Lade Prognosen …</div>;
  if (err) return <div style={{ color: "var(--red)" }}>{err}</div>;

  return (
    <>
      <Card title="Fristen-Belastung (30 Tage)">
        <pre
          style={{
            color: "var(--text2)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {fristen ? JSON.stringify(fristen, null, 2) : "—"}
        </pre>
      </Card>
      <Card title="Umsatz- & Risiko-Prognose">
        <pre
          style={{
            color: "var(--text2)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {umsatz ? JSON.stringify(umsatz, null, 2) : "—"}
        </pre>
      </Card>
      <Card title="Steuerfristen (Kalender)">
        <pre
          style={{
            color: "var(--text2)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: 0,
          }}
        >
          {steuer ? JSON.stringify(steuer, null, 2) : "—"}
        </pre>
      </Card>
    </>
  );
}

// ── Benchmark ───────────────────────────────────────────────
function BenchmarkTab() {
  const [branche, setBranche] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  const laden = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await getBenchmarking(branche || null);
      setData(unwrapData(r));
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [branche]);

  useEffect(() => {
    laden();
  }, [laden]);

  return (
    <Card title="Branchen-Benchmarking">
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <input
          placeholder="Branche filtern (optional)"
          value={branche}
          onChange={(e) => setBranche(e.target.value)}
          style={{
            flex: 1,
            minWidth: 200,
            padding: "10px 12px",
            borderRadius: 10,
            border: `1px solid var(--border2)`,
            background: "var(--bg3)",
            color: "var(--text)",
            fontSize: 14,
          }}
        />
        <button
          type="button"
          onClick={laden}
          disabled={loading}
          style={{
            padding: "10px 18px",
            borderRadius: 10,
            border: "none",
            background: "var(--accent)",
            color: "var(--on-accent)",
            fontWeight: 600,
            cursor: loading ? "wait" : "pointer",
          }}
        >
          {loading ? "…" : "Aktualisieren"}
        </button>
      </div>
      {err && <div style={{ color: "var(--red)", marginBottom: 10 }}>{err}</div>}
      <pre
        style={{
          color: "var(--text2)",
          fontSize: 12,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          margin: 0,
          maxHeight: 480,
          overflow: "auto",
        }}
      >
        {data ? JSON.stringify(data, null, 2) : "—"}
      </pre>
    </Card>
  );
}

// ── Audit ────────────────────────────────────────────────────
function AuditTab() {
  const [logs, setLogs] = useState([]);
  const [suche, setSuche] = useState("");
  const [loading, setLoading] = useState(true);

  const laden = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getAuditLog(80, suche || null);
      const raw = unwrapData(r);
      const L = raw?.logs || raw?.data?.logs || [];
      setLogs(Array.isArray(L) ? L : []);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [suche]);

  useEffect(() => {
    const t = setTimeout(() => laden(), suche ? 400 : 0);
    return () => clearTimeout(t);
  }, [laden, suche]);

  return (
    <Card title="Audit-Log">
      <input
        placeholder="Suche in Logs …"
        value={suche}
        onChange={(e) => setSuche(e.target.value)}
        style={{
          width: "100%",
          marginBottom: 12,
          padding: "10px 12px",
          borderRadius: 10,
          border: `1px solid var(--border2)`,
          background: "var(--bg3)",
          color: "var(--text)",
          fontSize: 14,
        }}
      />
      {loading ? (
        <div style={{ color: "var(--text3)" }}>Lade …</div>
      ) : (
        <div style={{ maxHeight: 520, overflow: "auto", fontSize: 12 }}>
          {logs.length === 0 ? (
            <span style={{ color: "var(--text3)" }}>Keine Einträge.</span>
          ) : (
            logs.map((l, i) => (
              <div
                key={i}
                style={{
                  padding: "8px 0",
                  borderBottom: `1px solid var(--border)`,
                  color: "var(--text2)",
                }}
              >
                <span style={{ color: "var(--text3)" }}>{l.zeit || l.timestamp || ""}</span>{" "}
                {l.text || JSON.stringify(l)}
              </div>
            ))
          )}
        </div>
      )}
    </Card>
  );
}

// ── Engine ─────────────────────────────────────────────────
function EngineTab() {
  const [bericht, setBericht] = useState(null);
  const [analyse, setAnalyse] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const run = async (fn) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fn();
      return unwrapData(r);
    } catch (e) {
      setMsg(e.message || String(e));
      return null;
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Decision Engine">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            const d = await run(engineRun);
            if (d) {
              setRunResult(d);
              const n = d.mandanten_geprueft ?? d.mandanten ?? "?";
              const w = Array.isArray(d.warnungen) ? d.warnungen.length : 0;
              setMsg(
                `Daily Checks fertig: ${n} Mandanten, ${w} Warnung(en), ${d.emails_gesendet ?? 0} E-Mail(s) gesendet.`
              );
            }
          }}
          style={{
            padding: "10px 16px",
            borderRadius: 10,
            border: `1px solid var(--border2)`,
            background: "var(--bg3)",
            color: "var(--text)",
            cursor: busy ? "wait" : "pointer",
          }}
        >
          Engine jetzt ausführen
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            const d = await run(engineAnalyse);
            setAnalyse(d);
          }}
          style={{
            padding: "10px 16px",
            borderRadius: 10,
            border: `1px solid var(--border2)`,
            background: "var(--bg3)",
            color: "var(--text)",
            cursor: busy ? "wait" : "pointer",
          }}
        >
          Vollanalyse laden
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            const d = await run(engineBericht);
            setBericht(d);
          }}
          style={{
            padding: "10px 16px",
            borderRadius: 10,
            border: `1px solid var(--border2)`,
            background: "var(--bg3)",
            color: "var(--text)",
            cursor: busy ? "wait" : "pointer",
          }}
        >
          Tagesbericht laden
        </button>
      </div>
      {msg && <div style={{ color: "var(--orange)", marginBottom: 10 }}>{msg}</div>}
      {runResult && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ color: "var(--text3)", marginBottom: 6 }}>Letzter Engine-Lauf</div>
          <pre
            style={{
              color: "var(--text2)",
              fontSize: 11,
              whiteSpace: "pre-wrap",
              maxHeight: 280,
              overflow: "auto",
              margin: 0,
            }}
          >
            {JSON.stringify(runResult, null, 2)}
          </pre>
        </div>
      )}
      {bericht && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ color: "var(--text3)", marginBottom: 6 }}>Tagesbericht</div>
          <pre
            style={{
              color: "var(--text2)",
              fontSize: 12,
              whiteSpace: "pre-wrap",
              maxHeight: 220,
              overflow: "auto",
              margin: 0,
            }}
          >
            {typeof bericht.bericht === "string"
              ? bericht.bericht
              : JSON.stringify(bericht, null, 2)}
          </pre>
        </div>
      )}
      {analyse && (
        <div>
          <div style={{ color: "var(--text3)", marginBottom: 6 }}>Analyse</div>
          <pre
            style={{
              color: "var(--text2)",
              fontSize: 11,
              whiteSpace: "pre-wrap",
              maxHeight: 360,
              overflow: "auto",
              margin: 0,
            }}
          >
            {JSON.stringify(analyse, null, 2)}
          </pre>
        </div>
      )}
    </Card>
  );
}

// ── Hauptkomponente ─────────────────────────────────────────
export default function Analytics() {
  const [tab, setTab] = useState("uebersicht");
  const [kpis, setKpis] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [liveData, setLiveData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([getKpis(), getDashboard()]).then(([k, d]) => {
      if (cancelled) return;
      if (k.status === "fulfilled") setKpis(unwrapArray(k.value));
      if (d.status === "fulfilled") setDashboard(unwrapData(d.value) || d.value);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const apiBase = process.env.REACT_APP_API_URL || "/api";
    let wsUrl;
    if (apiBase.startsWith("http://") || apiBase.startsWith("https://")) {
      wsUrl = apiBase
        .replace(/\/api\/?$/i, "")
        .replace("http://", "ws://")
        .replace("https://", "wss://");
    } else {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      wsUrl = `${proto}//${window.location.host}`;
    }
    const tok = localStorage.getItem("kanzlei_token");
    const ws = new WebSocket(
      `${wsUrl}/ws/live${tok ? `?token=${encodeURIComponent(tok)}` : ""}`
    );
    ws.onmessage = (e) => {
      try {
        setLiveData(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
    };
    ws.onerror = () => {};
    return () => ws.close();
  }, []);

  return (
    <div
      style={{
        flex: 1,
        background: "var(--bg)",
        overflowY: "auto",
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      <style>{`
        ${FONTS}
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }
      `}</style>

      <div style={{ padding: "24px 28px 40px", maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ marginBottom: 6, fontSize: 11, letterSpacing: "0.12em", color: "var(--text3)" }}>
          REPORTING
        </div>
        <h1
          style={{
            fontFamily: "'DM Serif Display',serif",
            fontSize: 28,
            fontWeight: 400,
            color: "var(--text)",
            marginBottom: 18,
          }}
        >
          Analytics &amp; Reporting
        </h1>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: 22,
          }}
        >
          <TabBtn active={tab === "uebersicht"} onClick={() => setTab("uebersicht")}>
            Übersicht
          </TabBtn>
          <TabBtn active={tab === "prognose"} onClick={() => setTab("prognose")}>
            Prognose
          </TabBtn>
          <TabBtn active={tab === "benchmark"} onClick={() => setTab("benchmark")}>
            Benchmarking
          </TabBtn>
          <TabBtn active={tab === "audit"} onClick={() => setTab("audit")}>
            Audit-Log
          </TabBtn>
          <TabBtn active={tab === "engine"} onClick={() => setTab("engine")}>
            Engine
          </TabBtn>
        </div>

        {tab === "uebersicht" && (
          <UebersichtTab
            kpis={kpis}
            dashboard={dashboard}
            liveData={liveData}
            loading={loading}
          />
        )}
        {tab === "prognose" && <PrognoseTab />}
        {tab === "benchmark" && <BenchmarkTab />}
        {tab === "audit" && <AuditTab />}
        {tab === "engine" && <EngineTab />}
      </div>
    </div>
  );
}
