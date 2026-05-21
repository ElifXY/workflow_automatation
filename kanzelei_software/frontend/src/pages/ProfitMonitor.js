// ============================================================
// KANZLEI AI — PROFIT MONITOR v1.0
// Datei: src/pages/ProfitMonitor.js
//
// "Verdiene ich an diesem Mandant gerade Geld — oder lege ich drauf?"
// Sekündlich aktualisierbar. Zeigt Honoraranpassungs-Vorschläge.
// ============================================================

import { useState, useEffect, useCallback } from "react";

const BASE   = process.env.REACT_APP_API_URL || "/api";
const api    = async (url) => {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE + url, {headers: token ? {Authorization:`Bearer ${token}`}:{}});
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};

const STATUS_CFG = {
  profitabel: { color: "var(--green)",  label: "Profitabel",  icon: "▲" },
  ok:         { color: "var(--blue)",   label: "OK",          icon: "→" },
  warnung:    { color: "var(--orange)", label: "Warnung",      icon: "⚠" },
  verlust:    { color: "var(--red)",    label: "Verlust ⛔",   icon: "▼" },
};

const fmt = (v) => `€${Number(v||0).toLocaleString("de-DE",{minimumFractionDigits:2})}`;
const pct  = (v) => `${Number(v||0).toFixed(1)}%`;

