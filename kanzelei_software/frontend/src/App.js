// ============================================================
// Kanzlei AI — Haupt-App
// Alle Bugs behoben:
//   ✓ Dashboard zeigt echte KPIs + Heute + Empfehlungen
//   ✓ Aufgaben-Tab: Erstellen funktioniert, alle Mandanten geladen
//   ✓ AufgabenSeite: API-Reihenfolge korrekt, /kpis für alle Aufgaben
//   ✓ MandantDetailPage: useParams statt window.location
//   ✓ getMandanten: einheitliche Datenverarbeitung
//   ✓ Login: Auth-Check korrekt
// ============================================================

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { BrowserRouter as Router, Routes, Route, Link, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  getMandanten, getHeute, getEmpfehlungen, getKpis,
  addMandantAPI, updateMandantAPI, deleteMandantAPI,
  addAufgabeAPI, toggleAufgabeAPI, updateAufgabeAPI, deleteAufgabeAPI,
  getEmailPreview, sendEmail, getSaasReadiness, getBillingUsage,
  createStripeCheckoutSession,
  trackBillingFunnelEvent,
  apiGet,
  getSettings,
  extrahiereAufgabenArray,
  extrahiereHeuteEintraege,
  istAufgabeErledigt,
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
import AufgabeEditModal  from "./AufgabeEditModal";
import AdminUsers        from "./pages/AdminUsers";
import TeamUsers         from "./pages/TeamUsers";
import Profile           from "./pages/Profile";
import Register          from "./pages/Register";
import ForgotPassword    from "./pages/ForgotPassword";
import ResetPassword     from "./pages/ResetPassword";
import VerifyEmail       from "./pages/VerifyEmail";
import { hasRoleReal, getEffectiveRole } from "./components/PermissionGate";
import { hasNavTab } from "./navAccess";
import { useContentLayoutWidth, readContentLayoutWidth } from "./useContentLayoutWidth";
import ViewAsControls from "./components/ViewAsControls";
import { ThemeProvider, ThemeQuickSwitch } from "./theme";

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

function normalisiereKpis(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw?.data && Array.isArray(raw.data)) return raw.data;
  return [];
}

function mergeMandantenMitKpis(mandantenRows, kpiRows) {
  const byName = new Map();
  (mandantenRows || []).forEach((m) => {
    const name = String(m?.name || m?.mandant || "").trim();
    if (!name) return;
    byName.set(name, {
      mandant: name,
      name,
      email: m?.email || "",
      telefon: m?.telefon || "",
      branche: m?.branche || "",
      umsatz: Number(m?.umsatz || 0),
      score: 0,
      status: "NORMAL",
      aufgaben_offen: 0,
      aufgaben_ueberfaellig: 0,
      tage_ohne_antwort: 0,
    });
  });
  (kpiRows || []).forEach((k) => {
    const name = String(k?.mandant || k?.name || "").trim();
    if (!name) return;
    const prev = byName.get(name) || {
      mandant: name,
      name,
      email: "",
      telefon: "",
      branche: "",
      umsatz: 0,
      score: 0,
      status: "NORMAL",
      aufgaben_offen: 0,
      aufgaben_ueberfaellig: 0,
      tage_ohne_antwort: 0,
    };
    byName.set(name, {
      ...prev,
      ...k,
      mandant: name,
      name,
      umsatz: Number(k?.umsatz ?? prev.umsatz ?? 0),
      score: Number(k?.score ?? prev.score ?? 0),
      status: String(k?.status || prev.status || "NORMAL"),
      aufgaben_offen: Number(k?.aufgaben_offen ?? prev.aufgaben_offen ?? 0),
      aufgaben_ueberfaellig: Number(k?.aufgaben_ueberfaellig ?? prev.aufgaben_ueberfaellig ?? 0),
      tage_ohne_antwort: Number(k?.tage_ohne_antwort ?? prev.tage_ohne_antwort ?? 0),
    });
  });

  // Pending-Aufgaben (lokal) in KPI-Zähler einrechnen, bis der Server nachgezogen hat.
  const heute = new Date().toISOString().slice(0, 10);
  for (const p of lesePendingAufgaben()) {
    const name = String(p?.mandant || "").trim();
    if (!name) continue;
    const prev = byName.get(name) || {
      mandant: name,
      name,
      email: "",
      telefon: "",
      branche: "",
      umsatz: 0,
      score: 0,
      status: "NORMAL",
      aufgaben_offen: 0,
      aufgaben_ueberfaellig: 0,
      tage_ohne_antwort: 0,
    };
    const offen = !istAufgabeErledigt(p);
    const ueberfaellig = offen && String(p?.frist || "") < heute;
    byName.set(name, {
      ...prev,
      aufgaben_offen: Number(prev.aufgaben_offen || 0) + (offen ? 1 : 0),
      aufgaben_ueberfaellig: Number(prev.aufgaben_ueberfaellig || 0) + (ueberfaellig ? 1 : 0),
    });
  }
  return Array.from(byName.values());
}

