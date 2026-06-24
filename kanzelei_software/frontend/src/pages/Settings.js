// ============================================================
// Kanzlei Automation — Einstellungen
// Datei: src/pages/Settings.js
//
// 6 Kategorien = 6 Profitabilitäts-Hebel:
//   1. KI-Konfiguration       — Autonomiegrad + Lernkurve
//   2. Workflow-Designer       — Fristen-Radar + Eskalation
//   3. Mandanten-Self-Service  — Sichtbarkeit + Validierung
//   4. Monetarisierung         — Billing + Value-Pricing
//   5. Compliance & Security   — Rollen + GoBD + DSGVO
//   6. Schnittstellen          — Bank-Feeds + Drittsysteme
// ============================================================

import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useContentLayoutWidth } from "../useContentLayoutWidth";
import {
  getSettings,
  unwrapSettingsPayload,
  updateSetting,
  resetSettings,
  getSystemInfo,
  getSystemExport,
  getSaasReadiness,
  getBillingMetrics,
  getBillingFunnel,
  getBillingWeeklyReport,
  sendBillingWeeklyReport,
  getKpis,
  getSettingsSuggestions,
  applySettingsSuggestion,
  getStripePublicConfig,
  createStripeCheckoutSession,
  createStripePortalSession,
  setPilotBaseline,
  testTenantSmtp,
  readAuthed,
  getM365Status,
  startM365Connect,
  disconnectM365,
  getM365CalendarPreview,
  getM365MailPreview,
  getBetreuerMatrix,
  updateMandantAPI,
  bulkAssignBetreuer,
} from "../api";
import PermissionGate, { hasRoleReal } from "../components/PermissionGate";
import {
  NAV_TAB_IDS,
  NAV_TAB_LABELS,
  NAV_SETTINGS_GROUPS,
  ROLE_NAV_PRESETS,
  FEATURE_PERMISSION_KEYS,
} from "../navAccess";
import { ThemeQuickSwitch } from "../theme";

const NAV_TOGGLE_IDS = NAV_TAB_IDS.filter((id) => !["ki", "belege"].includes(id));

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');`;

// ─── Tabs (Produktfokus) ───────────────────────────────────────
const TABS = [
  { id: "email", label: "E-Mail & Versand", icon: "✉", badge: "Start" },
  { id: "automation", label: "Automation & Eskalation", icon: "⚙" },
  { id: "portal", label: "Mandanten-Portal", icon: "📱" },
  { id: "kanzlei", label: "Kanzlei-Daten", icon: "🏢" },
  { id: "team", label: "Team & Berechtigungen", icon: "🛡", adminOnly: true },
  { id: "integrationen", label: "Integrationen", icon: "🔌", adminOnly: true },
  { id: "erweitert", label: "Erweitert", icon: "⋯", adminOnly: true },
];

const ADMIN_TABS = new Set(["team", "integrationen", "erweitert"]);

// ─── Primitives ───────────────────────────────────────────────
const Btn = ({children,onClick,variant="ghost",size="md",loading=false,disabled=false,style={}}) => {
  const vs = {
    primary:{background:"var(--accent)",color:"var(--on-accent)",border:"none"},
    ghost:{background:"transparent",color:"var(--text2)",border:"1px solid var(--border2)"},
    subtle:{background:"var(--bg3)",color:"var(--text2)",border:"1px solid var(--border)"},
    success:{background:"color-mix(in srgb, var(--green) 14%, var(--bg3))",color:"var(--green)",border:"1px solid color-mix(in srgb, var(--green) 22%, transparent)"},
    danger:{background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",color:"var(--red)",border:"1px solid color-mix(in srgb, var(--red) 22%, transparent)"},
  };
  const ss={xs:"4px 9px",sm:"6px 13px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,
    padding:ss[size],fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading||disabled?"not-allowed":"pointer",
    opacity:loading||disabled?0.5:1,transition:"all 0.15s",
    fontFamily:"var(--font-body)",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",
      border:"2px solid currentColor",borderTopColor:"transparent",
      animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

const Toggle = ({value,onChange,disabled=false}) => (
  <div onClick={!disabled?()=>onChange(!value):undefined} style={{
    width:44,height:24,borderRadius:12,cursor:disabled?"not-allowed":"pointer",
    background:value?"var(--accent)":"var(--bg3)",
    border:`1px solid ${value?"var(--accent)":"var(--border2)"}`,
    position:"relative",transition:"all 0.2s",
    opacity:disabled?0.5:1,flexShrink:0,
  }}>
    <div style={{
      position:"absolute",top:2,left:value?22:2,
      width:18,height:18,borderRadius:"50%",
      background:value?"var(--bg)":"var(--text3)",transition:"left 0.2s",
    }}/>
  </div>
);

// Schieberegler
const Slider = ({value,onChange,min=0,max=100,step=1,label,suffix="%",color="var(--accent)"}) => (
  <div>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:6}}>
      <span style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.06em"}}>
        {label}
      </span>
      <span style={{fontSize:14,fontWeight:700,color}}>{value}{suffix}</span>
    </div>
    <div style={{position:"relative",height:6,background:"var(--bg3)",borderRadius:4}}>
      <div style={{
        position:"absolute",left:0,top:0,height:"100%",borderRadius:4,
        width:`${(value-min)/(max-min)*100}%`,
        background:`linear-gradient(90deg, color-mix(in srgb, ${color} 55%, var(--bg3)), ${color})`,
      }}/>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e=>onChange(Number(e.target.value))}
        style={{
          position:"absolute",top:"50%",transform:"translateY(-50%)",
          left:0,right:0,width:"100%",
          opacity:0,cursor:"pointer",height:20,margin:0,
        }}/>
    </div>
    <div style={{display:"flex",justifyContent:"space-between",marginTop:3,
                  fontSize:10,color:"var(--text3)"}}>
      <span>{min}{suffix}</span><span>{max}{suffix}</span>
    </div>
  </div>
);

// Einstellungs-Zeile
const Row = ({label,description,children,locked=false}) => (
  <div style={{
    display:"flex",justifyContent:"space-between",alignItems:"flex-start",
    flexWrap:"wrap",gap:12,
    padding:"13px 0",borderBottom:"1px solid var(--border)",
    opacity:locked?0.6:1,
  }}>
    <div style={{flex:"1 1 200px",minWidth:0,paddingRight:12}}>
      <div style={{fontSize:14,fontWeight:500,color:"var(--text)",display:"flex",alignItems:"center",gap:6}}>
        {label}
        {locked&&<span style={{fontSize:10,padding:"1px 6px",borderRadius:8,
          background:"color-mix(in srgb, var(--text3) 18%, transparent)",color:"var(--text3)",fontWeight:400}}>FESTGESCHRIEBEN</span>}
      </div>
      {description&&<div style={{fontSize:12,color:"var(--text3)",marginTop:3,lineHeight:1.5}}>
        {description}
      </div>}
    </div>
    <div style={{flexShrink:0,marginLeft:"auto",display:"flex",justifyContent:"flex-end"}}>{children}</div>
  </div>
);

const SectionTitle = ({children}) => (
  <div style={{
    fontFamily:"var(--font-head)",fontSize:17,color:"var(--text)",
    marginBottom:16,marginTop:8,paddingBottom:10,
    borderBottom:"1px solid var(--border)",
  }}>{children}</div>
);

// ═══════════════════════════════════════════════════════════
// 1. KI-KONFIGURATION
// ═══════════════════════════════════════════════════════════

