// ============================================================
// KANZLEI AI — PROFIT MONITOR v1.0
// Datei: src/pages/ProfitMonitor.js
//
// "Verdiene ich an diesem Mandant gerade Geld — oder lege ich drauf?"
// Sekündlich aktualisierbar. Zeigt Honoraranpassungs-Vorschläge.
// ============================================================

import { useState, useEffect, useCallback } from "react";

const C = {
  red:"#e05555",orange:"#e08c45",green:"#5cb87a",blue:"#5b8de8",
  accent:"#c8a96e",purple:"#9b72e8",
  text:"#e8eaf0",text2:"#8b91a0",text3:"#555d6e",
  bg:"#0b0d11",bg2:"#111419",bg3:"#181c24",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.14)",
};

const BASE   = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";
const api    = async (url) => {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE + url, {headers: token ? {Authorization:`Bearer ${token}`}:{}});
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

const STATUS_CFG = {
  profitabel: { color: C.green,  label: "Profitabel",  icon: "▲" },
  ok:         { color: C.blue,   label: "OK",          icon: "→" },
  warnung:    { color: C.orange, label: "Warnung",      icon: "⚠" },
  verlust:    { color: C.red,    label: "Verlust ⛔",   icon: "▼" },
};

const fmt = (v) => `€${Number(v||0).toLocaleString("de-DE",{minimumFractionDigits:2})}`;
const pct  = (v) => `${Number(v||0).toFixed(1)}%`;

