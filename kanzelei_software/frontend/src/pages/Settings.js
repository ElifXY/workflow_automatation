// ============================================================
// KANZLEI AI — EINSTELLUNGEN v3.0 (MILLIARDEN-EDITION)
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

import { useEffect, useState, useCallback, useRef } from "react";
import {
  getSettings,
  updateSetting,
  resetSettings,
  getSystemInfo,
  getSystemExport,
  getSaasReadiness,
  getSettingsSuggestions,
  applySettingsSuggestion,
} from "../api";

const C = {
  red:"#e05555", orange:"#e08c45", green:"#5cb87a", blue:"#5b8de8",
  accent:"#c8a96e", purple:"#9b72e8",
  text:"#e8eaf0", text2:"#8b91a0", text3:"#555d6e",
  bg:"#0b0d11", bg2:"#111419", bg3:"#181c24",
  border:"rgba(255,255,255,0.07)", border2:"rgba(255,255,255,0.14)",
};

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');`;

// ─── Tabs ────────────────────────────────────────────────────
const TABS = [
  { id:"ki",          label:"KI-Konfiguration",      icon:"🧠", badge:"Herzstück" },
  { id:"workflow",    label:"Workflow-Designer",      icon:"⚙",  badge:null },
  { id:"portal",      label:"Mandanten-Portal",       icon:"📱",  badge:null },
  { id:"billing",     label:"Monetarisierung",        icon:"💰",  badge:"Umsatz-Hebel" },
  { id:"compliance",  label:"Compliance & Security",  icon:"🛡",  badge:null },
  { id:"schnittstellen",label:"Schnittstellen",       icon:"🔌",  badge:"API-Center" },
  { id:"kanzlei",     label:"Kanzlei-Daten",         icon:"🏢",  badge:null },
];