const KITab = ({s, save, kpiStats}) => {
  const [autonomie, setAutonomie] = useState(s.ki_autonomie_grad ?? 75);
  const [autoKonfidenz, setAutoKonfidenz] = useState(s.ki_auto_buchen_ab_konfidenz ?? 92);
  const [reviewKonfidenz, setReviewKonfidenz] = useState(s.ki_review_ab_konfidenz ?? 75);
  const [anomalieBetrag] = useState(s.ki_anomalie_betrag_euro ?? 500);
  const stundensatz = Number(s.stundensatz || 150) || 150;
  const umsatzJahr = Number(kpiStats?.gesamtUmsatz || 0);
  const mandanten = Number(kpiStats?.mandanten || 0);
  const offeneAufgaben = Number(kpiStats?.offeneAufgaben || 0);
  const kritischeAufgaben = Number(kpiStats?.kritischeAufgaben || 0);
  const fehlendeDokumente = Number(kpiStats?.fehlendeDokumente || 0);
  const kontaktStille = Number(kpiStats?.kontaktStille || 0);

  // V2: Basisstunden aus Umsatz + Lastfaktor aus operativer Komplexität
  const baselineHoursRaw = umsatzJahr > 0
    ? ((umsatzJahr / 12) / stundensatz) * 0.07
    : Math.max(18, mandanten * 3.5 || 35);
  const baselineHours = Math.max(10, Math.min(280, baselineHoursRaw));
  const operationsFactor = Math.min(
    2.0,
    1 +
      offeneAufgaben * 0.015 +
      kritischeAufgaben * 0.05 +
      fehlendeDokumente * 0.012 +
      kontaktStille * 0.01
  );
  const automationFactor = Math.max(0.08, Math.min(1, (autonomie / 100) * (autoKonfidenz / 100)));
  const stundenGespart = baselineHours * operationsFactor * automationFactor;
  const euroGespart = stundenGespart * stundensatz;

  return (
    <div>
      <div style={{background:"linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, transparent), color-mix(in srgb, var(--blue) 4%, transparent))",
        border:"1px solid color-mix(in srgb, var(--accent) 22%, transparent)",borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:"var(--accent)",fontSize:14,marginBottom:4}}>
          Das Herzstück — KI-Autonomiegrad bestimmt Lohnkosteneinsparung
        </div>
        <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.6}}>
          Bei 92% Konfidenz-Schwellenwert: ~70% aller Buchungen vollautomatisch.
          Spart ca. 4-6 Stunden täglich pro Kanzlei.
        </div>
      </div>

      <SectionTitle>Autonomie & Konfidenz</SectionTitle>

      <div style={{marginBottom:20}}>
        <Slider label="KI-Autonomiegrad" value={autonomie}
          onChange={v=>{setAutonomie(v); save("ki_autonomie_grad",v);}}
          color={autonomie>=80?"var(--green)":autonomie>=50?"var(--orange)":"var(--text2)"}
          suffix="%" min={0} max={100} step={5} />
        <div style={{fontSize:12,color:"var(--text3)",marginTop:6,textAlign:"center"}}>
          {autonomie<=20?"Vollständig manuell — alle Buchungen werden geprüft":
           autonomie<=50?"Halbautomatisch — KI schlägt vor, Mensch entscheidet":
           autonomie<=80?"Hochautomatisch — KI bucht, Ausnahmen werden gemeldet":
           "Vollautonom — KI bucht bei hoher Sicherheit ohne Review"}
        </div>
        {/* Echtzeit-Ersparnis-Rechner */}
        {autonomie > 30 && (
          <div style={{
            marginTop:12, background:"color-mix(in srgb, var(--green) 8%, var(--bg3))",
            border:"1px solid color-mix(in srgb, var(--green) 20%, transparent)", borderRadius:10,
            padding:"10px 14px", display:"grid",
            gridTemplateColumns:"1fr 1fr 1fr", gap:10,
          }}>
            {[
              {l:"Auto-Buchungen", v:`~${Math.round(autonomie*0.7)}%`, c:"var(--green)"},
              {l:"Stunden/Monat gespart", v:`~${stundenGespart.toFixed(1)}h`, c:"var(--blue)"},
              {l:"€/Monat gespart", v:`~€${Math.round(euroGespart).toLocaleString("de")}`, c:"var(--accent)"},
            ].map((x,i)=>(
              <div key={i} style={{textAlign:"center"}}>
                <div style={{fontSize:11,color:"var(--text3)",marginBottom:3}}>{x.l}</div>
                <div style={{fontSize:16,fontWeight:700,color:x.c,
                  fontFamily:"var(--font-head)"}}>{x.v}</div>
              </div>
            ))}
          </div>
        )}
        <div style={{fontSize:11,color:"var(--text3)",marginTop:8,lineHeight:1.5}}>
          Berechnungsbasis: {umsatzJahr > 0
            ? `Mandanten-Umsatz gesamt ${Math.round(umsatzJahr).toLocaleString("de")} €/Jahr`
            : "Fallback auf Mandantenanzahl (keine Umsatzdaten verfügbar)"} ·
          Stundensatz {stundensatz.toLocaleString("de")} €/h ·
          Lastfaktor {operationsFactor.toFixed(2)}x (Aufgaben/Dokumente/Fristdruck).
        </div>
      </div>

      <Row label="Automatisch buchen ab Konfidenz"
           description="Bei diesem Wert bucht die KI ohne menschliche Prüfung">
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <div style={{width:160}}>
            <Slider label="" value={autoKonfidenz}
              onChange={v=>{setAutoKonfidenz(v); save("ki_auto_buchen_ab_konfidenz",v);}}
              color="var(--green)" suffix="%" min={75} max={99} step={1}/>
          </div>
        </div>
      </Row>

      <Row label="Review empfohlen ab Konfidenz"
           description="Zwischen diesem Wert und dem Auto-Wert: kurzer menschlicher Check">
        <div style={{width:160}}>
          <Slider label="" value={reviewKonfidenz}
            onChange={v=>{setReviewKonfidenz(v); save("ki_review_ab_konfidenz",v);}}
            color="var(--orange)" suffix="%" min={50} max={autoKonfidenz-1} step={1}/>
        </div>
      </Row>

      <SectionTitle>Lernkurve & Datenteilung</SectionTitle>

      <Row label="Kanzleiübergreifendes Lernen"
           description="Darf die KI von Mandant A lernen, um Mandant B schneller zu buchen? Erhöht die Qualität über alle Mandanten hinweg — nur wenn Sie das wünschen.">
        <Toggle value={s.ki_lernen_kanzleiweit??true}
          onChange={v=>save("ki_lernen_kanzleiweit",v)}/>
      </Row>

      <Row label="Anonymisiertes Aggregat-Lernen"
           description="KI lernt aus aggregierten, anonymisierten Mustern aller Kanzleien. Kein Mandant ist identifizierbar. Stärkstes Lern-Signal.">
        <Toggle value={s.ki_lernen_anonym??true}
          onChange={v=>save("ki_lernen_anonym",v)}/>
      </Row>

      <SectionTitle>Anomalie-Schwellenwerte</SectionTitle>

      <Row label="Alarm ab Betrag (€)"
           description="Ab diesem Betrag wird ein Mitarbeiter alarmiert — egal wie hoch die Konfidenz">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={anomalieBetrag} min={0}
            onBlur={e=>save("ki_anomalie_betrag_euro",parseInt(e.target.value))}
            style={{width:90,background:"var(--bg)",border:`1px solid var(--border2)`,
              borderRadius:8,color:"var(--text)",padding:"7px 10px",fontSize:14,
              textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>€</span>
        </div>
      </Row>

      <Row label="Alarm ab Abweichung (%)"
           description="Wenn Betrag X% vom Durchschnitt dieses Lieferanten abweicht → Alarm">
        <div style={{width:140}}>
          <Slider label="" value={s.ki_anomalie_abweichung_pct??30}
            onChange={v=>save("ki_anomalie_abweichung_pct",v)}
            color="var(--orange)" suffix="%" min={5} max={100} step={5}/>
        </div>
      </Row>

      <SectionTitle>KI-Module aktivieren</SectionTitle>

      {[
        {key:"ki_steuer_autopilot_aktiv", label:"Steuer-Autopilot", desc:"Vollautomatische Steuerfälle"},
        {key:"ki_beleg_ocr_aktiv",         label:"Belegscanner (OCR)", desc:"Claude Vision analysiert Belege"},
        {key:"ki_email_generierung_aktiv", label:"KI-Email-Generierung", desc:"Emails automatisch erstellen"},
        {key:"ki_bot_proaktiv_aktiv",      label:"Proaktiver Bot", desc:"Bot fragt Mandanten automatisch"},
      ].map(item=>(
        <Row key={item.key} label={item.label} description={item.desc}>
          <Toggle value={s[item.key]??true} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}

      <Row label="KI-Modell"
           description="Welches Claude-Modell soll verwendet werden?">
        <select value={s.ki_modell||"gpt-4o-mini"}
          onChange={e=>save("ki_modell",e.target.value)}
          style={{background:"var(--bg)",border:`1px solid var(--border2)`,
            borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,
            fontFamily:"'DM Sans',sans-serif",outline:"none"}}>
          <option value="gpt-4o-mini">GPT-4o mini (schnell, günstig)</option>
          <option value="gpt-4o">GPT-4o (stärkstes Modell)</option>
        </select>
      </Row>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 2. WORKFLOW-DESIGNER
// ═══════════════════════════════════════════════════════════

const WorkflowTab = ({s, save}) => {
  const FRISTEN_CONFIG = [
    {label:"Fristen-Voralarm (Tage)",        key:"frist_warnung_tage",            desc:"Erste Warnung vor Frist"},
    {label:"Kritische Warnung (Tage)",        key:"frist_kritisch_tage",           desc:"Letzte Warnung — dringend"},
    {label:"Keine Antwort → Alarm (Tage)",    key:"antwort_warnung_tage",          desc:"Mandant meldet sich nicht"},
    {label:"USt-Voranmeldung Vorwarnung",     key:"ustva_vorwarnung_tage",         desc:"Tage vor USt-Fälligkeit"},
    {label:"Jahresabschluss Vorwarnung",      key:"jahresabschluss_vorwarnung_tage",desc:"Tage vor JA-Fälligkeit"},
    {label:"ESt-Erklärung Vorwarnung",        key:"est_vorwarnung_tage",           desc:"Tage vor ESt-Fälligkeit"},
  ];

  return (
    <div>
      <SectionTitle>Fristen-Radar</SectionTitle>
      <div style={{background:"var(--bg3)",borderRadius:12,padding:"14px 18px",marginBottom:16,
        border:`1px solid var(--border)`}}>
        <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.7}}>
          Fristen-Radar schickt automatische Warnungen an Steuerberater und Mandant.
          Eskalationsstufen definieren wer bei welcher Dringlichkeit informiert wird.
        </div>
      </div>

      {FRISTEN_CONFIG.map(f=>(
        <Row key={f.key} label={f.label} description={f.desc}>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <input type="number" defaultValue={s[f.key]||7} min={1} max={180}
              onBlur={e=>save(f.key,parseInt(e.target.value))}
              style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,
                borderRadius:8,color:"var(--text)",padding:"7px 10px",fontSize:14,
                textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:"var(--text3)"}}>Tage</span>
          </div>
        </Row>
      ))}

      <SectionTitle>Eskalationsstufen</SectionTitle>

      {[
        {nr:1, tage_key:"eskalation_stufe_1_tage", email_key:"eskalation_stufe_1_empfaenger",
         label:"Stufe 1 — Standardwarnung"},
        {nr:2, tage_key:"eskalation_stufe_2_tage", email_key:"eskalation_stufe_2_empfaenger",
         label:"Stufe 2 — Kritische Warnung (Inhaber)"},
      ].map(e=>(
        <div key={e.nr} style={{background:"var(--bg3)",borderRadius:10,padding:"14px 16px",
          marginBottom:10,border:`1px solid var(--border)`}}>
          <div style={{fontWeight:600,color:"var(--text)",fontSize:14,marginBottom:10}}>
            {e.label}
          </div>
          <div style={{display:"flex",gap:12,alignItems:"center",flexWrap:"wrap"}}>
            <div>
              <div style={{fontSize:10,color:"var(--text3)",marginBottom:4}}>Auslöser: nach X Tagen</div>
              <input type="number" defaultValue={s[e.tage_key]||7} min={1}
                onBlur={ev=>save(e.tage_key,parseInt(ev.target.value))}
                style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,
                  borderRadius:8,color:"var(--text)",padding:"7px 10px",fontSize:13,
                  textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            </div>
            <div style={{flex:1}}>
              <div style={{fontSize:10,color:"var(--text3)",marginBottom:4}}>Empfänger (Email)</div>
              <input type="email" defaultValue={s[e.email_key]||""}
                placeholder={`stufe${e.nr}@kanzlei.de`}
                onBlur={ev=>save(e.email_key,ev.target.value)}
                style={{width:"100%",background:"var(--bg)",border:`1px solid var(--border2)`,
                  borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,
                  outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            </div>
          </div>
        </div>
      ))}

      <SectionTitle>Historie & automatische Löschung</SectionTitle>

      <Row
        label="Erledigte Mandanten-Aufgaben (Tage)"
        description="Einträge in der Aufgaben-Historie werden nach dieser Anzahl Tagen endgültig entfernt."
      >
        <input
          type="number"
          defaultValue={s.historie_erledigte_aufgaben_tage ?? 30}
          min={1}
          max={3650}
          onBlur={(ev) => save("historie_erledigte_aufgaben_tage", parseInt(ev.target.value, 10))}
          style={{
            width: 88, background: "var(--bg)", border: "1px solid var(--border2)",
            borderRadius: 8, color: "var(--text)", padding: "7px 10px", fontSize: 13,
            textAlign: "center", outline: "none", fontFamily: "'DM Sans', sans-serif",
          }}
        />
      </Row>

      <Row
        label="Steuerfälle in der Historie (Tage)"
        description="Freigegebene oder archivierte Steuerfälle verschwinden nach dieser Frist vom System."
      >
        <input
          type="number"
          defaultValue={s.historie_steuerfaelle_tage ?? 30}
          min={1}
          max={3650}
          onBlur={(ev) => save("historie_steuerfaelle_tage", parseInt(ev.target.value, 10))}
          style={{
            width: 88, background: "var(--bg)", border: "1px solid var(--border2)",
            borderRadius: 8, color: "var(--text)", padding: "7px 10px", fontSize: 13,
            textAlign: "center", outline: "none", fontFamily: "'DM Sans', sans-serif",
          }}
        />
      </Row>

      <SectionTitle>Automatische Workflows</SectionTitle>

      {[
        {key:"auto_workflow_monatsabschluss", label:"Monatsabschluss automatisch starten"},
        {key:"auto_workflow_lohn",            label:"Lohnabrechnung automatisch starten"},
        {key:"auto_eskalation_aktiv",          label:"Automatische Eskalation (Tag 3→30)"},
        {key:"auto_frist_rettung_aktiv",       label:"Fristen-Rettung (Frist + fehlende Docs)"},
      ].map(item=>(
        <Row key={item.key} label={item.label}>
          <Toggle value={s[item.key]??true} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}

      <SectionTitle>Eskalationsplan (Vorschau)</SectionTitle>
      <div style={{background:"var(--bg3)",borderRadius:12,padding:"14px 16px",marginBottom:16,
        border:"1px solid var(--border)"}}>
        <div style={{fontSize:12,color:"var(--text3)",marginBottom:12}}>
          Standard-Ablauf ohne manuelles Nachfassen — sichtbar in der Mandantenakte.
        </div>
        {[
          "Tag 0 — Dokument angefordert",
          "Tag 3 — Erste Erinnerung",
          "Tag 7 — Zweite Erinnerung",
          "Tag 14 — Deutlicher Hinweis",
          "Tag 21 — Interne Eskalation",
          "Tag 30 — Mandant rot markiert",
        ].map((line, i) => (
          <div key={i} style={{
            display:"flex",alignItems:"center",gap:10,padding:"8px 0",
            borderBottom: i < 5 ? "1px solid var(--border)" : "none",
            fontSize:13,color:"var(--text2)",
          }}>
            <span style={{
              width:8,height:8,borderRadius:"50%",flexShrink:0,
              background:"var(--accent)",opacity:0.5 + i * 0.08,
            }}/>
            {line}
          </div>
        ))}
      </div>

      <SectionTitle>ROI-Monatsbericht</SectionTitle>
      <Row label="ROI-Bericht per E-Mail (monatlich)" description="Am 1. des Monats — Zusammenfassung der Automationen.">
        <Toggle value={s.auto_roi_email_aktiv ?? true} onChange={(v) => save("auto_roi_email_aktiv", v)} />
      </Row>
      <Row label="Empfänger (optional)" description="Leer = Kanzlei-E-Mail aus Stammdaten.">
        <input
          type="email"
          defaultValue={s.roi_email_empfaenger || ""}
          placeholder={s.kanzlei_email || "partner@kanzlei.de"}
          onBlur={(ev) => save("roi_email_empfaenger", ev.target.value)}
          style={{
            width: "100%", maxWidth: 320, background: "var(--bg)", border: "1px solid var(--border2)",
            borderRadius: 8, color: "var(--text)", padding: "7px 11px", fontSize: 13,
            outline: "none", fontFamily: "var(--font-body)",
          }}
        />
      </Row>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 3. MANDANTEN-PORTAL
// ═══════════════════════════════════════════════════════════

const PortalTab = ({s, save}) => {
  const portalUrl = typeof window !== "undefined"
    ? `${window.location.origin}/portal`
    : "/portal";

  return (
  <div>
    <div style={{ background:"var(--bg3)", border:`1px solid var(--border)`,
      borderRadius:14, padding:"14px 18px", marginBottom:20 }}>
      <div style={{ fontSize:11, color:"var(--text3)", textTransform:"uppercase",
        letterSpacing:"0.07em", marginBottom:8 }}>
        Portal-Adresse für Mandanten
      </div>
      <code style={{
        display:"block", fontSize:13, color:"var(--accent)", wordBreak:"break-all",
        marginBottom:12, padding:"10px 12px", background:"var(--bg)",
        borderRadius:8, border:"1px solid var(--border2)",
      }}>
        {portalUrl}
      </code>
      <div style={{ display:"flex", gap:8, flexWrap:"wrap", marginBottom:10 }}>
        <Btn size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(portalUrl)}>
          URL kopieren
        </Btn>
        <Btn size="sm" variant="subtle" onClick={() => window.open(portalUrl, "_blank", "noopener")}>
          Portal öffnen
        </Btn>
      </div>
      <div style={{ fontSize:12, color:"var(--text3)", lineHeight:1.55 }}>
        Persönliche Zugangslinks:{" "}
        <strong style={{ color:"var(--text2)" }}>Mandanten → Mandant öffnen → Mandantenportal</strong>
      </div>
    </div>

    <div style={{background:"linear-gradient(135deg, color-mix(in srgb, var(--blue) 8%, transparent), color-mix(in srgb, var(--purple) 4%, transparent))",
      border:"1px solid color-mix(in srgb, var(--blue) 22%, transparent)",borderRadius:14,padding:"14px 18px",marginBottom:20}}>
      <div style={{fontWeight:600,color:"var(--blue)",fontSize:14,marginBottom:4}}>
        Mandanten-Self-Service — Arbeit delegieren ohne Kontrollverlust
      </div>
      <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.6}}>
        Je mehr der Mandant selbst machen kann, desto mehr Zeit bleibt für wertschöpfende Beratung.
        Proaktive Bot-Fragen erscheinen in der Portal-Übersicht — Mandant antwortet per Klick.
      </div>
    </div>

    <SectionTitle>Bot-Benachrichtigungen</SectionTitle>
    <Row label="E-Mail an Mandant bei neuer Bot-Frage"
         description="Mandant wird zum Portal eingeladen — sonst bleibt die Antwortquote bei 0">
      <Toggle value={s.bot_email_mandant_aktiv??true} onChange={v=>save("bot_email_mandant_aktiv",v)}/>
    </Row>
    <Row label="E-Mail an Kanzlei nach Bot-Analyse"
         description="Zusammenfassung nach Scheduler oder manueller Analyse">
      <Toggle value={s.bot_email_kanzlei_aktiv??true} onChange={v=>save("bot_email_kanzlei_aktiv",v)}/>
    </Row>
    <Row label="Empfänger Bot-Analyse"
         description="Leer = Eskalations-E-Mail Stufe 1">
      <input
        type="email"
        defaultValue={s.bot_analyse_benachrichtigung_email||""}
        placeholder="kanzlei@beispiel.de"
        onBlur={e=>save("bot_analyse_benachrichtigung_email", e.target.value.trim())}
        style={{width:"100%",maxWidth:320,background:"var(--bg)",border:"1px solid var(--border2)",
          borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,outline:"none",
          fontFamily:"'DM Sans',sans-serif"}}
      />
    </Row>

    <SectionTitle>Pilot-Scorecard</SectionTitle>
    <Row label="Baseline zurücksetzen"
         description="Vorher/Nachher-Zähler im Dashboard ab jetzt neu">
      <button
        type="button"
        onClick={async ()=>{
          try {
            await setPilotBaseline();
            window.alert("Pilot-Baseline wurde gesetzt. Dashboard zeigt ab jetzt das Delta.");
          } catch (e) {
            window.alert(e?.message || "Baseline konnte nicht gesetzt werden.");
          }
        }}
        style={{background:"var(--bg3)",border:"1px solid var(--border2)",borderRadius:8,
          color:"var(--accent)",padding:"8px 14px",fontSize:13,fontWeight:600,cursor:"pointer",
          fontFamily:"'DM Sans',sans-serif"}}
      >
        Baseline jetzt setzen
      </button>
    </Row>

    <SectionTitle>Portal aktivieren</SectionTitle>
    <Row label="Mandantenportal aktiv"
         description="Mandanten können sich einloggen, Dokumente hochladen, Fragen beantworten">
      <Toggle value={s.portal_aktiv??true} onChange={v=>save("portal_aktiv",v)}/>
    </Row>
    <Row label="Digitale Unterschrift"
         description="Mandanten können Dokumente rechtsgültig digital unterzeichnen (eIDAS EES)">
      <Toggle value={s.portal_unterschrift_aktiv??true} onChange={v=>save("portal_unterschrift_aktiv",v)}/>
    </Row>

    <SectionTitle>Sichtbarkeits-Level (was sieht der Mandant?)</SectionTitle>

    {[
      {key:"portal_sichtbarkeit_bwa",         label:"BWA (Betriebswirtschaftliche Auswertung)", desc:"Monatliche Auswertung"},
      {key:"portal_sichtbarkeit_liquiditaet",  label:"Liquiditäts-Dashboard",                   desc:"Kassenbestand + Forderungen"},
      {key:"portal_sichtbarkeit_offene_posten",label:"Offene Posten",                            desc:"Ausstehende Zahlungen"},
      {key:"portal_sichtbarkeit_steuerprognose",label:"Steuerprognose",                          desc:"Voraussichtliche Steuerlast"},
      {key:"portal_sichtbarkeit_benchmarks",   label:"Branchen-Benchmarks",
       desc:"'Ihr Personalaufwand ist 15% über Branchenschnitt' — Premium-Feature"},
      {key:"portal_simulation_aktiv",          label:"Steuer-Simulation",                        desc:"Mandant rechnet selbst Szenarien durch"},
    ].map(item=>(
      <Row key={item.key} label={item.label} description={item.desc}>
        <Toggle value={s[item.key]??true} onChange={v=>save(item.key,v)}/>
      </Row>
    ))}

    <SectionTitle>Upload-Validierung</SectionTitle>
    <div style={{background:"var(--bg3)",borderRadius:10,padding:"14px 16px",
      border:`1px solid var(--border)`,marginBottom:12}}>
      <div style={{fontSize:13,color:"var(--text2)",marginBottom:10}}>
        Pflichtfelder beim Dokument-Upload — je mehr Infos, desto höher die KI-Erkennungsrate
      </div>
      {[
        {key:"portal_projektnummer_pflicht", label:"Projektnummer Pflichtfeld"},
      ].map(item=>(
        <Row key={item.key} label={item.label}>
          <Toggle value={s[item.key]??false} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}
      <Row label="Max. Upload-Größe" description="Pro Datei">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.portal_upload_max_mb||20} min={1} max={100}
            onBlur={e=>save("portal_upload_max_mb",parseInt(e.target.value))}
            style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,
              borderRadius:8,color:"var(--text)",padding:"7px 10px",fontSize:14,
              textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>MB</span>
        </div>
      </Row>
    </div>
  </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 4. MONETARISIERUNG
// ═══════════════════════════════════════════════════════════

const BillingTab = ({s, save}) => {
  const [stripeCfg, setStripeCfg] = useState(null);
  const [stripeBusy, setStripeBusy] = useState(false);
  const [stripeErr, setStripeErr] = useState("");
  const [billingMetrics, setBillingMetrics] = useState(null);
  const [billingFunnel, setBillingFunnel] = useState(null);
  const [weeklyDigest, setWeeklyDigest] = useState(null);
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestInfo, setDigestInfo] = useState("");

  useEffect(() => {
    let alive = true;
    getStripePublicConfig()
      .then((d) => {
        if (!alive) return;
        const raw = d?.data !== undefined ? d.data : d;
        setStripeCfg(raw && typeof raw === "object" ? raw : null);
      })
      .catch(() => alive && setStripeCfg(null));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    getBillingWeeklyReport()
      .then((d) => {
        if (!alive) return;
        const raw = d?.data !== undefined ? d.data : d;
        setWeeklyDigest(raw && typeof raw === "object" ? raw : null);
      })
      .catch(() => alive && setWeeklyDigest(null));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    getBillingFunnel(24)
      .then((d) => {
        if (!alive) return;
        const raw = d?.data?.funnel || d?.funnel || null;
        setBillingFunnel(raw && typeof raw === "object" ? raw : null);
      })
      .catch(() => alive && setBillingFunnel(null));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    getBillingMetrics()
      .then((d) => {
        if (!alive) return;
        const raw = d?.data !== undefined ? d.data : d;
        setBillingMetrics(raw && typeof raw === "object" ? raw : null);
      })
      .catch(() => alive && setBillingMetrics(null));
    return () => {
      alive = false;
    };
  }, []);

  const startStripeCheckout = async (targetPlan) => {
    setStripeErr("");
    setStripeBusy(true);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const ret = `${origin}/settings?stripe=1`;
      const r = await createStripeCheckoutSession({
        success_url: `${ret}&ok=1`,
        cancel_url: `${ret}&cancel=1`,
        target_plan: targetPlan,
      });
      const inner = r?.data !== undefined ? r.data : r;
      const url = inner?.url;
      if (url) window.location.href = url;
      else setStripeErr("Zahlungslink nicht verfügbar. Bitte Support oder IT kontaktieren.");
    } catch (e) {
      setStripeErr(e?.message || "Checkout nicht möglich");
    } finally {
      setStripeBusy(false);
    }
  };

  const openStripePortal = async () => {
    setStripeErr("");
    setStripeBusy(true);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const r = await createStripePortalSession(`${origin}/settings?portal=1`);
      const inner = r?.data !== undefined ? r.data : r;
      const url = inner?.url;
      if (url) window.location.href = url;
      else setStripeErr("Kein Portal-Link.");
    } catch (e) {
      setStripeErr(e?.message || "Portal nicht verfügbar (zuerst Checkout abschließen).");
    } finally {
      setStripeBusy(false);
    }
  };

  const modell = s.billing_modell || "pauschal";
  const sendWeeklyDigestNow = async () => {
    setDigestBusy(true);
    setDigestInfo("");
    try {
      const r = await sendBillingWeeklyReport();
      const raw = r?.data !== undefined ? r.data : r;
      const count = Number(raw?.sent || 0);
      setDigestInfo(count > 0 ? `Digest an ${count} Empfänger angestoßen.` : "Keine Owner/Admin-Empfänger gefunden.");
    } catch (e) {
      setDigestInfo(e?.message || "Digest-Versand fehlgeschlagen.");
    } finally {
      setDigestBusy(false);
    }
  };

  const MODELLE = [
    {val:"pauschal",         label:"Pauschal",          desc:"Monatliche Festgebühr pro Kanzlei"},
    {val:"pro_buchung",      label:"Pro KI-Buchung",    desc:"€X pro automatisch verbuchtem Beleg"},
    {val:"pro_mitarbeiter",  label:"Pro Mitarbeiter",   desc:"€X pro Nutzer-Account"},
    {val:"value",            label:"Value Pricing",     desc:"Preis basiert auf Mandanten-Umsatz"},
  ];

  return (
    <div>
      <div style={{background:"linear-gradient(135deg, color-mix(in srgb, var(--green) 8%, transparent), color-mix(in srgb, var(--accent) 4%, transparent))",
        border:"1px solid color-mix(in srgb, var(--green) 22%, transparent)",borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:"var(--green)",fontSize:14,marginBottom:4}}>
          Umsatz-Hebel — Automatisierte Abrechnung an Mandanten
        </div>
        <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.6}}>
          Die Kanzlei stellt ihren Mandanten KI-Nutzung direkt in Rechnung.
          Das System rechnet automatisch ab — ohne manuellen Aufwand.
        </div>
      </div>
      {billingMetrics && (
        <div style={{
          background:"var(--bg3)",borderRadius:12,padding:"12px 14px",marginBottom:18,
          border:`1px solid var(--border)`,
        }}>
          <div style={{display:"grid",gridTemplateColumns:"repeat(4, minmax(0,1fr))",gap:10}}>
            {[
              {k:"MRR (est.)", v:`€${Number(billingMetrics.mrr_estimate||0).toLocaleString("de")}`, c:"var(--green)"},
              {k:"ARR (est.)", v:`€${Number(billingMetrics.arr_estimate||0).toLocaleString("de")}`, c:"var(--accent)"},
              {k:"Plan", v:String((billingMetrics.plan||"starter")).toUpperCase(), c:"var(--blue)"},
              {k:"Churn-Risk", v:String((billingMetrics.churn_risk||"low")).toUpperCase(), c:(billingMetrics.churn_risk==="high"?"var(--red)":billingMetrics.churn_risk==="medium"?"var(--orange)":"var(--green)")},
            ].map((it)=>(<div key={it.k} style={{padding:"8px 10px",borderRadius:10,background:"var(--bg)",border:`1px solid var(--border)`}}>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>{it.k}</div>
              <div style={{fontSize:17,fontWeight:700,color:it.c}}>{it.v}</div>
            </div>))}
          </div>
          {billingMetrics.recommended_offer?.recommended_plan && (
            <div style={{marginTop:10,fontSize:12,color:"var(--text2)"}}>
              Empfohlenes Upgrade: <span style={{color:"var(--accent)",fontWeight:700}}>{String(billingMetrics.recommended_offer.recommended_plan).toUpperCase()}</span>
              {" "}({billingMetrics.recommended_offer.message})
            </div>
          )}
        </div>
      )}
      {billingFunnel && (
        <div style={{
          background:"var(--bg3)",borderRadius:12,padding:"12px 14px",marginBottom:18,
          border:`1px solid var(--border)`,
        }}>
          <div style={{fontSize:13,color:"var(--text2)",marginBottom:8}}>Revenue Funnel (24h)</div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:8}}>
            {[
              ["Views", billingFunnel.stages?.cta_view ?? 0],
              ["Clicks", billingFunnel.stages?.cta_click ?? 0],
              ["Checkout", billingFunnel.stages?.checkout_start ?? 0],
              ["Paid", billingFunnel.stages?.checkout_success ?? 0],
              ["Paywall", billingFunnel.stages?.paywall_402 ?? 0],
            ].map(([k,v])=>(
              <div key={k} style={{padding:"8px 10px",borderRadius:8,background:"var(--bg)",border:`1px solid var(--border)`}}>
                <div style={{fontSize:10,color:"var(--text3)"}}>{k}</div>
                <div style={{fontSize:17,fontWeight:700,color:"var(--accent)"}}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{marginTop:8,fontSize:12,color:"var(--text2)"}}>
            CTR: <b>{billingFunnel.rates?.ctr_percent ?? 0}%</b> ·
            Checkout→Paid: <b>{billingFunnel.rates?.checkout_to_paid_percent ?? 0}%</b> ·
            View→Paid: <b>{billingFunnel.rates?.view_to_paid_percent ?? 0}%</b>
          </div>
          {!!(billingFunnel.source_breakdown || []).length && (
            <div style={{marginTop:10}}>
              <div style={{fontSize:12,color:"var(--text3)",marginBottom:6}}>UTM-Drilldown (Top Sources)</div>
              <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:8}}>
                {(billingFunnel.source_breakdown || []).slice(0, 4).map((row, idx) => (
                  <div key={`${row.utm_source || "direct"}-${idx}`} style={{padding:"8px 10px",borderRadius:8,background:"var(--bg)",border:`1px solid var(--border)`}}>
                    <div style={{fontSize:11,color:"var(--text2)"}}>{String(row.utm_source || "direct")}</div>
                    <div style={{fontSize:14,fontWeight:700,color:"var(--accent)"}}>{Number(row.view_to_paid_percent || 0)}%</div>
                    <div style={{fontSize:10,color:"var(--text3)"}}>
                      Paid {Number(row.paid || 0)} / Events {Number(row.events || 0)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {weeklyDigest && (
        <div style={{
          background:"var(--bg3)",borderRadius:12,padding:"12px 14px",marginBottom:18,
          border:`1px solid var(--border)`,
        }}>
          <div style={{fontSize:13,color:"var(--text2)",marginBottom:8}}>Weekly Revenue Digest</div>
          {weeklyDigest?.channel_shift_alert?.message && (
            <div style={{
              marginBottom:8,
              padding:"8px 10px",
              borderRadius:8,
              background:"color-mix(in srgb, var(--orange) 12%, var(--bg3))",
              border:"1px solid color-mix(in srgb, var(--orange) 40%, transparent)",
              color:"var(--orange)",
              fontSize:12,
              fontWeight:600,
            }}>
              Kanal-Shift Alert: {weeklyDigest.channel_shift_alert.message}
            </div>
          )}
          <div style={{fontSize:12,color:"var(--text3)",marginBottom:6}}>
            Plan: <b style={{color:"var(--text)"}}>{String(weeklyDigest.plan || "").toUpperCase()}</b> ·
            Quota-Status: <b style={{color:"var(--text)"}}>{String(weeklyDigest.quota_status || "").toUpperCase()}</b>
          </div>
          <div style={{fontSize:12,color:"var(--text3)",marginBottom:8}}>
            7d View→Paid: <b style={{color:"var(--green)"}}>{weeklyDigest?.funnel_7d?.rates?.view_to_paid_percent ?? 0}%</b>
          </div>
          {(weeklyDigest?.utm_ranking?.top_source || weeklyDigest?.utm_ranking?.flop_source) && (
            <div style={{fontSize:12,color:"var(--text3)",marginBottom:8}}>
              Top UTM: <b style={{color:"var(--green)"}}>{weeklyDigest?.utm_ranking?.top_source?.utm_source || "—"}</b>
              {" "}({weeklyDigest?.utm_ranking?.top_source?.view_to_paid_percent ?? 0}%)
              {" "}· Flop UTM: <b style={{color:"var(--red)"}}>{weeklyDigest?.utm_ranking?.flop_source?.utm_source || "—"}</b>
              {" "}({weeklyDigest?.utm_ranking?.flop_source?.view_to_paid_percent ?? 0}%)
            </div>
          )}
          <ul style={{margin:0,paddingLeft:18,color:"var(--text2)",fontSize:12,lineHeight:1.6}}>
            {(weeklyDigest.recommended_actions || []).slice(0,3).map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
          <div style={{marginTop:10,display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>
            <Btn size="sm" variant="subtle" loading={digestBusy} onClick={sendWeeklyDigestNow}>
              Weekly Digest jetzt senden
            </Btn>
            {digestInfo ? <span style={{fontSize:12,color:"var(--text3)"}}>{digestInfo}</span> : null}
          </div>
        </div>
      )}

      <Row label="Billing-Modul aktiv"
           description="Automatische Abrechnung von KI-Leistungen an Mandanten">
        <Toggle value={s.billing_aktiv??false} onChange={v=>save("billing_aktiv",v)}/>
      </Row>

      <SectionTitle>Abrechnungsmodell</SectionTitle>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:20}}>
        {MODELLE.map(m=>{
          const aktiv = modell === m.val;
          return (
            <div key={m.val} onClick={()=>save("billing_modell",m.val)} style={{
              padding:"14px 16px",borderRadius:12,cursor:"pointer",
              border:`2px solid ${aktiv?"var(--accent)":"var(--border)"}`,
              background:aktiv?"color-mix(in srgb, var(--accent) 10%, var(--bg3))":"var(--bg3)",
              transition:"all 0.15s",
            }}>
              <div style={{fontWeight:600,fontSize:14,color:aktiv?"var(--accent)":"var(--text)",
                marginBottom:4}}>{m.label}</div>
              <div style={{fontSize:12,color:"var(--text3)"}}>{m.desc}</div>
            </div>
          );
        })}
      </div>

      {/* Pauschal */}
      {modell==="pauschal"&&(
        <Row label="Pauschalgebühr pro Monat" description="Wird automatisch als Rechnung erstellt">
          <div style={{display:"flex",gap:6,alignItems:"center"}}>
            <input type="number" defaultValue={s.billing_pauschal_euro||299} min={0}
              onBlur={e=>save("billing_pauschal_euro",parseFloat(e.target.value))}
              style={{width:90,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
                color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
                outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:"var(--text3)"}}>€/Monat</span>
          </div>
        </Row>
      )}

      {/* Pro Buchung */}
      {modell==="pro_buchung"&&(
        <Row label="Preis pro KI-Buchung" description="Pro automatisch verarbeitetem Beleg">
          <div style={{display:"flex",gap:6,alignItems:"center"}}>
            <input type="number" defaultValue={s.billing_pro_buchung_euro||0.20} min={0} step={0.01}
              onBlur={e=>save("billing_pro_buchung_euro",parseFloat(e.target.value))}
              style={{width:90,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
                color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
                outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:"var(--text3)"}}>€/Buchung</span>
          </div>
        </Row>
      )}

      {/* Value Pricing */}
      {modell==="value"&&(
        <div>
          <div style={{fontSize:12,color:"var(--text3)",marginBottom:12}}>
            Preis basiert auf Jahresumsatz des Mandanten — fairer und skalierbarer.
          </div>
          {[
            {tier:"Tier 1 (bis €100k)",    bis_key:"billing_value_tier_1_bis",  euro_key:"billing_value_tier_1_euro",  def_bis:100000, def_euro:199},
            {tier:"Tier 2 (€100k–€500k)", bis_key:"billing_value_tier_2_bis",  euro_key:"billing_value_tier_2_euro",  def_bis:500000, def_euro:399},
            {tier:"Tier 3 (>€500k)",       bis_key:null,                         euro_key:"billing_value_tier_3_euro",  def_bis:null,   def_euro:699},
          ].map((t,i)=>(
            <div key={i} style={{background:"var(--bg3)",borderRadius:8,padding:"10px 14px",
              marginBottom:8,border:`1px solid var(--border)`,
              display:"flex",alignItems:"center",gap:16}}>
              <div style={{flex:1,fontSize:13,color:"var(--text)"}}>{t.tier}</div>
              <div style={{display:"flex",gap:6,alignItems:"center"}}>
                <input type="number" defaultValue={s[t.euro_key]||t.def_euro} min={0}
                  onBlur={e=>save(t.euro_key,parseFloat(e.target.value))}
                  style={{width:80,background:"var(--bg)",border:`1px solid var(--border2)`,
                    borderRadius:8,color:"var(--text)",padding:"7px 10px",fontSize:13,
                    textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
                <span style={{fontSize:12,color:"var(--text3)"}}>€/Monat</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <SectionTitle>Automatische Rechnungsstellung</SectionTitle>

      <Row label="Rechnungen automatisch erstellen"
           description="System erstellt monatlich Rechnungen an Mandanten">
        <Toggle value={s.billing_rechnung_auto??false} onChange={v=>save("billing_rechnung_auto",v)}/>
      </Row>

      <Row label="Zahlungsziel (Tage)">
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          <input type="number" defaultValue={s.billing_zahlungsziel_tage||14} min={1} max={90}
            onBlur={e=>save("billing_zahlungsziel_tage",parseInt(e.target.value))}
            style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
              color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>Tage</span>
        </div>
      </Row>

      <Row label="KI-Aufschlag auf Honorar"
           description="Zusätzlicher Aufschlag auf Basis-Honorar für KI-Nutzung">
        <div style={{width:140}}>
          <Slider label="" value={s.billing_ki_aufschlag_prozent||20}
            onChange={v=>save("billing_ki_aufschlag_prozent",v)}
            color="var(--green)" suffix="%" min={0} max={100} step={5}/>
        </div>
      </Row>

      <SectionTitle>Stripe-Integration</SectionTitle>
      <div style={{background:"var(--bg3)",borderRadius:12,padding:"14px 16px",
        border:`1px solid var(--border)`}}>
        <Row label="Stripe aktiv" description="Automatische Kreditkartenzahlung von Mandanten">
          <Toggle value={s.billing_stripe_aktiv??false}
            onChange={v=>save("billing_stripe_aktiv",v)}/>
        </Row>
        {s.billing_stripe_aktiv&&(
          <Row label="Stripe Secret Key" description="Unter dashboard.stripe.com/apikeys">
            <input type="password" defaultValue={s.billing_stripe_key||""}
              placeholder="sk_live_..."
              onBlur={e=>save("billing_stripe_key",e.target.value)}
              style={{width:260,background:"var(--bg)",border:`1px solid var(--border2)`,
                borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,
                outline:"none",fontFamily:"'DM Mono',monospace"}}/>
          </Row>
        )}
        <div style={{fontSize:12,color:"var(--text3)",marginTop:8,lineHeight:1.6}}>
          Mit Stripe: Mandanten zahlen Honorare automatisch per Lastschrift/Kreditkarte.
          Zahlungsausfall-Rate sinkt auf unter 0,5&nbsp;%.
        </div>
        {stripeCfg?.checkout_ready ? (
          <div style={{marginTop:14, display:"flex", flexWrap:"wrap", gap:10, alignItems:"center"}}>
            <span style={{fontSize:12, color:"var(--text2)"}}>Abo per Kreditkarte (Stripe):</span>
            <button type="button" disabled={stripeBusy} onClick={() => startStripeCheckout("professional")}
              style={{padding:"8px 14px", borderRadius:8, border:"1px solid var(--accent)", background:"color-mix(in srgb, var(--accent) 18%, var(--bg3))",
                color:"var(--accent)", fontWeight:600, cursor: stripeBusy ? "wait" : "pointer", fontSize:13}}>
              {stripeBusy ? "…" : "Professional buchen"}
            </button>
            {stripeCfg?.enterprise_price_configured ? (
              <button type="button" disabled={stripeBusy} onClick={() => startStripeCheckout("enterprise")}
                style={{padding:"8px 14px", borderRadius:8, border:"1px solid var(--purple)", background:"color-mix(in srgb, var(--purple) 14%, var(--bg3))",
                  color:"var(--purple)", fontWeight:600, cursor: stripeBusy ? "wait" : "pointer", fontSize:13}}>
                Enterprise
              </button>
            ) : null}
            <button type="button" disabled={stripeBusy} onClick={openStripePortal}
              style={{padding:"8px 14px", borderRadius:8, border:`1px solid var(--border2)`, background:"transparent",
                color:"var(--text2)", fontSize:13, cursor: stripeBusy ? "wait" : "pointer"}}>
              Abo im Stripe-Portal
            </button>
          </div>
        ) : (
          <div style={{marginTop:10, fontSize:12, color:"var(--text3)"}}>
            Online-Zahlungen sind noch nicht eingerichtet. Bitte kontaktieren Sie den Support oder Ihre IT.
          </div>
        )}
        {stripeErr ? (
          <div style={{marginTop:8, fontSize:12, color:"var(--red)"}}>{stripeErr}</div>
        ) : null}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 5. TEAM & BERECHTIGUNGEN (schlank)
// ═══════════════════════════════════════════════════════════

const BetreuerMatrix = ({ showToast }) => {
  const [matrix, setMatrix] = useState(null);
  const [busy, setBusy] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [bulkBetreuer, setBulkBetreuer] = useState("");
  const canEdit = hasRoleReal(["owner", "admin", "steuerberater"]);

  const load = useCallback(() => {
    getBetreuerMatrix()
      .then((r) => setMatrix(r?.data ?? r))
      .catch(() => setMatrix(null));
  }, []);

  useEffect(() => { load(); }, [load]);

  const assign = async (mandantName, betreuerEmail) => {
    if (!canEdit) return;
    setBusy(mandantName);
    try {
      await updateMandantAPI(mandantName, { betreuer_email: betreuerEmail || "" });
      showToast?.(`Betreuer für ${mandantName} gespeichert`);
      load();
    } catch (e) {
      showToast?.(e.message || "Speichern fehlgeschlagen", "error");
    } finally {
      setBusy("");
    }
  };

  const toggleSelect = (name) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const assignBulk = async (payload) => {
    if (!canEdit) return;
    setBusy("bulk");
    try {
      const res = await bulkAssignBetreuer(payload);
      const msg = res?.data?.message ?? res?.message ?? "Bulk-Zuweisung gespeichert";
      showToast?.(msg);
      setSelected(new Set());
      load();
    } catch (e) {
      showToast?.(e.message || "Bulk-Zuweisung fehlgeschlagen", "error");
    } finally {
      setBusy("");
    }
  };

  if (!matrix?.mandanten?.length) {
    return (
      <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 16 }}>
        Noch keine Mandanten für die Betreuer-Matrix.
      </div>
    );
  }

  const team = matrix.team || [];

  return (
    <div style={{
      marginBottom: 20, borderRadius: 12, border: "1px solid var(--border)",
      overflow: "hidden", background: "var(--bg3)",
    }}>
      {canEdit ? (
        <div style={{
          padding: "10px 14px", borderBottom: "1px solid var(--border)",
          display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
        }}>
          <select
            value={bulkBetreuer}
            onChange={(e) => setBulkBetreuer(e.target.value)}
            style={{
              flex: "1 1 180px", maxWidth: 280, padding: "7px 10px", borderRadius: 8,
              border: "1px solid var(--border2)", background: "var(--bg)", fontSize: 12,
            }}
          >
            <option value="">Betreuer wählen…</option>
            {team.map((t) => (
              <option key={t.email} value={t.email}>{t.email}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={!bulkBetreuer || selected.size === 0 || busy === "bulk"}
            onClick={() => assignBulk({
              betreuer_email: bulkBetreuer,
              mandanten: [...selected],
            })}
            style={{
              padding: "7px 12px", borderRadius: 8, border: "none", cursor: "pointer",
              background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 600,
              opacity: !bulkBetreuer || selected.size === 0 ? 0.5 : 1,
            }}
          >
            Auf Auswahl ({selected.size})
          </button>
          <button
            type="button"
            disabled={!bulkBetreuer || busy === "bulk"}
            onClick={() => assignBulk({ betreuer_email: bulkBetreuer, nur_ohne_betreuer: true })}
            style={{
              padding: "7px 12px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "var(--bg)", color: "var(--text)", fontSize: 12, cursor: "pointer",
            }}
          >
            Alle ohne Betreuer
          </button>
        </div>
      ) : null}
      <div style={{
        padding: "10px 14px", fontSize: 11, color: "var(--text3)",
        textTransform: "uppercase", letterSpacing: "0.06em",
        borderBottom: "1px solid var(--border)",
      }}>
        Mandant · Betreuer (E-Mail)
      </div>
      {matrix.mandanten.map((row) => (
        <div key={row.name} style={{
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
          padding: "10px 14px", borderBottom: "1px solid var(--border)",
        }}>
          {canEdit ? (
            <input
              type="checkbox"
              checked={selected.has(row.name)}
              onChange={() => toggleSelect(row.name)}
              style={{ flexShrink: 0 }}
            />
          ) : null}
          <div style={{ flex: "1 1 140px", minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text)" }}>{row.name}</div>
            <div style={{ fontSize: 11, color: "var(--text3)" }}>{row.email || "—"}</div>
          </div>
          <select
            disabled={!canEdit || busy === row.name}
            value={row.betreuer_email || ""}
            onChange={(e) => assign(row.name, e.target.value)}
            style={{
              flex: "1 1 200px", maxWidth: 280, padding: "7px 10px", borderRadius: 8,
              border: "1px solid var(--border2)", background: "var(--bg)", color: "var(--text)", fontSize: 12,
            }}
          >
            <option value="">— alle Mitarbeiter —</option>
            {team.map((t) => (
              <option key={t.email} value={t.email}>
                {t.email} ({t.rolle})
              </option>
            ))}
          </select>
        </div>
      ))}
      {!canEdit ? (
        <div style={{ padding: "8px 14px", fontSize: 11, color: "var(--text3)" }}>
          Nur Steuerberater/Admin können Betreuer zuweisen.
        </div>
      ) : null}
    </div>
  );
};

const TeamTab = ({ s, save, showToast }) => {
  const ROLLEN = ["owner", "admin", "teamleiter", "steuerberater", "mitarbeiter"];
  const canEditRoleMatrix = hasRoleReal(["owner", "admin"]);

  const applyPreset = (presetId) => {
    const preset = ROLE_NAV_PRESETS[presetId];
    if (!preset || !canEditRoleMatrix) return;
    save("produkt_fokus_aktiv", presetId === "mitarbeiter" || presetId === "teamleiter");
    save("rollen_nav_steuerberater", preset.steuerberater);
    save("rollen_nav_teamleiter", preset.teamleiter || preset.steuerberater);
    save("rollen_nav_mitarbeiter", preset.mitarbeiter);
    try {
      window.dispatchEvent(new CustomEvent("kanzlei-settings-changed"));
    } catch {}
  };

  const renderNavBlock = (block) => {
    const defMit = NAV_TOGGLE_IDS.filter(
      (id) => !["profit", "steuerbot", "automation", "analytics", "neu", "settings"].includes(id),
    );
    const fallback = block.key === "rollen_nav_steuerberater"
      ? NAV_TOGGLE_IDS.filter((id) => id !== "ki")
      : defMit;
    const cur = Array.isArray(s[block.key]) && s[block.key].length ? [...s[block.key]] : fallback;
    const set = new Set(cur.map((x) => String(x).toLowerCase()).filter((id) => id !== "ki"));

    return (
      <div
        key={block.key}
        style={{
          marginBottom: 14,
          padding: "12px 14px",
          borderRadius: 12,
          border: "1px solid var(--border)",
          background: "var(--bg3)",
        }}
      >
        <div style={{ fontWeight: 600, color: "var(--text)", marginBottom: 10, fontSize: 13 }}>{block.title}</div>
        {NAV_SETTINGS_GROUPS.map((group) => {
          const ids = group.ids.filter((id) => NAV_TOGGLE_IDS.includes(id));
          if (!ids.length) return null;
          return (
            <div key={`${block.key}-${group.id}`} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                {group.label}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {ids.map((tid) => {
                  const on = set.has(tid);
                  return (
                    <button
                      key={`${block.key}-${tid}`}
                      type="button"
                      disabled={!canEditRoleMatrix}
                      onClick={() => {
                        if (!canEditRoleMatrix) return;
                        const next = new Set(set);
                        if (on) {
                          if (tid === "dashboard") return;
                          next.delete(tid);
                        } else {
                          next.add(tid);
                        }
                        if (!next.has("dashboard")) next.add("dashboard");
                        save(block.key, [...next]);
                      }}
                      style={{
                        padding: "4px 10px",
                        borderRadius: 20,
                        cursor: canEditRoleMatrix ? "pointer" : "not-allowed",
                        border: `1px solid ${on ? "color-mix(in srgb, var(--blue) 38%, transparent)" : "var(--border2)"}`,
                        background: on ? "color-mix(in srgb, var(--blue) 16%, var(--bg))" : "var(--bg)",
                        color: on ? "var(--blue)" : "var(--text3)",
                        fontSize: 11,
                        fontWeight: on ? 600 : 400,
                      }}
                      title={NAV_TAB_LABELS[tid] || tid}
                    >
                      {NAV_TAB_LABELS[tid] || tid}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div>
      <div style={{
        background: "var(--bg3)", borderRadius: 12, padding: "14px 16px",
        border: "1px solid var(--border)", marginBottom: 18,
      }}>
        <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.55 }}>
          <Link to="/users" style={{ color: "var(--accent)", fontWeight: 600 }}>Team verwalten →</Link>
          {" "}Personen einladen und Rollen zuweisen. Hier steuern Sie, welche Bereiche in der Sidebar sichtbar sind.
        </div>
      </div>

      <SectionTitle>Betreuer-Matrix</SectionTitle>
      <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 10, lineHeight: 1.5 }}>
        Mitarbeiter sehen nur Mandanten mit ihrer E-Mail als Betreuer — oder ohne Zuweisung (alle).
      </div>
      <BetreuerMatrix showToast={showToast} />

      <SectionTitle>Produktfokus</SectionTitle>
      <Row label="Schlanke Navigation (empfohlen)"
           description="Hauptbereiche sichtbar — Analytics, Profit & Co. unter „Mehr anzeigen“.">
        <Toggle value={s.produkt_fokus_aktiv ?? true} onChange={(v) => {
          save("produkt_fokus_aktiv", v);
          if (v) {
            save("rollen_nav_steuerberater", [
              "dashboard", "mandanten", "dokumente", "automation", "aufgaben", "settings",
            ]);
            save("rollen_nav_mitarbeiter", [
              "dashboard", "mandanten", "dokumente", "aufgaben", "settings",
            ]);
          } else {
            applyPreset("inhaber");
          }
          try {
            window.dispatchEvent(new CustomEvent("kanzlei-settings-changed"));
          } catch {}
        }} />
      </Row>

      <SectionTitle>Schnell-Presets</SectionTitle>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {Object.entries(ROLE_NAV_PRESETS).map(([id, preset]) => (
          <button
            key={id}
            type="button"
            disabled={!canEditRoleMatrix}
            onClick={() => applyPreset(id)}
            style={{
              padding: "8px 12px", borderRadius: 10, cursor: canEditRoleMatrix ? "pointer" : "not-allowed",
              border: "1px solid var(--border2)", background: "var(--bg2)", textAlign: "left",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{preset.label}</div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>{preset.hint}</div>
          </button>
        ))}
      </div>

      <SectionTitle>Feature-Berechtigungen</SectionTitle>
      <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 10, lineHeight: 1.5 }}>
        Gilt serverseitig für API-Aktionen (Löschen, DATEV, Lohn, Einstellungen) — nicht nur in der Oberfläche.
      </div>
      <PermissionGate roles={["owner", "admin"]} mode="disable" fallback={null}>
        <div style={{ background: "var(--bg3)", borderRadius: 12, padding: "14px 16px", border: "1px solid var(--border)" }}>
          {FEATURE_PERMISSION_KEYS.map((item) => (
            <div key={item.key} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <div style={{ fontWeight: 500, color: "var(--text)", fontSize: 13, marginBottom: 6 }}>{item.label}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {ROLLEN.map((rolle) => {
                  const aktiv = (s[item.key] || ["admin"]).includes(rolle);
                  return (
                    <div
                      key={rolle}
                      onClick={() => {
                        if (!canEditRoleMatrix) return;
                        const current = s[item.key] || ["admin"];
                        const next = aktiv ? current.filter((r) => r !== rolle) : [...current, rolle];
                        if (next.length > 0) save(item.key, next);
                      }}
                      style={{
                        padding: "4px 12px", borderRadius: 20, cursor: canEditRoleMatrix ? "pointer" : "not-allowed",
                        background: aktiv ? "color-mix(in srgb, var(--blue) 16%, var(--bg))" : "var(--bg)",
                        border: `1px solid ${aktiv ? "color-mix(in srgb, var(--blue) 38%, transparent)" : "var(--border2)"}`,
                        color: aktiv ? "var(--blue)" : "var(--text3)", fontSize: 12, fontWeight: aktiv ? 600 : 400,
                      }}
                    >
                      {rolle}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </PermissionGate>
      {!canEditRoleMatrix && (
        <div style={{ marginTop: 10, fontSize: 12, color: "var(--text3)" }}>
          Nur Owner/Admin dürfen Berechtigungen bearbeiten.
        </div>
      )}

      <SectionTitle>Navigation pro Rolle</SectionTitle>
      <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 10, lineHeight: 1.5 }}>
        Owner und Admin sehen immer die volle Navigation. KI ist unsichtbar im Hintergrund — kein eigener Menüpunkt.
      </div>
      <PermissionGate
        roles={["owner", "admin"]}
        mode="disable"
        fallback={
          <div style={{ fontSize: 12, color: "var(--text3)" }}>
            Nur Owner/Admin können die Sidebar für andere Rollen anpassen.
          </div>
        }
      >
        {[
          { key: "rollen_nav_steuerberater", title: "Steuerberater/in" },
          { key: "rollen_nav_teamleiter", title: "Teamleiter/in" },
          { key: "rollen_nav_mitarbeiter", title: "Mitarbeiter/in" },
        ].map(renderNavBlock)}
      </PermissionGate>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ERWEITERT — GoBD, KI, Abrechnung
// ═══════════════════════════════════════════════════════════

const ErweitertTab = ({ s, save, kpiStats }) => (
  <div>
    <div style={{
      fontSize: 13, color: "var(--text2)", lineHeight: 1.55, marginBottom: 18,
      padding: "12px 14px", borderRadius: 12, background: "var(--bg3)", border: "1px solid var(--border)",
    }}>
      Selten gebrauchte Optionen: Compliance, KI-Parameter und Abrechnung. Für den Alltag reichen die ersten fünf Einstellungs-Tabs.
    </div>

    <SectionTitle>Sicherheit & GoBD</SectionTitle>
    <Row label="GoBD-Konformität" locked description="Gesetzlich vorgeschrieben — nicht änderbar (§ 147 AO)">
      <div style={{ color: "var(--green)", fontWeight: 600, fontSize: 14 }}>✓ Aktiv</div>
    </Row>
    <Row label="Audit-Log unveränderbar" locked description="Revisionssichere Protokollierung">
      <div style={{ color: "var(--green)", fontWeight: 600, fontSize: 14 }}>✓ Aktiv</div>
    </Row>
    <Row label="Aufbewahrung (Jahre)" description="§ 147 AO: Handelsbücher 10 Jahre">
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>{s.gobd_aufbewahrung_jahre || 10} Jahre</div>
    </Row>
    <Row label="Server-Standort" description="DSGVO: Daten in EU speichern">
      <select
        value={s.server_standort || "DE"}
        onChange={(e) => save("server_standort", e.target.value)}
        style={{
          background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
          color: "var(--text)", padding: "7px 11px", fontSize: 13, outline: "none",
        }}
      >
        <option value="DE">🇩🇪 Deutschland (DSGVO)</option>
        <option value="EU">🇪🇺 EU (DSGVO)</option>
        <option value="CH">🇨🇭 Schweiz (DSG)</option>
      </select>
    </Row>
    <Row label="Datenschutzbeauftragter (E-Mail)">
      <input
        type="email"
        defaultValue={s.datenschutz_beauftragter || ""}
        placeholder="dsb@kanzlei.de"
        onBlur={(e) => save("datenschutz_beauftragter", e.target.value)}
        style={{
          width: 220, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
          color: "var(--text)", padding: "7px 11px", fontSize: 13, outline: "none",
        }}
      />
    </Row>
    {[
      { key: "2fa_pflicht", label: "2-Faktor-Authentifizierung Pflicht" },
      { key: "verschluesselung_aktiv", label: "Daten-Verschlüsselung" },
      { key: "ip_whitelist_aktiv", label: "IP-Whitelist aktiv" },
    ].map((item) => (
      <Row key={item.key} label={item.label}>
        <Toggle value={s[item.key] ?? false} onChange={(v) => save(item.key, v)} />
      </Row>
    ))}
    <Row label="Session-Timeout">
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="number"
          defaultValue={s.session_timeout_minuten || 60}
          min={5}
          max={480}
          onBlur={(e) => save("session_timeout_minuten", parseInt(e.target.value, 10))}
          style={{
            width: 70, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
            color: "var(--text)", padding: "7px 10px", fontSize: 14, textAlign: "center", outline: "none",
          }}
        />
        <span style={{ fontSize: 12, color: "var(--text3)" }}>Minuten</span>
      </div>
    </Row>

    <SectionTitle>KI (Erweitert)</SectionTitle>
    <KITab s={s} save={save} kpiStats={kpiStats} />

    <SectionTitle>Abrechnung</SectionTitle>
    <BillingTab s={s} save={save} />
  </div>
);

// ═══════════════════════════════════════════════════════════
// 6. SCHNITTSTELLEN
// ═══════════════════════════════════════════════════════════

const SchnittstellenTab = ({s, save, showToast}) => {
  const [m365, setM365] = useState(null);
  const [m365Busy, setM365Busy] = useState("");
  const [calPreview, setCalPreview] = useState(null);
  const [mailPreview, setMailPreview] = useState(null);

  const reloadM365 = useCallback(() => {
    getM365Status()
      .then((r) => setM365(r?.data ?? r))
      .catch(() => setM365(null));
  }, []);

  useEffect(() => {
    reloadM365();
    try {
      const params = new URLSearchParams(window.location.search);
      if (params.get("m365") === "connected") {
        showToast("✓ Microsoft 365 verbunden");
        params.delete("m365");
        const qs = params.toString();
        const next = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
        window.history.replaceState({}, "", next);
      }
    } catch {}
  }, [reloadM365, showToast]);

  const handleM365Connect = async () => {
    setM365Busy("connect");
    try {
      const res = await startM365Connect("/settings");
      const url = res?.data?.url ?? res?.url;
      if (!url) throw new Error("Keine OAuth-URL erhalten");
      window.location.href = url;
    } catch (e) {
      showToast(e.message || "Verbindung fehlgeschlagen", "error");
      setM365Busy("");
    }
  };

  const handleM365Disconnect = async () => {
    if (!window.confirm("Microsoft 365 Verbindung wirklich trennen?")) return;
    setM365Busy("disconnect");
    try {
      await disconnectM365();
      setCalPreview(null);
      setMailPreview(null);
      reloadM365();
      showToast("Microsoft 365 getrennt");
    } catch (e) {
      showToast(e.message || "Trennen fehlgeschlagen", "error");
    } finally {
      setM365Busy("");
    }
  };

  const handleCalPreview = async () => {
    setM365Busy("preview");
    try {
      const res = await getM365CalendarPreview();
      setCalPreview(res?.data ?? res);
    } catch (e) {
      showToast(e.message || "Kalender-Vorschau fehlgeschlagen", "error");
    } finally {
      setM365Busy("");
    }
  };

  const handleMailPreview = async () => {
    setM365Busy("mail");
    try {
      const res = await getM365MailPreview(10);
      setMailPreview(res?.data ?? res);
    } catch (e) {
      showToast(e.message || "Postfach-Vorschau fehlgeschlagen", "error");
    } finally {
      setM365Busy("");
    }
  };

  const ROADMAP = [
    {icon:"📧", label:"Microsoft 365 / Outlook (Kalender & Postfach)"},
    {icon:"🏛", label:"DATEV Live-Sync (Import)"},
    {icon:"🏦", label:"FinTS / EBICS live"},
    {icon:"⚖", label:"ELSTER Direktversand (ERiC)"},
    {icon:"📊", label:"Lexoffice, Personio, Shopify"},
  ];

  return (
    <div>
      <div style={{background:"linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, transparent), color-mix(in srgb, var(--blue) 5%, transparent))",
        border:"1px solid color-mix(in srgb, var(--accent) 22%, transparent)",borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:"var(--accent)",fontSize:14,marginBottom:4}}>
          DATEV bleibt Ihre Buchhaltung
        </div>
        <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.65}}>
          Kanzlei Automation steuert Mandanten, Portal und Nachfassen. Exporte gehen <strong>zu</strong> DATEV —
          wir ersetzen keine Fibu. Nur aktivierte, produktive Schnittstellen sind schaltbar.
        </div>
      </div>

      <SectionTitle>Produktiv verfügbar</SectionTitle>

      <Row label="DATEV-Export (Pilot)" description="Buchungsstapel + Stammdaten (EXTF v700) — Export in DATEV prüfen, kein Live-Sync">
        <Toggle value={s.datev_export_aktiv??true}
          onChange={v=>save("datev_export_aktiv",v)}/>
      </Row>
      {s.datev_export_aktiv&&(
        <Row label="DATEV Beraternummer">
          <input type="text" defaultValue={s.datev_berater_nr||""}
            placeholder="123456"
            onBlur={e=>save("datev_berater_nr",e.target.value)}
            style={{width:140,background:"var(--bg)",border:`1px solid var(--border2)`,
              borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,
              outline:"none",fontFamily:"'DM Mono',monospace"}}/>
        </Row>
      )}
      <Row label="ELSTER XML" description="Steuer-XML erzeugen — Versand über Ihre ELSTER-Software">
        <Toggle value={s.elster_aktiv??true} onChange={v=>save("elster_aktiv",v)}/>
      </Row>
      <Row label="Kontoauszug-Import (CSV)"
           description="Manueller Upload unter API /bank/import — kein Live-Banking">
        <span style={{fontSize:12,color:"var(--green)"}}>✓ verfügbar</span>
      </Row>

      <SectionTitle>Microsoft 365</SectionTitle>
      {m365 ? (
        <div style={{
          fontSize: 12, color: "var(--text2)", lineHeight: 1.55, marginBottom: 12,
          padding: "12px 14px", borderRadius: 10, background: "var(--bg3)", border: "1px solid var(--border)",
        }}>
          {m365.graph_verbunden ? (
            <>
              <span style={{ color: "var(--green)", fontWeight: 600 }}>✓ Graph verbunden</span>
              {m365.graph_connected_email ? ` · ${m365.graph_connected_email}` : ""}
            </>
          ) : (
            <>
              Login-OAuth: {m365.oauth_login_verfuegbar ? "✓ konfiguriert" : "— .env fehlt"} ·
              Kalender: {m365.kalender_sync_status} · Postfach: {m365.postfach_status}
            </>
          )}
          <div style={{ marginTop: 6, color: "var(--text3)" }}>{m365.naechster_schritt}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
            {!m365.graph_verbunden ? (
              <button
                type="button"
                disabled={!m365.oauth_login_verfuegbar || m365Busy === "connect"}
                onClick={handleM365Connect}
                style={{
                  padding: "7px 14px", borderRadius: 8, border: "none", cursor: "pointer",
                  background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 600,
                  opacity: !m365.oauth_login_verfuegbar ? 0.5 : 1,
                }}
              >
                {m365Busy === "connect" ? "Weiterleitung…" : "Microsoft 365 verbinden"}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  disabled={m365Busy === "preview"}
                  onClick={handleCalPreview}
                  style={{
                    padding: "7px 14px", borderRadius: 8, border: "1px solid var(--border2)",
                    background: "var(--bg)", color: "var(--text)", fontSize: 12, cursor: "pointer",
                  }}
                >
                  {m365Busy === "preview" ? "Lade…" : "Kalender-Vorschau"}
                </button>
                <button
                  type="button"
                  disabled={m365Busy === "mail" || !s.m365_postfach_readonly_aktiv}
                  onClick={handleMailPreview}
                  style={{
                    padding: "7px 14px", borderRadius: 8, border: "1px solid var(--border2)",
                    background: "var(--bg)", color: "var(--text)", fontSize: 12, cursor: "pointer",
                    opacity: s.m365_postfach_readonly_aktiv ? 1 : 0.55,
                  }}
                >
                  {m365Busy === "mail" ? "Lade…" : "Postfach-Vorschau"}
                </button>
                <button
                  type="button"
                  disabled={m365Busy === "disconnect"}
                  onClick={handleM365Disconnect}
                  style={{
                    padding: "7px 14px", borderRadius: 8, border: "1px solid var(--red, #c44)",
                    background: "transparent", color: "var(--red, #c44)", fontSize: 12, cursor: "pointer",
                  }}
                >
                  Trennen
                </button>
              </>
            )}
          </div>
          {calPreview?.events?.length ? (
            <div style={{ marginTop: 10, fontSize: 11, color: "var(--text3)" }}>
              {calPreview.hinweis}
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {calPreview.events.slice(0, 5).map((ev, i) => (
                  <li key={i}>{ev.subject} — {String(ev.start || "").slice(0, 16)}</li>
                ))}
              </ul>
            </div>
          ) : calPreview?.hinweis ? (
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text3)" }}>{calPreview.hinweis}</div>
          ) : null}
          {mailPreview?.messages?.length ? (
            <div style={{ marginTop: 10, fontSize: 11, color: "var(--text3)" }}>
              {mailPreview.hinweis}
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {mailPreview.messages.slice(0, 5).map((msg, i) => (
                  <li key={i}>
                    {msg.subject}
                    {msg.mandant_vorschlag ? ` → ${msg.mandant_vorschlag}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : mailPreview?.hinweis ? (
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text3)" }}>{mailPreview.hinweis}</div>
          ) : null}
        </div>
      ) : null}
      <Row label="Kalender-Sync (Pilot)" description="Vorbereitet — aktiviert Graph-Anbindung wenn verfügbar">
        <Toggle value={s.m365_kalender_sync_aktiv ?? false} onChange={(v) => save("m365_kalender_sync_aktiv", v)} />
      </Row>
      <Row label="Postfach read-only (Pilot)" description="Eingehende Mandanten-Mails zuordnen — folgt">
        <Toggle value={s.m365_postfach_readonly_aktiv ?? false} onChange={(v) => save("m365_postfach_readonly_aktiv", v)} />
      </Row>
      <Row label="Microsoft-Anmeldung" description="OAuth für Login — Kalender-Sync folgt in M365-Integration">
        <span style={{ fontSize: 12, color: "var(--green)" }}>✓ Login verfügbar</span>
      </Row>

      <SectionTitle>In Entwicklung (nicht aktivierbar)</SectionTitle>
      <div style={{fontSize:12,color:"var(--text3)",marginBottom:10,lineHeight:1.5}}>
        Diese Schalter würden falsche Erwartungen wecken — sie sind bis zur Fertigstellung gesperrt.
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:20}}>
        {ROADMAP.map((r,i)=>(
          <div key={i} style={{background:"var(--bg3)",border:"1px solid var(--border)",borderRadius:10,
            padding:"10px 12px",fontSize:12,color:"var(--text3)",opacity:0.85}}>
            <span style={{marginRight:6}}>{r.icon}</span>{r.label}
          </div>
        ))}
      </div>

      <SectionTitle>API & Webhooks</SectionTitle>

      <Row label="Ausgehende Webhooks (URL)"
           description="Events werden an deine URL gesendet (neue Buchung, Unterschrift, etc.)">
        <input type="url" defaultValue={s.webhook_url||""}
          placeholder="https://mein-system.de/webhook"
          onBlur={e=>save("webhook_url",e.target.value)}
          style={{width:280,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
            color:"var(--text)",padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:"'DM Sans',sans-serif"}}/>
      </Row>

      <Row label="API Rate Limit (Schreibzugriffe)" description="0 = aus. Nur POST/PUT/DELETE zählen — Lese-Polling blockiert nicht. Unter 500 wird ignoriert.">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.api_rate_limit_pro_minute ?? 0} min={0} max={10000}
            onBlur={e=>save("api_rate_limit_pro_minute",parseInt(e.target.value,10)||0)}
            style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
              color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>/min</span>
        </div>
      </Row>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 7. E-MAIL-VERSAND (SMTP pro Kanzlei)
// ═══════════════════════════════════════════════════════════

const SMTP_PRESETS = [
  { label: "Microsoft 365", host: "smtp.office365.com", port: 587 },
  { label: "Google / Gmail", host: "smtp.gmail.com", port: 587 },
  { label: "IONOS", host: "smtp.ionos.de", port: 587 },
  { label: "STRATO", host: "smtp.strato.de", port: 465 },
];

const EmailVersandTab = ({ s, save, setSettings, showToast }) => {
  const [testing, setTesting] = useState(false);
  const userMail = (readAuthed()?.email || "").trim();

  const applyPreset = (p) => {
    setSettings((prev) => ({ ...prev, smtp_host: p.host, smtp_port: p.port }));
    save("smtp_host", p.host);
    save("smtp_port", p.port);
  };

  const runTest = async () => {
    setTesting(true);
    try {
      await testTenantSmtp(userMail || undefined);
      showToast("SMTP-Test gesendet — Postfach prüfen");
    } catch (e) {
      showToast(e.message || "SMTP-Test fehlgeschlagen", "error");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div>
      <div style={{
        background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, transparent), color-mix(in srgb, var(--blue) 6%, transparent))",
        border: "1px solid color-mix(in srgb, var(--accent) 22%, transparent)",
        borderRadius: 14, padding: "14px 18px", marginBottom: 20,
      }}>
        <div style={{ fontWeight: 600, color: "var(--accent)", fontSize: 14, marginBottom: 4 }}>
          Ihr Kanzlei-Postfach — nicht das des Software-Betreibers
        </div>
        <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.65 }}>
          Jede Steuerkanzlei hinterlegt hier SMTP-Server, Benutzer und App-Passwort.
          Mandanten-E-Mails gehen von <strong>Ihrer</strong> Adresse aus.
          Microsoft 365 OAuth folgt später — bis dahin App-Passwort oder SMTP-Zugang des Providers.
        </div>
      </div>

      <SectionTitle>SMTP-Verbindung</SectionTitle>

      <Row label="E-Mail-Versand aktiv" description="Ohne Aktivierung werden keine Mandanten-Mails versendet">
        <Toggle value={!!s.smtp_aktiv} onChange={(v) => save("smtp_aktiv", v)} />
      </Row>

      <Row label="Vorlage" description="Übliche Provider — Host/Port werden übernommen">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {SMTP_PRESETS.map((p) => (
            <Btn key={p.label} variant="subtle" size="sm" onClick={() => applyPreset(p)}>{p.label}</Btn>
          ))}
        </div>
      </Row>

      <Row label="SMTP-Server">
        <input type="text" value={s.smtp_host ?? ""} placeholder="smtp.office365.com"
          onChange={(e) => setSettings((prev) => ({ ...prev, smtp_host: e.target.value }))}
          onBlur={(e) => save("smtp_host", e.target.value)}
          style={{ width: 280, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
            color: "var(--text)", padding: "7px 11px", fontSize: 13, outline: "none" }} />
      </Row>

      <Row label="Port" description="587 (STARTTLS) oder 465 (SSL)">
        <input type="number" value={s.smtp_port ?? 587} min={1} max={65535}
          onChange={(e) => setSettings((prev) => ({ ...prev, smtp_port: parseInt(e.target.value, 10) || 587 }))}
          onBlur={(e) => save("smtp_port", parseInt(e.target.value, 10) || 587)}
          style={{ width: 90, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
            color: "var(--text)", padding: "7px 10px", fontSize: 14, textAlign: "center", outline: "none" }} />
      </Row>

      <Row label="STARTTLS">
        <Toggle value={s.smtp_tls !== false} onChange={(v) => save("smtp_tls", v)} />
      </Row>

      <Row label="Benutzer (E-Mail)" description="Muss mit dem Postfach übereinstimmen, von dem versendet wird">
        <input type="email" value={s.smtp_user ?? ""} placeholder="info@ihre-kanzlei.de"
          onChange={(e) => setSettings((prev) => ({ ...prev, smtp_user: e.target.value }))}
          onBlur={(e) => save("smtp_user", e.target.value)}
          style={{ width: 280, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
            color: "var(--text)", padding: "7px 11px", fontSize: 13, outline: "none" }} />
      </Row>

      <Row label="Passwort / App-Passwort" description={s.smtp_pass_gesetzt ? "Gespeichert — nur bei Änderung neu eintragen" : "Vom Mail-Provider erzeugen (nicht Ihr Login-Passwort)"}>
        <input type="password" autoComplete="new-password"
          placeholder={s.smtp_pass_gesetzt ? "********" : ""}
          onBlur={(e) => {
            const v = e.target.value.trim();
            if (v && v !== "********") save("smtp_pass", v);
          }}
          style={{ width: 280, background: "var(--bg)", border: "1px solid var(--border2)", borderRadius: 8,
            color: "var(--text)", padding: "7px 11px", fontSize: 13, outline: "none" }} />
      </Row>

      <Row label="Verbindung testen" description={userMail ? `Test an ${userMail}` : "Test an Ihre Login-E-Mail"}>
        <Btn variant="primary" loading={testing} disabled={!s.smtp_aktiv} onClick={runTest}>
          Test-E-Mail senden
        </Btn>
      </Row>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 8. KANZLEI-DATEN
// ═══════════════════════════════════════════════════════════

const KanzleiTab = ({s, save, setSettings, sysInfo, readiness, onExport, onReset}) => (
  <div>
    <SectionTitle>Kanzlei-Stammdaten</SectionTitle>

    {[
      {id:"k_name",   key:"kanzlei_name",         label:"Kanzlei-Name",       ph:"Dr. Müller Steuerberatung GmbH"},
      {id:"k_abs",    key:"email_absender_name",  label:"Name im Postfach des Empfängers",
        ph:"Dr. Müller Steuerberatung", description:"So erscheint der Absender bei Mandanten-E-Mails (nicht „Kanzlei Automation“). Leer = Kanzlei-Name."},
      {id:"k_email",  key:"kanzlei_email",         label:"E-Mail-Adresse der Kanzlei", ph:"kanzlei@mail.de", type:"email",
        description:"Kontakt in Mailtext & Signatur. Versand-Adresse = Tab „E-Mail-Versand“ (smtp_user)."},
      {id:"k_telefon",key:"kanzlei_telefon",       label:"Telefon",            ph:"+49 89 123456"},
      {id:"k_web",    key:"kanzlei_website",       label:"Website",            ph:"https://kanzlei.de",        type:"url"},
      {id:"k_adr",    key:"kanzlei_adresse",       label:"Adresse"},
      {id:"k_stnr",   key:"kanzlei_steuernummer",  label:"Kanzlei-StNr.",     ph:"123/456/78901"},
      {id:"k_iban",   key:"kanzlei_iban",          label:"IBAN",               ph:"DE89 3704 0044 ...",  mono:true},
      {id:"k_bic",    key:"kanzlei_bic",           label:"BIC",                mono:true},
    ].map(f=>(
      <Row key={f.key} label={f.label} description={f.description}>
        <input id={f.id} type={f.type||"text"} value={s[f.key] ?? ""}
          placeholder={f.ph||""}
          onChange={e=>setSettings(p=>({...p,[f.key]:e.target.value}))}
          onBlur={e=>{ const v=e.target.value; if(v!==(s[f.key]??"")) save(f.key,v); }}
          style={{width:260,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
            color:"var(--text)",padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:f.mono?"'DM Mono',monospace":"'DM Sans',sans-serif"}}/>
      </Row>
    ))}

    <Row label="Stundensatz (€/h)" description="Für Profit-Monitor und Zeiterfassung">
      <div style={{display:"flex",gap:6,alignItems:"center"}}>
        <input type="number" defaultValue={s.stundensatz||150} min={50} max={500}
          onBlur={e=>save("stundensatz",parseFloat(e.target.value))}
          style={{width:90,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
            color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
            outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
        <span style={{fontSize:12,color:"var(--text3)"}}>€/Stunde</span>
      </div>
    </Row>

    <SectionTitle>Email-Signatur</SectionTitle>
    <textarea id="email_sig" rows={4} value={s.email_signatur||""}
      onChange={e=>setSettings(p=>({...p,email_signatur:e.target.value}))}
      onBlur={e=>save("email_signatur",e.target.value)}
      style={{width:"100%",background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:10,
        color:"var(--text)",padding:"9px 13px",fontSize:13,fontFamily:"'DM Sans',sans-serif",
        resize:"vertical",outline:"none",marginBottom:12}}/>

    <SectionTitle>Backup-Konfiguration</SectionTitle>
    <Row label="Automatische Backups" description="Daten regelmäßig sichern">
      <Toggle value={s.backup_aktiv??true} onChange={v=>save("backup_aktiv",v)}/>
    </Row>
    {s.backup_aktiv!==false&&(<>
      <Row label="Backup-Intervall">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.backup_interval_stunden||24} min={1} max={168}
            onBlur={e=>save("backup_interval_stunden",parseInt(e.target.value))}
            style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
              color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>Stunden</span>
        </div>
      </Row>
      <Row label="Aufbewahrung (Anzahl)">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.backup_anzahl_aufbewahren||30} min={1} max={365}
            onBlur={e=>save("backup_anzahl_aufbewahren",parseInt(e.target.value))}
            style={{width:70,background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
              color:"var(--text)",padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:"var(--text3)"}}>Backups</span>
        </div>
      </Row>
    </>)}

    <SectionTitle>System-Status</SectionTitle>

    {sysInfo&&(
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:16}}>
        {[
          ["Datenbankgröße",  `${sysInfo.groesse_kb||0} KB`],
          ["Backups",          sysInfo.backup_anzahl||0],
          ["Letztes Backup",   sysInfo.letztes_backup||"—"],
          ["Mandanten",        sysInfo.mandanten_gesamt||0],
          ["Aufgaben gesamt",  sysInfo.aufgaben_gesamt||0],
          ["Completion Rate",  `${sysInfo.completion_rate||0}%`],
        ].map(([l,v])=>(
          <div key={l} style={{background:"var(--bg3)",borderRadius:8,padding:"8px 12px",
            display:"flex",justifyContent:"space-between",
            border:`1px solid var(--border)`}}>
            <span style={{fontSize:12,color:"var(--text3)"}}>{l}</span>
            <span style={{fontSize:12,fontWeight:600,color:"var(--text)"}}>{String(v)}</span>
          </div>
        ))}
      </div>
    )}

    {readiness && (
      <>
        <SectionTitle>Systemstatus</SectionTitle>
        <div style={{
          marginBottom:14,
          background:"linear-gradient(135deg, color-mix(in srgb, var(--blue) 10%, transparent), color-mix(in srgb, var(--accent) 8%, transparent))",
          border:`1px solid var(--border2)`,
          borderRadius:12,
          padding:"12px 14px",
        }}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
            <div style={{fontSize:13,color:"var(--text2)"}}>Gesamt-Score (0–100)</div>
            <div style={{fontSize:24,fontFamily:"'DM Serif Display',serif",color:"var(--accent)"}}>
              {readiness.readiness_score ?? 0}
            </div>
          </div>
          <div style={{height:6,background:"var(--bg3)",borderRadius:6,overflow:"hidden"}}>
            <div style={{
              width:`${Math.max(0, Math.min(100, readiness.readiness_score || 0))}%`,
              height:"100%",
              background:(readiness.readiness_score || 0) >= 80 ? "var(--green)" : (readiness.readiness_score || 0) >= 60 ? "var(--orange)" : "var(--red)",
            }}/>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:10}}>
            <div style={{fontSize:12,color:"var(--text3)"}}>
              E-Mail-Queue (24h): <span style={{color:"var(--text)"}}>{readiness.health?.email_outbox_dead_24h ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:"var(--text3)"}}>
              Webhook-Fehler (24h): <span style={{color:"var(--text)"}}>{readiness.health?.webhook_failures_24h ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:"var(--text3)"}}>
              API-Schlüssel aktiv: <span style={{color:"var(--text)"}}>{readiness.health?.api_keys_aktiv ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:"var(--text3)"}}>
              Webhooks aktiv: <span style={{color:"var(--text)"}}>{readiness.health?.webhooks_aktiv ?? 0}</span>
            </div>
          </div>
          {!!(readiness.alerts || []).length && (
            <div style={{marginTop:10}}>
              {(readiness.alerts || []).slice(0, 3).map((a, i) => (
                <div key={i} style={{
                  fontSize:12,
                  color:a.severity==="high"?"var(--red)":a.severity==="medium"?"var(--orange)":"var(--text2)",
                  marginTop:4,
                }}>
                  - {a.title}
                </div>
              ))}
            </div>
          )}
        </div>
      </>
    )}

    <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
      <Btn onClick={onExport} variant="subtle">⬇ Vollständiger Datenexport (JSON)</Btn>
      <Btn onClick={onReset} variant="danger">Settings zurücksetzen</Btn>
    </div>
  </div>
);

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

const SETTINGS_RAIL_KEY = "kanzlei_settings_tab_rail_width";

export default function Settings() {
  const lw = useContentLayoutWidth();
  const stackTabs = lw < 720;
  const [tabRail, setTabRail] = useState(() => {
    if (typeof window === "undefined") return 220;
    try {
      const n = Number(localStorage.getItem(SETTINGS_RAIL_KEY));
      if (Number.isFinite(n)) return Math.min(340, Math.max(160, n));
    } catch {}
    return 220;
  });
  useEffect(() => {
    try {
      localStorage.setItem(SETTINGS_RAIL_KEY, String(tabRail));
    } catch {}
  }, [tabRail]);

  const [settings,  setSettings]  = useState(null);
  const [sysInfo,   setSysInfo]   = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [,          setSaving]    = useState({});
  const [toast,     setToast]     = useState(null);
  const [tab,       setTab]       = useState(() => {
    try {
      const open = sessionStorage.getItem("kanzlei_settings_open_tab");
      if (open && TABS.some((t) => t.id === open)) return open;
    } catch {}
    return "email";
  });
  const [formEpoch, setFormEpoch] = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  const [applyingS, setApplyingS] = useState({});
  const [readiness, setReadiness] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [kpiStats, setKpiStats] = useState({
    mandanten: 0,
    gesamtUmsatz: 0,
    offeneAufgaben: 0,
    kritischeAufgaben: 0,
    fehlendeDokumente: 0,
    kontaktStille: 0,
  });

  const showToast = (text, type="success") => {
    setToast({text,type});
    setTimeout(()=>setToast(null),3000);
  };

  const laden = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [s,si,ss,sr,sk] = await Promise.allSettled([
        getSettings(),
        getSystemInfo(),
        getSettingsSuggestions(),
        getSaasReadiness(),
        getKpis(),
      ]);
      if (s.status === "fulfilled") {
        setSettings(unwrapSettingsPayload(s.value));
        setFormEpoch((e) => e + 1);
      } else {
        setSettings({});
        const reason = s.reason?.message || "unbekannter Fehler";
        setLoadError(`Einstellungen konnten nicht geladen werden (${reason}).`);
      }
      if(si.status==="fulfilled") setSysInfo(si.value?.data ?? si.value ?? null);
      if(ss.status==="fulfilled") {
        const sug = ss.value?.vorschlaege || ss.value?.data?.vorschlaege || [];
        setSuggestions(Array.isArray(sug) ? sug : []);
      } else {
        setSuggestions([]);
      }
      if(sr.status==="fulfilled") {
        const r = sr.value?.data || sr.value;
        setReadiness(r || null);
      } else {
        setReadiness(null);
      }
      if (sk.status === "fulfilled") {
        const arr = Array.isArray(sk.value) ? sk.value : (sk.value?.data?.eintraege || sk.value?.eintraege || []);
        const gesamtUmsatz = (Array.isArray(arr) ? arr : []).reduce((sum, item) => sum + Number(item?.umsatz || 0), 0);
        const mandanten = Array.isArray(arr) ? arr.length : 0;
        const offeneAufgaben = (Array.isArray(arr) ? arr : []).reduce((sum, item) => sum + Number(item?.aufgaben_offen || 0), 0);
        const kritischeAufgaben = (Array.isArray(arr) ? arr : []).reduce((sum, item) => sum + Number(item?.aufgaben_ueberfaellig || 0), 0);
        const fehlendeDokumente = (Array.isArray(arr) ? arr : []).reduce((sum, item) => sum + Number(item?.fehlende_dokumente || 0), 0);
        const kontaktStille = (Array.isArray(arr) ? arr : []).filter((item) => Number(item?.tage_ohne_antwort || 0) >= 14).length;
        setKpiStats({ mandanten, gesamtUmsatz, offeneAufgaben, kritischeAufgaben, fehlendeDokumente, kontaktStille });
      } else {
        setKpiStats({
          mandanten: 0,
          gesamtUmsatz: 0,
          offeneAufgaben: 0,
          kritischeAufgaben: 0,
          fehlendeDokumente: 0,
          kontaktStille: 0,
        });
      }
    } catch(e){
      console.error(e);
      setSettings({});
      setLoadError("Einstellungen konnten nicht geladen werden. Bitte erneut versuchen.");
      setKpiStats({
        mandanten: 0,
        gesamtUmsatz: 0,
        offeneAufgaben: 0,
        kritischeAufgaben: 0,
        fehlendeDokumente: 0,
        kontaktStille: 0,
      });
    }
    finally { setLoading(false); }
  },[]);

  useEffect(()=>{ laden(); },[laden]);

  useEffect(() => {
    try {
      const aliases = {
        workflow: "automation",
        compliance: "team",
        schnittstellen: "integrationen",
        ki: "erweitert",
        billing: "erweitert",
      };
      let open = sessionStorage.getItem("kanzlei_settings_open_tab");
      if (open && aliases[open]) open = aliases[open];
      if (open && TABS.some((t) => t.id === open)) {
        setTab(open);
        sessionStorage.removeItem("kanzlei_settings_open_tab");
      }
    } catch {}
  }, []);

  const isSettingsAdmin = hasRoleReal(["owner", "admin"]);
  const visibleTabs = TABS.filter((t) => !t.adminOnly || isSettingsAdmin);

  useEffect(() => {
    if (!isSettingsAdmin && ADMIN_TABS.has(tab)) setTab("email");
  }, [tab, isSettingsAdmin]);

  const save = useCallback(async (key, wert) => {
    setSaving(p=>({...p,[key]:true}));
    try {
      const res = await updateSetting(key, wert);
      const bestaetigt = res?.bestaetigt ?? res?.data?.bestaetigt ?? res?.wert ?? wert;
      const fresh = await getSettings();
      setSettings(fresh);
      setFormEpoch((e) => e + 1);
      if (
        String(key).startsWith("rollen_nav")
        || String(key).startsWith("kanzlei_")
        || String(key).startsWith("email_")
      ) {
        try {
          window.dispatchEvent(new CustomEvent("kanzlei-settings-changed"));
        } catch {}
      }
      showToast(`✓ Gespeichert: ${String(bestaetigt).slice(0, 48)}`);
    } catch(e) {
      showToast(e.message||"Fehler","error");
    } finally {
      setSaving(p=>({...p,[key]:false}));
    }
  },[]);

  const handleReset = async () => {
    if(!window.confirm("Alle Einstellungen zurücksetzen?")) return;
    try { await resetSettings(); await laden(); showToast("✓ Zurückgesetzt"); }
    catch(e) { showToast(e.message,"error"); }
  };

  const handleExport = async () => {
    try {
      const data = await getSystemExport();
      const blob = new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `kanzlei_backup_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      showToast("✓ Export gestartet");
    } catch(e) { showToast(e.message,"error"); }
  };

  const applySuggestionNow = async (sug) => {
    const sid = sug?.id;
    if (!sid) return;
    setApplyingS((p) => ({ ...p, [sid]: true }));
    try {
      const r = await applySettingsSuggestion(sid);
      const key = r?.key || r?.data?.key || sug?.empfehlung?.key;
      const wert = r?.wert ?? r?.data?.wert ?? sug?.empfehlung?.wert;
      if (key) setSettings((p) => ({ ...p, [key]: wert }));
      showToast(`✓ Vorschlag "${sug.titel}" angewendet`);
      await laden();
    } catch (e) {
      showToast(e.message || "Vorschlag konnte nicht angewendet werden", "error");
    } finally {
      setApplyingS((p) => ({ ...p, [sid]: false }));
    }
  };

  if(loading) return (
    <div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",
      background:"var(--bg)"}}>
      <style>{`${FONTS} @keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <div style={{width:32,height:32,borderRadius:"50%",
        border:`2px solid var(--border2)`,borderTopColor:"var(--accent)",
        animation:"spin 0.7s linear infinite"}}/>
    </div>
  );

  const CONTENT = {
    email:           <EmailVersandTab s={settings} save={save} setSettings={setSettings} showToast={showToast} />,
    automation:      <WorkflowTab s={settings} save={save}/>,
    portal:          <PortalTab s={settings} save={save}/>,
    kanzlei:         <KanzleiTab s={settings} save={save} setSettings={setSettings} sysInfo={sysInfo}
                      readiness={readiness}
                       onExport={handleExport} onReset={handleReset}/>,
    team:            <TeamTab s={settings} save={save} showToast={showToast}/>,
    integrationen:   <SchnittstellenTab s={settings} save={save} showToast={showToast}/>,
    erweitert:       <ErweitertTab s={settings} save={save} kpiStats={kpiStats}/>,
  };

  return (
    <div style={{flex:1,background:"var(--bg)",display:"flex",flexDirection:"column",
      overflowY:"hidden",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        ${FONTS}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
        input:focus,textarea:focus,select:focus{outline:none;border-color:var(--accent)!important}
      `}</style>

      {/* Toast */}
      {toast&&(
        <div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
          background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
          fontSize:13,fontWeight:500,animation:"slideIn 0.25s ease",
          border:`1px solid ${toast.type==="error"?"color-mix(in srgb, var(--red) 32%, transparent)":"color-mix(in srgb, var(--green) 32%, transparent)"}`,
          borderLeft:`3px solid ${toast.type==="error"?"var(--red)":"var(--green)"}`,
          boxShadow:"var(--shadow-elev)"}}>
          {toast.text}
        </div>
      )}

      {/* Header */}
      <div style={{background:"var(--bg2)",borderBottom:"1px solid var(--border)",
        padding:stackTabs ? "16px max(14px, env(safe-area-inset-right)) 16px max(14px, env(safe-area-inset-left))" : "20px 32px",
        flexShrink:0}}>
        <div style={{fontFamily:"var(--font-head)",fontSize:stackTabs?20:24,
          color:"var(--text)",marginBottom:4}}>Einstellungen</div>
        <div style={{fontSize:12,color:"var(--text3)",lineHeight:1.45}}>
          Zuerst E-Mail konfigurieren — dann laufen Erinnerungen, Portal und Eskalation automatisch.
        </div>
      </div>

      {/* Layout: Sidebar + Content */}
      <div style={{flex:1,display:"flex",flexDirection:stackTabs?"column":"row",overflow:"hidden",minHeight:0}}>

        {/* Sidebar Tabs */}
        <div style={stackTabs ? {
          width:"100%",background:"var(--bg2)",borderRight:"none",borderBottom:"1px solid var(--border)",
          padding:"10px 8px",overflowX:"auto",overflowY:"hidden",flexShrink:0,
          display:"flex",flexDirection:"row",flexWrap:"nowrap",gap:8,
          WebkitOverflowScrolling:"touch",
        } : {
          width:tabRail,minWidth:160,maxWidth:340,background:"var(--bg2)",borderRight:"1px solid var(--border)",
          padding:"16px 8px",overflowY:"auto",overflowX:"hidden",flexShrink:0,
          display:"flex",flexDirection:"column",
        }}>
          {visibleTabs.map(t=>{
            const aktiv = tab===t.id;
            return (
              <button key={t.id} onClick={()=>setTab(t.id)} style={{
                ...(stackTabs ? {
                  flex:"0 0 auto",whiteSpace:"nowrap",width:"auto",
                } : { width:"100%" }),
                display:"flex",alignItems:"center",gap:10,
                padding:stackTabs?"8px 12px":"10px 12px",borderRadius:10,border:"none",
                background:aktiv?"var(--bg3)":"transparent",
                color:aktiv?"var(--accent)":"var(--text2)",cursor:"pointer",
                fontFamily:"'DM Sans',sans-serif",fontSize:stackTabs?12:13,
                fontWeight:aktiv?600:400,marginBottom:stackTabs?0:2,textAlign:"left",
                transition:"all 0.15s",
                borderLeft:stackTabs ? "none" : (aktiv?"3px solid var(--accent)":"3px solid transparent"),
                borderBottom:stackTabs ? (aktiv?"2px solid var(--accent)":"2px solid transparent") : "none",
              }}>
                <span style={{fontSize:16}}>{t.icon}</span>
                <span style={{flex:stackTabs?0:1,whiteSpace:stackTabs?"nowrap":"normal"}}>{t.label}</span>
                {t.badge&&(
                  <span style={{fontSize:9,padding:"2px 6px",borderRadius:8,
                    background:"color-mix(in srgb, var(--accent) 22%, var(--bg3))",color:"var(--accent)",fontWeight:700,
                    letterSpacing:"0.04em",textTransform:"uppercase"}}>
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {!stackTabs ? (
          <div
            role="separator"
            aria-orientation="vertical"
            title="Breite ziehen"
            onPointerDown={(e) => {
              e.preventDefault();
              const startX = e.clientX;
              const startW = tabRail;
              const onMove = (ev) => {
                const dx = ev.clientX - startX;
                setTabRail(Math.min(340, Math.max(160, startW + dx)));
              };
              const onUp = () => {
                window.removeEventListener("pointermove", onMove);
                window.removeEventListener("pointerup", onUp);
                document.body.style.cursor = "";
                document.body.style.userSelect = "";
              };
              document.body.style.cursor = "col-resize";
              document.body.style.userSelect = "none";
              window.addEventListener("pointermove", onMove);
              window.addEventListener("pointerup", onUp);
            }}
            style={{
              width: 10,
              flexShrink: 0,
              cursor: "col-resize",
              background: "linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 12%, transparent), transparent)",
              touchAction: "none",
            }}
          />
        ) : null}

        {/* Content */}
        <div style={{
          flex:1,overflowY:"auto",overflowX:"hidden",minWidth:0,
          padding:stackTabs ? "16px max(14px, env(safe-area-inset-right)) 24px max(14px, env(safe-area-inset-left))" : "24px 32px",
        }}>
          <div style={{
            marginBottom: 18,
            padding: "14px 16px",
            borderRadius: 14,
            border: "1px solid var(--border2)",
            background: "var(--bg2)",
          }}>
            <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 16, color: "var(--text)", marginBottom: 4 }}>
              Erscheinungsbild
            </div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 12 }}>
              Hell, dunkel oder automatisch (Systemeinstellung). Gilt für die Hauptansicht; Formulare folgen schrittweise.
            </div>
            <ThemeQuickSwitch />
          </div>
          {suggestions.length > 0 && (
            <div style={{
              marginBottom:18,
              background:"linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, transparent), color-mix(in srgb, var(--blue) 6%, transparent))",
              border:"1px solid color-mix(in srgb, var(--accent) 26%, transparent)",
              borderRadius:14,
              padding:"14px 16px",
            }}>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:"var(--text)",marginBottom:6}}>
                Empfohlene Optimierungen
              </div>
              <div style={{fontSize:12,color:"var(--text2)",marginBottom:12}}>
                Basierend auf den letzten 7 Tagen Nutzung.
              </div>
              <div style={{display:"grid",gap:10}}>
                {suggestions.map((sug) => (
                  <div key={sug.id} style={{
                    background:"var(--bg2)",
                    border:`1px solid var(--border2)`,
                    borderRadius:10,
                    padding:"10px 12px",
                  }}>
                    <div style={{display:"flex",justifyContent:"space-between",gap:10,alignItems:"flex-start"}}>
                      <div style={{minWidth:0}}>
                        <div style={{fontSize:14,color:"var(--text)",fontWeight:600}}>{sug.titel}</div>
                        <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>{sug.grund}</div>
                        <div style={{fontSize:11,color:"var(--text3)",marginTop:6}}>
                          Empfehlung: <span style={{color:"var(--accent)"}}>{sug.empfehlung?.key}</span> = {String(sug.empfehlung?.wert)}
                        </div>
                        <div style={{fontSize:11,color:"var(--text3)",marginTop:2}}>
                          Confidence: {Math.round((sug.confidence || 0) * 100)}% · Signal: {sug.signal_count || 0}
                        </div>
                      </div>
                      <Btn
                        size="sm"
                        variant="success"
                        loading={!!applyingS[sug.id]}
                        onClick={() => applySuggestionNow(sug)}
                      >
                        Anwenden
                      </Btn>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {loadError && (
            <div style={{
              background:"color-mix(in srgb, var(--red) 12%, var(--bg3))",
              border:"1px solid color-mix(in srgb, var(--red) 35%, transparent)",
              borderRadius:12,
              padding:"14px 16px",
              color:"var(--red)",
              fontSize:13,
              marginBottom:16,
            }}>
              {loadError}
              <div style={{marginTop:10}}>
                <Btn variant="ghost" size="sm" onClick={laden}>Erneut laden</Btn>
              </div>
            </div>
          )}
          <div key={`settings-tab-${tab}-${formEpoch}`}>
            {CONTENT[tab]}
          </div>
        </div>
      </div>
    </div>
  );
}