const Btn = ({children,onClick,variant="primary",size="md",loading=false,style={}}) => {
  const vs={primary:{background:C.accent,color:"#1a1200",border:"none"},
    ghost:{background:"transparent",color:C.text2,border:`1px solid ${C.border2}`},
    subtle:{background:C.bg3,color:C.text2,border:`1px solid ${C.border}`},
    danger:{background:C.red+"18",color:C.red,border:`1px solid ${C.red}30`}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],
    fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading?"not-allowed":"pointer",opacity:loading?0.6:1,
    transition:"all 0.15s",fontFamily:"'DM Sans',sans-serif",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",
      border:"2px solid currentColor",borderTopColor:"transparent",
      animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

// ── Profit-Karte für einen Mandant ───────────────────────────
const ProfitKarte = ({ daten, onAnpassungEmail }) => {
  const [benchmark, setBenchmark] = useState(null);
  const [showBench, setShowBench] = useState(false);
  const [loadBench, setLoadBench] = useState(false);

  const cfg = STATUS_CFG[daten.status] || STATUS_CFG.ok;
  const a   = daten.honoraranpassung;

  const ladeBenchmark = async () => {
    if (benchmark) { setShowBench(!showBench); return; }
    setLoadBench(true);
    try {
      const d = await api(`/profit/${encodeURIComponent(daten.mandant)}/benchmarking`);
      setBenchmark(d);
      setShowBench(true);
    } catch(e) { console.error(e); }
    finally { setLoadBench(false); }
  };

  const marge_bar_width = Math.max(0, Math.min(100, daten.marge_prozent));

  return (
    <div style={{
      background:C.bg2, border:`1px solid ${cfg.color}30`,
      borderRadius:14, overflow:"hidden",
      borderLeft:`4px solid ${cfg.color}`,
      animation:"fadeUp 0.3s ease both",
    }}>
      {/* Header */}
      <div style={{padding:"14px 18px",display:"flex",alignItems:"center",gap:14}}>
        <div style={{fontSize:22}}>{cfg.icon}</div>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:600,color:C.text,fontSize:15}}>{daten.mandant}</div>
          <div style={{fontSize:12,color:C.text3,marginTop:2}}>
            {daten.aufwand_stunden}h Aufwand · €{daten.effektiver_stundensatz}/h Ø
          </div>
        </div>
        <div style={{textAlign:"right",flexShrink:0}}>
          <div style={{
            fontFamily:"'DM Serif Display',serif",fontSize:22,
            color:daten.profit_euro >= 0 ? C.green : C.red,
          }}>
            {daten.profit_euro >= 0 ? "+" : ""}{fmt(daten.profit_euro)}
          </div>
          <span style={{
            fontSize:11,fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
            padding:"2px 8px",borderRadius:20,
            background:cfg.color+"20",color:cfg.color,border:`1px solid ${cfg.color}33`,
          }}>{cfg.label}</span>
        </div>
      </div>

      {/* Marge-Balken */}
      <div style={{padding:"0 18px 12px"}}>
        <div style={{display:"flex",justifyContent:"space-between",
                      fontSize:11,color:C.text3,marginBottom:5}}>
          <span>Marge: {pct(daten.marge_prozent)}</span>
          <span>Ziel: 40%</span>
        </div>
        <div style={{background:C.bg3,borderRadius:4,height:6,overflow:"hidden"}}>
          <div style={{
            width:`${marge_bar_width}%`,height:"100%",
            background:`linear-gradient(90deg, ${
              daten.marge_prozent < 0 ? C.red :
              daten.marge_prozent < 20 ? C.orange :
              daten.marge_prozent < 40 ? C.blue : C.green
            }, ${daten.marge_prozent >= 40 ? C.accent : "transparent"})`,
            borderRadius:4, transition:"width 1s ease",
          }}/>
          {/* 40%-Marke */}
          <div style={{
            position:"relative",top:-6,
            left:"40%",width:1,height:6,
            background:C.text3,opacity:0.5,
          }}/>
        </div>

        {/* Kennzahlen */}
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,marginTop:12}}>
          {[
            {l:"Honorar (Netto)", v:fmt(daten.honorar_netto)},
            {l:"Aufwand",         v:fmt(daten.aufwand_euro)},
            {l:"Eff. Stundensatz",v:`€${daten.effektiver_stundensatz}/h`},
          ].map((item,i)=>(
            <div key={i} style={{background:C.bg3,borderRadius:8,padding:"8px 10px"}}>
              <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",
                            letterSpacing:"0.06em",marginBottom:2}}>{item.l}</div>
              <div style={{fontSize:13,fontWeight:600,color:C.text}}>{item.v}</div>
            </div>
          ))}
        </div>

        {/* Honoraranpassungs-Vorschlag */}
        {a && (
          <div style={{
            marginTop:12,background:C.orange+"10",
            border:`1px solid ${C.orange}30`,borderRadius:10,padding:"12px 14px",
          }}>
            <div style={{fontWeight:600,color:C.orange,fontSize:13,marginBottom:6}}>
              💡 Honoraranpassung empfohlen ({a.dringlichkeit})
            </div>
            <div style={{fontSize:12,color:C.text2,marginBottom:8}}>
              {a.grund}<br/>
              Aktuell: {fmt(a.aktuelles_honorar)}/Monat →{" "}
              <strong style={{color:C.green}}>Empfohlen: {fmt(a.empfohlenes_honorar)}/Monat</strong>
              {" "}(+{pct(a.differenz_prozent)})<br/>
              <span style={{color:C.green,fontWeight:600}}>
                +{fmt(a.jahres_mehreinnahme)} pro Jahr
              </span>
            </div>
            <Btn size="xs" variant="ghost"
                 onClick={() => onAnpassungEmail(daten.mandant, a.email_vorlage)}>
              ✉ Email-Vorlage öffnen
            </Btn>
          </div>
        )}

        {/* Aktionen */}
        <div style={{display:"flex",gap:8,marginTop:10,flexWrap:"wrap"}}>
          <Btn size="xs" variant="ghost" onClick={ladeBenchmark} loading={loadBench}>
            📊 Branchenvergleich
          </Btn>
        </div>

        {/* Branchen-Benchmark */}
        {showBench && benchmark && (
          <div style={{
            marginTop:10,background:C.bg3,borderRadius:10,padding:"12px 14px",
            border:`1px solid ${C.border}`,
          }}>
            <div style={{fontWeight:600,color:C.text,fontSize:13,marginBottom:8}}>
              Branchenvergleich: {benchmark.branche}
              <span style={{color:C.text3,fontSize:11,marginLeft:8}}>
                ({benchmark.vergleichsgruppe} Mandanten)
              </span>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:6,marginBottom:10}}>
              {[
                {l:"Meine Marge",  v:pct(benchmark.meine_marge),   c:benchmark.meine_marge>=40?C.green:C.orange},
                {l:"Ø Branche",    v:pct(benchmark.ø_marge),       c:C.text2},
                {l:"Mein Honorar", v:fmt(benchmark.mein_honorar),  c:C.text},
                {l:"Ø Honorar",    v:fmt(benchmark["ø_honorar"]),  c:C.text2},
              ].map((x,i)=>(
                <div key={i} style={{background:C.bg2,borderRadius:6,padding:"6px 10px"}}>
                  <div style={{fontSize:10,color:C.text3}}>{x.l}</div>
                  <div style={{fontSize:13,fontWeight:600,color:x.c}}>{x.v}</div>
                </div>
              ))}
            </div>
            {benchmark.insights?.map((ins,i)=>(
              <div key={i} style={{
                fontSize:12,color:C.text2,padding:"6px 0",
                borderTop:i===0?`1px solid ${C.border}`:"none",
                lineHeight:1.6,
              }}>→ {ins}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function ProfitMonitor() {
  const [uebersicht, setUebersicht] = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [tage,       setTage]       = useState(30);
  const [emailModal, setEmailModal] = useState(null);
  const [toast,      setToast]      = useState(null);

  const showToast = (text) => { setToast(text); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    setLoading(true);
    try {
      const d = await api(`/profit/kanzlei/uebersicht?tage=${tage}`);
      setUebersicht(d);
    } catch(e) { console.error(e); }
    finally { setLoading(false); }
  }, [tage]);

  useEffect(() => { laden(); }, [laden]);

  const handleEmailVorlage = (mandant, vorlage) => {
    setEmailModal({ mandant, vorlage });
  };

  const u = uebersicht;

  return (
    <div style={{flex:1,background:C.bg,overflowY:"auto",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}
      `}</style>

      {toast && <div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
        fontSize:13,border:`1px solid ${C.green}44`,borderLeft:`3px solid ${C.green}`}}>
        {toast}</div>}

      {/* Email Modal */}
      {emailModal && (
        <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.8)",
          display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000,padding:20}}>
          <div style={{background:C.bg2,border:`1px solid ${C.border2}`,borderRadius:16,
            width:"min(600px,95vw)",padding:24,maxHeight:"80vh",overflow:"auto"}}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:16}}>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:C.accent}}>
                Email-Vorlage: {emailModal.mandant}
              </div>
              <Btn size="xs" variant="ghost" onClick={()=>setEmailModal(null)}>✕</Btn>
            </div>
            <textarea defaultValue={emailModal.vorlage} rows={12}
              style={{width:"100%",background:C.bg3,border:`1px solid ${C.border2}`,
                borderRadius:10,color:C.text,padding:"10px 14px",fontSize:13,
                fontFamily:"'DM Sans',sans-serif",resize:"vertical",outline:"none"}}/>
            <div style={{display:"flex",gap:8,marginTop:12}}>
              <Btn variant="primary" onClick={()=>{
                navigator.clipboard.writeText(emailModal.vorlage);
                showToast("✓ In Zwischenablage kopiert");
                setEmailModal(null);
              }}>📋 Kopieren</Btn>
              <Btn variant="ghost" onClick={()=>setEmailModal(null)}>Schließen</Btn>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,
        padding:"20px 32px",display:"flex",alignItems:"center",gap:16,
        position:"sticky",top:0,zIndex:10}}>
        <div style={{flex:1}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,color:C.text}}>
            Profit Monitor
          </div>
          <div style={{fontSize:12,color:C.text3,marginTop:2}}>
            Echtzeit: Verdient die Kanzlei Geld? Welcher Mandant lohnt sich?
          </div>
        </div>
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          <span style={{fontSize:12,color:C.text3}}>Zeitraum:</span>
          {[7,30,90].map(t=>(
            <Btn key={t} size="xs" variant={tage===t?"subtle":"ghost"}
                 onClick={()=>setTage(t)}>{t} Tage</Btn>
          ))}
          <Btn size="sm" variant="primary" loading={loading} onClick={laden}>↻</Btn>
        </div>
      </div>

      <div style={{padding:"28px 32px"}}>
        {loading && !u && (
          <div style={{display:"flex",alignItems:"center",justifyContent:"center",padding:60}}>
            <div style={{width:36,height:36,borderRadius:"50%",
              border:`2px solid ${C.border2}`,borderTopColor:C.accent,
              animation:"spin 0.7s linear infinite"}}/>
          </div>
        )}

        {u && (
          <>
            {/* Kanzlei-KPIs */}
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16,marginBottom:24}}>
              {[
                {l:"Kanzlei-Profit",    v:fmt(u.gesamt_profit),  c:u.gesamt_profit>=0?C.green:C.red},
                {l:"Kanzlei-Marge",     v:pct(u.gesamt_marge_prozent), c:u.gesamt_marge_prozent>=40?C.green:C.orange},
                {l:"Verlust-Mandanten", v:u.verlust_mandanten,   c:u.verlust_mandanten>0?C.red:C.green},
                {l:"Potenzial/Jahr",    v:fmt(u.potenzial_euro_jährlich), c:C.accent},
              ].map((s,i)=>(
                <div key={i} style={{background:C.bg2,border:`1px solid ${C.border}`,
                  borderRadius:14,padding:"18px 20px",animation:`fadeUp 0.4s ease ${i*60}ms both`}}>
                  <div style={{fontSize:11,color:C.text3,textTransform:"uppercase",
                    letterSpacing:"0.07em",marginBottom:6}}>{s.l}</div>
                  <div style={{fontFamily:"'DM Serif Display',serif",fontSize:26,color:s.c}}>{s.v}</div>
                </div>
              ))}
            </div>

            {/* Verlust-Alert */}
            {u.verlust_mandanten > 0 && (
              <div style={{background:C.red+"10",border:`1px solid ${C.red}25`,
                borderRadius:12,padding:"14px 18px",marginBottom:20}}>
                <div style={{color:C.red,fontWeight:600,fontSize:14,marginBottom:6}}>
                  ⛔ {u.verlust_mandanten} Verlust-Mandant(en) — sofort Honorar prüfen!
                </div>
                {u.top3_verlustreich.filter(m=>m.status==="verlust").map((m,i)=>(
                  <div key={i} style={{fontSize:13,color:C.text2}}>
                    · {m.mandant}: {fmt(m.profit_euro)}/Monat ({pct(m.marge_prozent)} Marge)
                  </div>
                ))}
              </div>
            )}

            {/* Honoraranpassungs-Alert */}
            {u.anpassung_empfohlen > 0 && (
              <div style={{background:C.orange+"10",border:`1px solid ${C.orange}25`,
                borderRadius:12,padding:"14px 18px",marginBottom:20}}>
                <div style={{color:C.orange,fontWeight:600,fontSize:13}}>
                  💡 {u.anpassung_empfohlen} Mandant(en): Honoraranpassung empfohlen
                </div>
                <div style={{color:C.text3,fontSize:12,marginTop:4}}>
                  Gesamtpotenzial: <strong style={{color:C.green}}>+{fmt(u.potenzial_euro_jährlich)}/Jahr</strong>
                </div>
              </div>
            )}

            {/* Mandanten-Karten */}
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              {(u.ranking||[]).map((r,i)=>(
                <ProfitKarte key={i} daten={r}
                  onAnpassungEmail={handleEmailVorlage} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}