// ─── Primitives ───────────────────────────────────────────────
const Btn = ({children,onClick,variant="ghost",size="md",loading=false,disabled=false,style={}}) => {
  const vs = {
    primary:{background:C.accent,color:"#1a1200",border:"none"},
    ghost:{background:"transparent",color:C.text2,border:`1px solid ${C.border2}`},
    subtle:{background:C.bg3,color:C.text2,border:`1px solid ${C.border}`},
    success:{background:C.green+"18",color:C.green,border:`1px solid ${C.green}30`},
    danger:{background:C.red+"18",color:C.red,border:`1px solid ${C.red}30`},
  };
  const ss={xs:"4px 9px",sm:"6px 13px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,
    padding:ss[size],fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading||disabled?"not-allowed":"pointer",
    opacity:loading||disabled?0.5:1,transition:"all 0.15s",
    fontFamily:"'DM Sans',sans-serif",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",
      border:"2px solid currentColor",borderTopColor:"transparent",
      animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

const Toggle = ({value,onChange,disabled=false}) => (
  <div onClick={!disabled?()=>onChange(!value):undefined} style={{
    width:44,height:24,borderRadius:12,cursor:disabled?"not-allowed":"pointer",
    background:value?C.accent:C.bg3,
    border:`1px solid ${value?C.accent:C.border2}`,
    position:"relative",transition:"all 0.2s",
    opacity:disabled?0.5:1,flexShrink:0,
  }}>
    <div style={{
      position:"absolute",top:2,left:value?22:2,
      width:18,height:18,borderRadius:"50%",
      background:value?"#1a1200":C.text3,transition:"left 0.2s",
    }}/>
  </div>
);

// Schieberegler
const Slider = ({value,onChange,min=0,max=100,step=1,label,suffix="%",color=C.accent}) => (
  <div>
    <div style={{display:"flex",justifyContent:"space-between",marginBottom:6}}>
      <span style={{fontSize:11,color:C.text3,textTransform:"uppercase",letterSpacing:"0.06em"}}>
        {label}
      </span>
      <span style={{fontSize:14,fontWeight:700,color}}>{value}{suffix}</span>
    </div>
    <div style={{position:"relative",height:6,background:C.bg3,borderRadius:4}}>
      <div style={{
        position:"absolute",left:0,top:0,height:"100%",borderRadius:4,
        width:`${(value-min)/(max-min)*100}%`,
        background:`linear-gradient(90deg, ${color}80, ${color})`,
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
                  fontSize:10,color:C.text3}}>
      <span>{min}{suffix}</span><span>{max}{suffix}</span>
    </div>
  </div>
);

// Einstellungs-Zeile
const Row = ({label,description,children,locked=false}) => (
  <div style={{
    display:"flex",justifyContent:"space-between",alignItems:"center",
    padding:"13px 0",borderBottom:`1px solid ${C.border}`,
    opacity:locked?0.6:1,
  }}>
    <div style={{flex:1,paddingRight:20}}>
      <div style={{fontSize:14,fontWeight:500,color:C.text,display:"flex",alignItems:"center",gap:6}}>
        {label}
        {locked&&<span style={{fontSize:10,padding:"1px 6px",borderRadius:8,
          background:C.text3+"20",color:C.text3,fontWeight:400}}>FESTGESCHRIEBEN</span>}
      </div>
      {description&&<div style={{fontSize:12,color:C.text3,marginTop:3,lineHeight:1.5}}>
        {description}
      </div>}
    </div>
    <div style={{flexShrink:0}}>{children}</div>
  </div>
);

const Inp = ({id,defaultValue,onBlur,type="text",placeholder="",width=220,mono=false}) => (
  <input id={id} type={type} defaultValue={defaultValue} placeholder={placeholder}
    onBlur={onBlur}
    style={{
      width,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
      color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
      fontFamily:mono?"'DM Mono',monospace":"'DM Sans',sans-serif",
      transition:"border 0.15s",
    }}/>
);

const SectionTitle = ({children}) => (
  <div style={{
    fontFamily:"'DM Serif Display',serif",fontSize:17,color:C.text,
    marginBottom:16,marginTop:8,paddingBottom:10,
    borderBottom:`1px solid ${C.border}`,
  }}>{children}</div>
);

const Badge = ({children,color=C.accent}) => (
  <span style={{
    fontSize:10,padding:"2px 8px",borderRadius:20,marginLeft:6,
    background:color+"20",color,border:`1px solid ${color}30`,
    fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
  }}>{children}</span>
);

// ═══════════════════════════════════════════════════════════
// 1. KI-KONFIGURATION
// ═══════════════════════════════════════════════════════════

const KITab = ({s, save, saving}) => {
  const [autonomie, setAutonomie] = useState(s.ki_autonomie_grad ?? 75);
  const [autoKonfidenz, setAutoKonfidenz] = useState(s.ki_auto_buchen_ab_konfidenz ?? 92);
  const [reviewKonfidenz, setReviewKonfidenz] = useState(s.ki_review_ab_konfidenz ?? 75);
  const [anomalieBetrag, setAnomalieBetrag] = useState(s.ki_anomalie_betrag_euro ?? 500);

  return (
    <div>
      <div style={{background:`linear-gradient(135deg,${C.accent}10,${C.blue}05)`,
        border:`1px solid ${C.accent}30`,borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:C.accent,fontSize:14,marginBottom:4}}>
          Das Herzstück — KI-Autonomiegrad bestimmt Lohnkosteneinsparung
        </div>
        <div style={{fontSize:13,color:C.text2,lineHeight:1.6}}>
          Bei 92% Konfidenz-Schwellenwert: ~70% aller Buchungen vollautomatisch.
          Spart ca. 4-6 Stunden täglich pro Kanzlei.
        </div>
      </div>

      <SectionTitle>Autonomie & Konfidenz</SectionTitle>

      <div style={{marginBottom:20}}>
        <Slider label="KI-Autonomiegrad" value={autonomie}
          onChange={v=>{setAutonomie(v); save("ki_autonomie_grad",v);}}
          color={autonomie>=80?C.green:autonomie>=50?C.orange:C.text2}
          suffix="%" min={0} max={100} step={5} />
        <div style={{fontSize:12,color:C.text3,marginTop:6,textAlign:"center"}}>
          {autonomie<=20?"Vollständig manuell — alle Buchungen werden geprüft":
           autonomie<=50?"Halbautomatisch — KI schlägt vor, Mensch entscheidet":
           autonomie<=80?"Hochautomatisch — KI bucht, Ausnahmen werden gemeldet":
           "Vollautonom — KI bucht bei hoher Sicherheit ohne Review"}
        </div>
        {/* Echtzeit-Ersparnis-Rechner */}
        {autonomie > 30 && (
          <div style={{
            marginTop:12, background:C.green+"0d",
            border:`1px solid ${C.green}25`, borderRadius:10,
            padding:"10px 14px", display:"grid",
            gridTemplateColumns:"1fr 1fr 1fr", gap:10,
          }}>
            {[
              {l:"Auto-Buchungen", v:`~${Math.round(autonomie*0.7)}%`, c:C.green},
              {l:"Stunden/Tag gespart", v:`~${(autonomie/100*4).toFixed(1)}h`, c:C.blue},
              {l:"€/Monat gespart", v:`~€${Math.round(autonomie/100*4*22*(s.stundensatz||150)).toLocaleString("de")}`, c:C.accent},
            ].map((x,i)=>(
              <div key={i} style={{textAlign:"center"}}>
                <div style={{fontSize:11,color:C.text3,marginBottom:3}}>{x.l}</div>
                <div style={{fontSize:16,fontWeight:700,color:x.c,
                  fontFamily:"'DM Serif Display',serif"}}>{x.v}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Row label="Automatisch buchen ab Konfidenz"
           description="Bei diesem Wert bucht die KI ohne menschliche Prüfung">
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <div style={{width:160}}>
            <Slider label="" value={autoKonfidenz}
              onChange={v=>{setAutoKonfidenz(v); save("ki_auto_buchen_ab_konfidenz",v);}}
              color={C.green} suffix="%" min={75} max={99} step={1}/>
          </div>
        </div>
      </Row>

      <Row label="Review empfohlen ab Konfidenz"
           description="Zwischen diesem Wert und dem Auto-Wert: kurzer menschlicher Check">
        <div style={{width:160}}>
          <Slider label="" value={reviewKonfidenz}
            onChange={v=>{setReviewKonfidenz(v); save("ki_review_ab_konfidenz",v);}}
            color={C.orange} suffix="%" min={50} max={autoKonfidenz-1} step={1}/>
        </div>
      </Row>

      <SectionTitle>Lernkurve & Datenteilung</SectionTitle>

      <Row label="Kanzleiübergreifendes Lernen"
           description="Darf die KI von Mandant A lernen, um Mandant B schneller zu buchen? Der Hebel für Milliarden-Effizienz — jede Kanzlei profitiert von allen anderen.">
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
            style={{width:90,background:C.bg,border:`1px solid ${C.border2}`,
              borderRadius:8,color:C.text,padding:"7px 10px",fontSize:14,
              textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>€</span>
        </div>
      </Row>

      <Row label="Alarm ab Abweichung (%)"
           description="Wenn Betrag X% vom Durchschnitt dieses Lieferanten abweicht → Alarm">
        <div style={{width:140}}>
          <Slider label="" value={s.ki_anomalie_abweichung_pct??30}
            onChange={v=>save("ki_anomalie_abweichung_pct",v)}
            color={C.orange} suffix="%" min={5} max={100} step={5}/>
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
          style={{background:C.bg,border:`1px solid ${C.border2}`,
            borderRadius:8,color:C.text,padding:"7px 11px",fontSize:13,
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
      <div style={{background:C.bg3,borderRadius:12,padding:"14px 18px",marginBottom:16,
        border:`1px solid ${C.border}`}}>
        <div style={{fontSize:13,color:C.text2,lineHeight:1.7}}>
          Fristen-Radar schickt automatische Warnungen an Steuerberater und Mandant.
          Eskalationsstufen definieren wer bei welcher Dringlichkeit informiert wird.
        </div>
      </div>

      {FRISTEN_CONFIG.map(f=>(
        <Row key={f.key} label={f.label} description={f.desc}>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <input type="number" defaultValue={s[f.key]||7} min={1} max={180}
              onBlur={e=>save(f.key,parseInt(e.target.value))}
              style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,
                borderRadius:8,color:C.text,padding:"7px 10px",fontSize:14,
                textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:C.text3}}>Tage</span>
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
        <div key={e.nr} style={{background:C.bg3,borderRadius:10,padding:"14px 16px",
          marginBottom:10,border:`1px solid ${C.border}`}}>
          <div style={{fontWeight:600,color:C.text,fontSize:14,marginBottom:10}}>
            {e.label}
          </div>
          <div style={{display:"flex",gap:12,alignItems:"center",flexWrap:"wrap"}}>
            <div>
              <div style={{fontSize:10,color:C.text3,marginBottom:4}}>Auslöser: nach X Tagen</div>
              <input type="number" defaultValue={s[e.tage_key]||7} min={1}
                onBlur={ev=>save(e.tage_key,parseInt(ev.target.value))}
                style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,
                  borderRadius:8,color:C.text,padding:"7px 10px",fontSize:13,
                  textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            </div>
            <div style={{flex:1}}>
              <div style={{fontSize:10,color:C.text3,marginBottom:4}}>Empfänger (Email)</div>
              <input type="email" defaultValue={s[e.email_key]||""}
                placeholder={`stufe${e.nr}@kanzlei.de`}
                onBlur={ev=>save(e.email_key,ev.target.value)}
                style={{width:"100%",background:C.bg,border:`1px solid ${C.border2}`,
                  borderRadius:8,color:C.text,padding:"7px 11px",fontSize:13,
                  outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            </div>
          </div>
        </div>
      ))}

      <SectionTitle>Automatische Workflows</SectionTitle>

      {[
        {key:"auto_workflow_monatsabschluss", label:"Monatsabschluss automatisch starten"},
        {key:"auto_workflow_lohn",            label:"Lohnabrechnung automatisch starten"},
      ].map(item=>(
        <Row key={item.key} label={item.label}>
          <Toggle value={s[item.key]??true} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 3. MANDANTEN-PORTAL
// ═══════════════════════════════════════════════════════════

const PortalTab = ({s, save}) => (
  <div>
    <div style={{background:`linear-gradient(135deg,${C.blue}10,${C.purple}05)`,
      border:`1px solid ${C.blue}30`,borderRadius:14,padding:"14px 18px",marginBottom:20}}>
      <div style={{fontWeight:600,color:C.blue,fontSize:14,marginBottom:4}}>
        Mandanten-Self-Service — Arbeit delegieren ohne Kontrollverlust
      </div>
      <div style={{fontSize:13,color:C.text2,lineHeight:1.6}}>
        Je mehr der Mandant selbst machen kann, desto mehr Zeit bleibt für wertschöpfende Beratung.
        Sichtbarkeits-Level steuern Transparenz und Bindung.
      </div>
    </div>

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
    <div style={{background:C.bg3,borderRadius:10,padding:"14px 16px",
      border:`1px solid ${C.border}`,marginBottom:12}}>
      <div style={{fontSize:13,color:C.text2,marginBottom:10}}>
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
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,
              borderRadius:8,color:C.text,padding:"7px 10px",fontSize:14,
              textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>MB</span>
        </div>
      </Row>
    </div>
  </div>
);

// ═══════════════════════════════════════════════════════════
// 4. MONETARISIERUNG
// ═══════════════════════════════════════════════════════════

const BillingTab = ({s, save}) => {
  const modell = s.billing_modell || "pauschal";

  const MODELLE = [
    {val:"pauschal",         label:"Pauschal",          desc:"Monatliche Festgebühr pro Kanzlei"},
    {val:"pro_buchung",      label:"Pro KI-Buchung",    desc:"€X pro automatisch verbuchtem Beleg"},
    {val:"pro_mitarbeiter",  label:"Pro Mitarbeiter",   desc:"€X pro Nutzer-Account"},
    {val:"value",            label:"Value Pricing",     desc:"Preis basiert auf Mandanten-Umsatz"},
  ];

  return (
    <div>
      <div style={{background:`linear-gradient(135deg,${C.green}10,${C.accent}05)`,
        border:`1px solid ${C.green}30`,borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:C.green,fontSize:14,marginBottom:4}}>
          Umsatz-Hebel — Automatisierte Abrechnung an Mandanten
        </div>
        <div style={{fontSize:13,color:C.text2,lineHeight:1.6}}>
          Die Kanzlei stellt ihren Mandanten KI-Nutzung direkt in Rechnung.
          Das System rechnet automatisch ab — ohne manuellen Aufwand.
        </div>
      </div>

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
              border:`2px solid ${aktiv?C.accent:C.border}`,
              background:aktiv?C.accent+"10":C.bg3,
              transition:"all 0.15s",
            }}>
              <div style={{fontWeight:600,fontSize:14,color:aktiv?C.accent:C.text,
                marginBottom:4}}>{m.label}</div>
              <div style={{fontSize:12,color:C.text3}}>{m.desc}</div>
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
              style={{width:90,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
                color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
                outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:C.text3}}>€/Monat</span>
          </div>
        </Row>
      )}

      {/* Pro Buchung */}
      {modell==="pro_buchung"&&(
        <Row label="Preis pro KI-Buchung" description="Pro automatisch verarbeitetem Beleg">
          <div style={{display:"flex",gap:6,alignItems:"center"}}>
            <input type="number" defaultValue={s.billing_pro_buchung_euro||0.20} min={0} step={0.01}
              onBlur={e=>save("billing_pro_buchung_euro",parseFloat(e.target.value))}
              style={{width:90,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
                color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
                outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
            <span style={{fontSize:12,color:C.text3}}>€/Buchung</span>
          </div>
        </Row>
      )}

      {/* Value Pricing */}
      {modell==="value"&&(
        <div>
          <div style={{fontSize:12,color:C.text3,marginBottom:12}}>
            Preis basiert auf Jahresumsatz des Mandanten — fairer und skalierbarer.
          </div>
          {[
            {tier:"Tier 1 (bis €100k)",    bis_key:"billing_value_tier_1_bis",  euro_key:"billing_value_tier_1_euro",  def_bis:100000, def_euro:199},
            {tier:"Tier 2 (€100k–€500k)", bis_key:"billing_value_tier_2_bis",  euro_key:"billing_value_tier_2_euro",  def_bis:500000, def_euro:399},
            {tier:"Tier 3 (>€500k)",       bis_key:null,                         euro_key:"billing_value_tier_3_euro",  def_bis:null,   def_euro:699},
          ].map((t,i)=>(
            <div key={i} style={{background:C.bg3,borderRadius:8,padding:"10px 14px",
              marginBottom:8,border:`1px solid ${C.border}`,
              display:"flex",alignItems:"center",gap:16}}>
              <div style={{flex:1,fontSize:13,color:C.text}}>{t.tier}</div>
              <div style={{display:"flex",gap:6,alignItems:"center"}}>
                <input type="number" defaultValue={s[t.euro_key]||t.def_euro} min={0}
                  onBlur={e=>save(t.euro_key,parseFloat(e.target.value))}
                  style={{width:80,background:C.bg,border:`1px solid ${C.border2}`,
                    borderRadius:8,color:C.text,padding:"7px 10px",fontSize:13,
                    textAlign:"center",outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
                <span style={{fontSize:12,color:C.text3}}>€/Monat</span>
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
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>Tage</span>
        </div>
      </Row>

      <Row label="KI-Aufschlag auf Honorar"
           description="Zusätzlicher Aufschlag auf Basis-Honorar für KI-Nutzung">
        <div style={{width:140}}>
          <Slider label="" value={s.billing_ki_aufschlag_prozent||20}
            onChange={v=>save("billing_ki_aufschlag_prozent",v)}
            color={C.green} suffix="%" min={0} max={100} step={5}/>
        </div>
      </Row>

      <SectionTitle>Stripe-Integration</SectionTitle>
      <div style={{background:C.bg3,borderRadius:12,padding:"14px 16px",
        border:`1px solid ${C.border}`}}>
        <Row label="Stripe aktiv" description="Automatische Kreditkartenzahlung von Mandanten">
          <Toggle value={s.billing_stripe_aktiv??false}
            onChange={v=>save("billing_stripe_aktiv",v)}/>
        </Row>
        {s.billing_stripe_aktiv&&(
          <Row label="Stripe Secret Key" description="Unter dashboard.stripe.com/apikeys">
            <input type="password" defaultValue={s.billing_stripe_key||""}
              placeholder="sk_live_..."
              onBlur={e=>save("billing_stripe_key",e.target.value)}
              style={{width:260,background:C.bg,border:`1px solid ${C.border2}`,
                borderRadius:8,color:C.text,padding:"7px 11px",fontSize:13,
                outline:"none",fontFamily:"'DM Mono',monospace"}}/>
          </Row>
        )}
        <div style={{fontSize:12,color:C.text3,marginTop:8,lineHeight:1.6}}>
          Mit Stripe: Mandanten zahlen Honorare automatisch per Lastschrift/Kreditkarte.
          Zahlungsausfall-Rate sinkt auf &lt;0.5%.
        </div>
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 5. COMPLIANCE & SECURITY
// ═══════════════════════════════════════════════════════════

const ComplianceTab = ({s, save}) => {
  const ROLLEN = ["admin","steuerberater","assistent"];

  return (
    <div>
      <SectionTitle>GoBD & Rechtliches</SectionTitle>

      <Row label="GoBD-Konformität" locked description="Gesetzlich vorgeschrieben — nicht änderbar (§ 147 AO)">
        <div style={{color:C.green,fontWeight:600,fontSize:14}}>✓ Aktiv</div>
      </Row>
      <Row label="Audit-Log unveränderbar" locked description="Revisionssichere Protokollierung — Haftungsschutz">
        <div style={{color:C.green,fontWeight:600,fontSize:14}}>✓ Aktiv</div>
      </Row>
      <Row label="Aufbewahrung (Jahre)" description="§ 147 AO: Handelsbücher 10 Jahre">
        <div style={{fontSize:14,fontWeight:600,color:C.text}}>{s.gobd_aufbewahrung_jahre||10} Jahre</div>
      </Row>

      <SectionTitle>Server & Datenschutz</SectionTitle>

      <Row label="Server-Standort" description="DSGVO: Daten müssen in EU gespeichert werden">
        <select value={s.server_standort||"DE"}
          onChange={e=>save("server_standort",e.target.value)}
          style={{background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
            color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:"'DM Sans',sans-serif"}}>
          <option value="DE">🇩🇪 Deutschland (DSGVO)</option>
          <option value="EU">🇪🇺 EU (DSGVO)</option>
          <option value="CH">🇨🇭 Schweiz (DSG)</option>
          <option value="US">🇺🇸 USA (DSGVO-Einschränkungen!)</option>
        </select>
      </Row>

      <Row label="Datenschutzbeauftragter (Email)">
        <input type="email" defaultValue={s.datenschutz_beauftragter||""}
          placeholder="dsb@kanzlei.de"
          onBlur={e=>save("datenschutz_beauftragter",e.target.value)}
          style={{width:220,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
            color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:"'DM Sans',sans-serif"}}/>
      </Row>

      <SectionTitle>Sicherheit</SectionTitle>

      {[
        {key:"2fa_pflicht",           label:"2-Faktor-Authentifizierung Pflicht", desc:"Für alle Mitarbeiter"},
        {key:"verschluesselung_aktiv",label:"Daten-Verschlüsselung",               desc:"AES-256 für gespeicherte Daten"},
        {key:"ip_whitelist_aktiv",    label:"IP-Whitelist aktiv",                  desc:"Nur erlaubte IPs"},
      ].map(item=>(
        <Row key={item.key} label={item.label} description={item.desc}>
          <Toggle value={s[item.key]??false} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}

      <Row label="Session-Timeout">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.session_timeout_minuten||60} min={5} max={480}
            onBlur={e=>save("session_timeout_minuten",parseInt(e.target.value))}
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>Minuten</span>
        </div>
      </Row>

      <SectionTitle>Rollen & Rechte</SectionTitle>

      <div style={{background:C.bg3,borderRadius:12,padding:"14px 16px",
        border:`1px solid ${C.border}`}}>
        <div style={{fontSize:13,color:C.text2,marginBottom:12}}>
          Wer darf was? Extrem feingliedrig — schützt Haftung des Steuerberaters.
        </div>
        {[
          {key:"rollen_lohn_sichtbar",     label:"Löhne & Gehälter sehen",        desc:"Lohnabrechnung einsehen"},
          {key:"rollen_zahlungen_freigabe",label:"Zahlungen freigeben",            desc:"Bank-Überweisungen autorisieren"},
          {key:"rollen_mandant_loeschen",  label:"Mandanten löschen",              desc:"Unwiderrufliche Löschung"},
          {key:"rollen_export_datev",      label:"DATEV-Export durchführen",       desc:"Daten exportieren"},
          {key:"rollen_einstellungen",     label:"Einstellungen ändern",           desc:"Dieses Menü"},
        ].map(item=>(
          <div key={item.key} style={{padding:"10px 0",borderBottom:`1px solid ${C.border}`}}>
            <div style={{fontWeight:500,color:C.text,fontSize:13,marginBottom:4}}>{item.label}</div>
            <div style={{fontSize:11,color:C.text3,marginBottom:6}}>{item.desc}</div>
            <div style={{display:"flex",gap:6}}>
              {ROLLEN.map(rolle=>{
                const aktiv = (s[item.key]||["admin"]).includes(rolle);
                return (
                  <div key={rolle} onClick={()=>{
                    const current = s[item.key]||["admin"];
                    const next = aktiv
                      ? current.filter(r=>r!==rolle)
                      : [...current, rolle];
                    if(next.length > 0) save(item.key, next);
                  }} style={{
                    padding:"4px 12px",borderRadius:20,cursor:"pointer",
                    background:aktiv?C.blue+"20":C.bg,
                    border:`1px solid ${aktiv?C.blue+"50":C.border2}`,
                    color:aktiv?C.blue:C.text3,fontSize:12,fontWeight:aktiv?600:400,
                  }}>{rolle}</div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 6. SCHNITTSTELLEN
// ═══════════════════════════════════════════════════════════

const SchnittstellenTab = ({s, save}) => {
  const CONNECTOREN = [
    {key:"datev",    label:"DATEV",     icon:"🏛", desc:"Export + bidirekt. Import (Premium)",   aktiv_key:"datev_export_aktiv"},
    {key:"elster",   label:"ELSTER",    icon:"⚖",  desc:"Steuerformulare + XML-Versand",         aktiv_key:"elster_aktiv"},
    {key:"shopify",  label:"Shopify",   icon:"🛍",  desc:"E-Commerce Umsätze automatisch buchen", aktiv_key:"shopify_aktiv"},
    {key:"amazon",   label:"Amazon Seller",icon:"📦",desc:"Marketplace-Umsätze importieren",      aktiv_key:"amazon_seller_aktiv"},
    {key:"personio", label:"Personio",  icon:"👥",  desc:"HR-Daten für Lohnabrechnung",           aktiv_key:"personio_aktiv"},
    {key:"lexoffice",label:"LexOffice", icon:"📊",  desc:"Belegdaten synchronisieren",            aktiv_key:"lexoffice_aktiv"},
  ];

  return (
    <div>
      <div style={{background:`linear-gradient(135deg,${C.purple}10,${C.blue}05)`,
        border:`1px solid ${C.purple}30`,borderRadius:14,padding:"14px 18px",marginBottom:20}}>
        <div style={{fontWeight:600,color:C.purple,fontSize:14,marginBottom:4}}>
          API-Center — Ein Milliarden-System ist offen
        </div>
        <div style={{fontSize:13,color:C.text2,lineHeight:1.6}}>
          Je mehr Systeme verbunden sind, desto höher die Klebrigkeit.
          Kanzlei kann nicht mehr wechseln wenn alle Daten hier zusammenfließen.
        </div>
      </div>

      <SectionTitle>Bank-Schnittstellen</SectionTitle>

      {[
        {key:"bank_fints_aktiv",   label:"FinTS (HBCI)",          desc:"Direktverbindung Deutsche Banken"},
        {key:"bank_ebics_aktiv",   label:"EBICS",                  desc:"Electronic Banking Internet Communication Standard"},
        {key:"bank_auto_import",   label:"Automatischer Import",   desc:"Kontoauszüge täglich automatisch laden"},
      ].map(item=>(
        <Row key={item.key} label={item.label} description={item.desc}>
          <Toggle value={s[item.key]??false} onChange={v=>save(item.key,v)}/>
        </Row>
      ))}

      {s.bank_auto_import&&(
        <Row label="Import-Uhrzeit">
          <input type="time" defaultValue={s.bank_import_uhrzeit||"08:00"}
            onBlur={e=>save("bank_import_uhrzeit",e.target.value)}
            style={{background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
              fontFamily:"'DM Sans',sans-serif"}}/>
        </Row>
      )}

      <Row label="DATEV-Export" description="Buchungsstapel + Stammdaten (EXTF v700)">
        <Toggle value={s.datev_export_aktiv??true}
          onChange={v=>save("datev_export_aktiv",v)}/>
      </Row>
      <Row label="DATEV Bidirektional (Import)" description="Premium: Daten aus DATEV zurücklesen">
        <Toggle value={s.datev_import_aktiv??false}
          onChange={v=>save("datev_import_aktiv",v)}/>
      </Row>
      {(s.datev_export_aktiv||s.datev_import_aktiv)&&(
        <Row label="DATEV Beraternummer">
          <input type="text" defaultValue={s.datev_berater_nr||""}
            placeholder="123456"
            onBlur={e=>save("datev_berater_nr",e.target.value)}
            style={{width:140,background:C.bg,border:`1px solid ${C.border2}`,
              borderRadius:8,color:C.text,padding:"7px 11px",fontSize:13,
              outline:"none",fontFamily:"'DM Mono',monospace"}}/>
        </Row>
      )}
      <Row label="ELSTER aktiv" description="Steuerformulare als XML erstellen">
        <Toggle value={s.elster_aktiv??true} onChange={v=>save("elster_aktiv",v)}/>
      </Row>
      <Row label="ELSTER Direktversand"
           description="ERiC SDK von Finanzverwaltung erforderlich — sonst XML-Export">
        <Toggle value={s.elster_direktversand??false}
          onChange={v=>save("elster_direktversand",v)}/>
      </Row>

      <SectionTitle>Drittsystem-Connectoren</SectionTitle>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        {CONNECTOREN.map(c=>(
          <div key={c.key} style={{
            background:C.bg3,border:`1px solid ${s[c.aktiv_key]?C.green+"40":C.border}`,
            borderRadius:12,padding:"14px 16px",
            transition:"all 0.2s",
          }}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}>
              <div style={{display:"flex",gap:8,alignItems:"center"}}>
                <span style={{fontSize:22}}>{c.icon}</span>
                <div>
                  <div style={{fontWeight:600,color:C.text,fontSize:14}}>{c.label}</div>
                  <div style={{fontSize:11,color:C.text3}}>{c.desc}</div>
                </div>
              </div>
              <Toggle value={s[c.aktiv_key]??false}
                onChange={v=>save(c.aktiv_key,v)}/>
            </div>
            {s[c.aktiv_key]&&s[`${c.key}_api_key`]!==undefined&&(
              <input type="password" defaultValue={s[`${c.key}_api_key`]||""}
                placeholder="API Key..."
                onBlur={e=>save(`${c.key}_api_key`,e.target.value)}
                style={{width:"100%",background:C.bg,border:`1px solid ${C.border2}`,
                  borderRadius:8,color:C.text,padding:"7px 10px",fontSize:13,
                  outline:"none",fontFamily:"'DM Mono',monospace",marginTop:4}}/>
            )}
          </div>
        ))}
      </div>

      <SectionTitle>API & Webhooks</SectionTitle>

      <Row label="Ausgehende Webhooks (URL)"
           description="Events werden an deine URL gesendet (neue Buchung, Unterschrift, etc.)">
        <input type="url" defaultValue={s.webhook_url||""}
          placeholder="https://mein-system.de/webhook"
          onBlur={e=>save("webhook_url",e.target.value)}
          style={{width:280,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
            color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:"'DM Sans',sans-serif"}}/>
      </Row>

      <Row label="API Rate Limit" description="Max. Anfragen pro Minute an Kanzlei AI API">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.api_rate_limit_pro_minute||60} min={10} max={1000}
            onBlur={e=>save("api_rate_limit_pro_minute",parseInt(e.target.value))}
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>/min</span>
        </div>
      </Row>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// 7. KANZLEI-DATEN
// ═══════════════════════════════════════════════════════════

const KanzleiTab = ({s, save, sysInfo, readiness, onExport, onReset}) => (
  <div>
    <SectionTitle>Kanzlei-Stammdaten</SectionTitle>

    {[
      {id:"k_name",   key:"kanzlei_name",         label:"Kanzlei-Name",       ph:"Dr. Müller Steuerberatung GmbH"},
      {id:"k_email",  key:"kanzlei_email",         label:"Email",              ph:"kanzlei@mail.de",          type:"email"},
      {id:"k_telefon",key:"kanzlei_telefon",       label:"Telefon",            ph:"+49 89 123456"},
      {id:"k_web",    key:"kanzlei_website",       label:"Website",            ph:"https://kanzlei.de",        type:"url"},
      {id:"k_adr",    key:"kanzlei_adresse",       label:"Adresse"},
      {id:"k_stnr",   key:"kanzlei_steuernummer",  label:"Kanzlei-StNr.",     ph:"123/456/78901"},
      {id:"k_iban",   key:"kanzlei_iban",          label:"IBAN",               ph:"DE89 3704 0044 ...",  mono:true},
      {id:"k_bic",    key:"kanzlei_bic",           label:"BIC",                mono:true},
    ].map(f=>(
      <Row key={f.key} label={f.label}>
        <input id={f.id} type={f.type||"text"} defaultValue={s[f.key]||""}
          placeholder={f.ph||""}
          onBlur={e=>{ if(e.target.value!==s[f.key]) save(f.key,e.target.value); }}
          style={{width:260,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
            color:C.text,padding:"7px 11px",fontSize:13,outline:"none",
            fontFamily:f.mono?"'DM Mono',monospace":"'DM Sans',sans-serif"}}/>
      </Row>
    ))}

    <Row label="Stundensatz (€/h)" description="Für Profit-Monitor und Zeiterfassung">
      <div style={{display:"flex",gap:6,alignItems:"center"}}>
        <input type="number" defaultValue={s.stundensatz||150} min={50} max={500}
          onBlur={e=>save("stundensatz",parseFloat(e.target.value))}
          style={{width:90,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
            color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
            outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
        <span style={{fontSize:12,color:C.text3}}>€/Stunde</span>
      </div>
    </Row>

    <SectionTitle>Email-Signatur</SectionTitle>
    <textarea id="email_sig" rows={4} defaultValue={s.email_signatur||""}
      onBlur={e=>save("email_signatur",e.target.value)}
      style={{width:"100%",background:C.bg,border:`1px solid ${C.border2}`,borderRadius:10,
        color:C.text,padding:"9px 13px",fontSize:13,fontFamily:"'DM Sans',sans-serif",
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
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>Stunden</span>
        </div>
      </Row>
      <Row label="Aufbewahrung (Anzahl)">
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <input type="number" defaultValue={s.backup_anzahl_aufbewahren||30} min={1} max={365}
            onBlur={e=>save("backup_anzahl_aufbewahren",parseInt(e.target.value))}
            style={{width:70,background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
              color:C.text,padding:"7px 10px",fontSize:14,textAlign:"center",
              outline:"none",fontFamily:"'DM Sans',sans-serif"}}/>
          <span style={{fontSize:12,color:C.text3}}>Backups</span>
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
          <div key={l} style={{background:C.bg3,borderRadius:8,padding:"8px 12px",
            display:"flex",justifyContent:"space-between",
            border:`1px solid ${C.border}`}}>
            <span style={{fontSize:12,color:C.text3}}>{l}</span>
            <span style={{fontSize:12,fontWeight:600,color:C.text}}>{String(v)}</span>
          </div>
        ))}
      </div>
    )}

    {readiness && (
      <>
        <SectionTitle>SaaS Readiness</SectionTitle>
        <div style={{
          marginBottom:14,
          background:`linear-gradient(135deg, ${C.blue}12, ${C.accent}10)`,
          border:`1px solid ${C.border2}`,
          borderRadius:12,
          padding:"12px 14px",
        }}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:8}}>
            <div style={{fontSize:13,color:C.text2}}>Readiness Score</div>
            <div style={{fontSize:24,fontFamily:"'DM Serif Display',serif",color:C.accent}}>
              {readiness.readiness_score ?? 0}
            </div>
          </div>
          <div style={{height:6,background:C.bg3,borderRadius:6,overflow:"hidden"}}>
            <div style={{
              width:`${Math.max(0, Math.min(100, readiness.readiness_score || 0))}%`,
              height:"100%",
              background:(readiness.readiness_score || 0) >= 80 ? C.green : (readiness.readiness_score || 0) >= 60 ? C.orange : C.red,
            }}/>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginTop:10}}>
            <div style={{fontSize:12,color:C.text3}}>
              Dead Emails 24h: <span style={{color:C.text}}>{readiness.health?.email_outbox_dead_24h ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:C.text3}}>
              Webhook Failures 24h: <span style={{color:C.text}}>{readiness.health?.webhook_failures_24h ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:C.text3}}>
              API Keys aktiv: <span style={{color:C.text}}>{readiness.health?.api_keys_aktiv ?? 0}</span>
            </div>
            <div style={{fontSize:12,color:C.text3}}>
              Webhooks aktiv: <span style={{color:C.text}}>{readiness.health?.webhooks_aktiv ?? 0}</span>
            </div>
          </div>
          {!!(readiness.alerts || []).length && (
            <div style={{marginTop:10}}>
              {(readiness.alerts || []).slice(0, 3).map((a, i) => (
                <div key={i} style={{
                  fontSize:12,
                  color:a.severity==="high"?C.red:a.severity==="medium"?C.orange:C.text2,
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

export default function Settings() {
  const [settings,  setSettings]  = useState(null);
  const [sysInfo,   setSysInfo]   = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [saving,    setSaving]    = useState({});
  const [toast,     setToast]     = useState(null);
  const [tab,       setTab]       = useState("ki");
  const [resetting, setResetting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [applyingS, setApplyingS] = useState({});
  const [readiness, setReadiness] = useState(null);

  const showToast = (text, type="success") => {
    setToast({text,type});
    setTimeout(()=>setToast(null),3000);
  };

  const laden = useCallback(async () => {
    try {
      const [s,si,ss,sr] = await Promise.allSettled([
        getSettings(),
        getSystemInfo(),
        getSettingsSuggestions(),
        getSaasReadiness(),
      ]);
      if(s.status==="fulfilled")  setSettings(s.value);
      if(si.status==="fulfilled") setSysInfo(si.value);
      if(ss.status==="fulfilled") {
        const sug = ss.value?.vorschlaege || ss.value?.data?.vorschlaege || [];
        setSuggestions(Array.isArray(sug) ? sug : []);
      }
      if(sr.status==="fulfilled") {
        const r = sr.value?.data || sr.value;
        setReadiness(r || null);
      }
    } catch(e){ console.error(e); }
    finally { setLoading(false); }
  },[]);

  useEffect(()=>{ laden(); },[laden]);

  const save = useCallback(async (key, wert) => {
    setSaving(p=>({...p,[key]:true}));
    try {
      await updateSetting(key, wert);
      setSettings(p=>({...p,[key]:wert}));
      showToast(`✓ ${key.replace(/_/g," ")} gespeichert`);
    } catch(e) {
      showToast(e.message||"Fehler","error");
    } finally {
      setSaving(p=>({...p,[key]:false}));
    }
  },[]);

  const handleReset = async () => {
    if(!window.confirm("Alle Einstellungen zurücksetzen?")) return;
    setResetting(true);
    try { await resetSettings(); await laden(); showToast("✓ Zurückgesetzt"); }
    catch(e) { showToast(e.message,"error"); }
    finally { setResetting(false); }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await getSystemExport();
      const blob = new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `kanzlei_backup_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      showToast("✓ Export gestartet");
    } catch(e) { showToast(e.message,"error"); }
    finally { setExporting(false); }
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

  if(loading||!settings) return (
    <div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",
      background:C.bg}}>
      <style>{`${FONTS} @keyframes spin{to{transform:rotate(360deg)}}`}</style>
      <div style={{width:32,height:32,borderRadius:"50%",
        border:`2px solid ${C.border2}`,borderTopColor:C.accent,
        animation:"spin 0.7s linear infinite"}}/>
    </div>
  );

  const CONTENT = {
    ki:              <KITab s={settings} save={save} saving={saving}/>,
    workflow:        <WorkflowTab s={settings} save={save}/>,
    portal:          <PortalTab s={settings} save={save}/>,
    billing:         <BillingTab s={settings} save={save}/>,
    compliance:      <ComplianceTab s={settings} save={save}/>,
    schnittstellen:  <SchnittstellenTab s={settings} save={save}/>,
    kanzlei:         <KanzleiTab s={settings} save={save} sysInfo={sysInfo}
                      readiness={readiness}
                       onExport={handleExport} onReset={handleReset}/>,
  };

  return (
    <div style={{flex:1,background:C.bg,display:"flex",flexDirection:"column",
      overflowY:"hidden",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        ${FONTS}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}
        input:focus,textarea:focus,select:focus{outline:none;border-color:${C.accent}!important}
      `}</style>

      {/* Toast */}
      {toast&&(
        <div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
          background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
          fontSize:13,fontWeight:500,animation:"slideIn 0.25s ease",
          border:`1px solid ${toast.type==="error"?C.red:C.green}44`,
          borderLeft:`3px solid ${toast.type==="error"?C.red:C.green}`,
          boxShadow:"0 8px 32px rgba(0,0,0,0.5)"}}>
          {toast.text}
        </div>
      )}

      {/* Header */}
      <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,
        padding:"20px 32px",flexShrink:0}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:24,
          color:C.text,marginBottom:4}}>Einstellungen</div>
        <div style={{fontSize:12,color:C.text3}}>
          Steuerzentrum der Profitabilität — 6 Hebel für Skalierbarkeit & Klebrigkeit
        </div>
      </div>

      {/* Layout: Sidebar + Content */}
      <div style={{flex:1,display:"flex",overflow:"hidden"}}>

        {/* Sidebar Tabs */}
        <div style={{width:220,background:C.bg2,borderRight:`1px solid ${C.border}`,
          padding:"16px 8px",overflowY:"auto",flexShrink:0}}>
          {TABS.map(t=>{
            const aktiv = tab===t.id;
            return (
              <button key={t.id} onClick={()=>setTab(t.id)} style={{
                width:"100%",display:"flex",alignItems:"center",gap:10,
                padding:"10px 12px",borderRadius:10,border:"none",
                background:aktiv?C.bg3:"transparent",
                color:aktiv?C.accent:C.text2,cursor:"pointer",
                fontFamily:"'DM Sans',sans-serif",fontSize:13,
                fontWeight:aktiv?600:400,marginBottom:2,textAlign:"left",
                transition:"all 0.15s",
                borderLeft:aktiv?`3px solid ${C.accent}`:"3px solid transparent",
              }}>
                <span style={{fontSize:16}}>{t.icon}</span>
                <span style={{flex:1}}>{t.label}</span>
                {t.badge&&(
                  <span style={{fontSize:9,padding:"2px 6px",borderRadius:8,
                    background:C.accent+"25",color:C.accent,fontWeight:700,
                    letterSpacing:"0.04em",textTransform:"uppercase"}}>
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div style={{flex:1,overflowY:"auto",padding:"24px 32px"}}>
          {suggestions.length > 0 && (
            <div style={{
              marginBottom:18,
              background:`linear-gradient(135deg, ${C.accent}10, ${C.blue}08)`,
              border:`1px solid ${C.accent}35`,
              borderRadius:14,
              padding:"14px 16px",
            }}>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:C.text,marginBottom:6}}>
                Empfohlene Optimierungen
              </div>
              <div style={{fontSize:12,color:C.text2,marginBottom:12}}>
                Basierend auf den letzten 7 Tagen Nutzung.
              </div>
              <div style={{display:"grid",gap:10}}>
                {suggestions.map((sug) => (
                  <div key={sug.id} style={{
                    background:C.bg2,
                    border:`1px solid ${C.border2}`,
                    borderRadius:10,
                    padding:"10px 12px",
                  }}>
                    <div style={{display:"flex",justifyContent:"space-between",gap:10,alignItems:"flex-start"}}>
                      <div style={{minWidth:0}}>
                        <div style={{fontSize:14,color:C.text,fontWeight:600}}>{sug.titel}</div>
                        <div style={{fontSize:12,color:C.text3,marginTop:2}}>{sug.grund}</div>
                        <div style={{fontSize:11,color:C.text3,marginTop:6}}>
                          Empfehlung: <span style={{color:C.accent}}>{sug.empfehlung?.key}</span> = {String(sug.empfehlung?.wert)}
                        </div>
                        <div style={{fontSize:11,color:C.text3,marginTop:2}}>
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
          {CONTENT[tab]}
        </div>
      </div>
    </div>
  );
}