const Btn = ({children,onClick,variant="primary",size="md",loading=false,style={}}) => {
  const vs={primary:{background:"var(--accent)",color:"var(--on-accent)",border:"none"},
    ghost:{background:"transparent",color:"var(--text2)",border:"1px solid var(--border2)"},
    subtle:{background:"var(--bg3)",color:"var(--text2)",border:"1px solid var(--border)"},
    danger:{background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",color:"var(--red)",border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)"}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],
    fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading?"not-allowed":"pointer",opacity:loading?0.6:1,
    transition:"all 0.15s",fontFamily:"var(--font-body)",...vs[variant],...style}}>
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
      background:"var(--bg2)", border:`1px solid color-mix(in srgb, ${cfg.color} 22%, transparent)`,
      borderRadius:14, overflow:"hidden",
      borderLeft:`4px solid ${cfg.color}`,
      animation:"fadeUp 0.3s ease both",
    }}>
      {/* Header */}
      <div style={{padding:"14px 18px",display:"flex",alignItems:"center",gap:14}}>
        <div style={{fontSize:22}}>{cfg.icon}</div>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:600,color:"var(--text)",fontSize:15}}>{daten.mandant}</div>
          <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>
            {daten.aufwand_stunden}h Aufwand · €{daten.effektiver_stundensatz}/h Ø
          </div>
        </div>
        <div style={{textAlign:"right",flexShrink:0}}>
          <div style={{
            fontFamily:"var(--font-head)",fontSize:22,
            color:daten.profit_euro >= 0 ? "var(--green)" : "var(--red)",
          }}>
            {daten.profit_euro >= 0 ? "+" : ""}{fmt(daten.profit_euro)}
          </div>
          <span style={{
            fontSize:11,fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
            padding:"2px 8px",borderRadius:20,
            background:`color-mix(in srgb, ${cfg.color} 16%, var(--bg3))`,color:cfg.color,border:`1px solid color-mix(in srgb, ${cfg.color} 26%, transparent)`,
          }}>{cfg.label}</span>
        </div>
      </div>

      {/* Marge-Balken */}
      <div style={{padding:"0 18px 12px"}}>
        <div style={{display:"flex",justifyContent:"space-between",
                      fontSize:11,color:"var(--text3)",marginBottom:5}}>
          <span>Marge: {pct(daten.marge_prozent)}</span>
          <span>Ziel: 40%</span>
        </div>
        <div style={{background:"var(--bg3)",borderRadius:4,height:6,overflow:"hidden"}}>
          <div style={{
            width:`${marge_bar_width}%`,height:"100%",
            background:`linear-gradient(90deg, ${
              daten.marge_prozent < 0 ? "var(--red)" :
              daten.marge_prozent < 20 ? "var(--orange)" :
              daten.marge_prozent < 40 ? "var(--blue)" : "var(--green)"
            }, ${daten.marge_prozent >= 40 ? "var(--accent)" : "transparent"})`,
            borderRadius:4, transition:"width 1s ease",
          }}/>
          {/* 40%-Marke */}
          <div style={{
            position:"relative",top:-6,
            left:"40%",width:1,height:6,
            background:"var(--text3)",opacity:0.5,
          }}/>
        </div>

        {/* Kennzahlen */}
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8,marginTop:12}}>
          {[
            {l:"Honorar (Netto)", v:fmt(daten.honorar_netto)},
            {l:"Aufwand",         v:fmt(daten.aufwand_euro)},
            {l:"Eff. Stundensatz",v:`€${daten.effektiver_stundensatz}/h`},
          ].map((item,i)=>(
            <div key={i} style={{background:"var(--bg3)",borderRadius:8,padding:"8px 10px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
                            letterSpacing:"0.06em",marginBottom:2}}>{item.l}</div>
              <div style={{fontSize:13,fontWeight:600,color:"var(--text)"}}>{item.v}</div>
            </div>
          ))}
        </div>

        {/* Honoraranpassungs-Vorschlag */}
        {a && (
          <div style={{
            marginTop:12,background:"color-mix(in srgb, var(--orange) 10%, var(--bg3))",
            border:"1px solid color-mix(in srgb, var(--orange) 24%, transparent)",borderRadius:10,padding:"12px 14px",
          }}>
            <div style={{fontWeight:600,color:"var(--orange)",fontSize:13,marginBottom:6}}>
              💡 Honoraranpassung empfohlen ({a.dringlichkeit})
            </div>
            <div style={{fontSize:12,color:"var(--text2)",marginBottom:8}}>
              {a.grund}<br/>
              Aktuell: {fmt(a.aktuelles_honorar)}/Monat →{" "}
              <strong style={{color:"var(--green)"}}>Empfohlen: {fmt(a.empfohlenes_honorar)}/Monat</strong>
              {" "}(+{pct(a.differenz_prozent)})<br/>
              <span style={{color:"var(--green)",fontWeight:600}}>
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
            marginTop:10,background:"var(--bg3)",borderRadius:10,padding:"12px 14px",
            border:`1px solid var(--border)`,
          }}>
            <div style={{fontWeight:600,color:"var(--text)",fontSize:13,marginBottom:8}}>
              Branchenvergleich: {benchmark.branche}
              <span style={{color:"var(--text3)",fontSize:11,marginLeft:8}}>
                ({benchmark.vergleichsgruppe} Mandanten)
              </span>
            </div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:6,marginBottom:10}}>
              {[
                {l:"Meine Marge",  v:pct(benchmark.meine_marge),   c:benchmark.meine_marge>=40?"var(--green)":"var(--orange)"},
                {l:"Ø Branche",    v:pct(benchmark.ø_marge),       c:"var(--text2)"},
                {l:"Mein Honorar", v:fmt(benchmark.mein_honorar),  c:"var(--text)"},
                {l:"Ø Honorar",    v:fmt(benchmark["ø_honorar"]),  c:"var(--text2)"},
              ].map((x,i)=>(
                <div key={i} style={{background:"var(--bg2)",borderRadius:6,padding:"6px 10px"}}>
                  <div style={{fontSize:10,color:"var(--text3)"}}>{x.l}</div>
                  <div style={{fontSize:13,fontWeight:600,color:x.c}}>{x.v}</div>
                </div>
              ))}
            </div>
            {benchmark.insights?.map((ins,i)=>(
              <div key={i} style={{
                fontSize:12,color:"var(--text2)",padding:"6px 0",
                borderTop:i===0?`1px solid var(--border)`:"none",
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
  const [loadError,  setLoadError]  = useState(null);

  const showToast = (text) => { setToast(text); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const d = await api(`/profit/kanzlei/uebersicht?tage=${tage}`);
      setUebersicht(d);
    } catch (e) {
      console.error(e);
      setUebersicht(null);
      setLoadError(e?.message || String(e));
    } finally { setLoading(false); }
  }, [tage]);

  useEffect(() => { laden(); }, [laden]);

  const handleEmailVorlage = (mandant, vorlage) => {
    setEmailModal({ mandant, vorlage });
  };

  const u = uebersicht;

  return (
    <div style={{background:"var(--bg)",fontFamily:"var(--font-body)"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
      `}</style>

      {toast && <div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
        fontSize:13,border:"1px solid color-mix(in srgb, var(--green) 32%, transparent)",borderLeft:"3px solid var(--green)"}}>
        {toast}</div>}

      {/* Email Modal */}
      {emailModal && (
        <div style={{position:"fixed",inset:0,background:"var(--overlay-scrim)",
          display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000,padding:20}}>
          <div style={{background:"var(--bg2)",border:`1px solid var(--border2)`,borderRadius:16,
            width:"min(600px,95vw)",padding:24,maxHeight:"80vh",overflow:"auto"}}>
            <div style={{display:"flex",justifyContent:"space-between",marginBottom:16}}>
              <div style={{fontFamily:"var(--font-head)",fontSize:18,color:"var(--accent)"}}>
                Email-Vorlage: {emailModal.mandant}
              </div>
              <Btn size="xs" variant="ghost" onClick={()=>setEmailModal(null)}>✕</Btn>
            </div>
            <textarea defaultValue={emailModal.vorlage} rows={12}
              style={{width:"100%",background:"var(--bg3)",border:`1px solid var(--border2)`,
                borderRadius:10,color:"var(--text)",padding:"10px 14px",fontSize:13,
                fontFamily:"var(--font-body)",resize:"vertical",outline:"none"}}/>
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
      <div style={{background:"var(--bg2)",borderBottom:`1px solid var(--border)`,
        padding:"20px 32px",display:"flex",alignItems:"center",gap:16,
        position:"sticky",top:0,zIndex:10}}>
        <div style={{flex:1}}>
          <div style={{fontFamily:"var(--font-head)",fontSize:22,color:"var(--text)"}}>
            Profit Monitor
          </div>
          <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>
            Echtzeit: Verdient die Kanzlei Geld? Welcher Mandant lohnt sich?
          </div>
        </div>
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          <span style={{fontSize:12,color:"var(--text3)"}}>Zeitraum:</span>
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
              border:`2px solid var(--border2)`,borderTopColor:"var(--accent)",
              animation:"spin 0.7s linear infinite"}}/>
          </div>
        )}

        {!loading && loadError && (
          <div style={{
            padding:24,maxWidth:560,margin:"0 auto",
            background:"color-mix(in srgb, var(--orange) 12%, var(--bg2))",
            border:"1px solid color-mix(in srgb, var(--orange) 35%, transparent)",
            borderRadius:14,fontSize:14,color:"var(--text)",lineHeight:1.6,
          }}>
            <div style={{fontWeight:600,marginBottom:8,color:"var(--orange)"}}>Profit-Daten konnten nicht geladen werden</div>
            <div style={{color:"var(--text2)",marginBottom:12}}>
              Häufig: API-Pfad (Nginx → FastAPI), Session abgelaufen oder Rate-Limit. Technisch: {loadError}
            </div>
            <Btn size="sm" variant="primary" onClick={laden}>Erneut versuchen</Btn>
          </div>
        )}

        {u && (
          <>
            {/* Kanzlei-KPIs */}
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16,marginBottom:24}}>
              {[
                {l:"Kanzlei-Profit",    v:fmt(u.gesamt_profit),  c:u.gesamt_profit>=0?"var(--green)":"var(--red)"},
                {l:"Kanzlei-Marge",     v:pct(u.gesamt_marge_prozent), c:u.gesamt_marge_prozent>=40?"var(--green)":"var(--orange)"},
                {l:"Verlust-Mandanten", v:u.verlust_mandanten,   c:u.verlust_mandanten>0?"var(--red)":"var(--green)"},
                {l:"Potenzial/Jahr",    v:fmt(u.potenzial_euro_jährlich), c:"var(--accent)"},
              ].map((s,i)=>(
                <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
                  borderRadius:14,padding:"18px 20px",animation:`fadeUp 0.4s ease ${i*60}ms both`}}>
                  <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",
                    letterSpacing:"0.07em",marginBottom:6}}>{s.l}</div>
                  <div style={{fontFamily:"var(--font-head)",fontSize:26,color:s.c}}>{s.v}</div>
                </div>
              ))}
            </div>

            {/* Verlust-Alert */}
            {u.verlust_mandanten > 0 && (
              <div style={{background:"color-mix(in srgb, var(--red) 10%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--red) 22%, transparent)",
                borderRadius:12,padding:"14px 18px",marginBottom:20}}>
                <div style={{color:"var(--red)",fontWeight:600,fontSize:14,marginBottom:6}}>
                  ⛔ {u.verlust_mandanten} Verlust-Mandant(en) — sofort Honorar prüfen!
                </div>
                {u.top3_verlustreich.filter(m=>m.status==="verlust").map((m,i)=>(
                  <div key={i} style={{fontSize:13,color:"var(--text2)"}}>
                    · {m.mandant}: {fmt(m.profit_euro)}/Monat ({pct(m.marge_prozent)} Marge)
                  </div>
                ))}
              </div>
            )}

            {/* Honoraranpassungs-Alert */}
            {u.anpassung_empfohlen > 0 && (
              <div style={{background:"color-mix(in srgb, var(--orange) 10%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--orange) 22%, transparent)",
                borderRadius:12,padding:"14px 18px",marginBottom:20}}>
                <div style={{color:"var(--orange)",fontWeight:600,fontSize:13}}>
                  💡 {u.anpassung_empfohlen} Mandant(en): Honoraranpassung empfohlen
                </div>
                <div style={{color:"var(--text3)",fontSize:12,marginTop:4}}>
                  Gesamtpotenzial: <strong style={{color:"var(--green)"}}>+{fmt(u.potenzial_euro_jährlich)}/Jahr</strong>
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