// ============================================================
// KANZLEI AI — APP.JS v3.0 (PRODUKTIONSREIF)
// Alle Bugs behoben:
//   ✓ Dashboard zeigt echte KPIs + Heute + Empfehlungen
//   ✓ Aufgaben-Tab: Erstellen funktioniert, alle Mandanten geladen
//   ✓ AufgabenSeite: API-Reihenfolge korrekt, /kpis für alle Aufgaben
//   ✓ MandantDetailPage: useParams statt window.location
//   ✓ getMandanten: einheitliche Datenverarbeitung
//   ✓ Login: Auth-Check korrekt
// ============================================================

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { BrowserRouter as Router, Routes, Route, Link, useNavigate, useParams } from "react-router-dom";

import {
  getMandanten, getHeute, getEmpfehlungen, getKpis,
  addMandantAPI, updateMandantAPI, deleteMandantAPI,
  addAufgabeAPI, toggleAufgabeAPI, deleteAufgabeAPI,
  getEmailPreview, sendEmail, getSaasReadiness,
} from "./api";

import Analytics         from "./pages/Analytics";
import Settings          from "./pages/Settings";
import KIAssistent       from "./pages/KIAssistent";
import BelegScanner      from "./pages/BelegScanner";
import Rechnungen        from "./pages/Rechnungen";
import DokumentScanner   from "./pages/DokumentScanner";
import ProfitMonitor     from "./pages/ProfitMonitor";
import WorkflowBaukasten from "./pages/WorkflowBaukasten";
import SteuerAutopilot   from "./pages/SteuerAutopilot";
import Login             from "./pages/Login";

// ─── Hilfsfunktion: API mit Auth-Token ──────────────────────
const BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