// ─── Google Fonts + CSS Variablen ───────────────────────────
const FontLoader = () => (
  <style>{`
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* Mobil: Layout nutzt die Breite — seitliches Scrollen ist selten nötig, aber nicht gesperrt */
    html {
      -webkit-text-size-adjust: 100%;
      width: 100%;
    }
    body {
      width: 100%;
      position: relative;
    }
    #root {
      width: 100%;
      min-height: 100dvh;
    }

    :root, :root[data-theme="dark"] {
      --bg:         #0b0d11;
      --bg2:        #111419;
      --bg3:        #181c24;
      --border:     rgba(255,255,255,0.07);
      --border2:    rgba(255,255,255,0.14);
      --text:       #e8eaf0;
      --text2:      #8b91a0;
      --text3:      #555d6e;
      --accent:     #c8a96e;
      --on-accent:  #1a1200;
      --on-blue:    #f4f6fb;
      --red:        #e05555;
      --orange:     #e08c45;
      --green:      #5cb87a;
      --blue:       #5b8de8;
      --purple:     #9b72e8;
      --radius:     12px;
      --radius-lg:  18px;
      --font-head:  'DM Serif Display', Georgia, serif;
      --font-body:  'DM Sans', system-ui, sans-serif;
      --transition: 0.18s ease;
      --header-bg:  rgba(11,13,17,0.92);
      --overlay-scrim: color-mix(in srgb, black 62%, transparent);
      --shadow-modal: 0 20px 60px color-mix(in srgb, black 52%, transparent);
      --shadow-elev: 0 8px 32px color-mix(in srgb, black 42%, transparent);
    }

    :root[data-theme="light"] {
      --bg:         #f4f1ea;
      --bg2:        #ebe6dc;
      --bg3:        #e0d9cc;
      --border:     rgba(0,0,0,0.08);
      --border2:    rgba(0,0,0,0.12);
      --text:       #1a1d24;
      --text2:      #4b5260;
      --text3:      #7a8292;
      --accent:     #9a7b3c;
      --on-accent:  #1a1200;
      --on-blue:    #f4f6fb;
      --red:        #c43d3d;
      --orange:     #b86a24;
      --green:      #2d8a52;
      --blue:       #2a5ead;
      --purple:     #6b4fba;
      --header-bg:  rgba(244,241,234,0.94);
      --overlay-scrim: color-mix(in srgb, black 38%, transparent);
      --shadow-modal: 0 20px 60px color-mix(in srgb, var(--text) 14%, transparent);
      --shadow-elev: 0 8px 32px color-mix(in srgb, var(--text) 11%, transparent);
    }

    html, body, #root {
      height: 100%;
      min-height: 100dvh;
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

// ═══════════════════════════════════════════════════════════
// PRIMITIVE COMPONENTS (Farben = CSS-Variablen → Hell/Dunkel überall)
// ═══════════════════════════════════════════════════════════

const Badge = ({ children, color = "var(--accent)", style = {} }) => (
  <span style={{
    display:"inline-block", padding:"2px 8px", borderRadius:20,
    fontSize:11, fontWeight:600, letterSpacing:"0.04em", textTransform:"uppercase",
    background:`color-mix(in srgb, ${color} 18%, var(--bg3))`,
    color,
    border:`1px solid color-mix(in srgb, ${color} 28%, transparent)`,
    ...style,
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
    primary: { background:"var(--accent)", color:"var(--on-accent)", border:"none" },
    danger:  { background:"color-mix(in srgb, var(--red) 16%, var(--bg3))", color:"var(--red)", border:"1px solid color-mix(in srgb, var(--red) 28%, transparent)" },
    ghost:   { background:"transparent",   color:"var(--text2)", border:"1px solid var(--border2)" },
    subtle:  { background:"var(--bg3)",    color:"var(--text2)", border:"none" },
    success: { background:"color-mix(in srgb, var(--green) 16%, var(--bg3))", color:"var(--green)", border:"1px solid color-mix(in srgb, var(--green) 28%, transparent)" },
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
    maxWidth:"100%", minWidth:0,
    animation:animate?`fadeUp 0.4s ease ${delay}ms both`:"none", ...style,
  }}>
    {children}
  </div>
);

const StatusDot = ({ status }) => {
  const colors = { KRITISCH:"var(--red)", WICHTIG:"var(--orange)", NORMAL:"var(--green)", OK:"var(--green)" };
  const c = colors[status] || "var(--text3)";
  return (
    <span style={{
      display:"inline-block", width:8, height:8, borderRadius:"50%",
      background:c, boxShadow:`0 0 6px color-mix(in srgb, ${c} 55%, transparent)`, flexShrink:0,
      animation:status==="KRITISCH"?"pulse 1.5s ease infinite":"none",
    }} />
  );
};

// ═══════════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════

const ToastContainer = ({ toasts }) => (
  <div style={{ position:"fixed", top:20, right:12, zIndex:9999,
                display:"flex", flexDirection:"column", gap:10, alignItems:"flex-end",
                maxWidth:"calc(100vw - 24px)", pointerEvents:"none" }}>
    {toasts.map(t => {
      const colors = { success:"var(--green)", error:"var(--red)", info:"var(--blue)", warn:"var(--orange)" };
      const c = colors[t.type] || "var(--accent)";
      return (
        <div key={t.id} style={{
          background:"var(--bg3)", border:`1px solid color-mix(in srgb, ${c} 32%, transparent)`,
          borderLeft:`3px solid ${c}`, color:"var(--text)",
          borderRadius:"var(--radius)", padding:"12px 16px",
          width:"min(340px, calc(100vw - 24px))", minWidth:0, maxWidth:"100%",
          fontSize:13, fontWeight:500,
          pointerEvents:"auto",
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

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

/** Kurze Titel für die mobile Kopfzeile (neben ☰) */
const MOBILE_TAB_TITLE = {
  dashboard: "Dashboard",
  mandanten: "Mandanten",
  aufgaben: "Aufgaben",
  ki: "KI-Assistent",
  profit: "Profit",
  steuerbot: "Steuer-Autopilot",
  dokumente: "Dokumente",
  belege: "Belege",
  rechnungen: "Rechnungen",
  automation: "Automation",
  empfehlungen: "KI-Insights",
  analytics: "Analytics",
  neu: "Neu anlegen",
  settings: "Einstellungen",
};

const Sidebar = ({
  activeTab,
  setActiveTab,
  kpis,
  width,
  setWidth,
  minWidth,
  maxWidth,
  role,
  navSettings,
  footerAdmin,
  isMobile,
  mobileOpen,
  onCloseMobile,
  onOpenMobile,
  onDesktopCollapse,
}) => {
  const kritisch = kpis.filter(k => k.status === "KRITISCH").length;
  const wichtig  = kpis.filter(k => k.status === "WICHTIG").length;
  const normalizedRole = (role || "").toLowerCase();
  /** Auf dem Desktop: bei sehr schmaler Leiste Text kleiner statt komplett unsichtbar */
  const isCompact = !isMobile && width < 210;
  const dragStateRef = useRef({ active:false, startX:0, startWidth:0 });

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
  ].filter((item) => hasNavTab(normalizedRole, item.id, navSettings));

  const onResizeStart = useCallback((event) => {
    if (isMobile) return;
    event.preventDefault();
    dragStateRef.current = { active:true, startX:event.clientX, startWidth:width };
    document.body.style.userSelect = "none";

    const onMove = (moveEvent) => {
      if (!dragStateRef.current.active) return;
      const deltaX = moveEvent.clientX - dragStateRef.current.startX;
      setWidth(clamp(dragStateRef.current.startWidth + deltaX, minWidth, maxWidth));
    };
    const onUp = () => {
      dragStateRef.current.active = false;
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, [isMobile, maxWidth, minWidth, setWidth, width]);

  const goTab = (id) => {
    setActiveTab(id);
    if (isMobile && onCloseMobile) onCloseMobile();
  };

  const drawerWidth = Math.min(300, typeof window !== "undefined" ? Math.round(window.innerWidth * 0.88) : 300);

  const navShell = (
    <nav
      style={isMobile ? {
        width: drawerWidth,
        flexShrink: 0,
        background: "var(--bg2)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: "100dvh",
        padding: "max(12px, env(safe-area-inset-top)) 0 max(12px, env(safe-area-inset-bottom))",
        overflow: "hidden",
        boxSizing: "border-box",
      } : {
        width, flexShrink:0, background:"var(--bg2)",
        borderRight:"1px solid var(--border)", display:"flex",
        flexDirection:"column", height:"100vh", position:"sticky", top:0, padding:isCompact?"20px 0":"28px 0",
        overflow:"hidden",
      }}
    >
      <div style={{ padding:isMobile ? "0 max(16px, env(safe-area-inset-right)) 14px max(16px, env(safe-area-inset-left))" : isCompact?"0 14px 18px":"0 24px 28px", display:"flex", alignItems:"center", justifyContent:"space-between", gap:8 }}>
        <div style={{ minWidth: 0, flex: 1, paddingRight: isMobile ? 8 : 0 }}>
          <div style={{ fontFamily:"var(--font-head)", fontSize:isMobile ? 20 : 22,
                        color:"var(--accent)", letterSpacing:"-0.01em", lineHeight:1.2 }}>
            Kanzlei<br />
            <span style={{ color:"var(--text)", fontSize:isMobile ? 17 : 18 }}>AI</span>
          </div>
          <div style={{ fontSize:11, color:"var(--text3)", marginTop:4, display:(isCompact && !isMobile)?"none":"block" }}>
            Steuerberater Suite
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {!isMobile && onDesktopCollapse ? (
            <button
              type="button"
              onClick={onDesktopCollapse}
              aria-label="Seitenleiste ausblenden"
              title="Seitenleiste ausblenden"
              style={{
                border: "1px solid var(--border2)",
                background: "var(--bg3)",
                color: "var(--text)",
                borderRadius: 10,
                width: 40,
                height: 40,
                fontSize: 18,
                lineHeight: 1,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              ◀
            </button>
          ) : null}
          {isMobile ? (
            <button
              type="button"
              onClick={onCloseMobile}
              aria-label="Menü schließen"
              style={{
                border: "1px solid var(--border2)",
                background: "var(--bg3)",
                color: "var(--text2)",
                borderRadius: 10,
                minWidth: 44,
                minHeight: 44,
                fontSize: 20,
                lineHeight: 1,
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              ×
            </button>
          ) : null}
        </div>
      </div>

      <Divider />

      {(kritisch > 0 || wichtig > 0) && (
        <div style={{
          margin:isMobile ? "0 12px 12px" : "0 16px 16px",
          background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",
          border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)", borderRadius:"var(--radius)", padding:"10px 12px",
        }}>
          {kritisch > 0 && <div style={{ color:"var(--red)", fontWeight:600, fontSize:12 }}>● {kritisch} kritisch</div>}
          {wichtig  > 0 && <div style={{ color:"var(--orange)", fontWeight:500, fontSize:12, marginTop:2 }}>● {wichtig} wichtig</div>}
        </div>
      )}

      <div style={{ flex:1, padding:isMobile ? "0 10px" : isCompact?"0 8px":"0 12px", overflowY:"auto", WebkitOverflowScrolling: "touch" }}>
        {navItems.map(item => {
          const active = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              title={item.label}
              aria-current={active ? "page" : undefined}
              onClick={() => goTab(item.id)}
              style={{
                width:"100%", display:"flex", alignItems:"center", gap:10,
                padding:isMobile ? "12px 12px" : "10px 12px",
                minHeight: isMobile ? 48 : undefined,
                borderRadius:"var(--radius)", border:"none",
                background:active?"var(--bg3)":"transparent",
                color:active?"var(--accent)":"var(--text2)",
                fontWeight:active?600:400,
                fontSize: isMobile ? 15 : isCompact ? 13 : 14,
                cursor:"pointer", marginBottom:2,
                transition:"all var(--transition)",
                borderLeft:active?`3px solid var(--accent)`:"3px solid transparent",
                touchAction: "manipulation",
              }}
            >
              <span style={{ fontSize: isMobile ? 18 : 16, flexShrink: 0 }}>{item.icon}</span>
              <span style={{
                flex:1, textAlign:"left", minWidth: 0,
                overflow:"hidden",
                whiteSpace: isCompact && !isMobile ? "normal" : "nowrap",
                lineHeight: 1.25,
                ...(isCompact && !isMobile
                  ? {
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    wordBreak: "break-word",
                  }
                  : {
                    textOverflow: "ellipsis",
                  }),
              }}>{item.label}</span>
              {item.badge ? (
                <Badge color={item.id==="aufgaben"&&kritisch?"var(--red)":"var(--accent)"}
                       style={{ fontSize:10, flexShrink: 0 }}>
                  {item.badge}
                </Badge>
              ) : null}
            </button>
          );
        })}
      </div>

      <Divider />
      {footerAdmin && (
        <div style={{ padding: isMobile ? "0 10px 10px" : isCompact ? "0 8px 10px" : "0 16px 16px" }}>
          <Link
            to="/users"
            onClick={() => onCloseMobile?.()}
            style={{
              display: "block", textAlign: "center", padding: isMobile ? "12px 12px" : "10px 12px",
              minHeight: isMobile ? 48 : undefined,
              borderRadius: "var(--radius)", border: "1px solid var(--border2)",
              color: "var(--accent)", fontSize: 13, fontWeight: 600,
            }}
          >
            {isCompact && !isMobile ? "Team" : "Team & Einladungen"}
          </Link>
          <Link
            to="/profile"
            onClick={() => onCloseMobile?.()}
            style={{
              display: "block", textAlign: "center", padding: isMobile ? "12px 12px" : "10px 12px", marginTop: 8,
              minHeight: isMobile ? 48 : undefined,
              borderRadius: "var(--radius)", border: "1px solid var(--border2)",
              color: "var(--text2)", fontSize: 13, fontWeight: 600,
            }}
          >
            {isCompact && !isMobile ? "Profil" : "Mein Profil"}
          </Link>
        </div>
      )}
      {!footerAdmin && (
        <div style={{ padding: isMobile ? "0 10px 10px" : isCompact ? "0 8px 10px" : "0 16px 16px" }}>
          <Link
            to="/profile"
            onClick={() => onCloseMobile?.()}
            style={{
              display: "block", textAlign: "center", padding: isMobile ? "12px 12px" : "10px 12px",
              minHeight: isMobile ? 48 : undefined,
              borderRadius: "var(--radius)", border: "1px solid var(--border2)",
              color: "var(--text2)", fontSize: 13, fontWeight: 600,
            }}
          >
            {isCompact && !isMobile ? "Profil" : "Mein Profil"}
          </Link>
        </div>
      )}
      <div style={{ padding: isMobile ? "0 10px 12px" : isCompact ? "0 10px 10px" : "0 16px 12px" }}>
        <ThemeQuickSwitch compact />
      </div>
      {!isMobile ? (
        <div
          onPointerDown={onResizeStart}
          title="Sidebar-Breite anpassen"
          style={{
            position:"absolute",
            top:0,
            right:0,
            width:10,
            height:"100%",
            cursor:"col-resize",
            background:"transparent",
            touchAction: "none",
          }}
        />
      ) : null}
    </nav>
  );

  if (isMobile) {
    return (
      <>
        {mobileOpen ? (
          <div
            role="presentation"
            onClick={onCloseMobile}
            style={{
              position: "fixed",
              inset: 0,
              zIndex: 180,
              background: "var(--overlay-scrim)",
            }}
          />
        ) : null}
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            bottom: 0,
            zIndex: 190,
            width: drawerWidth,
            maxWidth: "92vw",
            transform: mobileOpen ? "translateX(0)" : "translateX(-105%)",
            transition: "transform 0.22s ease-out",
            pointerEvents: mobileOpen ? "auto" : "none",
            boxShadow: mobileOpen ? "var(--shadow-elev)" : "none",
          }}
        >
          {navShell}
        </div>
      </>
    );
  }

  return (
    <div style={{ position: "relative", flexShrink: 0 }}>
      {navShell}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HEUTE PANEL
// ═══════════════════════════════════════════════════════════

const HeutePanel = ({ heute, onToggle, onEdit, onDelete, actionLoadingId, isMobile = false }) => {
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
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
      {heute.map((item, i) => {
        const isUeber = (item.tage || 0) < 0;
        const c = isUeber ? "var(--red)" : item.tage === 0 ? "var(--orange)" : "var(--text2)";
        const taskId = item?.id || item?.aufgabe_id || item?.task_id || "";
        const canAct = Boolean(taskId) && (onToggle || onEdit || onDelete);
        return (
          <div key={i} style={{
            background:"var(--bg2)", border:`1px solid ${isUeber?"color-mix(in srgb, var(--red) 26%, transparent)":"var(--border)"}`,
            borderRadius:"var(--radius)", padding:"16px 18px",
            display:"flex", alignItems:"flex-start", flexWrap:"wrap", gap:16,
            animation:`fadeUp 0.3s ease ${i*50}ms both`,
          }}>
            <div style={{
              width:36, height:36, borderRadius:"var(--radius)",
              background:c+"20", display:"flex", alignItems:"center",
              justifyContent:"center", flexShrink:0, fontSize:16, color:c,
            }}>
              {isUeber ? "⚠" : item.tage === 0 ? "●" : "◎"}
            </div>
            <div style={{ flex:"1 1 160px", minWidth:0 }}>
              <div style={{ fontWeight:500, color:"var(--text)", fontSize:14, wordBreak:"break-word" }}>
                {item.text || item.beschreibung || "Aufgabe"}
              </div>
              <div style={{ fontSize:12, color:c, marginTop:2 }}>
                {item.label || item.frist || ""}
              </div>
            </div>
            <Badge color={c} style={{ flexShrink:0 }}>{item.prioritaet || "normal"}</Badge>
            {canAct && (
              <div style={{
                display:"flex", alignItems:"center", gap:6, flexWrap:"wrap",
                ...(isMobile ? { flex:"1 1 100%", justifyContent:"flex-start" } : { marginLeft:"auto" }),
              }}>
                {onToggle && (
                  <Btn
                    size="xs"
                    variant="ghost"
                    loading={actionLoadingId === taskId}
                    onClick={() => onToggle(item)}
                  >
                    Erledigt
                  </Btn>
                )}
                {onEdit && (
                  <Btn
                    size="xs"
                    variant="ghost"
                    loading={actionLoadingId === taskId}
                    onClick={() => onEdit(item)}
                  >
                    Bearb.
                  </Btn>
                )}
                {onDelete && (
                  <Btn
                    size="xs"
                    variant="danger"
                    loading={actionLoadingId === taskId}
                    onClick={() => onDelete(item)}
                  >
                    ✕
                  </Btn>
                )}
              </div>
            )}
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
    kritisch:"var(--red)", dringend:"var(--red)", wichtig:"var(--orange)",
    frist:"var(--orange)", dokumente:"var(--blue)", info:"var(--accent)",
  };

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
      {empfehlungen.slice(0, 12).map((m, i) => (
        <Card key={i} animate delay={i*50} style={{ padding:"16px 18px" }}>
          <div style={{ display:"flex", justifyContent:"space-between",
                        alignItems:"flex-start", marginBottom:12, flexWrap:"wrap", gap:10 }}>
            <div style={{ minWidth:0, flex:"1 1 160px" }}>
              <div style={{ fontWeight:600, color:"var(--text)", fontSize:15, wordBreak:"break-word" }}>{m.mandant}</div>
              <div style={{ fontSize:12, color:"var(--accent)", marginTop:2 }}>
                €{(m.umsatz || 0).toLocaleString("de")} Jahresumsatz
              </div>
            </div>
            <div style={{ display:"flex", gap:8, flexWrap:"wrap", flexShrink:0 }}>
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
                  <span style={{ fontSize:13, color:"var(--text2)", wordBreak:"break-word", minWidth:0 }}>{e.text}</span>
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

const MandantenTabelle = ({ kpis, onSelect, onDelete, onEmail, selectedName, isMobile = false }) => {
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
                    alignItems:"center", flexWrap:"wrap", borderBottom:"1px solid var(--border)" }}>
        <div style={{ flex:"1 1 200px", minWidth:0 }}>
          <Input placeholder="Mandanten suchen..." value={suche}
                 onChange={setSuche} style={{ maxWidth:isMobile ? "100%" : 260, width:"100%" }} />
        </div>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap" }}>
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
              const sc = { KRITISCH:"var(--red)", WICHTIG:"var(--orange)", NORMAL:"var(--green)" }[k.status] || "var(--text3)";
              return (
                <tr key={k.mandant} onClick={() => onSelect(k.mandant)}
                  style={{
                    borderBottom:"1px solid var(--border)",
                    background:isSelected?"var(--bg3)":i%2===0?"transparent":"color-mix(in srgb, var(--text) 4%, var(--bg))",
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
                  <td style={{ padding:"13px 16px", color:"var(--accent)", fontWeight:600 }}>
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
                      <Badge color={"var(--red)"}>{k.aufgaben_ueberfaellig} überfällig</Badge>
                    ) : (
                      <span style={{ color:"var(--text3)", fontSize:12 }}>
                        {k.aufgaben_offen||0} offen
                      </span>
                    )}
                  </td>
                  <td style={{ padding:"13px 16px" }}>
                    <span style={{ color:(k.tage_ohne_antwort||0)>=7?"var(--orange)":"var(--text2)", fontSize:13 }}>
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
        <div style={{ background:"color-mix(in srgb, var(--red) 14%, var(--bg3))", border:"1px solid color-mix(in srgb, var(--red) 26%, transparent)",
                      borderRadius:"var(--radius)", padding:"10px 14px",
                      color:"var(--red)", fontSize:13, marginBottom:16 }}>
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
    <div style={{ position:"fixed", inset:0, background:"var(--overlay-scrim)",
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

function aufgabenListeDedupeNachId(rows) {
  const m = new Map();
  for (const r of rows || []) {
    const id = r?.id;
    if (id != null && id !== "") m.set(String(id), r);
  }
  return [...m.values()];
}

const PENDING_AUFGABEN_KEY = "kanzlei_pending_aufgaben_v1";

function lesePendingAufgaben() {
  try {
    const raw = localStorage.getItem(PENDING_AUFGABEN_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(arr)) return [];
    return arr.filter((x) => x && x.id);
  } catch {
    return [];
  }
}

function schreibePendingAufgaben(rows) {
  try {
    localStorage.setItem(PENDING_AUFGABEN_KEY, JSON.stringify(rows || []));
  } catch {}
}

function mergeServerMitPending(serverRows, pendingRows) {
  const server = aufgabenListeDedupeNachId(serverRows || []);
  const ids = new Set(server.map((x) => String(x.id)));
  const pending = (pendingRows || [])
    .filter((x) => x?.id && !ids.has(String(x.id)))
    .map((x) => ({ ...x, _pending_local: true }));
  return aufgabenListeDedupeNachId([...server, ...pending]);
}

function mandantenNamenAusQuellen(liste, kpisRows) {
  const ausListe = (liste || [])
    .map((m) => String(m?.name ?? m?.mandant ?? "").trim())
    .filter(Boolean);
  const ausKpis = (kpisRows || [])
    .map((k) => String(k?.mandant ?? k?.name ?? "").trim())
    .filter(Boolean);
  const set = new Set([...ausListe, ...ausKpis]);
  return [...set].sort((a, b) => a.localeCompare(b, "de", { sensitivity: "base" }));
}

function AufgabenSeite({ kpis, heute, onRefresh, isMobile = false }) {
  const [mandantenNamen, setMandantenNamen] = useState([]);
  const [allAufgaben,    setAllAufgaben]    = useState([]);
  const [mandant,        setMandant]        = useState("");
  const [beschreibung,   setBeschreibung]   = useState("");
  const [frist,          setFrist]          = useState("");
  const [fristUhrzeit,   setFristUhrzeit]   = useState("");
  const [prioritaet,     setPrio]           = useState("normal");
  const [adding,         setAdding]         = useState(false);
  const [fehler,         setFehler]         = useState("");
  const [success,        setSuccess]        = useState("");
  const [ladeAufgaben,   setLadeAufgaben]   = useState(false);
  const [editAufgabe,   setEditAufgabe]    = useState(null);

  const PRIO_FARBEN = { kritisch:"var(--red)", hoch:"var(--orange)", normal:"var(--accent)", niedrig:"var(--text3)" };
  const showSuccess = useCallback((msg) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(""), 2500);
  }, []);

  // Alle Aufgaben aus allen Mandanten laden
  const laden = useCallback(async () => {
    setLadeAufgaben(true);
    setFehler("");
    try {
      const raw = await getMandanten();
      const liste = normalisiereMandanten(raw);
      let namen = mandantenNamenAusQuellen(liste, kpis);
      const pendingRows = lesePendingAufgaben();
      const pendingMandanten = pendingRows
        .map((x) => String(x?.mandant || "").trim())
        .filter(Boolean);
      if (pendingMandanten.length) {
        namen = [...new Set([...namen, ...pendingMandanten])].sort((a, b) =>
          a.localeCompare(b, "de", { sensitivity: "base" })
        );
      }
      setMandantenNamen(namen);

      const aufgabenArrays = await Promise.allSettled(
        namen.map((n) => apiGet(`/mandanten/${encodeURIComponent(n)}/aufgaben`))
      );

      let alle = [];
      const loadErrors = [];
      aufgabenArrays.forEach((res, idx) => {
        const label = namen[idx] || `Mandant ${idx}`;
        if (res.status === "fulfilled") {
          extrahiereAufgabenArray(res.value).forEach((aufg) => {
            alle.push({
              ...aufg,
              mandant: aufg.mandant || label,
            });
          });
        } else {
          loadErrors.push(
            `${label}: ${res.reason?.message || String(res.reason || "Laden fehlgeschlagen")}`
          );
        }
      });

      alle = aufgabenListeDedupeNachId(alle);
      const serverIds = new Set(alle.map((x) => String(x.id)));
      const weiterhinPending = pendingRows.filter((x) => !serverIds.has(String(x.id)));
      if (weiterhinPending.length !== pendingRows.length) {
        schreibePendingAufgaben(weiterhinPending);
      }
      alle = mergeServerMitPending(alle, weiterhinPending);

      setAllAufgaben(alle);
      if (loadErrors.length) {
        setFehler(
          loadErrors.slice(0, 3).join(" · ") + (loadErrors.length > 3 ? " …" : "")
        );
      }
    } catch (e) {
      console.error("AufgabenSeite laden:", e);
      setFehler(e.message || "Aufgaben konnten nicht geladen werden");
    } finally {
      setLadeAufgaben(false);
    }
  }, [kpis]);

  useEffect(() => { laden(); }, [laden]);

  const hinzufuegen = async () => {
    setFehler("");
    if (!mandant)           { setFehler("Bitte Mandant wählen");      return; }
    if (!beschreibung.trim()){ setFehler("Bitte Beschreibung eingeben"); return; }
    if (!frist)              { setFehler("Bitte Frist wählen");        return; }
    setAdding(true);
    try {
      const besch = beschreibung.trim();
      const created = await addAufgabeAPI(mandant, {
        beschreibung: besch,
        frist,
        frist_uhrzeit: fristUhrzeit || null,
        prioritaet,
      });
      const newId = created?.id ?? created?.data?.id;
      const optimisticRow = newId
        ? {
            id: newId,
            mandant,
            beschreibung: besch,
            frist,
            frist_uhrzeit: fristUhrzeit || "",
            prioritaet,
            erledigt: 0,
            kategorie: "allgemein",
            notiz: "",
          }
        : null;
      if (optimisticRow) {
        optimisticRow._pending_local = true;
        const prevPending = lesePendingAufgaben().filter((x) => String(x.id) !== String(newId));
        schreibePendingAufgaben([...prevPending, optimisticRow]);
        setAllAufgaben((prev) =>
          aufgabenListeDedupeNachId([
            ...prev.filter((x) => String(x.id) !== String(newId)),
            optimisticRow,
          ])
        );
      }
      setBeschreibung(""); setFrist(""); setFristUhrzeit(""); setPrio("normal"); setMandant("");
      showSuccess("✓ Aufgabe wurde erstellt");
      if (onRefresh) await onRefresh();
      await laden();
    } catch (e) {
      setFehler(e.message || "Fehler beim Speichern");
    } finally {
      setAdding(false);
    }
  };

  const resolveHeuteTaskId = (item) => item?.id || item?.aufgabe_id || item?.task_id || "";

  const handleHeuteToggleAufgaben = async (item) => {
    const id = resolveHeuteTaskId(item);
    if (!id) {
      setFehler("Aufgabe konnte nicht zugeordnet werden");
      return;
    }
    try {
      await toggleAufgabeAPI(id);
      await laden();
      if (onRefresh) await onRefresh();
    } catch (e) {
      setFehler(e.message || "Aufgabe konnte nicht aktualisiert werden");
    }
  };

  const handleHeuteDeleteAufgaben = async (item) => {
    const id = resolveHeuteTaskId(item);
    if (!id) return;
    if (!window.confirm("Aufgabe löschen?")) return;
    try {
      await deleteAufgabeAPI(id);
      await laden();
      if (onRefresh) await onRefresh();
    } catch (e) {
      setFehler(e.message || "Löschen fehlgeschlagen");
    }
  };

  const handleHeuteEditAufgaben = (item) => {
    const id = resolveHeuteTaskId(item);
    if (!id) return;
    setEditAufgabe({
      id,
      mandant: item.mandant,
      beschreibung: item.beschreibung || "",
      frist: item.frist || "",
      frist_uhrzeit: item.frist_uhrzeit || "",
      prioritaet: item.prioritaet || "normal",
      kategorie: item.kategorie,
      notiz: item.notiz,
    });
  };

  const toggleAufgabe = async (a) => {
    if (!a?.id) return;
    if (a?._pending_local) {
      const nextErledigt = istAufgabeErledigt(a) ? 0 : 1;
      setAllAufgaben((prev) => prev.map((x) => (
        String(x.id) === String(a.id) ? { ...x, erledigt: nextErledigt, _pending_local: true } : x
      )));
      const nextPending = lesePendingAufgaben().map((x) => (
        String(x.id) === String(a.id) ? { ...x, erledigt: nextErledigt } : x
      ));
      schreibePendingAufgaben(nextPending);
      showSuccess(nextErledigt ? "✓ Aufgabe als erledigt markiert" : "✓ Aufgabe wieder geöffnet");
      if (onRefresh) onRefresh();
      return;
    }
    const vorher = allAufgaben;
    setAllAufgaben((prev) => prev.map((x) => (
      x.id === a.id ? { ...x, erledigt: istAufgabeErledigt(x) ? 0 : 1 } : x
    )));
    try {
      await toggleAufgabeAPI(a.id);
      showSuccess(istAufgabeErledigt(a) ? "✓ Aufgabe wieder geöffnet" : "✓ Aufgabe als erledigt markiert");
      await laden();
      if (onRefresh) await onRefresh();
    } catch (e) {
      setAllAufgaben(vorher);
      setFehler(e.message || "Aufgabe konnte nicht aktualisiert werden");
    }
  };

  const loescheAufgabe = async (a) => {
    if (!a?.id) return;
    if (a?._pending_local) {
      if (!window.confirm("Aufgabe löschen?")) return;
      setAllAufgaben((prev) => prev.filter((x) => String(x.id) !== String(a.id)));
      const nextPending = lesePendingAufgaben().filter((x) => String(x.id) !== String(a.id));
      schreibePendingAufgaben(nextPending);
      showSuccess("✓ Aufgabe gelöscht");
      if (onRefresh) onRefresh();
      return;
    }
    if (!window.confirm("Aufgabe löschen?")) return;
    const vorher = allAufgaben;
    setAllAufgaben((prev) => prev.filter((x) => x.id !== a.id));
    try {
      await deleteAufgabeAPI(a.id);
      showSuccess("✓ Aufgabe gelöscht");
      await laden();
      if (onRefresh) await onRefresh();
    } catch (e) {
      setAllAufgaben(vorher);
      setFehler(e.message || "Aufgabe konnte nicht gelöscht werden");
    }
  };

  const bearbeiteAufgabe = (a) => {
    if (!a?.id) return;
    setEditAufgabe(a);
  };

  const speichereAufgabeEdit = async (payload) => {
    if (!editAufgabe?.id) return;
    const id = editAufgabe.id;
    const vorher = allAufgaben;
    setAllAufgaben((prev) => prev.map((x) => (x.id === id ? { ...x, ...payload, mandant: payload.mandant || x.mandant } : x)));
    if (editAufgabe?._pending_local) {
      const nextPending = lesePendingAufgaben().map((x) => (
        String(x.id) === String(id) ? { ...x, ...payload, mandant: payload.mandant || x.mandant } : x
      ));
      schreibePendingAufgaben(nextPending);
      setEditAufgabe(null);
      setFehler("");
      showSuccess("✓ Aufgabe bearbeitet");
      if (onRefresh) onRefresh();
      return;
    }
    try {
      await updateAufgabeAPI(id, payload);
      setEditAufgabe(null);
      setFehler("");
      showSuccess("✓ Aufgabe bearbeitet");
      await laden();
      if (onRefresh) await onRefresh();
    } catch (e) {
      setAllAufgaben(vorher);
      if (e?.status === 404 || /nicht gefunden/i.test(String(e?.message || ""))) {
        const fallbackPending = {
          ...(editAufgabe || {}),
          ...payload,
          id,
          mandant: payload.mandant || editAufgabe?.mandant || "",
          _pending_local: true,
        };
        const nextPending = lesePendingAufgaben().filter((x) => String(x.id) !== String(id));
        schreibePendingAufgaben([...nextPending, fallbackPending]);
        setAllAufgaben((prev) => aufgabenListeDedupeNachId([
          ...prev.filter((x) => String(x.id) !== String(id)),
          fallbackPending,
        ]));
        setEditAufgabe(null);
        setFehler("Aufgabe war serverseitig nicht auffindbar und wurde lokal gesichert.");
        return;
      }
      throw e;
    }
  };

  const offen    = allAufgaben.filter((a) => !istAufgabeErledigt(a));
  const kritisch = offen.filter(a => a.prioritaet === "kritisch" || a.prioritaet === "hoch");

  const inp = {
    background:"var(--bg)", border:"1px solid var(--border2)", borderRadius:10,
    color:"var(--text)", padding:"10px 14px", fontSize:14, outline:"none",
    fontFamily:"var(--font-body)", width:"100%",
  };

  return (
    <div style={{ padding:"clamp(12px, 3vw, 28px) clamp(12px, 4vw, 36px)", flex:1, overflowY:"auto",
                  maxWidth:"100%", minWidth:0, boxSizing:"border-box" }}>
      {/* Header */}
      <div style={{ fontFamily:"var(--font-head)", fontSize:24, color:"var(--text)", marginBottom:4 }}>
        Aufgaben & Fristen
      </div>
      <div style={{ fontSize:13, color:"var(--text3)", marginBottom:24 }}>
        {offen.length} offen · {kritisch.length} kritisch/hoch
        {ladeAufgaben && <span style={{ marginLeft:12, opacity:0.5 }}><Spinner size={12} /></span>}
      </div>

      {fehler && (
        <div style={{
          background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",
          border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)",
          borderRadius:8, padding:"10px 14px", marginBottom:20,
          color:"var(--red)", fontSize:13, maxWidth:"100%", wordBreak:"break-word",
        }}>
          ⚠ {fehler}
        </div>
      )}

      {/* Neue Aufgabe */}
      <Card style={{ marginBottom:28 }}>
        <div style={{ fontFamily:"var(--font-head)", fontSize:17, color:"var(--accent)", marginBottom:16 }}>
          + Neue Aufgabe erstellen
        </div>
        {success && (
          <div style={{ background:"color-mix(in srgb, var(--green) 14%, var(--bg3))", border:"1px solid color-mix(in srgb, var(--green) 24%, transparent)",
                        borderRadius:8, padding:"8px 12px", marginBottom:12,
                        color:"var(--green)", fontSize:13 }}>
            {success}
          </div>
        )}

        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(min(100%, 220px), 1fr))", gap:12, marginBottom:12 }}>
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
          <div>
            <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
                          letterSpacing:"0.07em", marginBottom:5 }}>Uhrzeit (optional)</div>
            <input type="time" value={fristUhrzeit} onChange={e => setFristUhrzeit(e.target.value)}
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

        <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:16, flexWrap:"wrap" }}>
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
          <HeutePanel
            heute={heute}
            onToggle={handleHeuteToggleAufgaben}
            onEdit={handleHeuteEditAufgaben}
            onDelete={handleHeuteDeleteAufgaben}
            isMobile={isMobile}
          />
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
              tage < 0  ? "var(--red)" :
              tage <= 2  ? "var(--orange)" : "var(--text3)";

            return (
              <div key={a.id || i} style={{
                background:"var(--bg2)", borderRadius:10, padding:"12px 16px",
                borderLeft:`3px solid ${pc}`,
                border:`1px solid var(--border)`,
                borderLeftColor:pc,
                display:"flex", alignItems:"flex-start", flexWrap:"wrap", gap:10,
                animation:`fadeUp 0.3s ease ${i*30}ms both`,
              }}>
                <input
                  type="checkbox"
                  checked={istAufgabeErledigt(a)}
                  onChange={() => toggleAufgabe(a)}
                  style={{ cursor:"pointer", accentColor:"var(--accent)", marginTop:2, flexShrink:0 }}
                />
                <div style={{ flex:"1 1 200px", minWidth:0 }}>
                  <div style={{
                    fontSize:14, color:"var(--text)", fontWeight:500,
                    ...(isMobile
                      ? { wordBreak:"break-word" }
                      : { overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }),
                  }}>
                    {a.beschreibung}
                  </div>
                  <div style={{ fontSize:12, color:"var(--text3)", marginTop:3 }}>
                    {a.mandant}
                    {a.frist && <span style={{ marginLeft:8 }}>📅 {a.frist}</span>}
                    {a.frist_uhrzeit && <span style={{ marginLeft:8 }}>🕒 {a.frist_uhrzeit}</span>}
                    {fristLabel && (
                      <span style={{ marginLeft:8, color:fristFarbe, fontWeight:600 }}>
                        {fristLabel}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:8, flexWrap:"wrap", ...(isMobile ? { flex:"1 1 100%", justifyContent:"flex-start" } : { marginLeft:"auto" }) }}>
                  <Badge color={pc}>{a.prioritaet || "normal"}</Badge>
                  <Btn size="xs" variant="ghost" onClick={() => bearbeiteAufgabe(a)}>Bearb.</Btn>
                  <Btn size="xs" variant="danger" onClick={() => loescheAufgabe(a)}>✕</Btn>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <AufgabeEditModal
        open={Boolean(editAufgabe)}
        task={editAufgabe}
        mandantenListe={mandantenNamen}
        allowMandantChange
        onClose={() => setEditAufgabe(null)}
        onSave={speichereAufgabeEdit}
      />
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

  const [viewportW, setViewportW] = useState(() => (typeof window !== "undefined" ? window.innerWidth : 1000));
  useEffect(() => {
    const onResize = () => setViewportW(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const detailMobile = viewportW <= 900;

  const [mandant,     setMandant]     = useState(null);
  const [aufgaben,    setAufgaben]    = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [beschreibung,setBeschreibung]= useState("");
  const [frist,       setFrist]       = useState("");
  const [fristUhrzeit,setFristUhrzeit]= useState("");
  const [prioritaet,  setPrio]        = useState("normal");
  const [addLoading,  setAddLoading]  = useState(false);
  const [toast,       setToast]       = useState("");
  const [editAufgabeDetail, setEditAufgabeDetail] = useState(null);

  const showToast = (t) => { setToast(t); setTimeout(() => setToast(""), 3000); };

  const ladeAlles = useCallback(async () => {
    try {
      // Mandanten-Daten
      const raw = await getMandanten();
      const liste = normalisiereMandanten(raw);
      const m = liste.find(
        (x) => String(x?.name ?? x?.mandant ?? x ?? "").trim() === name
      );
      setMandant(m || { name });

      // Aufgaben
      const a = await apiGet(`/mandanten/${encodeURIComponent(name)}/aufgaben`);
      const serverRows = extrahiereAufgabenArray(a);
      const pendingRows = lesePendingAufgaben().filter(
        (x) => String(x?.mandant || "").trim() === String(name || "").trim()
      );
      setAufgaben(mergeServerMitPending(serverRows, pendingRows));
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
      const besch = beschreibung.trim();
      const created = await addAufgabeAPI(name, {
        beschreibung: besch,
        frist,
        frist_uhrzeit: fristUhrzeit || null,
        prioritaet,
      });
      const newId = created?.id ?? created?.data?.id;
      if (newId) {
        const optimisticRow = {
          id: newId,
          mandant: name,
          beschreibung: besch,
          frist,
          frist_uhrzeit: fristUhrzeit || "",
          prioritaet,
          erledigt: 0,
          kategorie: "allgemein",
          notiz: "",
          _pending_local: true,
        };
        const prevPending = lesePendingAufgaben().filter((x) => String(x.id) !== String(newId));
        schreibePendingAufgaben([...prevPending, optimisticRow]);
        setAufgaben((p) => mergeServerMitPending(p, [optimisticRow]));
      }
      setBeschreibung(""); setFrist(""); setFristUhrzeit(""); setPrio("normal");
      showToast("✓ Aufgabe hinzugefügt");
      await ladeAlles();
    } catch (e) { showToast("⚠ " + e.message); }
    finally { setAddLoading(false); }
  };

  const toggleAufgabeRow = async (row) => {
    const id = row?.id;
    if (!id) return;
    if (row?._pending_local) {
      const nextErledigt = istAufgabeErledigt(row) ? 0 : 1;
      setAufgaben((p) =>
        p.map((a) =>
          a.id === id ? { ...a, erledigt: nextErledigt, _pending_local: true } : a
        )
      );
      const nextPending = lesePendingAufgaben().map((x) =>
        String(x.id) === String(id) ? { ...x, erledigt: nextErledigt } : x
      );
      schreibePendingAufgaben(nextPending);
      showToast(nextErledigt ? "✓ Aufgabe als erledigt markiert" : "✓ Aufgabe wieder geöffnet");
      return;
    }
    setAufgaben((p) =>
      p.map((a) =>
        a.id === id ? { ...a, erledigt: istAufgabeErledigt(a) ? 0 : 1 } : a
      )
    );
    try {
      await toggleAufgabeAPI(id);
      showToast(istAufgabeErledigt(row) ? "✓ Aufgabe wieder geöffnet" : "✓ Aufgabe als erledigt markiert");
    } catch {
      await ladeAlles();
    }
  };

  const deleteAufgabeRow = async (row) => {
    const id = row?.id;
    if (!id) return;
    if (!window.confirm("Aufgabe löschen?")) return;
    setAufgaben((p) => p.filter((a) => a.id !== id));
    if (row?._pending_local) {
      const nextPending = lesePendingAufgaben().filter((x) => String(x.id) !== String(id));
      schreibePendingAufgaben(nextPending);
      showToast("✓ Aufgabe gelöscht");
      return;
    }
    try {
      await deleteAufgabeAPI(id);
      showToast("✓ Aufgabe gelöscht");
    } catch {
      await ladeAlles();
    }
  };

  const editAufgabe = (a) => {
    setEditAufgabeDetail({ ...a, mandant: a.mandant || name });
  };

  const speichereDetailAufgabeEdit = async (payload) => {
    if (!editAufgabeDetail?.id) return;
    try {
      if (editAufgabeDetail?._pending_local) {
        const nextPending = lesePendingAufgaben().map((x) =>
          String(x.id) === String(editAufgabeDetail.id)
            ? { ...x, ...payload, mandant: payload.mandant || x.mandant }
            : x
        );
        schreibePendingAufgaben(nextPending);
        setAufgaben((p) =>
          p.map((a) =>
            a.id === editAufgabeDetail.id
              ? { ...a, ...payload, mandant: payload.mandant || a.mandant, _pending_local: true }
              : a
          )
        );
        showToast("✓ Aufgabe bearbeitet");
        setEditAufgabeDetail(null);
        return;
      }
      await updateAufgabeAPI(editAufgabeDetail.id, payload);
      showToast("✓ Aufgabe bearbeitet");
      setEditAufgabeDetail(null);
      await ladeAlles();
    } catch (e) {
      showToast("⚠ " + (e.message || "Bearbeiten fehlgeschlagen"));
      await ladeAlles();
      throw e;
    }
  };

  const PRIO_C = { kritisch:"var(--red)", hoch:"var(--orange)", normal:"var(--blue)", niedrig:"var(--text3)" };

  if (loading) return (
    <div style={{ flex:1, display:"flex", alignItems:"center",
                  justifyContent:"center", background:"var(--bg)" }}>
      <Spinner size={36} />
    </div>
  );

  const offen    = aufgaben.filter((a) => !istAufgabeErledigt(a));
  const erledigt = aufgaben.filter((a) => istAufgabeErledigt(a));

  return (
    <div style={{ flex:1, background:"var(--bg)", overflowY:"auto",
                  minHeight:"100vh", maxWidth:"100%", minWidth:0, boxSizing:"border-box" }}>
      <FontLoader />

      {/* Toast */}
      {toast && (
        <div style={{ position:"fixed", top:20, right:12, zIndex:9999,
                      maxWidth:"min(340px, calc(100vw - 24px))",
                      background:"var(--bg3)", border:"1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                      borderLeft:"3px solid var(--accent)",
                      borderRadius:"var(--radius)", padding:"12px 16px",
                      color:"var(--text)", fontSize:13, fontWeight:500, wordBreak:"break-word" }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div style={{ background:"var(--bg2)", borderBottom:"1px solid var(--border)",
                    padding:detailMobile ? "16px 14px" : "24px 36px",
                    display:"flex", alignItems:"center", gap:16, flexWrap:"wrap" }}>
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
        <div style={{ marginLeft:detailMobile ? 0 : "auto" }}>
          <Badge color={"var(--accent)"}>€{(mandant?.umsatz || 0).toLocaleString("de")}</Badge>
        </div>
      </div>

      <div style={{ padding:"clamp(12px, 3vw, 28px) clamp(12px, 4vw, 36px)", display:"grid",
                    gridTemplateColumns:"repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap:16,
                    maxWidth:"100%", minWidth:0, boxSizing:"border-box" }}>
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
            <div style={detailMobile ? {
              display:"flex", flexDirection:"column", gap:10, alignItems:"stretch",
            } : {
              display:"grid", gridTemplateColumns:"1fr auto auto auto", gap:10, alignItems:"end",
            }}>
              <Input placeholder="Beschreibung..." value={beschreibung}
                     onChange={setBeschreibung}
                     onKeyDown={e => e.key === "Enter" && addAufgabe()} />
              <input type="date" value={frist} onChange={e => setFrist(e.target.value)}
                     style={{ background:"var(--bg)", border:"1px solid var(--border2)",
                              borderRadius:"var(--radius)", color:"var(--text)",
                              padding:"9px 11px", fontSize:14, outline:"none", width:detailMobile ? "100%" : undefined,
                              boxSizing:"border-box" }} />
              <input type="time" value={fristUhrzeit} onChange={e => setFristUhrzeit(e.target.value)}
                     style={{ background:"var(--bg)", border:"1px solid var(--border2)",
                              borderRadius:"var(--radius)", color:"var(--text)",
                              padding:"9px 11px", fontSize:14, outline:"none", width:detailMobile ? "100%" : undefined,
                              boxSizing:"border-box" }} />
              <Btn onClick={addAufgabe} loading={addLoading} variant="primary">Hinzufügen</Btn>
            </div>
            <div style={{ display:"flex", gap:6, marginTop:10, flexWrap:"wrap" }}>
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
            const c = tage === null ? "var(--border2)" : tage < 0 ? "var(--red)" : tage <= 2 ? "var(--orange)" : "var(--border2)";
            return (
              <div key={a.id || i} style={{
                display:"flex", alignItems:"flex-start", gap:12, flexWrap:"wrap",
                padding:"14px 16px", marginBottom:8,
                background:"var(--bg2)", border:`1px solid ${c}`,
                borderRadius:"var(--radius)",
                animation:`fadeUp 0.3s ease ${i*40}ms both`,
              }}>
                <input type="checkbox" checked={istAufgabeErledigt(a)} onChange={() => toggleAufgabeRow(a)}
                       style={{ marginTop:3, cursor:"pointer", accentColor:"var(--accent)", flexShrink:0 }} />
                <div style={{ flex:"1 1 200px", minWidth:0 }}>
                  <div style={{ fontWeight:500, color:"var(--text)", wordBreak:"break-word" }}>{a.beschreibung}</div>
                  <div style={{ display:"flex", gap:8, marginTop:4, flexWrap:"wrap" }}>
                    {a.frist && <span style={{ fontSize:12, color:"var(--text3)" }}>📅 {a.frist}</span>}
                    {a.frist_uhrzeit && <span style={{ fontSize:12, color:"var(--text3)" }}>🕒 {a.frist_uhrzeit}</span>}
                    {tage !== null && (
                      <Badge color={tage<0?"var(--red)":tage<=2?"var(--orange)":"var(--blue)"}>
                        {tage<0?`${Math.abs(tage)}d überfällig`:tage===0?"Heute":`in ${tage}d`}
                      </Badge>
                    )}
                    {a.prioritaet && a.prioritaet !== "normal" && (
                      <Badge color={PRIO_C[a.prioritaet]||"var(--text3)"}>{a.prioritaet}</Badge>
                    )}
                  </div>
                </div>
                <div style={{ display:"flex", gap:8, flexWrap:"wrap", ...(detailMobile ? { flex:"1 1 100%" } : { marginLeft:"auto" }) }}>
                  <Btn size="xs" variant="ghost" onClick={() => editAufgabe(a)}>Bearb.</Btn>
                  <Btn size="xs" variant="danger" onClick={() => deleteAufgabeRow(a)}>✕</Btn>
                </div>
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
                  display:"flex", alignItems:"center", gap:12, flexWrap:"wrap",
                  padding:"10px 16px", marginBottom:6,
                  background:"var(--bg2)", border:"1px solid var(--border)",
                  borderRadius:"var(--radius)", opacity:0.55,
                }}>
                  <input type="checkbox" checked onChange={() => toggleAufgabeRow(a)}
                         style={{ cursor:"pointer", accentColor:"var(--green)" }} />
                  <span style={{ textDecoration:"line-through", fontSize:13, color:"var(--text2)",
                                 wordBreak:"break-word", flex:"1 1 160px", minWidth:0 }}>
                    {a.beschreibung}
                  </span>
                  <span style={{ marginLeft:detailMobile ? 0 : "auto", fontSize:11, color:"var(--text3)" }}>
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
                                        padding:"6px 0", borderBottom:"1px solid var(--border)",
                                        gap:10, flexWrap:"wrap" }}>
                <span style={{ fontSize:12, color:"var(--text3)" }}>{label}</span>
                <span style={{ fontSize:13, color:"var(--text)", fontWeight:500,
                               maxWidth:detailMobile ? "100%" : 180, textAlign:detailMobile ? "left" : "right",
                               wordBreak:"break-word", minWidth:0 }}>
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
            <div style={{ fontSize:24, fontFamily:"var(--font-head)", color:"var(--accent)" }}>
              {offen.length}
            </div>
            <div style={{ fontSize:12, color:"var(--text3)" }}>offen · {erledigt.length} erledigt</div>
          </Card>
        </div>
      </div>

      <AufgabeEditModal
        open={Boolean(editAufgabeDetail)}
        task={editAufgabeDetail}
        mandantenListe={[name]}
        allowMandantChange={false}
        onClose={() => setEditAufgabeDetail(null)}
        onSave={speichereDetailAufgabeEdit}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// RISIKO-DASHBOARD — Das Killer Feature
// Mandanten-Risiko- & Umsatz-AI auf einen Blick
// ═══════════════════════════════════════════════════════════

function RisikoDashboard({ kpis, heute, onEmail, onTab, onRefresh, isMobile = false }) {
  const VIP_THRESHOLD = 500000;
  const [filter,   setFilter]   = useState("alle");    // alle | kritisch | vip
  const [sortBy,   setSortBy]   = useState("risiko");  // risiko | umsatz | name
  const [sending,  setSending]  = useState(null);
  const [taskLoadingId, setTaskLoadingId] = useState("");
  const [toast,    setToast]    = useState("");
  const [heuteEditItem, setHeuteEditItem] = useState(null);

  /** echte sichtbare Breite — unabhängig von „Desktop-Website“ / großem layoutViewport */
  const lw = useContentLayoutWidth();
  const padX = lw < 960 ? "max(12px, env(safe-area-inset-left))" : 36;
  const padR = lw < 960 ? "max(12px, env(safe-area-inset-right))" : 36;
  const stackHeader = lw < 680;
  const kpiGrid =
    lw < 460 ? "minmax(0, 1fr)"
      : lw < 800 ? "repeat(2, minmax(0, 1fr))"
        : "repeat(4, minmax(0, 1fr))";
  const cardPadTight = lw < 560;
  const rowActionsBelow = lw < 620;
  const heuteCompact = lw < 760 || isMobile;
  /** Nur Abstand zwischen Blöcken — Karten/Pills unverändert */
  const gapTitleToKpi = lw < 520 ? 36 : lw < 800 ? 48 : 56;
  const gapKpiToFilter = lw < 520 ? 28 : lw < 800 ? 36 : 44;
  /** Filter (Alle/Kritisch/VIP) → Mandanten-Karte: knapp, aber sichtbar */
  const gapFilterToList = lw < 520 ? 10 : lw < 800 ? 12 : 14;
  const gapSection = lw < 520 ? 24 : lw < 800 ? 32 : 40;
  const gapListCards = lw < 520 ? 14 : lw < 800 ? 16 : 18;

  const mandantenNamenDashboard = useMemo(() => {
    const s = new Set();
    (kpis || []).forEach((k) => {
      if (k?.mandant) s.add(k.mandant);
    });
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [kpis]);

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
    KRITISCH: "var(--red)", WICHTIG: "var(--orange)", NORMAL: "var(--blue)", OK: "var(--green)",
  };

  const UMSATZ_FARBE = (u) =>
    u >= 500000 ? "var(--purple)" : u >= 100000 ? "var(--accent)" : u >= 30000 ? "var(--blue)" : "var(--text3)";

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

  const resolveTaskId = (item) => item?.id || item?.aufgabe_id || item?.task_id || "";

  const handleHeuteToggle = async (item) => {
    const id = resolveTaskId(item);
    if (!id) { showToast("⚠ Aufgabe konnte nicht zugeordnet werden"); return; }
    setTaskLoadingId(id);
    try {
      await toggleAufgabeAPI(id);
      showToast("✓ Status aktualisiert");
      if (onRefresh) await onRefresh();
    } catch (e) {
      showToast(`⚠ ${e.message || "Aktualisierung fehlgeschlagen"}`);
    } finally {
      setTaskLoadingId("");
    }
  };

  const handleHeuteDelete = async (item) => {
    const id = resolveTaskId(item);
    if (!id) { showToast("⚠ Aufgabe konnte nicht zugeordnet werden"); return; }
    if (!window.confirm("Aufgabe löschen?")) return;
    setTaskLoadingId(id);
    try {
      await deleteAufgabeAPI(id);
      showToast("✓ Aufgabe gelöscht");
      if (onRefresh) await onRefresh();
    } catch (e) {
      showToast(`⚠ ${e.message || "Löschen fehlgeschlagen"}`);
    } finally {
      setTaskLoadingId("");
    }
  };

  const handleHeuteEdit = (item) => {
    const id = resolveTaskId(item);
    if (!id) {
      showToast("⚠ Aufgabe konnte nicht zugeordnet werden");
      return;
    }
    setHeuteEditItem({ ...item, id });
  };

  const speichereHeuteAufgabeEdit = async (payload) => {
    const id = resolveTaskId(heuteEditItem);
    if (!id) return;
    setTaskLoadingId(id);
    try {
      await updateAufgabeAPI(id, payload);
      showToast("✓ Aufgabe bearbeitet");
      setHeuteEditItem(null);
      if (onRefresh) await onRefresh();
    } catch (e) {
      showToast(`⚠ ${e.message || "Bearbeiten fehlgeschlagen"}`);
      throw e;
    } finally {
      setTaskLoadingId("");
    }
  };

  return (
    <div style={{ flex:1, overflowY:"auto", background:"var(--bg)",
                  maxWidth:"100%", minWidth:0, boxSizing:"border-box" }}>

      {/* Toast */}
      {toast && (
        <div style={{ position:"fixed", top:20, right:12, zIndex:9999,
                      maxWidth:`min(340px, calc(${lw}px - 24px))`,
                      background:"var(--bg3)", border:"1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                      borderLeft:"3px solid var(--accent)", borderRadius:"var(--radius)",
                      padding:"12px 18px", color:"var(--text)", fontSize:13, fontWeight:500,
                      wordBreak:"break-word",
                      animation:"slideIn 0.25s ease" }}>
          {toast}
        </div>
      )}

      {/* ── Header ── */}
      <div style={{ background:"var(--bg2)", borderBottom:"1px solid var(--border)",
                    padding:lw < 960 ? `16px ${padR} 22px ${padX}` : "24px 36px 32px 36px" }}>
        <div style={{
          display:"flex",
          justifyContent:"space-between",
          alignItems:"flex-start",
          flexDirection:stackHeader ? "column" : "row",
          flexWrap:stackHeader ? "nowrap" : "wrap",
          gap:stackHeader ? 16 : 14,
        }}>
          <div style={{ minWidth:0, width:stackHeader ? "100%" : undefined, flex:stackHeader ? "none" : "1 1 220px" }}>
            <div style={{
              fontFamily:"var(--font-head)",
              fontSize:lw < 520 ? 17 : lw < 960 ? 20 : 26,
              lineHeight:stackHeader ? 1.22 : 1.2,
              color:"var(--text)",
              marginBottom:6,
              hyphens:"auto",
              wordBreak:"break-word",
            }}>
              Mandanten-Risiko & Umsatz AI
            </div>
            <div style={{ color:"var(--text3)", fontSize:lw < 520 ? 12 : 13, lineHeight:1.5 }}>
              {new Date().toLocaleDateString("de-DE", { weekday:"long", day:"numeric", month:"long" })}
              {" · "}KI analysiert automatisch wer sofortige Aufmerksamkeit braucht
            </div>
          </div>
          <div style={{
            display:"flex", gap:8, flexWrap:"wrap", flexShrink:0,
            width:stackHeader ? "100%" : undefined,
            justifyContent:stackHeader ? "flex-start" : "flex-end",
          }}>
            <Btn size="sm" variant="ghost" onClick={() => onTab("aufgaben")}>+ Aufgabe</Btn>
            <Btn size="sm" variant="ghost" onClick={() => onTab("neu")}>+ Mandant</Btn>
          </div>
        </div>
      </div>

      {/* ── KPI Zeile (Abstand nach unten zu Filter nur über marginBottom) ── */}
      <div style={{
        boxSizing:"border-box",
        width:"100%",
        maxWidth:"100%",
        minWidth:0,
        padding:`${gapTitleToKpi}px ${padR} 0 ${padX}`,
        marginBottom: gapKpiToFilter,
        display:"grid",
        gridTemplateColumns:kpiGrid,
        gap:lw < 520 ? 10 : 12,
      }}>
        {[
          { label:"Kritisch",     value:kritisch,     color:"var(--red)",     icon:"🚨",
            sub:"sofort handeln" },
          { label:"VIP-Mandanten",value:vips,         color:"var(--purple)", icon:"⭐",
            sub:">€500k Umsatz" },
          { label:"Keine Antwort",value:gefahr,       color:"var(--orange)",  icon:"📞",
            sub:">14 Tage still" },
          { label:"Gesamt-Umsatz",value:`€${(gesamt_umsatz/1000).toFixed(0)}k`,
            color:"var(--accent)", icon:"💰", sub:`${kpis.length} Mandanten` },
        ].map((item, i) => (
          <Card key={i} animate delay={i*50} style={{ padding:cardPadTight ? "12px 12px" : "16px 18px", minWidth:0 }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:8 }}>
              <div style={{ minWidth:0 }}>
                <div style={{ fontSize:10, color:"var(--text3)", textTransform:"uppercase",
                              letterSpacing:"0.08em", marginBottom:6 }}>{item.label}</div>
                <div style={{
                  fontSize:lw < 520 ? "clamp(20px, 9vw, 26px)" : lw < 960 ? "clamp(22px, 5vw, 28px)" : 30,
                  fontFamily:"var(--font-head)",
                  color:item.color, lineHeight:1,
                }}>{item.value}</div>
                <div style={{ fontSize:11, color:"var(--text3)", marginTop:4 }}>{item.sub}</div>
              </div>
              <span style={{ fontSize:24, opacity:0.6 }}>{item.icon}</span>
            </div>
          </Card>
        ))}
      </div>

      {/* ── Filter + Sort (kompakt; Abstand zur Liste über marginTop der Liste) ── */}
      <div style={{
        padding:`12px ${padR} 12px ${padX}`,
        display:"flex", gap:10, alignItems:"center",
        flexWrap:"wrap", boxSizing:"border-box", width:"100%", maxWidth:"100%", minWidth:0,
      }}>
        <div style={{ display:"flex", gap:4, background:"var(--bg3)",
                      borderRadius:10, padding:6, flexWrap:"wrap" }}>
          {[["alle","Alle"], ["kritisch","🚨 Kritisch"], ["vip","⭐ VIP"]].map(([v,l]) => (
            <button key={v} type="button" onClick={() => setFilter(v)} style={{
              padding:"8px 14px", borderRadius:8, border:"none", cursor:"pointer",
              background:filter===v?"var(--bg2)":"transparent",
              color:filter===v?"var(--accent)":"var(--text3)",
              fontSize:13, fontWeight:filter===v?600:400,
              fontFamily:"var(--font-body)", transition:"all 0.15s",
            }}>{l}</button>
          ))}
        </div>
        <div style={{ marginLeft:lw < 720 ? 0 : "auto", display:"flex", gap:8, alignItems:"center",
                      flexWrap:"wrap" }}>
          <span style={{ fontSize:12, color:"var(--text3)" }}>Sortierung:</span>
          {[["risiko","Risiko"], ["umsatz","Umsatz"], ["name","Name"]].map(([v,l]) => (
            <Btn key={v} size="xs" variant={sortBy===v?"subtle":"ghost"}
                 onClick={() => setSortBy(v)}>{l}</Btn>
          ))}
        </div>
        <span style={{ fontSize:12, color:"var(--text3)", ...(lw < 720 ? { width:"100%" } : {}) }}>{liste.length} Mandanten</span>
      </div>

      {/* ── Mandanten-Liste (Abstand zur Filterzeile nur über marginTop) ── */}
      <div style={{
        marginTop: gapFilterToList,
        padding:`0 ${padR} ${lw < 960 ? 24 : 44}px ${padX}`,
        display:"flex", flexDirection:"column", gap:gapListCards,
        boxSizing:"border-box", width:"100%", maxWidth:"100%", minWidth:0,
      }}>
        {liste.length === 0 && (
          <Card style={{ textAlign:"center", padding:40 }}>
            <div style={{ fontSize:36, marginBottom:10 }}>✅</div>
            <div style={{ color:"var(--text)", fontWeight:600, marginBottom:6 }}>
              Keine Mandanten in diesem Filter
            </div>
            <div style={{ color:"var(--text3)", fontSize:13, marginBottom:18, maxWidth:420, marginLeft:"auto", marginRight:"auto" }}>
              Wechseln Sie den Filter auf „Alle“, legen Sie einen Mandanten an oder importieren Sie Bestände — dann erscheint hier Ihr Risiko- und Umsatz-Radar.
            </div>
            <div style={{ display:"flex", gap:10, justifyContent:"center", flexWrap:"wrap" }}>
              <Btn size="sm" variant="primary" onClick={() => { setFilter("alle"); setSortBy("risiko"); }}>
                Alle Mandanten anzeigen
              </Btn>
              <Btn size="sm" variant="ghost" onClick={() => onTab("neu")}>
                + Mandant anlegen
              </Btn>
            </div>
          </Card>
        )}

        {liste.map((k, i) => {
          const risiko     = k.risiko_score ?? Math.min(100, Math.round((k.score||0) / 120));
          const risikoFarbe= risiko >= 70 ? "var(--red)" : risiko >= 40 ? "var(--orange)" : risiko >= 15 ? "var(--blue)" : "var(--green)";
          const statusFarbe= STATUS_FARBE[k.status] || "var(--green)";
          const empf       = k.empfehlung || {};
          const empfFarbe  = empf.farbe || statusFarbe;
          const istVip     = k.ist_vip || (k.umsatz || 0) >= VIP_THRESHOLD;
          const umsatzF    = UMSATZ_FARBE(k.umsatz || 0);

          return (
            <div key={k.mandant} style={{
              background:"var(--bg2)", border:`1px solid var(--border)`,
              borderLeft:`4px solid ${statusFarbe}`,
              borderRadius:"var(--radius-lg)",
              padding:lw < 480 ? "14px 12px" : "18px 20px",
              animation:`fadeUp 0.3s ease ${i*30}ms both`,
              transition:"all 0.15s",
              maxWidth:"100%", minWidth:0, boxSizing:"border-box",
            }}>
              <div style={{ display:"flex", gap:lw < 520 ? 12 : 16, alignItems:"flex-start", flexWrap:"wrap",
                            width:"100%", maxWidth:"100%", minWidth:0, boxSizing:"border-box" }}>

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
                  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:4, flexWrap:"wrap" }}>
                    <Link to={`/mandant/${encodeURIComponent(k.mandant)}`}
                      style={{ fontFamily:"var(--font-head)", fontSize:lw < 520 ? 16 : 18,
                               color:"var(--text)", fontWeight:600, wordBreak:"break-word", minWidth:0 }}>
                      {k.mandant}
                    </Link>
                    {istVip && (
                      <span style={{ fontSize:11, padding:"2px 8px", borderRadius:20,
                                     background:"color-mix(in srgb, var(--purple) 18%, var(--bg3))",
                                     color:"var(--purple)",
                                     border:"1px solid color-mix(in srgb, var(--purple) 28%, transparent)", fontWeight:700 }}>
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
                      <span style={{ fontSize:12, color:(k.tage_ohne_antwort||0)>=14?"var(--red)":"var(--orange)" }}>
                        📞 {k.tage_ohne_antwort}d kein Kontakt
                      </span>
                    )}
                    {k.aufgaben_ueberfaellig > 0 && (
                      <span style={{ fontSize:12, color:"var(--red)" }}>
                        ⏰ {k.aufgaben_ueberfaellig} überfällig
                      </span>
                    )}
                    {k.aufgaben_offen > 0 && (
                      <span style={{ fontSize:12, color:"var(--text3)" }}>
                        {k.aufgaben_offen} Aufgaben offen
                      </span>
                    )}
                    {k.fehlende_dokumente > 0 && (
                      <span style={{ fontSize:12, color:"var(--blue)" }}>
                        📄 {k.fehlende_dokumente} Dok. fehlen
                      </span>
                    )}
                  </div>

                  {/* Umsatz-Bar */}
                  <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:10 }}>
                    <div style={{ fontSize:10, color:"var(--text3)", width:40 }}>
                      {k.umsatz_kategorie || "—"}
                    </div>
                    <div style={{ flex:1, minWidth:0, height:3, background:"var(--bg3)",
                                  borderRadius:2, maxWidth:lw < 520 ? "none" : 220 }}>
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
                      display:"flex", alignItems:"flex-start", gap:8, flexWrap:"wrap",
                      padding:"8px 12px", borderRadius:8,
                      background:empfFarbe+"12",
                      border:`1px solid ${empfFarbe}25`,
                    }}>
                      <span style={{ fontSize:16, flexShrink:0 }}>{empf.icon || "●"}</span>
                      <div style={{ flex:"1 1 160px", minWidth:0 }}>
                        <div style={{ fontSize:13, fontWeight:600, color:empfFarbe }}>
                          {empf.titel}
                        </div>
                        {empf.text && (
                          <div style={{
                            fontSize:12, color:"var(--text3)", marginTop:1, wordBreak:"break-word",
                            ...(lw < 720 ? {} : { overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }),
                          }}>
                            {empf.text}
                          </div>
                        )}
                      </div>
                      {(empf.aktion_text || "") && (
                        <span style={{
                          fontSize:11, color:empfFarbe, flexShrink:0, fontWeight:600,
                          ...(lw < 720 ? { width:"100%" } : {}),
                        }}>
                          {empf.aktion_text}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Aktions-Buttons */}
                <div style={{
                  display:"flex",
                  flexDirection:rowActionsBelow ? "row" : "column",
                  gap:6, flexShrink:0,
                  ...(rowActionsBelow ? { flex:"1 1 100%", flexWrap:"wrap", width:"100%" } : {}),
                }}>
                  <Link to={`/mandant/${encodeURIComponent(k.mandant)}`} style={rowActionsBelow ? { flex:"1 1 160px", minWidth:0, maxWidth:"100%" } : undefined}>
                    <Btn size="sm" variant="ghost" style={{ width:"100%" }}>
                      Öffnen →
                    </Btn>
                  </Link>
                  {k.email && (
                    <Btn size="sm" variant={k.status==="KRITISCH"?"danger":"subtle"}
                         loading={sending===k.mandant}
                         onClick={() => handleEmail(k.mandant, k.email)}
                         style={rowActionsBelow ? { flex:"1 1 160px", minWidth:0, maxWidth:"100%" } : undefined}>
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
        <div style={{
          padding:`${gapSection}px ${padR} ${lw < 960 ? 28 : 44}px ${padX}`,
          boxSizing:"border-box", width:"100%", maxWidth:"100%", minWidth:0,
        }}>
          <div style={{ fontFamily:"var(--font-head)", fontSize:18,
                        color:"var(--text)", marginBottom:16 }}>
            Heute & Dringend
          </div>
          <HeutePanel
            heute={heute}
            onToggle={handleHeuteToggle}
            onEdit={handleHeuteEdit}
            onDelete={handleHeuteDelete}
            actionLoadingId={taskLoadingId}
            isMobile={heuteCompact}
          />
        </div>
      )}

      <AufgabeEditModal
        open={Boolean(heuteEditItem)}
        task={heuteEditItem}
        mandantenListe={mandantenNamenDashboard}
        allowMandantChange
        onClose={() => setHeuteEditItem(null)}
        onSave={speichereHeuteAufgabeEdit}
      />
    </div>
  );
}


function AppInner() {
  const [accessRev, setAccessRev] = useState(0);
  const [navSettings, setNavSettings] = useState(null);
  // accessRev: erneutes Lesen von Vorschau-Rolle (localStorage) nach View-as-Wechsel
  const appRole = useMemo(() => {
    void accessRev;
    return getEffectiveRole() || "mitarbeiter";
  }, [accessRev]);
  const showTechReadiness = hasRoleReal(["owner", "admin"]);
  const viewportWidth = useContentLayoutWidth();
  const isNarrow = viewportWidth < 900;
  const isTouchDevice = typeof window !== "undefined" && window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  const isMobile = viewportWidth <= 900 || isTouchDevice;
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarVisible, setSidebarVisible] = useState(() => {
    if (typeof window === "undefined") return true;
    return localStorage.getItem("kanzlei_sidebar_visible") !== "0";
  });
  const sidebarMinWidth = isNarrow ? 160 : 180;
  const sidebarMaxWidth = isNarrow
    ? Math.min(260, Math.max(150, Math.round(viewportWidth * 0.55)))
    : 360;
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const vd = typeof window !== "undefined" ? readContentLayoutWidth() : 900;
    const fallback = vd < 900 ? 150 : 220;
    if (typeof window === "undefined") return fallback;
    const stored = Number(localStorage.getItem("kanzlei_sidebar_width") || fallback);
    const initialMax = vd < 900
      ? Math.min(260, Math.max(150, Math.round(vd * 0.55)))
      : 360;
    const initialMin = vd < 900 ? 160 : 180;
    return clamp(Number.isFinite(stored) ? stored : fallback, initialMin, initialMax);
  });
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
  const [billingUsage, setBillingUsage] = useState(null);

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

  useEffect(() => {
    if (!isMobile) setMobileNavOpen(false);
  }, [isMobile]);

  useEffect(() => {
    try {
      localStorage.setItem("kanzlei_sidebar_visible", sidebarVisible ? "1" : "0");
    } catch {}
  }, [sidebarVisible]);

  useEffect(() => {
    if (!isMobile || !mobileNavOpen) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isMobile, mobileNavOpen]);

  useEffect(() => {
    if (!isMobile || !mobileNavOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setMobileNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isMobile, mobileNavOpen]);

  useEffect(() => {
    setSidebarWidth(prev => clamp(prev, sidebarMinWidth, sidebarMaxWidth));
  }, [sidebarMaxWidth, sidebarMinWidth]);

  useEffect(() => {
    localStorage.setItem("kanzlei_sidebar_width", String(Math.round(sidebarWidth)));
  }, [sidebarWidth]);

  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((body) => {
        const d = body?.data ?? body;
        if (!cancelled && d && typeof d === "object") setNavSettings(d);
      })
      .catch(() => {
        if (!cancelled) setNavSettings({});
      });
    return () => {
      cancelled = true;
    };
  }, [accessRev]);

  useEffect(() => {
    const h = () => setAccessRev((x) => x + 1);
    window.addEventListener("kanzlei-settings-changed", h);
    return () => window.removeEventListener("kanzlei-settings-changed", h);
  }, []);

  useEffect(() => {
    if (!hasNavTab(appRole, activeTab, navSettings)) {
      setActiveTab("dashboard");
    }
  }, [activeTab, appRole, navSettings]);

  const toast = useCallback((text, type="success") => {
    const id = Date.now() + Math.random();
    setToasts(p => [...p, { id, text, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000);
  }, []);

  const ladeAlles = useCallback(async (initial=false) => {
    try {
      if (initial) setLoading(true);
      const [m, k, h, e, r, b] = await Promise.allSettled([
        getMandanten(), getKpis(), getHeute(), getEmpfehlungen(), getSaasReadiness(), getBillingUsage(),
      ]);
      const mandantenRows = m.status === "fulfilled" ? normalisiereMandanten(m.value) : [];
      const kpiRows = k.status === "fulfilled" ? normalisiereKpis(k.value) : [];
      const mergedRows = mergeMandantenMitKpis(mandantenRows, kpiRows);
      setKpis((prev) => {
        const bothFailed = m.status !== "fulfilled" && k.status !== "fulfilled";
        if (bothFailed) return prev;
        return mergedRows;
      });
      if (h.status === "fulfilled") setHeute(extrahiereHeuteEintraege(h.value));
      if (e.status === "fulfilled") {
        const emp = Array.isArray(e.value) ? e.value : [];
        setEmpfehlungen(emp.filter(x => x?.mandant && (x?.empfehlungen?.length || x?.empfehlung)));
      }
      if (r.status === "fulfilled") {
        const rd = r.value?.data || r.value;
        setReadiness(rd || null);
      }
      if (b.status === "fulfilled") {
        const bd = b.value?.data || b.value;
        setBillingUsage(bd && typeof bd === "object" ? bd : null);
      } else {
        setBillingUsage(null);
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
      // Optimistic UI: neuer Mandant sofort in der Tabelle sichtbar,
      // auch wenn KPI-Neuberechnung oder Reload kurz verzögert ist.
      setKpis((prev) => {
        const name = String(data?.name || "").trim();
        if (!name) return prev;
        const exists = prev.some((x) => String(x?.mandant || x?.name || "").trim() === name);
        if (exists) return prev;
        return [
          {
            mandant: name,
            name,
            email: data?.email || "",
            telefon: data?.telefon || "",
            branche: data?.branche || "",
            umsatz: Number(data?.umsatz || 0),
            score: 0,
            status: "NORMAL",
            aufgaben_offen: 0,
            aufgaben_ueberfaellig: 0,
            tage_ohne_antwort: 0,
          },
          ...prev,
        ];
      });
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

  const contentPad = isMobile ? "14px 12px" : "28px 36px";

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
        return <RisikoDashboard kpis={kpis} heute={heute} onEmail={m => setEmailModal(m)} onTab={setActiveTab} onRefresh={ladeAlles} isMobile={isMobile} />;

      // ── MANDANTEN ──────────────────────────────────────────
      case "mandanten":
        return (
          <div style={{ padding:contentPad, flex:1, overflowY:"auto" }}>
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
              isMobile={isMobile}
            />
          </div>
        );

      // ── AUFGABEN ───────────────────────────────────────────
      case "aufgaben":
        return <AufgabenSeite kpis={kpis} heute={heute} onRefresh={ladeAlles} isMobile={isMobile} />;

      // ── KI-INSIGHTS ────────────────────────────────────────
      case "empfehlungen":
        return (
          <div style={{ padding:contentPad, flex:1, overflowY:"auto" }}>
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
          <div style={{ padding:contentPad, flex:1, overflowY:"auto" }}>
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
    <div style={{ display:"flex", minHeight:"100dvh", flexDirection: isMobile ? "column" : "row",
                  maxWidth:"100%", minWidth:0 }}>
      {(isMobile || sidebarVisible) ? (
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          kpis={kpis}
          width={sidebarWidth}
          setWidth={setSidebarWidth}
          minWidth={sidebarMinWidth}
          maxWidth={sidebarMaxWidth}
          role={appRole}
          navSettings={navSettings}
          footerAdmin={hasRoleReal(["owner", "admin"])}
          isMobile={isMobile}
          mobileOpen={mobileNavOpen}
          onCloseMobile={() => setMobileNavOpen(false)}
          onOpenMobile={() => setMobileNavOpen(true)}
          onDesktopCollapse={!isMobile ? () => setSidebarVisible(false) : undefined}
        />
      ) : null}
      <main style={{
        flex:1, display:"flex", flexDirection:"column",
        background:"var(--bg)", minWidth:0,
        width: isMobile ? "100%" : undefined,
        paddingBottom: isMobile ? "max(12px, env(safe-area-inset-bottom))" : undefined,
      }}>
        {isMobile ? (
          <header style={{
            position: "sticky",
            top: 0,
            zIndex: 45,
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "10px max(12px, env(safe-area-inset-right)) 10px max(12px, env(safe-area-inset-left))",
            paddingTop: "max(10px, env(safe-area-inset-top))",
            background: "var(--header-bg)",
            backdropFilter: "blur(8px)",
            borderBottom: "1px solid var(--border)",
            flexShrink: 0,
            boxSizing: "border-box",
            width: "100%",
            maxWidth: "100%",
          }}>
            <div style={{ flex: 1, minWidth: 0, fontWeight: 700, fontSize: 16, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {MOBILE_TAB_TITLE[activeTab] || "Kanzlei AI"}
            </div>
          </header>
        ) : null}
        {((showTechReadiness && readiness) || billingUsage?.plan) && (
          <div style={{
            position:"sticky",
            top:isMobile ? 64 : 0,
            zIndex:50,
            background:"var(--header-bg)",
            backdropFilter:"blur(8px)",
            borderBottom:"1px solid var(--border)",
            padding:isMobile
              ? "8px max(12px, env(safe-area-inset-right)) 8px max(12px, env(safe-area-inset-left))"
              : "10px 18px",
            display:"flex",
            flexDirection:"column",
            gap:isMobile ? 6 : 8,
          }}>
            {readiness && showTechReadiness ? (
              <div style={{ display:"flex", flexWrap:"wrap", alignItems:"center", gap:isMobile ? 8 : 16 }}>
                <div style={{ fontSize:12, color:"var(--text3)", textTransform:"uppercase", letterSpacing:"0.08em" }} title="Technischer Überblick (nur Administrator)">
                  Systemstatus
                </div>
                <div style={{ fontSize:15, fontWeight:700, color: (readiness.readiness_score||0)>=80?"var(--green)":(readiness.readiness_score||0)>=60?"var(--orange)":"var(--red)" }}>
                  {readiness.readiness_score ?? 0}
                </div>
                <div style={{ flex:1, minWidth:isMobile ? 90 : undefined, maxWidth:isMobile ? "none" : 280, height:5, background:"var(--bg3)", borderRadius:4, overflow:"hidden" }}>
                  <div style={{
                    width:`${Math.max(0, Math.min(100, readiness.readiness_score || 0))}%`,
                    height:"100%",
                    background:(readiness.readiness_score||0)>=80?"var(--green)":(readiness.readiness_score||0)>=60?"var(--orange)":"var(--red)",
                  }} />
                </div>
                {isMobile ? (
                  <div style={{ width: "100%", display: "flex", gap: 8, fontSize: 11, color: "var(--text2)", flexWrap: "wrap", alignItems: "center" }}>
                    <span>Compliance: {readiness.compliance?.percent ?? 0}%</span>
                    <span>Queue: {readiness.health?.email_outbox_dead_24h ?? 0}</span>
                    <ThemeQuickSwitch compact />
                  </div>
                ) : (
                  <div style={{ display:"flex", gap:12, marginLeft:"auto", fontSize:12, color:"var(--text2)", flexWrap:"wrap", alignItems:"center" }}>
                    <ViewAsControls onChanged={() => setAccessRev((x) => x + 1)} />
                    <ThemeQuickSwitch />
                    <span>E-Mail-Queue (24h): {readiness.health?.email_outbox_dead_24h ?? 0}</span>
                    <span>Webhook-Fehler (24h): {readiness.health?.webhook_failures_24h ?? 0}</span>
                    <span>API-Schlüssel: {readiness.health?.api_keys_aktiv ?? 0}</span>
                    <span>Compliance: {readiness.compliance?.percent ?? 0}%</span>
                  </div>
                )}
              </div>
            ) : null}
            {billingUsage?.plan ? (
              <div style={{ display:"flex", alignItems:"center", gap:isMobile ? 6 : 10, fontSize:isMobile ? 11 : 12, color:"var(--text2)", flexWrap:"wrap" }}>
                {(!readiness || !showTechReadiness) ? (
                  <>
                    {!isMobile ? <ViewAsControls onChanged={() => setAccessRev((x) => x + 1)} /> : null}
                    <ThemeQuickSwitch compact={isMobile} />
                  </>
                ) : null}
                <span style={{ color:"var(--text3)", textTransform:"uppercase", letterSpacing:"0.06em" }}>Plan</span>
                <span style={{ fontWeight:600, color:"var(--accent)" }}>{billingUsage.plan}</span>
                {billingUsage.quota?.overall === "warning" || billingUsage.quota?.overall === "critical" ? (
                  <span style={{ color: "var(--orange)" }}>
                    Hohe Auslastung — bei Bedarf Tarif erweitern oder Administrator informieren.
                  </span>
                ) : null}
                {billingUsage.quota?.overall === "limit" ? (
                  <span style={{ color: "var(--red)" }}>Tageslimit erreicht — Automation eingeschränkt.</span>
                ) : null}
                {billingUsage.customer_success?.upgrade_url ? (
                  <a href={billingUsage.customer_success.upgrade_url} target="_blank" rel="noopener noreferrer" style={{ color:"var(--blue)" }}>
                    Upgrade / Kontakt
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
        {renderContent()}
      </main>
      {emailModal && (
        <EmailModal name={emailModal}
                    onClose={() => setEmailModal(null)}
                    onSend={handleSendEmail} />
      )}
      {((!isMobile && !sidebarVisible) || (isMobile && !mobileNavOpen)) ? (
        <button
          type="button"
          onClick={() => {
            if (isMobile) setMobileNavOpen((v) => !v);
            else setSidebarVisible(true);
          }}
          aria-label={isMobile ? (mobileNavOpen ? "Menü ausblenden" : "Menü einblenden") : "Seitenleiste einblenden"}
          title={isMobile ? (mobileNavOpen ? "Menü ausblenden" : "Menü einblenden") : "Seitenleiste einblenden"}
          style={{
            position: "fixed",
            top: "max(12px, env(safe-area-inset-top))",
            left: "max(12px, env(safe-area-inset-left))",
            zIndex: 99999,
            border: "1px solid var(--border2)",
            background: "color-mix(in srgb, var(--bg3) 92%, var(--accent) 8%)",
            color: "var(--text)",
            borderRadius: 12,
            width: 46,
            height: 46,
            padding: 0,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 20,
            fontWeight: 700,
            lineHeight: 1,
            cursor: "pointer",
            boxShadow: "var(--shadow-elev)",
            touchAction: "manipulation",
          }}
        >
          <span aria-hidden="true">{isMobile ? (mobileNavOpen ? "◀" : "▶") : "▶"}</span>
        </button>
      ) : null}
      <ToastContainer toasts={toasts} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// ROOT APP — Login + Router
// ═══════════════════════════════════════════════════════════

const API_ROOT = process.env.REACT_APP_API_URL || "/api";

function RequireSession({ children }) {
  try {
    const t = typeof localStorage !== "undefined" && (
      localStorage.getItem("kanzlei_token") || localStorage.getItem("token")
    );
    if (!t) return <Navigate to="/login" replace />;
  } catch {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RequireRole({ roles, children }) {
  if (!hasRoleReal(roles)) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const [loggedIn,  setLoggedIn]  = useState(false);
  const [authAktiv, setAuthAktiv] = useState(false);
  const [checking,  setChecking]  = useState(true);
  const [billingAlert, setBillingAlert] = useState(null);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [billingUsage, setBillingUsage] = useState(null);
  const [upgradeBusy, setUpgradeBusy] = useState(false);
  const [upgradeErr, setUpgradeErr] = useState("");
  const [ctaVariant, setCtaVariant] = useState("A");

  const getAttributionMeta = () => {
    try {
      const p = new URLSearchParams(window.location.search || "");
      const fromUrl = {
        utm_source: p.get("utm_source") || "",
        utm_medium: p.get("utm_medium") || "",
        utm_campaign: p.get("utm_campaign") || "",
      };
      const key = "billing_first_touch_utm_v1";
      const stored = JSON.parse(localStorage.getItem(key) || "{}");
      const merged = {
        utm_source: fromUrl.utm_source || stored.utm_source || "",
        utm_medium: fromUrl.utm_medium || stored.utm_medium || "",
        utm_campaign: fromUrl.utm_campaign || stored.utm_campaign || "",
      };
      if (fromUrl.utm_source || fromUrl.utm_medium || fromUrl.utm_campaign) {
        localStorage.setItem(key, JSON.stringify(merged));
      }
      return { ...merged, referrer: document.referrer || "" };
    } catch {
      return {};
    }
  };

  useEffect(() => {
    const verifySession = async () => {
      const token =
        (typeof localStorage !== "undefined" &&
          (localStorage.getItem("kanzlei_token") || localStorage.getItem("token"))) || "";
      if (!token) {
        setLoggedIn(false);
        return;
      }
      try {
        const meRes = await fetch(`${API_ROOT}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!meRes.ok) {
          // Nur echte Auth-Fehler dürfen die Session verwerfen.
          // Transiente Fehler (429/5xx/Netzwerk) sollen nicht zum Logout-Loop führen.
          if (meRes.status === 401 || meRes.status === 403) {
            throw new Error("session invalid");
          }
          setLoggedIn(true);
          return;
        }
        setLoggedIn(true);
      } catch {
        // Bei temporären Connectivity-Problemen nicht sofort ausloggen.
        // Nur löschen, wenn die Session wirklich ungültig ist.
        try {
          const current =
            localStorage.getItem("kanzlei_token") || localStorage.getItem("token") || "";
          if (!current) {
            setLoggedIn(false);
            return;
          }
        } catch {}
        setLoggedIn(true);
      }
    };

    fetch(`${API_ROOT}/auth/setup-status`)
      .then(r => r.json())
      .then(d => { if (d.eingerichtet) setAuthAktiv(true); })
      .catch(() => {})
      .finally(async () => {
        await verifySession();
        setChecking(false);
      });
  }, []);

  useEffect(() => {
    try {
      const key = "billing_cta_variant_v1";
      const stored = localStorage.getItem(key);
      if (stored === "A" || stored === "B") {
        setCtaVariant(stored);
      } else {
        const v = Math.random() < 0.5 ? "A" : "B";
        localStorage.setItem(key, v);
        setCtaVariant(v);
      }
    } catch {}
  }, []);

  useEffect(() => {
    const onPaywall = (ev) => {
      const d = ev?.detail || {};
      const offer = d.upgrade_offer || {};
      try {
        localStorage.setItem("billing_nudge_last_ts", String(Date.now()));
      } catch {}
      setBillingAlert({
        level: "critical",
        title: "Plan-Limit erreicht",
        text:
          offer.message ||
          d.hint ||
          "Ein Nutzungs-Limit wurde erreicht. Upgrade verhindert Unterbrechungen.",
        upgradeUrl: d.upgrade_url || offer.upgrade_url || "",
        recommendedPlan: offer.recommended_plan || "professional",
      });
      try { trackBillingFunnelEvent("paywall_402", { source: "apiFetch", ...getAttributionMeta() }); } catch {}
    };
    const onQuotaWarning = (ev) => {
      const d = ev?.detail || {};
      const status = d.status === "critical" ? "critical" : "warning";
      // Reminder-Kampagne: warnings höchstens alle 6 Stunden, critical immer sofort.
      if (status !== "critical") {
        try {
          const last = Number(localStorage.getItem("billing_nudge_last_ts") || "0");
          if (last && Date.now() - last < 6 * 60 * 60 * 1000) return;
          localStorage.setItem("billing_nudge_last_ts", String(Date.now()));
        } catch {}
      }
      setBillingAlert({
        level: status,
        title: status === "critical" ? "Kritische Auslastung" : "Plan-Auslastung steigt",
        text: `${d.metric || "usage"} bei ${d.used || 0}/${d.limit || 0} (${d.percent || 0}%).`,
        upgradeUrl: d.upgrade_url || "",
        recommendedPlan: d.recommended_plan || "professional",
      });
    };
    window.addEventListener("billing:paywall", onPaywall);
    window.addEventListener("billing:quota-warning", onQuotaWarning);
    return () => {
      window.removeEventListener("billing:paywall", onPaywall);
      window.removeEventListener("billing:quota-warning", onQuotaWarning);
    };
  }, []);

  const openUpgradeModal = async () => {
    setShowUpgradeModal(true);
    setUpgradeErr("");
    try {
      try { trackBillingFunnelEvent("cta_view", { variant: ctaVariant, ...getAttributionMeta() }); } catch {}
      const usage = await getBillingUsage();
      const payload = usage?.data || usage || {};
      setBillingUsage(payload);
    } catch (e) {
      setUpgradeErr(e?.message || "Billing-Infos konnten nicht geladen werden.");
    }
  };

  const startCheckout = async (targetPlan = "professional") => {
    setUpgradeErr("");
    setUpgradeBusy(true);
    try {
      try { trackBillingFunnelEvent("cta_click", { variant: ctaVariant, target_plan: targetPlan, ...getAttributionMeta() }); } catch {}
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const success = `${origin}/settings?billing=upgrade_ok`;
      const cancel = `${origin}/settings?billing=upgrade_cancel`;
      const resp = await createStripeCheckoutSession({
        success_url: success,
        cancel_url: cancel,
        target_plan: targetPlan,
      });
      const data = resp?.data || resp || {};
      if (data?.url) {
        try { trackBillingFunnelEvent("checkout_start", { target_plan: targetPlan, ...getAttributionMeta() }); } catch {}
        window.location.href = data.url;
        return;
      }
      setUpgradeErr("Checkout-URL fehlt. Stripe-Konfiguration prüfen.");
    } catch (e) {
      setUpgradeErr(e?.message || "Checkout konnte nicht gestartet werden.");
    } finally {
      setUpgradeBusy(false);
    }
  };

  const comparePlansLabel = ctaVariant === "B" ? "Jetzt Umsatz sichern" : "Pläne vergleichen";
  const quickUpgradeLabel = ctaVariant === "B" ? "Jetzt upgraden" : "Upgrade";

  useEffect(() => {
    const syncLoginState = () => {
      try {
        setLoggedIn(!!(localStorage.getItem("kanzlei_token") || localStorage.getItem("token")));
      } catch {
        setLoggedIn(false);
      }
    };
    window.addEventListener("storage", syncLoginState);
    const i = setInterval(syncLoginState, 4000);
    return () => {
      window.removeEventListener("storage", syncLoginState);
      clearInterval(i);
    };
  }, []);

  useEffect(() => {
    // Checkout-Rückkehr aus Stripe auswerten.
    try {
      const p = new URLSearchParams(window.location.search || "");
      const billing = (p.get("billing") || "").toLowerCase();
      if (billing === "upgrade_ok") {
        setBillingAlert({
          level: "warning",
          title: "Upgrade abgeschlossen",
          text: "Danke! Ihr Abo wurde aktualisiert. Premium-Features sind jetzt aktiv.",
          upgradeUrl: "",
          recommendedPlan: "",
        });
        try { trackBillingFunnelEvent("checkout_success", { source: "return_url", ...getAttributionMeta() }); } catch {}
      } else if (billing === "upgrade_cancel") {
        try { trackBillingFunnelEvent("checkout_cancel", { source: "return_url", ...getAttributionMeta() }); } catch {}
      }
    } catch {}
  }, []);

  if (checking) return (
    <ThemeProvider>
      <FontLoader />
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
                    height:"100vh", background:"var(--bg)" }}>
        <Spinner size={36} />
      </div>
    </ThemeProvider>
  );

  return (
    <ThemeProvider>
      <FontLoader />
      {loggedIn && billingAlert ? (
        <div
          style={{
            position: "fixed",
            top: 10,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 9999,
            minWidth: 360,
            maxWidth: 760,
            background: billingAlert.level === "critical"
              ? "color-mix(in srgb, var(--red) 78%, black)"
              : "color-mix(in srgb, var(--orange) 72%, black)",
            color: "color-mix(in srgb, white 97%, var(--accent))",
            border: "1px solid color-mix(in srgb, white 32%, transparent)",
            borderRadius: 10,
            padding: "10px 12px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            boxShadow: "var(--shadow-elev)",
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{billingAlert.title}</div>
            <div style={{ fontSize: 12, opacity: 0.95 }}>{billingAlert.text}</div>
          </div>
          {billingAlert.upgradeUrl ? (
            <a
              href={billingAlert.upgradeUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                color: "color-mix(in srgb, white 97%, var(--accent))",
                fontSize: 12,
                fontWeight: 700,
                textDecoration: "underline",
                whiteSpace: "nowrap",
              }}
            >
              {quickUpgradeLabel}
            </a>
          ) : null}
          <button
            onClick={openUpgradeModal}
            style={{
              border: "1px solid color-mix(in srgb, white 45%, transparent)",
              background: "transparent",
              color: "color-mix(in srgb, white 97%, var(--accent))",
              borderRadius: 8,
              fontSize: 12,
              padding: "6px 10px",
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            {comparePlansLabel}
          </button>
          <button
            onClick={() => setBillingAlert(null)}
            style={{
              border: "none",
              background: "transparent",
              color: "color-mix(in srgb, white 97%, var(--accent))",
              fontSize: 16,
              cursor: "pointer",
              lineHeight: 1,
            }}
            aria-label="Hinweis schließen"
          >
            ×
          </button>
        </div>
      ) : null}
      {loggedIn && showUpgradeModal ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 10000,
            background: "var(--overlay-scrim)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            style={{
              width: "min(860px, 95vw)",
              maxHeight: "90vh",
              overflow: "auto",
              background: "var(--bg3)",
              color: "var(--text)",
              borderRadius: 14,
              border: "1px solid var(--border2)",
              padding: 18,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>Planvergleich & Upgrade</div>
                <div style={{ fontSize: 12, color: "var(--text3)" }}>
                  Empfohlen: {(billingAlert?.recommendedPlan || "professional").toUpperCase()}
                </div>
              </div>
              <button
                onClick={() => setShowUpgradeModal(false)}
                style={{ border: "none", background: "transparent", color: "var(--text2)", fontSize: 20, cursor: "pointer" }}
              >
                ×
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 14 }}>
              {[
                { id: "starter", price: "99€", text: "Ideal zum Start" },
                { id: "professional", price: "399€", text: "Empfohlen für Wachstum" },
                { id: "enterprise", price: "1299€", text: "Skalierung mit Team & SLA" },
              ].map((p) => {
                const recommended = (billingAlert?.recommendedPlan || "").toLowerCase() === p.id;
                return (
                  <div
                    key={p.id}
                    style={{
                      border: recommended
                        ? "1px solid color-mix(in srgb, var(--accent) 65%, transparent)"
                        : "1px solid var(--border)",
                      borderRadius: 10,
                      padding: 12,
                      background: recommended
                        ? "color-mix(in srgb, var(--accent) 14%, var(--bg2))"
                        : "var(--bg2)",
                    }}
                  >
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{p.id.toUpperCase()}</div>
                    <div style={{ fontSize: 24, fontWeight: 800, margin: "4px 0" }}>{p.price}</div>
                    <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 10 }}>{p.text}</div>
                    {p.id !== "starter" ? (
                      <button
                        onClick={() => startCheckout(p.id)}
                        disabled={upgradeBusy}
                        style={{
                          width: "100%",
                          border: "none",
                          borderRadius: 8,
                          padding: "8px 10px",
                          cursor: upgradeBusy ? "wait" : "pointer",
                          background: recommended ? "var(--accent)" : "var(--blue)",
                          color: recommended ? "var(--on-accent)" : "var(--on-blue)",
                          fontWeight: 700,
                        }}
                      >
                        {upgradeBusy ? "…" : `Auf ${p.id} upgraden`}
                      </button>
                    ) : (
                      <div style={{ fontSize: 12, color: "var(--text2)" }}>Aktueller Basisplan</div>
                    )}
                  </div>
                );
              })}
            </div>

            {billingUsage ? (
              <div style={{ fontSize: 12, color: "var(--text2)" }}>
                Aktueller Plan: <b>{String(billingUsage.plan || "starter").toUpperCase()}</b>
                {" · "}
                Auslastung:{" "}
                <b>
                  {(() => {
                    const q = String(billingUsage?.quota?.overall || "ok").toLowerCase();
                    if (q === "ok") return "Normal";
                    if (q === "limit") return "Am Tageslimit";
                    if (q === "warning" || q === "critical") return "Erhöht";
                    return "—";
                  })()}
                </b>
              </div>
            ) : null}
            {upgradeErr ? <div style={{ marginTop: 8, fontSize: 12, color: "var(--red)" }}>{upgradeErr}</div> : null}
          </div>
        </div>
      ) : null}
      <Router>
        <Routes>
          <Route path="/register-email" element={<Navigate to="/register" replace />} />
          <Route path="/register" element={<Register />} />
          <Route path="/login-email" element={<Navigate to="/login" replace />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          {authAktiv && !loggedIn ? (
            <Route path="*" element={<Login onLogin={() => setLoggedIn(true)} />} />
          ) : (
            <>
              <Route path="/login" element={<Login onLogin={() => setLoggedIn(true)} />} />
              <Route
                path="/"
                element={
                  loggedIn ? (
                    <RequireSession><AppInner /></RequireSession>
                  ) : (
                    <Login onLogin={() => setLoggedIn(true)} />
                  )
                }
              />
              <Route path="/mandant/:name" element={<RequireSession><MandantDetailPage /></RequireSession>} />
              <Route
                path="/admin/users"
                element={<RequireSession><RequireRole roles={["owner", "admin"]}><AdminUsers /></RequireRole></RequireSession>}
              />
              <Route
                path="/users"
                element={<RequireSession><RequireRole roles={["owner", "admin"]}><TeamUsers /></RequireRole></RequireSession>}
              />
              <Route path="/profile" element={<RequireSession><Profile /></RequireSession>} />
            </>
          )}
        </Routes>
      </Router>
    </ThemeProvider>
  );
}