async function apiGet(url) {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE_URL + url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ─── Mandanten-Array normalisieren ──────────────────────────
function normalisiereMandanten(raw) {
  if (!raw) return [];
  // Format 1: { data: [{name, ...}, ...] }
  if (Array.isArray(raw.data)) return raw.data;
  // Format 2: { data: { "Name": {...}, ... } }
  if (raw.data && typeof raw.data === "object") {
    return Object.entries(raw.data).map(([name, v]) => ({ name, ...v }));
  }
  // Format 3: direkt Array
  if (Array.isArray(raw)) return raw;
  // Format 4: direkt Objekt
  if (typeof raw === "object") {
    return Object.entries(raw).map(([name, v]) => ({ name, ...v }));
  }
  return [];
}

// ─── Google Fonts + CSS Variablen ───────────────────────────
const FontLoader = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:         #0b0d11;
      --bg2:        #111419;
      --bg3:        #181c24;
      --border:     rgba(255,255,255,0.07);
      --border2:    rgba(255,255,255,0.14);
      --text:       #e8eaf0;
      --text2:      #8b91a0;
      --text3:      #555d6e;
      --accent:     #c8a96e;
      --red:        #e05555;
      --orange:     #e08c45;
      --green:      #5cb87a;
      --blue:       #5b8de8;
      --radius:     12px;
      --radius-lg:  18px;
      --font-head:  'DM Serif Display', Georgia, serif;
      --font-body:  'DM Sans', system-ui, sans-serif;
      --transition: 0.18s ease;
    }

    html, body, #root {
      height: 100%;
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-body);
      font-size: 14px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }

    a { color: inherit; text-decoration: none; }
    button { font-family: var(--font-body); cursor: pointer; }
    input, select, textarea { font-family: var(--font-body); }

    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

    @keyframes fadeUp  { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
    @keyframes fadeIn  { from { opacity:0; } to { opacity:1; } }
    @keyframes pulse   { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
    @keyframes slideIn { from { transform:translateX(100%); opacity:0; } to { transform:translateX(0); opacity:1; } }
    @keyframes spin    { to { transform:rotate(360deg); } }
  `}</style>
);

// ─── Design Tokens ───────────────────────────────────────────
const C = {
  red:"#e05555", orange:"#e08c45", green:"#5cb87a",
  blue:"#5b8de8", accent:"#c8a96e",
};

// ═══════════════════════════════════════════════════════════
// PRIMITIVE COMPONENTS
// ═══════════════════════════════════════════════════════════

const Badge = ({ children, color = C.accent, style = {} }) => (
  <span style={{
    display:"inline-block", padding:"2px 8px", borderRadius:20,
    fontSize:11, fontWeight:600, letterSpacing:"0.04em", textTransform:"uppercase",
    background:color+"22", color, border:`1px solid ${color}33`, ...style,
  }}>
    {children}
  </span>
);

const Divider = () => <div style={{ height:1, background:"var(--border)", margin:"20px 0" }} />;

const Spinner = ({ size = 18 }) => (
  <div style={{
    width:size, height:size, borderRadius:"50%",
    border:`2px solid var(--border2)`, borderTopColor:"var(--accent)",
    animation:"spin 0.7s linear infinite", display:"inline-block",
  }} />
);

const Btn = ({ children, onClick, variant="primary", size="md",
               disabled=false, loading=false, style={}, title }) => {
  const sizes = {
    xs:{ padding:"4px 10px", fontSize:12 },
    sm:{ padding:"6px 14px", fontSize:13 },
    md:{ padding:"9px 18px", fontSize:14 },
    lg:{ padding:"12px 24px", fontSize:15 },
  };
  const variants = {
    primary: { background:"var(--accent)", color:"#1a1200", border:"none" },
    danger:  { background:C.red+"22",      color:C.red,    border:`1px solid ${C.red}33` },
    ghost:   { background:"transparent",   color:"var(--text2)", border:"1px solid var(--border2)" },
    subtle:  { background:"var(--bg3)",    color:"var(--text2)", border:"none" },
    success: { background:C.green+"22",    color:C.green,  border:`1px solid ${C.green}33` },
  };
  return (
    <button onClick={!disabled && !loading ? onClick : undefined} title={title}
      style={{
        display:"inline-flex", alignItems:"center", gap:6,
        borderRadius:"var(--radius)", fontWeight:500, whiteSpace:"nowrap",
        cursor:disabled||loading?"not-allowed":"pointer",
        opacity:disabled||loading?0.5:1,
        transition:"all var(--transition)",
        ...sizes[size], ...variants[variant], ...style,
      }}>
      {loading && <Spinner size={13} />}
      {children}
    </button>
  );
};

const Input = ({ placeholder, value, onChange, onKeyDown, type="text", disabled=false, style={} }) => (
  <input type={type} placeholder={placeholder} value={value}
    onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown} disabled={disabled}
    style={{
      width:"100%", background:"var(--bg)", border:"1px solid var(--border2)",
      borderRadius:"var(--radius)", color:"var(--text)", padding:"9px 13px",
      fontSize:14, outline:"none", transition:"border var(--transition)", ...style,
    }}
    onFocus={e => e.target.style.borderColor="var(--accent)"}
    onBlur={e  => e.target.style.borderColor=""}
  />
);

const Card = ({ children, style={}, animate=false, delay=0 }) => (
  <div style={{
    background:"var(--bg2)", border:"1px solid var(--border)",
    borderRadius:"var(--radius-lg)", padding:20,
    animation:animate?`fadeUp 0.4s ease ${delay}ms both`:"none", ...style,
  }}>
    {children}
  </div>
);

const StatusDot = ({ status }) => {
  const colors = { KRITISCH:C.red, WICHTIG:C.orange, NORMAL:C.green, OK:C.green };
  const c = colors[status] || "var(--text3)";
  return (
    <span style={{
      display:"inline-block", width:8, height:8, borderRadius:"50%",
      background:c, boxShadow:`0 0 6px ${c}88`, flexShrink:0,
      animation:status==="KRITISCH"?"pulse 1.5s ease infinite":"none",
    }} />
  );
};

// ═══════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════

const ToastContainer = ({ toasts }) => (
  <div style={{ position:"fixed", top:20, right:20, zIndex:9999,
                display:"flex", flexDirection:"column", gap:10 }}>
    {toasts.map(t => {
      const colors = { success:C.green, error:C.red, info:C.blue, warn:C.orange };
      const c = colors[t.type] || C.accent;
      return (
        <div key={t.id} style={{
          background:"var(--bg3)", border:`1px solid ${c}44`,
          borderLeft:`3px solid ${c}`, color:"var(--text)",
          borderRadius:"var(--radius)", padding:"12px 16px",
          minWidth:260, maxWidth:340, fontSize:13, fontWeight:500,
          animation:"slideIn 0.25s ease both",
        }}>
          {t.text}
        </div>
      );
    })}
  </div>
);

// ═══════════════════════════════════════════════════════════
// SIDEBAR
// ═══════════════════════════════════════════════════════════

const Sidebar = ({ activeTab, setActiveTab, kpis }) => {
  const kritisch = kpis.filter(k => k.status === "KRITISCH").length;
  const wichtig  = kpis.filter(k => k.status === "WICHTIG").length;

  const navItems = [
    { id:"dashboard",    label:"Dashboard",        icon:"⬛" },
    { id:"mandanten",    label:"Mandanten",        icon:"◉",  badge:kpis.length },
    { id:"aufgaben",     label:"Aufgaben",          icon:"▦",  badge:kritisch||null },
    { id:"ki",           label:"KI-Assistent",     icon:"✦" },
    { id:"profit",       label:"Profit Monitor",   icon:"📈" },
    { id:"steuerbot",    label:"Steuer-Autopilot", icon:"🤖" },
    { id:"dokumente",    label:"Dokument-Scanner", icon:"📂" },
    { id:"belege",       label:"Belegscanner",     icon:"📎" },
    { id:"rechnungen",   label:"Rechnungen",       icon:"🧾" },
    { id:"automation",   label:"Automation",       icon:"⚙" },
    { id:"empfehlungen", label:"KI-Insights",      icon:"◈" },
    { id:"analytics",    label:"Analytics",        icon:"◎" },
    { id:"neu",          label:"Neu anlegen",      icon:"＋" },
    { id:"settings",     label:"Einstellungen",    icon:"🔧" },
  ];

  return (
    <nav style={{
      width:220, flexShrink:0, background:"var(--bg2)",
      borderRight:"1px solid var(--border)", display:"flex",
      flexDirection:"column", height:"100vh", position:"sticky", top:0, padding:"28px 0",
    }}>
      <div style={{ padding:"0 24px 28px" }}>
        <div style={{ fontFamily:"var(--font-head)", fontSize:22,
                      color:"var(--accent)", letterSpacing:"-0.01em", lineHeight:1.2 }}>
          Kanzlei<br />
          <span style={{ color:"var(--text)", fontSize:18 }}>AI</span>
        </div>
        <div style={{ fontSize:11, color:"var(--text3)", marginTop:4 }}>
          Steuerberater Suite
        </div>
      </div>

      <Divider />

      {(kritisch > 0 || wichtig > 0) && (
        <div style={{
          margin:"0 16px 16px", background:C.red+"15",
          border:`1px solid ${C.red}30`, borderRadius:"var(--radius)", padding:"10px 12px",
        }}>
          {kritisch > 0 && <div style={{ color:C.red, fontWeight:600, fontSize:12 }}>● {kritisch} kritisch</div>}
          {wichtig  > 0 && <div style={{ color:C.orange, fontWeight:500, fontSize:12, marginTop:2 }}>● {wichtig} wichtig</div>}
        </div>
      )}

      <div style={{ flex:1, padding:"0 12px", overflowY:"auto" }}>
        {navItems.map(item => {
          const active = activeTab === item.id;
          return (
            <button key={item.id} onClick={() => setActiveTab(item.id)} style={{
              width:"100%", display:"flex", alignItems:"center", gap:10,
              padding:"10px 12px", borderRadius:"var(--radius)", border:"none",
              background:active?"var(--bg3)":"transparent",
              color:active?"var(--accent)":"var(--text2)",
              fontWeight:active?600:400, fontSize:14, cursor:"pointer", marginBottom:2,
              transition:"all var(--transition)",
              borderLeft:active?`3px solid var(--accent)`:"3px solid transparent",
            }}>
              <span style={{ fontSize:16 }}>{item.icon}</span>
              <span style={{ flex:1, textAlign:"left" }}>{item.label}</span>
              {item.badge ? (
                <Badge color={item.id==="aufgaben"&&kritisch?C.red:C.accent}
                       style={{ fontSize:10 }}>
                  {item.badge}
                </Badge>
              ) : null}
            </button>
          );
        })}
      </div>

      <Divider />
      <div style={{ padding:"0 24px", fontSize:11, color:"var(--text3)" }}>
        v3.0 · Auto-Refresh aktiv
      </div>
    </nav>
  );
};

// ═══════════════════════════════════════════════════════════
// KPI STRIP (Dashboard)
// ═══════════════════════════════════════════════════════════

const KpiStrip = ({ kpis, heute }) => {
  const gesamt   = kpis.length;
  const kritisch = kpis.filter(k => k.status === "KRITISCH").length;
  const umsatz   = kpis.reduce((s, k) => s + (k.umsatz || 0), 0);
  const dringend = heute.length;

  return (
    <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:16, marginBottom:28 }}>
      {[
        { label:"Mandanten",    value:gesamt,                               icon:"◉", color:C.blue },
        { label:"Kritisch",     value:kritisch,                             icon:"●", color:kritisch?C.red:C.green },
        { label:"Heute fällig", value:dringend,                            icon:"▦", color:dringend?C.orange:C.green },
        { label:"Gesamtumsatz", value:`€${umsatz.toLocaleString("de")}`,   icon:"◈", color:C.accent },
      ].map((item, i) => (
        <Card key={i} animate delay={i*60} style={{ padding:"18px 20px" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
            <div>
              <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                            letterSpacing:"0.08em", marginBottom:6 }}>{item.label}</div>
              <div style={{ fontSize:28, fontFamily:"var(--font-head)",
                            color:item.color, lineHeight:1 }}>{item.value}</div>
            </div>
            <span style={{ fontSize:22, color:item.color+"66" }}>{item.icon}</span>
          </div>
        </Card>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HEUTE PANEL
// ═══════════════════════════════════════════════════════════

const HeutePanel = ({ heute }) => {
  if (!heute || heute.length === 0) {
    return (
      <Card style={{ textAlign:"center", padding:32 }}>
        <div style={{ fontSize:32, marginBottom:10 }}>✓</div>
        <div style={{ color:"var(--text2)", fontWeight:500 }}>Alles im grünen Bereich</div>
        <div style={{ color:"var(--text3)", fontSize:13, marginTop:4 }}>
          Keine dringenden Aufgaben für heute
        </div>
      </Card>
    );
  }

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
      {heute.map((item, i) => {
        const isUeber = (item.tage || 0) < 0;
        const c = isUeber ? C.red : item.tage === 0 ? C.orange : "var(--text2)";
        return (
          <div key={i} style={{
            background:"var(--bg2)", border:`1px solid ${isUeber?C.red+"33":"var(--border)"}`,
            borderRadius:"var(--radius)", padding:"14px 16px",
            display:"flex", alignItems:"center", gap:14,
            animation:`fadeUp 0.3s ease ${i*50}ms both`,
          }}>
            <div style={{
              width:36, height:36, borderRadius:"var(--radius)",
              background:c+"20", display:"flex", alignItems:"center",
              justifyContent:"center", flexShrink:0, fontSize:16, color:c,
            }}>
              {isUeber ? "⚠" : item.tage === 0 ? "●" : "◎"}
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontWeight:500, color:"var(--text)", fontSize:14 }}>
                {item.text || item.beschreibung || "Aufgabe"}
              </div>
              <div style={{ fontSize:12, color:c, marginTop:2 }}>
                {item.label || item.frist || ""}
              </div>
            </div>
            <Badge color={c}>{item.prioritaet || "normal"}</Badge>
          </div>
        );
      })}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// EMPFEHLUNGEN PANEL
// ═══════════════════════════════════════════════════════════

const EmpfehlungenPanel = ({ empfehlungen, onEmail }) => {
  if (!empfehlungen || empfehlungen.length === 0) {
    return (
      <Card style={{ textAlign:"center", padding:32 }}>
        <div style={{ color:"var(--text3)" }}>Keine Handlungsempfehlungen</div>
      </Card>
    );
  }

  const typColors = {
    kritisch:C.red, dringend:C.red, wichtig:C.orange,
    frist:C.orange, dokumente:C.blue, info:C.accent,
  };

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
      {empfehlungen.slice(0, 12).map((m, i) => (
        <Card key={i} animate delay={i*50} style={{ padding:"16px 18px" }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"flex-start", marginBottom:12 }}>
            <div>
              <div style={{ fontWeight:600, color:"var(--text)", fontSize:15 }}>{m.mandant}</div>
              <div style={{ fontSize:12, color:"var(--accent)", marginTop:2 }}>
                €{(m.umsatz || 0).toLocaleString("de")} Jahresumsatz
              </div>
            </div>
            <div style={{ display:"flex", gap:8 }}>
              <Link to={`/mandant/${encodeURIComponent(m.mandant)}`}>
                <Btn size="xs" variant="ghost">Details →</Btn>
              </Link>
              {onEmail && (
                <Btn size="xs" variant="subtle" onClick={() => onEmail(m.mandant)}>
                  ✉ Email
                </Btn>
              )}
            </div>
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
            {(m.empfehlungen || []).map((e, j) => {
              const c = typColors[e.typ] || "var(--text3)";
              return (
                <div key={j} style={{
                  display:"flex", alignItems:"center", gap:10,
                  padding:"7px 10px", borderRadius:8,
                  background:c+"10", border:`1px solid ${c}22`,
                }}>
                  <span style={{ color:c, fontSize:12, flexShrink:0 }}>●</span>
                  <span style={{ fontSize:13, color:"var(--text2)" }}>{e.text}</span>
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// MANDANTEN TABELLE
// ═══════════════════════════════════════════════════════════

const MandantenTabelle = ({ kpis, onSelect, onDelete, onEmail, selectedName }) => {
  const [suche, setSuche] = useState("");
  const [sort,  setSort]  = useState("score");

  const gefiltert = kpis
    .filter(k => !suche || (k.mandant || "").toLowerCase().includes(suche.toLowerCase()))
    .slice()
    .sort((a, b) => {
      if (sort === "score")  return (b.score||0) - (a.score||0);
      if (sort === "umsatz") return (b.umsatz||0) - (a.umsatz||0);
      return (a.mandant||"").localeCompare(b.mandant||"");
    });

  return (
    <Card style={{ padding:0, overflow:"hidden" }}>
      <div style={{ padding:"16px 20px", display:"flex", gap:12,
                    alignItems:"center", borderBottom:"1px solid var(--border)" }}>
        <div style={{ flex:1 }}>
          <Input placeholder="Mandanten suchen..." value={suche}
                 onChange={setSuche} style={{ maxWidth:260 }} />
        </div>
        <div style={{ display:"flex", gap:6 }}>
          {[["score","Priorität"],["umsatz","Umsatz"],["name","Name"]].map(([s,l]) => (
            <Btn key={s} variant={sort===s?"subtle":"ghost"} size="xs"
                 onClick={() => setSort(s)}>{l}</Btn>
          ))}
        </div>
      </div>

      <div style={{ overflowX:"auto" }}>
        <table style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead>
            <tr style={{ borderBottom:"1px solid var(--border)" }}>
              {["Status","Mandant","Umsatz","Score","Aufgaben","Tage o.A.",""].map(h => (
                <th key={h} style={{ padding:"10px 16px", textAlign:"left",
                                     fontSize:11, fontWeight:600, color:"var(--text3)",
                                     textTransform:"uppercase", letterSpacing:"0.07em" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {gefiltert.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding:"32px 16px", textAlign:"center",
                                          color:"var(--text3)" }}>
                  Keine Mandanten gefunden
                </td>
              </tr>
            )}
            {gefiltert.map((k, i) => {
              const isSelected = k.mandant === selectedName;
              const sc = { KRITISCH:C.red, WICHTIG:C.orange, NORMAL:C.green }[k.status] || "var(--text3)";
              return (
                <tr key={k.mandant} onClick={() => onSelect(k.mandant)}
                  style={{
                    borderBottom:"1px solid var(--border)",
                    background:isSelected?"var(--bg3)":i%2===0?"transparent":"rgba(255,255,255,0.01)",
                    cursor:"pointer", transition:"background var(--transition)",
                    animation:`fadeUp 0.3s ease ${i*40}ms both`,
                  }}>
                  <td style={{ padding:"13px 16px" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <StatusDot status={k.status} />
                      <Badge color={sc} style={{ fontSize:10 }}>{k.status}</Badge>
                    </div>
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    <Link to={`/mandant/${encodeURIComponent(k.mandant)}`}
                      onClick={e => e.stopPropagation()}
                      style={{ color:"var(--text)", fontWeight:500 }}>
                      {k.mandant}
                    </Link>
                    {k.email && (
                      <div style={{ fontSize:11, color:"var(--text3)", marginTop:2 }}>{k.email}</div>
                    )}
                  </td>
                  <td style={{ padding:"13px 16px", color:C.accent, fontWeight:600 }}>
                    €{(k.umsatz||0).toLocaleString("de")}
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <div style={{ width:60, height:4, borderRadius:2,
                                    background:"var(--bg3)", overflow:"hidden" }}>
                        <div style={{ width:`${Math.min(100,(k.score||0)/20000*100)}%`,
                                      height:"100%", background:sc, borderRadius:2,
                                      transition:"width 0.5s ease" }} />
                      </div>
                      <span style={{ fontSize:12, color:"var(--text2)" }}>
                        {Math.round(k.score||0).toLocaleString("de")}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    {k.aufgaben_ueberfaellig > 0 ? (
                      <Badge color={C.red}>{k.aufgaben_ueberfaellig} überfällig</Badge>
                    ) : (
                      <span style={{ color:"var(--text3)", fontSize:12 }}>
                        {k.aufgaben_offen||0} offen
                      </span>
                    )}
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    <span style={{ color:(k.tage_ohne_antwort||0)>=7?C.orange:"var(--text2)", fontSize:13 }}>
                      {k.tage_ohne_antwort===999?"∞":(k.tage_ohne_antwort||0)}d
                    </span>
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    <div style={{ display:"flex", gap:6 }} onClick={e => e.stopPropagation()}>
                      {k.email && (
                        <Btn size="xs" variant="ghost" title="Email senden"
                             onClick={() => onEmail(k.mandant)}>✉</Btn>
                      )}
                      <Btn size="xs" variant="danger" title="Löschen"
                           onClick={() => onDelete(k.mandant)}>✕</Btn>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// MANDANT FORM
// ═══════════════════════════════════════════════════════════

const MandantFormPanel = ({ initialData, onSubmit, onCancel, loading, onDirtyChange }) => {
  const isEdit = !!initialData;
  const initialForm = useMemo(() => ({
    name:    initialData?.name    || "",
    email:   initialData?.email   || "",
    umsatz:  initialData?.umsatz?.toString() || "",
    telefon: initialData?.telefon || "",
    branche: initialData?.branche || "",
    notizen: initialData?.notizen || "",
  }), [initialData]);
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");

  useEffect(() => {
    const next = {
      name:    initialData?.name    || "",
      email:   initialData?.email   || "",
      umsatz:  initialData?.umsatz?.toString() || "",
      telefon: initialData?.telefon || "",
      branche: initialData?.branche || "",
      notizen: initialData?.notizen || "",
    };
    setForm(next);
    setError("");
  }, [initialData]);

  useEffect(() => {
    if (!onDirtyChange) return;
    const dirty =
      form.name !== initialForm.name ||
      form.email !== initialForm.email ||
      form.umsatz !== initialForm.umsatz ||
      form.telefon !== initialForm.telefon ||
      form.branche !== initialForm.branche ||
      form.notizen !== initialForm.notizen;
    onDirtyChange(dirty);
  }, [form, initialForm, onDirtyChange]);

  const set = (field, val) => { setForm(p => ({ ...p, [field]:val })); setError(""); };

  const validate = () => {
    if (!form.name.trim())                return "Name ist Pflichtfeld";
    if (form.email && !form.email.includes("@")) return "Ungültige E-Mail";
    if (!form.umsatz || isNaN(form.umsatz))      return "Umsatz muss eine Zahl sein";
    if (Number(form.umsatz) < 0)          return "Umsatz darf nicht negativ sein";
    return null;
  };

  const handleSubmit = async () => {
    const err = validate();
    if (err) { setError(err); return; }
    try {
      await onSubmit({
        name:    form.name.trim(),
        email:   form.email.trim(),
        umsatz:  parseFloat(form.umsatz),
        telefon: form.telefon.trim(),
        branche: form.branche.trim(),
        notizen: form.notizen.trim(),
      });
    } catch (e) { setError(e.message || "Fehler beim Speichern"); }
  };

  return (
    <Card animate style={{ maxWidth:480 }}>
      <div style={{ marginBottom:20 }}>
        <div style={{ fontFamily:"var(--font-head)", fontSize:20, color:"var(--accent)", marginBottom:4 }}>
          {isEdit ? "Mandant bearbeiten" : "Neuer Mandant"}
        </div>
        <div style={{ color:"var(--text3)", fontSize:13 }}>
          {isEdit ? `Daten für ${initialData.name} aktualisieren` : "Mandant im System anlegen"}
        </div>
      </div>

      {error && (
        <div style={{ background:C.red+"15", border:`1px solid ${C.red}33`,
                      borderRadius:"var(--radius)", padding:"10px 14px",
                      color:C.red, fontSize:13, marginBottom:16 }}>
          ⚠ {error}
        </div>
      )}

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>
        {[
          { key:"name",    label:"Name *",         fullWidth:true, disabled:isEdit },
          { key:"email",   label:"E-Mail" },
          { key:"umsatz",  label:"Jahresumsatz (€) *" },
          { key:"telefon", label:"Telefon" },
          { key:"branche", label:"Branche" },
        ].map(f => (
          <div key={f.key} style={{ gridColumn:f.fullWidth?"1 / -1":"auto" }}>
            <div style={{ fontSize:11, color:"var(--text3)", marginBottom:5,
                          textTransform:"uppercase", letterSpacing:"0.06em" }}>
              {f.label}
            </div>
            <Input placeholder={f.label} value={form[f.key]}
                   onChange={v => set(f.key, v)}
                   onKeyDown={e => e.key === "Enter" && handleSubmit()}
                   disabled={f.disabled} />
          </div>
        ))}
      </div>

      <div style={{ marginBottom:20 }}>
        <div style={{ fontSize:11, color:"var(--text3)", marginBottom:5,
                      textTransform:"uppercase", letterSpacing:"0.06em" }}>Notizen</div>
        <textarea placeholder="Interne Notizen..." value={form.notizen}
          onChange={e => set("notizen", e.target.value)} rows={3}
          style={{ width:"100%", background:"var(--bg)", border:"1px solid var(--border2)",
                   borderRadius:"var(--radius)", color:"var(--text)", padding:"9px 13px",
                   fontSize:14, outline:"none", resize:"vertical", fontFamily:"var(--font-body)" }} />
      </div>

      <div style={{ display:"flex", gap:10 }}>
        <Btn onClick={handleSubmit} loading={loading} variant="primary">
          {isEdit ? "Aktualisieren" : "Anlegen"}
        </Btn>
        <Btn onClick={onCancel} variant="ghost">Abbrechen</Btn>
      </div>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// EMAIL MODAL
// ═══════════════════════════════════════════════════════════

const EmailModal = ({ name, onClose, onSend }) => {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    getEmailPreview(name)
      .then(d => setPreview(d))
      .catch(() => setPreview({ email_text:"Vorschau nicht verfügbar", empfaenger:"" }))
      .finally(() => setLoading(false));
  }, [name]);

  const handleSend = async () => {
    setSending(true);
    try { await onSend(name); onClose(); }
    catch (e) { alert("Fehler: " + e.message); }
    finally { setSending(false); }
  };

  return (
    <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.75)",
                  display:"flex", alignItems:"center", justifyContent:"center",
                  zIndex:1000, animation:"fadeIn 0.15s ease" }}
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ background:"var(--bg2)", border:"1px solid var(--border2)",
                    borderRadius:"var(--radius-lg)", width:"min(560px,90vw)",
                    maxHeight:"80vh", display:"flex", flexDirection:"column" }}>
        <div style={{ padding:"20px 24px", borderBottom:"1px solid var(--border)",
                      display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div>
            <div style={{ fontFamily:"var(--font-head)", fontSize:18, color:"var(--accent)" }}>
              Email-Vorschau
            </div>
            <div style={{ fontSize:12, color:"var(--text3)", marginTop:2 }}>
              {name}{preview?.empfaenger ? ` · ${preview.empfaenger}` : ""}
            </div>
          </div>
          <Btn variant="ghost" size="sm" onClick={onClose}>✕</Btn>
        </div>

        <div style={{ flex:1, overflowY:"auto", padding:"20px 24px" }}>
          {loading ? (
            <div style={{ textAlign:"center", padding:40 }}><Spinner size={28} /></div>
          ) : (
            <pre style={{ whiteSpace:"pre-wrap", fontFamily:"var(--font-body)",
                          fontSize:13, color:"var(--text2)", lineHeight:1.7,
                          background:"var(--bg)", border:"1px solid var(--border)",
                          borderRadius:"var(--radius)", padding:16 }}>
              {preview?.email_text}
            </pre>
          )}
        </div>

        <div style={{ padding:"16px 24px", borderTop:"1px solid var(--border)",
                      display:"flex", gap:10 }}>
          <Btn onClick={handleSend} loading={sending} variant="primary">Email senden</Btn>
          <Btn onClick={onClose} variant="ghost">Schließen</Btn>
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// AUFGABEN SEITE
// Bug-fixes:
//   - apiFetchAll vor useCallback definiert
//   - /kpis für Mandanten-Liste (alle Mandanten)
//   - /heute für dringende Aufgaben
//   - Alle Aufgaben über getMandanten + getAufgabenMandant
// ═══════════════════════════════════════════════════════════

function AufgabenSeite({ kpis, heute, onRefresh }) {
  const [mandantenNamen, setMandantenNamen] = useState([]);
  const [allAufgaben,    setAllAufgaben]    = useState([]);
  const [mandant,        setMandant]        = useState("");
  const [beschreibung,   setBeschreibung]   = useState("");
  const [frist,          setFrist]          = useState("");
  const [prioritaet,     setPrio]           = useState("normal");
  const [adding,         setAdding]         = useState(false);
  const [fehler,         setFehler]         = useState("");
  const [success,        setSuccess]        = useState("");
  const [ladeAufgaben,   setLadeAufgaben]   = useState(false);

  const PRIO_FARBEN = { kritisch:C.red, hoch:C.orange, normal:C.accent, niedrig:"var(--text3)" };

  // Alle Aufgaben aus allen Mandanten laden
  const laden = useCallback(async () => {
    setLadeAufgaben(true);
    try {
      const raw = await getMandanten();
      const liste = normalisiereMandanten(raw);
      const namen = liste.map(m => m.name || m).filter(Boolean);
      setMandantenNamen(namen);

      // Alle Aufgaben aller Mandanten laden
      const aufgabenArrays = await Promise.allSettled(
        namen.map(n => apiGet(`/mandanten/${encodeURIComponent(n)}/aufgaben`))
      );

      const alle = [];
      aufgabenArrays.forEach((res, idx) => {
        if (res.status === "fulfilled") {
          const a = res.value?.aufgaben || res.value || [];
          (Array.isArray(a) ? a : []).forEach(aufg => {
            alle.push({ ...aufg, mandant: namen[idx] });
          });
        }
      });

      setAllAufgaben(alle);
    } catch (e) {
      console.error("AufgabenSeite laden:", e);
    } finally {
      setLadeAufgaben(false);
    }
  }, []);

  useEffect(() => { laden(); }, [laden]);

  const hinzufuegen = async () => {
    setFehler("");
    if (!mandant)           { setFehler("Bitte Mandant wählen");      return; }
    if (!beschreibung.trim()){ setFehler("Bitte Beschreibung eingeben"); return; }
    if (!frist)              { setFehler("Bitte Frist wählen");        return; }
    setAdding(true);
    try {
      await addAufgabeAPI(mandant, {
        beschreibung: beschreibung.trim(), frist, prioritaet,
      });
      setBeschreibung(""); setFrist(""); setPrio("normal"); setMandant("");
      setSuccess("✓ Aufgabe wurde erstellt");
      setTimeout(() => setSuccess(""), 3000);
      laden();
      if (onRefresh) onRefresh();
    } catch (e) {
      setFehler(e.message || "Fehler beim Speichern");
    } finally {
      setAdding(false);
    }
  };

  const offen    = allAufgaben.filter(a => !a.erledigt);
  const kritisch = offen.filter(a => a.prioritaet === "kritisch" || a.prioritaet === "hoch");

  const inp = {
    background:"var(--bg)", border:"1px solid var(--border2)", borderRadius:10,
    color:"var(--text)", padding:"10px 14px", fontSize:14, outline:"none",
    fontFamily:"var(--font-body)", width:"100%",
  };

  return (
    <div style={{ padding:"28px 36px", flex:1, overflowY:"auto" }}>
      {/* Header */}
      <div style={{ fontFamily:"var(--font-head)", fontSize:24, color:"var(--text)", marginBottom:4 }}>
        Aufgaben & Fristen
      </div>
      <div style={{ fontSize:13, color:"var(--text3)", marginBottom:24 }}>
        {offen.length} offen · {kritisch.length} kritisch/hoch
        {ladeAufgaben && <span style={{ marginLeft:12, opacity:0.5 }}><Spinner size={12} /></span>}
      </div>

      {/* Neue Aufgabe */}
      <Card style={{ marginBottom:28 }}>
        <div style={{ fontFamily:"var(--font-head)", fontSize:17, color:"var(--accent)", marginBottom:16 }}>
          + Neue Aufgabe erstellen
        </div>

        {fehler && (
          <div style={{ background:C.red+"15", border:`1px solid ${C.red}30`,
                        borderRadius:8, padding:"8px 12px", marginBottom:12,
                        color:C.red, fontSize:13 }}>
            ⚠ {fehler}
          </div>
        )}
        {success && (
          <div style={{ background:C.green+"15", border:`1px solid ${C.green}30`,
                        borderRadius:8, padding:"8px 12px", marginBottom:12,
                        color:C.green, fontSize:13 }}>
            {success}
          </div>
        )}

        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12, marginBottom:12 }}>
          <div>
            <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                          letterSpacing:"0.07em", marginBottom:5 }}>Mandant *</div>
            <select value={mandant} onChange={e => setMandant(e.target.value)} style={inp}>
              <option value="">— Mandant wählen —</option>
              {mandantenNamen.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                          letterSpacing:"0.07em", marginBottom:5 }}>Frist *</div>
            <input type="date" value={frist} onChange={e => setFrist(e.target.value)}
                   style={{ ...inp, colorScheme:"dark" }} />
          </div>
        </div>

        <div style={{ marginBottom:12 }}>
          <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                        letterSpacing:"0.07em", marginBottom:5 }}>Beschreibung *</div>
          <input value={beschreibung} onChange={e => setBeschreibung(e.target.value)}
                 onKeyDown={e => e.key === "Enter" && hinzufuegen()}
                 placeholder="z.B. USt-Voranmeldung Januar einreichen"
                 style={inp} />
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:16 }}>
          <span style={{ fontSize:12, color:"var(--text3)" }}>Priorität:</span>
          {Object.entries(PRIO_FARBEN).map(([p, fc]) => (
            <button key={p} onClick={() => setPrio(p)} style={{
              padding:"5px 13px", borderRadius:20, cursor:"pointer",
              background:prioritaet===p?fc+"30":"var(--bg3)",
              color:prioritaet===p?fc:"var(--text3)",
              fontWeight:prioritaet===p?600:400, fontSize:13,
              border:`1px solid ${prioritaet===p?fc+"60":"var(--border)"}`,
              fontFamily:"var(--font-body)",
            }}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>

        <Btn onClick={hinzufuegen} loading={adding} variant="primary" size="lg">
          Aufgabe speichern
        </Btn>
      </Card>

      {/* Heute & Dringend */}
      {heute && heute.length > 0 && (
        <div style={{ marginBottom:28 }}>
          <div style={{ fontFamily:"var(--font-head)", fontSize:17, color:"var(--text)", marginBottom:12 }}>
            Heute & Dringend
          </div>
          <HeutePanel heute={heute} />
        </div>
      )}

      {/* Alle offenen Aufgaben */}
      <div style={{ fontFamily:"var(--font-head)", fontSize:17, color:"var(--text)", marginBottom:12 }}>
        Alle offenen Aufgaben ({offen.length})
      </div>

      {offen.length === 0 ? (
        <Card style={{ textAlign:"center", padding:32 }}>
          <div style={{ fontSize:32, marginBottom:10 }}>✓</div>
          <div style={{ color:"var(--text3)" }}>
            {ladeAufgaben ? "Laden..." : "Keine offenen Aufgaben — alles erledigt!"}
          </div>
        </Card>
      ) : (
        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
          {offen.slice(0, 50).map((a, i) => {
            const pc = PRIO_FARBEN[a.prioritaet] || "var(--text3)";
            const fristDt = a.frist ? new Date(a.frist + "T12:00:00") : null;
            const tage    = fristDt ? Math.round((fristDt - new Date()) / 86400000) : null;
            const fristLabel = tage === null ? "" :
              tage < 0  ? `${Math.abs(tage)}d überfällig` :
              tage === 0 ? "Heute" :
              tage === 1 ? "Morgen" : `in ${tage}d`;
            const fristFarbe = tage === null ? "var(--text3)" :
              tage < 0  ? C.red :
              tage <= 2  ? C.orange : "var(--text3)";

            return (
              <div key={a.id || i} style={{
                background:"var(--bg2)", borderRadius:10, padding:"12px 16px",
                borderLeft:`3px solid ${pc}`,
                border:`1px solid var(--border)`,
                borderLeftColor:pc,
                display:"flex", alignItems:"center", gap:14,
                animation:`fadeUp 0.3s ease ${i*30}ms both`,
              }}>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:14, color:"var(--text)", fontWeight:500,
                                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                    {a.beschreibung}
                  </div>
                  <div style={{ fontSize:12, color:"var(--text3)", marginTop:3 }}>
                    {a.mandant}
                    {a.frist && <span style={{ marginLeft:8 }}>📅 {a.frist}</span>}
                    {fristLabel && (
                      <span style={{ marginLeft:8, color:fristFarbe, fontWeight:600 }}>
                        {fristLabel}
                      </span>
                    )}
                  </div>
                </div>
                <Badge color={pc}>{a.prioritaet || "normal"}</Badge>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// MANDANT DETAIL PAGE (via Router /mandant/:name)
// Bug-fix: useParams statt window.location
// ═══════════════════════════════════════════════════════════

function MandantDetailPage() {
  const { name: encodedName } = useParams();
  const name    = decodeURIComponent(encodedName || "");
  const navigate = useNavigate();

  const [mandant,     setMandant]     = useState(null);
  const [aufgaben,    setAufgaben]    = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [beschreibung,setBeschreibung]= useState("");
  const [frist,       setFrist]       = useState("");
  const [prioritaet,  setPrio]        = useState("normal");
  const [addLoading,  setAddLoading]  = useState(false);
  const [toast,       setToast]       = useState("");

  const showToast = (t) => { setToast(t); setTimeout(() => setToast(""), 3000); };

  const ladeAlles = useCallback(async () => {
    try {
      // Mandanten-Daten
      const raw = await getMandanten();
      const liste = normalisiereMandanten(raw);
      const m = liste.find(x => (x.name || x) === name);
      setMandant(m || { name });

      // Aufgaben
      const a = await apiGet(`/mandanten/${encodeURIComponent(name)}/aufgaben`);
      setAufgaben(a?.aufgaben || a || []);
    } catch (e) {
      console.error(e);
      setMandant({ name });
    } finally {
      setLoading(false);
    }
  }, [name]);

  useEffect(() => { ladeAlles(); }, [ladeAlles]);

  const addAufgabe = async () => {
    if (!beschreibung.trim() || !frist) {
      showToast("⚠ Beschreibung und Frist erforderlich"); return;
    }
    setAddLoading(true);
    try {
      await addAufgabeAPI(name, { beschreibung: beschreibung.trim(), frist, prioritaet });
      setBeschreibung(""); setFrist(""); setPrio("normal");
      showToast("✓ Aufgabe hinzugefügt");
      await ladeAlles();
    } catch (e) { showToast("⚠ " + e.message); }
    finally { setAddLoading(false); }
  };

  const toggleAufgabe = async (id) => {
    setAufgaben(p => p.map(a => a.id === id ? { ...a, erledigt:!a.erledigt } : a));
    try { await toggleAufgabeAPI(id); }
    catch (e) { await ladeAlles(); }
  };

  const deleteAufgabe = async (id) => {
    if (!window.confirm("Aufgabe löschen?")) return;
    setAufgaben(p => p.filter(a => a.id !== id));
    try { await deleteAufgabeAPI(id); }
    catch (e) { await ladeAlles(); }
  };

  const PRIO_C = { kritisch:C.red, hoch:C.orange, normal:C.blue, niedrig:"var(--text3)" };

  if (loading) return (
    <div style={{ flex:1, display:"flex", alignItems:"center",
                  justifyContent:"center", background:"var(--bg)" }}>
      <Spinner size={36} />
    </div>
  );

  const offen    = aufgaben.filter(a => !a.erledigt);
  const erledigt = aufgaben.filter(a => a.erledigt);

  return (
    <div style={{ flex:1, background:"var(--bg)", overflowY:"auto", minHeight:"100vh" }}>
      <FontLoader />

      {/* Toast */}
      {toast && (
        <div style={{ position:"fixed", top:20, right:20, zIndex:9999,
                      background:"var(--bg3)", border:`1px solid ${C.accent}44`,
                      borderLeft:`3px solid ${C.accent}`,
                      borderRadius:"var(--radius)", padding:"12px 16px",
                      color:"var(--text)", fontSize:13, fontWeight:500 }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div style={{ background:"var(--bg2)", borderBottom:"1px solid var(--border)",
                    padding:"24px 36px", display:"flex", alignItems:"center", gap:16 }}>
        <button onClick={() => navigate("/")} style={{
          background:"var(--bg3)", border:"1px solid var(--border2)",
          borderRadius:"var(--radius)", padding:"7px 14px", color:"var(--text2)",
          fontSize:13, cursor:"pointer",
        }}>← Zurück</button>
        <div>
          <div style={{ fontFamily:"var(--font-head)", fontSize:24, color:"var(--text)" }}>{name}</div>
          <div style={{ color:"var(--text3)", fontSize:13, marginTop:2 }}>
            {mandant?.email || "Keine E-Mail"} · {mandant?.branche || "Keine Branche"}
          </div>
        </div>
        <div style={{ marginLeft:"auto" }}>
          <Badge color={C.accent}>€{(mandant?.umsatz || 0).toLocaleString("de")}</Badge>
        </div>
      </div>

      <div style={{ padding:"28px 36px", display:"grid",
                    gridTemplateColumns:"1fr 320px", gap:24 }}>
        {/* Links: Aufgaben */}
        <div>
          <div style={{ fontFamily:"var(--font-head)", fontSize:20, color:"var(--text)", marginBottom:16 }}>
            Aufgaben & Fristen
          </div>

          {/* Neue Aufgabe */}
          <Card style={{ marginBottom:20, padding:"16px 18px" }}>
            <div style={{ fontSize:11, color:"var(--text3)", marginBottom:10,
                          textTransform:"uppercase", letterSpacing:"0.07em" }}>
              Neue Aufgabe
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr auto auto", gap:10, alignItems:"end" }}>
              <Input placeholder="Beschreibung..." value={beschreibung}
                     onChange={setBeschreibung}
                     onKeyDown={e => e.key === "Enter" && addAufgabe()} />
              <input type="date" value={frist} onChange={e => setFrist(e.target.value)}
                     style={{ background:"var(--bg)", border:"1px solid var(--border2)",
                              borderRadius:"var(--radius)", color:"var(--text)",
                              padding:"9px 11px", fontSize:14, outline:"none" }} />
              <Btn onClick={addAufgabe} loading={addLoading} variant="primary">Hinzufügen</Btn>
            </div>
            <div style={{ display:"flex", gap:6, marginTop:10 }}>
              {["niedrig","normal","hoch","kritisch"].map(p => (
                <Btn key={p} size="xs"
                     variant={prioritaet===p?"subtle":"ghost"}
                     onClick={() => setPrio(p)}
                     style={{ color:PRIO_C[p] }}>
                  {p}
                </Btn>
              ))}
            </div>
          </Card>

          {/* Offene Aufgaben */}
          {offen.length === 0 ? (
            <div style={{ color:"var(--text3)", padding:"20px 0", textAlign:"center" }}>
              Keine offenen Aufgaben ✓
            </div>
          ) : offen.map((a, i) => {
            const fristDt = a.frist ? new Date(a.frist + "T12:00:00") : null;
            const tage    = fristDt ? Math.round((fristDt - new Date()) / 86400000) : null;
            const c = tage === null ? "var(--border2)" : tage < 0 ? C.red : tage <= 2 ? C.orange : "var(--border2)";
            return (
              <div key={a.id || i} style={{
                display:"flex", alignItems:"flex-start", gap:12,
                padding:"14px 16px", marginBottom:8,
                background:"var(--bg2)", border:`1px solid ${c}`,
                borderRadius:"var(--radius)",
                animation:`fadeUp 0.3s ease ${i*40}ms both`,
              }}>
                <input type="checkbox" checked={false} onChange={() => toggleAufgabe(a.id)}
                       style={{ marginTop:3, cursor:"pointer", accentColor:C.accent }} />
                <div style={{ flex:1 }}>
                  <div style={{ fontWeight:500, color:"var(--text)" }}>{a.beschreibung}</div>
                  <div style={{ display:"flex", gap:8, marginTop:4, flexWrap:"wrap" }}>
                    {a.frist && <span style={{ fontSize:12, color:"var(--text3)" }}>📅 {a.frist}</span>}
                    {tage !== null && (
                      <Badge color={tage<0?C.red:tage<=2?C.orange:C.blue}>
                        {tage<0?`${Math.abs(tage)}d überfällig`:tage===0?"Heute":`in ${tage}d`}
                      </Badge>
                    )}
                    {a.prioritaet && a.prioritaet !== "normal" && (
                      <Badge color={PRIO_C[a.prioritaet]||"var(--text3)"}>{a.prioritaet}</Badge>
                    )}
                  </div>
                </div>
                <Btn size="xs" variant="danger" onClick={() => deleteAufgabe(a.id)}>✕</Btn>
              </div>
            );
          })}

          {/* Erledigte */}
          {erledigt.length > 0 && (
            <div style={{ marginTop:24 }}>
              <div style={{ fontSize:12, color:"var(--text3)", textTransform:"uppercase",
                            letterSpacing:"0.07em", marginBottom:10 }}>
                Erledigt ({erledigt.length})
              </div>
              {erledigt.slice(0, 5).map((a, i) => (
                <div key={a.id || i} style={{
                  display:"flex", alignItems:"center", gap:12,
                  padding:"10px 16px", marginBottom:6,
                  background:"var(--bg2)", border:"1px solid var(--border)",
                  borderRadius:"var(--radius)", opacity:0.55,
                }}>
                  <input type="checkbox" checked onChange={() => toggleAufgabe(a.id)}
                         style={{ cursor:"pointer", accentColor:C.green }} />
                  <span style={{ textDecoration:"line-through", fontSize:13, color:"var(--text2)" }}>
                    {a.beschreibung}
                  </span>
                  <span style={{ marginLeft:"auto", fontSize:11, color:"var(--text3)" }}>
                    {a.frist}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Rechts: Stammdaten */}
        <div>
          <Card style={{ marginBottom:16 }}>
            <div style={{ fontFamily:"var(--font-head)", fontSize:16, marginBottom:14, color:"var(--accent)" }}>
              Stammdaten
            </div>
            {[
              ["E-Mail",    mandant?.email      || "—"],
              ["Telefon",   mandant?.telefon    || "—"],
              ["Branche",   mandant?.branche    || "—"],
              ["Steuer-ID", mandant?.steuer_id  || "—"],
              ["Umsatz",    `€${(mandant?.umsatz||0).toLocaleString("de")}`],
            ].map(([label, value]) => (
              <div key={label} style={{ display:"flex", justifyContent:"space-between",
                                        padding:"6px 0", borderBottom:"1px solid var(--border)" }}>
                <span style={{ fontSize:12, color:"var(--text3)" }}>{label}</span>
                <span style={{ fontSize:13, color:"var(--text)", fontWeight:500,
                               maxWidth:180, textAlign:"right", wordBreak:"break-word" }}>
                  {value}
                </span>
              </div>
            ))}
          </Card>

          {mandant?.notizen && (
            <Card>
              <div style={{ fontSize:11, color:"var(--text3)", marginBottom:8,
                            textTransform:"uppercase", letterSpacing:"0.07em" }}>Notizen</div>
              <div style={{ fontSize:13, color:"var(--text2)", lineHeight:1.7 }}>
                {mandant.notizen}
              </div>
            </Card>
          )}

          <Card style={{ marginTop:16 }}>
            <div style={{ fontSize:11, color:"var(--text3)", marginBottom:8,
                          textTransform:"uppercase", letterSpacing:"0.07em" }}>Aufgaben</div>
            <div style={{ fontSize:24, fontFamily:"var(--font-head)", color:C.accent }}>
              {offen.length}
            </div>
            <div style={{ fontSize:12, color:"var(--text3)" }}>offen · {erledigt.length} erledigt</div>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// RISIKO-DASHBOARD — Das Killer Feature
// Mandanten-Risiko- & Umsatz-AI auf einen Blick
// ═══════════════════════════════════════════════════════════

function RisikoDashboard({ kpis, heute, onEmail, onTab }) {
  const VIP_THRESHOLD = 500000;
  const [filter,   setFilter]   = useState("alle");    // alle | kritisch | vip
  const [sortBy,   setSortBy]   = useState("risiko");  // risiko | umsatz | name
  const [sending,  setSending]  = useState(null);
  const [toast,    setToast]    = useState("");

  const showToast = (t) => { setToast(t); setTimeout(() => setToast(""), 3500); };

  // Mandanten filtern + sortieren
  const liste = [...kpis]
    .filter(k => {
      if (filter === "kritisch") return k.status === "KRITISCH" || k.status === "WICHTIG";
      if (filter === "vip")      return k.ist_vip || (k.umsatz || 0) >= VIP_THRESHOLD;
      return true;
    })
    .sort((a, b) => {
      if (sortBy === "risiko")  return (b.risiko_score || b.score || 0) - (a.risiko_score || a.score || 0);
      if (sortBy === "umsatz")  return (b.umsatz || 0) - (a.umsatz || 0);
      return (a.mandant || "").localeCompare(b.mandant || "");
    });

  const kritisch = kpis.filter(k => k.status === "KRITISCH").length;
  const vips     = kpis.filter(k => k.ist_vip || (k.umsatz || 0) >= VIP_THRESHOLD).length;
  const gefahr   = kpis.filter(k => (k.tage_ohne_antwort || 0) >= 14).length;
  const gesamt_umsatz = kpis.reduce((s, k) => s + (k.umsatz || 0), 0);

  const STATUS_FARBE = {
    KRITISCH: C.red, WICHTIG: C.orange, NORMAL: C.blue, OK: C.green,
  };

  const UMSATZ_FARBE = (u) =>
    u >= 500000 ? "#9b72e8" : u >= 100000 ? C.accent : u >= 30000 ? C.blue : "var(--text3)";

  const handleEmail = async (name, email) => {
    if (!email) { showToast("⚠ Keine E-Mail-Adresse hinterlegt"); return; }
    setSending(name);
    try {
      await sendEmail(name);
      showToast(`✓ Email an ${name} gesendet`);
    } catch (e) {
      showToast(`⚠ ${e.message}`);
    } finally {
      setSending(null);
    }
  };

  return (
    <div style={{ flex:1, overflowY:"auto", background:"var(--bg)" }}>

      {/* Toast */}
      {toast && (
        <div style={{ position:"fixed", top:20, right:20, zIndex:9999,
                      background:"var(--bg3)", border:`1px solid ${C.accent}44`,
                      borderLeft:`3px solid ${C.accent}`, borderRadius:"var(--radius)",
                      padding:"12px 18px", color:"var(--text)", fontSize:13, fontWeight:500,
                      animation:"slideIn 0.25s ease" }}>
          {toast}
        </div>
      )}

      {/* ── Header ── */}
      <div style={{ background:"var(--bg2)", borderBottom:"1px solid var(--border)",
                    padding:"24px 36px" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
          <div>
            <div style={{ fontFamily:"var(--font-head)", fontSize:26, color:"var(--text)", marginBottom:4 }}>
              Mandanten-Risiko & Umsatz AI
            </div>
            <div style={{ color:"var(--text3)", fontSize:13 }}>
              {new Date().toLocaleDateString("de-DE", { weekday:"long", day:"numeric", month:"long" })}
              {" · "}KI analysiert automatisch wer sofortige Aufmerksamkeit braucht
            </div>
          </div>
          <div style={{ display:"flex", gap:8 }}>
            <Btn size="sm" variant="ghost" onClick={() => onTab("aufgaben")}>+ Aufgabe</Btn>
            <Btn size="sm" variant="ghost" onClick={() => onTab("neu")}>+ Mandant</Btn>
          </div>
        </div>
      </div>

      {/* ── KPI Zeile ── */}
      <div style={{ padding:"20px 36px 0", display:"grid",
                    gridTemplateColumns:"repeat(4,1fr)", gap:14 }}>
        {[
          { label:"Kritisch",     value:kritisch,     color:C.red,     icon:"🚨",
            sub:"sofort handeln" },
          { label:"VIP-Mandanten",value:vips,         color:"#9b72e8", icon:"⭐",
            sub:">€500k Umsatz" },
          { label:"Keine Antwort",value:gefahr,       color:C.orange,  icon:"📞",
            sub:">14 Tage still" },
          { label:"Gesamt-Umsatz",value:`€${(gesamt_umsatz/1000).toFixed(0)}k`,
            color:C.accent, icon:"💰", sub:`${kpis.length} Mandanten` },
        ].map((item, i) => (
          <Card key={i} animate delay={i*50} style={{ padding:"16px 18px" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
              <div>
                <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                              letterSpacing:"0.08em", marginBottom:6 }}>{item.label}</div>
                <div style={{ fontSize:30, fontFamily:"var(--font-head)",
                              color:item.color, lineHeight:1 }}>{item.value}</div>
                <div style={{ fontSize:11, color:"var(--text3)", marginTop:4 }}>{item.sub}</div>
              </div>
              <span style={{ fontSize:24, opacity:0.6 }}>{item.icon}</span>
            </div>
          </Card>
        ))}
      </div>

      {/* ── Filter + Sort ── */}
      <div style={{ padding:"16px 36px", display:"flex", gap:10, alignItems:"center" }}>
        <div style={{ display:"flex", gap:4, background:"var(--bg3)",
                      borderRadius:10, padding:4 }}>
          {[["alle","Alle"], ["kritisch","🚨 Kritisch"], ["vip","⭐ VIP"]].map(([v,l]) => (
            <button key={v} onClick={() => setFilter(v)} style={{
              padding:"6px 14px", borderRadius:8, border:"none", cursor:"pointer",
              background:filter===v?"var(--bg2)":"transparent",
              color:filter===v?"var(--accent)":"var(--text3)",
              fontSize:13, fontWeight:filter===v?600:400,
              fontFamily:"var(--font-body)", transition:"all 0.15s",
            }}>{l}</button>
          ))}
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:6, alignItems:"center" }}>
          <span style={{ fontSize:12, color:"var(--text3)" }}>Sortierung:</span>
          {[["risiko","Risiko"], ["umsatz","Umsatz"], ["name","Name"]].map(([v,l]) => (
            <Btn key={v} size="xs" variant={sortBy===v?"subtle":"ghost"}
                 onClick={() => setSortBy(v)}>{l}</Btn>
          ))}
        </div>
        <span style={{ fontSize:12, color:"var(--text3)" }}>{liste.length} Mandanten</span>
      </div>

      {/* ── Mandanten-Liste ── */}
      <div style={{ padding:"0 36px 36px", display:"flex", flexDirection:"column", gap:10 }}>
        {liste.length === 0 && (
          <Card style={{ textAlign:"center", padding:40 }}>
            <div style={{ fontSize:36, marginBottom:10 }}>✅</div>
            <div style={{ color:"var(--text3)" }}>Keine Mandanten in diesem Filter</div>
          </Card>
        )}

        {liste.map((k, i) => {
          const risiko     = k.risiko_score ?? Math.min(100, Math.round((k.score||0) / 120));
          const risikoFarbe= risiko >= 70 ? C.red : risiko >= 40 ? C.orange : risiko >= 15 ? C.blue : C.green;
          const statusFarbe= STATUS_FARBE[k.status] || C.green;
          const empf       = k.empfehlung || {};
          const empfFarbe  = empf.farbe || statusFarbe;
          const istVip     = k.ist_vip || (k.umsatz || 0) >= VIP_THRESHOLD;
          const umsatzF    = UMSATZ_FARBE(k.umsatz || 0);

          return (
            <div key={k.mandant} style={{
              background:"var(--bg2)", border:`1px solid var(--border)`,
              borderLeft:`4px solid ${statusFarbe}`,
              borderRadius:"var(--radius-lg)", padding:"18px 20px",
              animation:`fadeUp 0.3s ease ${i*30}ms both`,
              transition:"all 0.15s",
            }}>
              <div style={{ display:"flex", gap:16, alignItems:"flex-start" }}>

                {/* Risiko-Ring */}
                <div style={{ flexShrink:0, textAlign:"center", minWidth:72 }}>
                  <div style={{
                    width:64, height:64, borderRadius:"50%",
                    background:`conic-gradient(${risikoFarbe} ${risiko*3.6}deg, var(--bg3) 0deg)`,
                    display:"flex", alignItems:"center", justifyContent:"center",
                    margin:"0 auto 4px",
                  }}>
                    <div style={{
                      width:52, height:52, borderRadius:"50%",
                      background:"var(--bg2)", display:"flex", alignItems:"center",
                      justifyContent:"center", flexDirection:"column",
                    }}>
                      <div style={{ fontSize:16, fontWeight:700, color:risikoFarbe, lineHeight:1 }}>
                        {risiko}
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize:10, color:"var(--text3)", textTransform:"uppercase",
                                letterSpacing:"0.05em" }}>Risiko</div>
                </div>

                {/* Mandant Info */}
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4 }}>
                    <Link to={`/mandant/${encodeURIComponent(k.mandant)}`}
                      style={{ fontFamily:"var(--font-head)", fontSize:18,
                               color:"var(--text)", fontWeight:600 }}>
                      {k.mandant}
                    </Link>
                    {istVip && (
                      <span style={{ fontSize:11, padding:"2px 8px", borderRadius:20,
                                     background:"#9b72e822", color:"#9b72e8",
                                     border:"1px solid #9b72e833", fontWeight:700 }}>
                        ⭐ VIP
                      </span>
                    )}
                    <Badge color={statusFarbe} style={{ fontSize:10 }}>{k.status}</Badge>
                  </div>

                  {/* Umsatz + Metriken */}
                  <div style={{ display:"flex", gap:16, flexWrap:"wrap", marginBottom:10 }}>
                    <span style={{ fontSize:15, fontWeight:700, color:umsatzF,
                                   fontFamily:"var(--font-head)" }}>
                      €{(k.umsatz||0).toLocaleString("de")}
                    </span>
                    {k.tage_ohne_antwort > 0 && (
                      <span style={{ fontSize:12, color:(k.tage_ohne_antwort||0)>=14?C.red:C.orange }}>
                        📞 {k.tage_ohne_antwort}d kein Kontakt
                      </span>
                    )}
                    {k.aufgaben_ueberfaellig > 0 && (
                      <span style={{ fontSize:12, color:C.red }}>
                        ⏰ {k.aufgaben_ueberfaellig} überfällig
                      </span>
                    )}
                    {k.aufgaben_offen > 0 && (
                      <span style={{ fontSize:12, color:"var(--text3)" }}>
                        {k.aufgaben_offen} Aufgaben offen
                      </span>
                    )}
                    {k.fehlende_dokumente > 0 && (
                      <span style={{ fontSize:12, color:C.blue }}>
                        📄 {k.fehlende_dokumente} Dok. fehlen
                      </span>
                    )}
                  </div>

                  {/* Umsatz-Bar */}
                  <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:10 }}>
                    <div style={{ fontSize:10, color:"var(--text3)", width:40 }}>
                      {k.umsatz_kategorie || "—"}
                    </div>
                    <div style={{ flex:1, height:3, background:"var(--bg3)",
                                  borderRadius:2, maxWidth:200 }}>
                      <div style={{
                        width:`${k.umsatz_score || Math.min(100,(k.umsatz||0)/5000)}%`,
                        height:"100%", background:umsatzF, borderRadius:2,
                        transition:"width 0.8s ease",
                      }} />
                    </div>
                    <div style={{ fontSize:10, color:"var(--text3)" }}>Umsatz-Score</div>
                  </div>

                  {/* KI-Empfehlung */}
                  {empf.titel && (
                    <div style={{
                      display:"flex", alignItems:"center", gap:8,
                      padding:"8px 12px", borderRadius:8,
                      background:empfFarbe+"12",
                      border:`1px solid ${empfFarbe}25`,
                    }}>
                      <span style={{ fontSize:16, flexShrink:0 }}>{empf.icon || "●"}</span>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ fontSize:13, fontWeight:600, color:empfFarbe }}>
                          {empf.titel}
                        </div>
                        {empf.text && (
                          <div style={{ fontSize:12, color:"var(--text3)", marginTop:1,
                                        overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                            {empf.text}
                          </div>
                        )}
                      </div>
                      <span style={{ fontSize:11, color:empfFarbe, flexShrink:0, fontWeight:600 }}>
                        {empf.aktion_text || ""}
                      </span>
                    </div>
                  )}
                </div>

                {/* Aktions-Buttons */}
                <div style={{ display:"flex", flexDirection:"column", gap:6, flexShrink:0 }}>
                  <Link to={`/mandant/${encodeURIComponent(k.mandant)}`}>
                    <Btn size="sm" variant="ghost" style={{ width:"100%" }}>
                      Öffnen →
                    </Btn>
                  </Link>
                  {k.email && (
                    <Btn size="sm" variant={k.status==="KRITISCH"?"danger":"subtle"}
                         loading={sending===k.mandant}
                         onClick={() => handleEmail(k.mandant, k.email)}>
                      {k.status==="KRITISCH" ? "⚡ Email jetzt" : "✉ Email"}
                    </Btn>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Heute & Dringend unten */}
      {heute && heute.length > 0 && (
        <div style={{ padding:"0 36px 36px" }}>
          <div style={{ fontFamily:"var(--font-head)", fontSize:18,
                        color:"var(--text)", marginBottom:12 }}>
            Heute & Dringend
          </div>
          <HeutePanel heute={heute} />
        </div>
      )}
    </div>
  );
}


function AppInner() {
  const [activeTab,    setActiveTab]    = useState("dashboard");
  const [kpis,         setKpis]         = useState([]);
  const [heute,        setHeute]        = useState([]);
  const [empfehlungen, setEmpfehlungen] = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [formLoading,  setFormLoading]  = useState(false);
  const [isFormDirty,  setIsFormDirty]  = useState(false);
  const [selectedName, setSelectedName] = useState(null);
  const [emailModal,   setEmailModal]   = useState(null);
  const [toasts,       setToasts]       = useState([]);
  const [readiness,    setReadiness]    = useState(null);

  const refreshRef    = useRef(null);
  const typingRef     = useRef(false);   // true während User tippt → kein Reload
  const typingTimeout = useRef(null);
  const formLoadingRef = useRef(false);
  const formDirtyRef = useRef(false);
  const formOpenRef = useRef(false);

  // User tippt → Reload pausieren
  useEffect(() => {
    const onFocus = () => {
      typingRef.current = true;
      clearTimeout(typingTimeout.current);
    };
    const onBlur = () => {
      clearTimeout(typingTimeout.current);
      typingTimeout.current = setTimeout(() => { typingRef.current = false; }, 2000);
    };
    document.addEventListener("focusin",  onFocus);
    document.addEventListener("focusout", onBlur);
    return () => {
      document.removeEventListener("focusin",  onFocus);
      document.removeEventListener("focusout", onBlur);
    };
  }, []);

  const toast = useCallback((text, type="success") => {
    const id = Date.now() + Math.random();
    setToasts(p => [...p, { id, text, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);

  const ladeAlles = useCallback(async (initial=false) => {
    try {
      if (initial) setLoading(true);
      const [k, h, e, r] = await Promise.allSettled([
        getKpis(), getHeute(), getEmpfehlungen(), getSaasReadiness(),
      ]);
      if (k.status === "fulfilled") {
        // kpis können Array oder Objekt sein — immer normalisieren
        const raw = k.value;
        setKpis(Array.isArray(raw) ? raw : (raw?.data ? normalisiereMandanten(raw) : []));
      }
      if (h.status === "fulfilled") setHeute(Array.isArray(h.value) ? h.value : []);
      if (e.status === "fulfilled") {
        const emp = Array.isArray(e.value) ? e.value : [];
        setEmpfehlungen(emp.filter(x => x?.mandant && (x?.empfehlungen?.length || x?.empfehlung)));
      }
      if (r.status === "fulfilled") {
        const rd = r.value?.data || r.value;
        setReadiness(rd || null);
      }
    } catch (err) {
      console.error("ladeAlles:", err);
    } finally {
      if (initial) setLoading(false);
    }
  }, []);

  useEffect(() => { formLoadingRef.current = formLoading; }, [formLoading]);
  useEffect(() => { formDirtyRef.current = isFormDirty; }, [isFormDirty]);
  useEffect(() => { formOpenRef.current = activeTab === "neu" || !!selectedName; }, [activeTab, selectedName]);

  useEffect(() => {
    ladeAlles(true);
    // Auto-Reload alle 15s — pausiert beim Tippen/Formularen/Save
    refreshRef.current = setInterval(() => {
      if (
        !typingRef.current &&
        !formLoadingRef.current &&
        !formDirtyRef.current &&
        !formOpenRef.current
      ) {
        ladeAlles();
      }
    }, 15000);
    return () => clearInterval(refreshRef.current);
  }, [ladeAlles]);

  const handleCreate = async (data) => {
    setFormLoading(true);
    try {
      await addMandantAPI(data);
      toast(`✓ ${data.name} angelegt`);
      setActiveTab("mandanten");
      await ladeAlles();
    } catch (e) { toast(e.message, "error"); }
    finally { setFormLoading(false); }
  };

  const handleUpdate = async (data) => {
    setFormLoading(true);
    try {
      await updateMandantAPI(selectedName, data);
      toast("✓ Mandant aktualisiert");
      setSelectedName(null);
      await ladeAlles();
    } catch (e) { toast(e.message, "error"); }
    finally { setFormLoading(false); }
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`"${name}" wirklich löschen?`)) return;
    try {
      await deleteMandantAPI(name);
      toast(`${name} gelöscht`, "warn");
      if (selectedName === name) setSelectedName(null);
      await ladeAlles();
    } catch (e) { toast(e.message, "error"); }
  };

  const handleSendEmail = async (name) => {
    await sendEmail(name);
    toast(`✓ Email an ${name} gesendet`);
  };

  const renderContent = () => {
    if (loading) return (
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
                    flex:1, flexDirection:"column", gap:16 }}>
        <Spinner size={40} />
        <div style={{ color:"var(--text3)" }}>Lade Daten...</div>
      </div>
    );

    const selectedData = selectedName ? kpis.find(k => k.mandant === selectedName) : null;

    switch (activeTab) {

      // ── DASHBOARD ──────────────────────────────────────────
      case "dashboard":
        return <RisikoDashboard kpis={kpis} heute={heute} onEmail={m => setEmailModal(m)} onTab={setActiveTab} />;

      // ── MANDANTEN ──────────────────────────────────────────
      case "mandanten":
        return (
          <div style={{ padding:"28px 36px", flex:1, overflowY:"auto" }}>
            {selectedName && (
              <div style={{ marginBottom:20 }}>
                <MandantFormPanel
                  key={selectedName}
                  initialData={selectedData}
                  onSubmit={handleUpdate}
                  onCancel={() => { setSelectedName(null); setIsFormDirty(false); }}
                  loading={formLoading}
                  onDirtyChange={setIsFormDirty}
                />
              </div>
            )}
            <MandantenTabelle
              kpis={kpis}
              onSelect={n => setSelectedName(prev => prev === n ? null : n)}
              onDelete={handleDelete}
              onEmail={m => setEmailModal(m)}
              selectedName={selectedName}
            />
          </div>
        );

      // ── AUFGABEN ───────────────────────────────────────────
      case "aufgaben":
        return <AufgabenSeite kpis={kpis} heute={heute} onRefresh={ladeAlles} />;

      // ── KI-INSIGHTS ────────────────────────────────────────
      case "empfehlungen":
        return (
          <div style={{ padding:"28px 36px", flex:1, overflowY:"auto" }}>
            <div style={{ marginBottom:24 }}>
              <div style={{ fontFamily:"var(--font-head)", fontSize:24, color:"var(--text)", marginBottom:4 }}>
                KI-Insights
              </div>
              <div style={{ color:"var(--text3)" }}>
                Automatische Analyse · {empfehlungen.length} Mandanten mit Handlungsbedarf
              </div>
            </div>
            <EmpfehlungenPanel empfehlungen={empfehlungen} onEmail={m => setEmailModal(m)} />
          </div>
        );

      // ── SEITEN-KOMPONENTEN ─────────────────────────────────
      case "steuerbot":  return <SteuerAutopilot />;
      case "profit":     return <ProfitMonitor />;
      case "automation": return <WorkflowBaukasten />;
      case "dokumente":  return <DokumentScanner />;
      case "belege":     return <BelegScanner />;
      case "rechnungen": return <Rechnungen />;
      case "ki":         return <KIAssistent />;
      case "analytics":  return <Analytics />;
      case "settings":   return <Settings />;

      // ── NEUER MANDANT ──────────────────────────────────────
      case "neu":
        return (
          <div style={{ padding:"28px 36px", flex:1, overflowY:"auto" }}>
            <div style={{ fontFamily:"var(--font-head)", fontSize:24, marginBottom:24, color:"var(--text)" }}>
              Neuer Mandant
            </div>
            <MandantFormPanel
              key="new-mandant-form"
              initialData={null}
              onSubmit={handleCreate}
              onCancel={() => { setActiveTab("mandanten"); setIsFormDirty(false); }}
              loading={formLoading}
              onDirtyChange={setIsFormDirty}
            />
          </div>
        );

      default: return null;
    }
  };

  return (
    <div style={{ display:"flex", minHeight:"100vh" }}>
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} kpis={kpis} />
      <main style={{ flex:1, display:"flex", flexDirection:"column",
                     background:"var(--bg)", overflowX:"hidden" }}>
        {readiness && (
          <div style={{
            position:"sticky",
            top:0,
            zIndex:50,
            background:"rgba(11,13,17,0.92)",
            backdropFilter:"blur(8px)",
            borderBottom:"1px solid var(--border)",
            padding:"10px 18px",
            display:"flex",
            alignItems:"center",
            gap:16,
          }}>
            <div style={{ fontSize:12, color:"var(--text3)", textTransform:"uppercase", letterSpacing:"0.08em" }}>
              SaaS Readiness
            </div>
            <div style={{ fontSize:15, fontWeight:700, color: (readiness.readiness_score||0)>=80?C.green:(readiness.readiness_score||0)>=60?C.orange:C.red }}>
              {readiness.readiness_score ?? 0}
            </div>
            <div style={{ flex:1, maxWidth:280, height:5, background:"var(--bg3)", borderRadius:4, overflow:"hidden" }}>
              <div style={{
                width:`${Math.max(0, Math.min(100, readiness.readiness_score || 0))}%`,
                height:"100%",
                background:(readiness.readiness_score||0)>=80?C.green:(readiness.readiness_score||0)>=60?C.orange:C.red,
              }} />
            </div>
            <div style={{ display:"flex", gap:12, marginLeft:"auto", fontSize:12, color:"var(--text2)" }}>
              <span>Dead Mail: {readiness.health?.email_outbox_dead_24h ?? 0}</span>
              <span>Webhook Fail: {readiness.health?.webhook_failures_24h ?? 0}</span>
              <span>Keys: {readiness.health?.api_keys_aktiv ?? 0}</span>
              <span>Compliance: {readiness.compliance?.percent ?? 0}%</span>
            </div>
          </div>
        )}
        {renderContent()}
      </main>
      {emailModal && (
        <EmailModal name={emailModal}
                    onClose={() => setEmailModal(null)}
                    onSend={handleSendEmail} />
      )}
      <ToastContainer toasts={toasts} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// ROOT APP — Login + Router
// ═══════════════════════════════════════════════════════════

export default function App() {
  const [loggedIn,  setLoggedIn]  = useState(!!localStorage.getItem("kanzlei_token"));
  const [authAktiv, setAuthAktiv] = useState(false);
  const [checking,  setChecking]  = useState(true);

  useEffect(() => {
    fetch(BASE_URL + "/auth/setup-status")
      .then(r => r.json())
      .then(d => { if (d.eingerichtet) setAuthAktiv(true); })
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);

  if (checking) return (
    <>
      <FontLoader />
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
                    height:"100vh", background:"var(--bg)" }}>
        <Spinner size={36} />
      </div>
    </>
  );

  if (authAktiv && !loggedIn) return (
    <>
      <FontLoader />
      <Login onLogin={() => setLoggedIn(true)} />
    </>
  );

  return (
    <>
      <FontLoader />
      <Router>
        <Routes>
          <Route path="/"              element={<AppInner />} />
          <Route path="/mandant/:name" element={<MandantDetailPage />} />
        </Routes>
      </Router>
    </>
  );
}