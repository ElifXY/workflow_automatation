// ============================================================
// KANZLEI AI — STEUER AUTOPILOT v1.0
// Datei: src/pages/SteuerAutopilot.js
//
// 3 Module in einem:
//   1. Steuer-Autopilot (KI verarbeitet Steuerfälle vollautomatisch)
//   2. Finanzierung (Nachzahlung → sofort Lösungen)
//   3. ML-Buchung (zeigt was das System gelernt hat)
// ============================================================

import { useState, useEffect, useCallback } from "react";

const BASE = process.env.REACT_APP_API_URL || "/api";
const api  = async (url, opts={}) => {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE+url, {...opts, headers:{
    "Content-Type":"application/json",
    ...(token?{Authorization:`Bearer ${token}`}:{}), ...(opts.headers||{}),
  }});
  const d = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(d.detail||`${r.status}`);
  return d;
};

const fmt = v => `€${Number(v||0).toLocaleString("de-DE",{minimumFractionDigits:2})}`;

/** Betrag beim Tippen als String halten — vermeidet `parseFloat('')||0` → störendes führendes 0 */
const sanitizeDecimalTyping = (raw) => {
  if (raw === "") return "";
  const v = raw.replace(",", ".");
  if (!/^\d*\.?\d*$/.test(v)) return null;
  return v;
};

const Btn = ({children,onClick,variant="primary",size="md",loading=false,disabled=false,style={}}) => {
  const vs={primary:{background:"var(--accent)",color:"var(--on-accent)",border:"none"},
    ghost:{background:"transparent",color:"var(--text2)",border:`1px solid var(--border2)`},
    subtle:{background:"var(--bg3)",color:"var(--text2)",border:`1px solid var(--border)`},
    success:{background:"color-mix(in srgb, var(--green) 14%, var(--bg3))",color:"var(--green)",border:"1px solid color-mix(in srgb, var(--green) 24%, transparent)"},
    danger:{background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",color:"var(--red)",border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)"}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px",lg:"12px 24px"};
  const fs={xs:11,sm:13,md:14,lg:15};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],
    fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading||disabled?"not-allowed":"pointer",opacity:loading||disabled?0.5:1,
    transition:"all 0.15s",fontFamily:"var(--font-body)",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",
      border:"2px solid currentColor",borderTopColor:"transparent",
      animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

const TABS = [
  {id:"autopilot", label:"Steuer-Autopilot", icon:"🤖"},
  {id:"finanzierung",label:"Finanzierung",   icon:"💳"},
  {id:"ml",         label:"ML-Buchung",      icon:"🧠"},
];

const KONFIDENZ_FARBE = (score) =>
  score >= 92 ? "var(--green)" : score >= 75 ? "var(--blue)" : score >= 50 ? "var(--orange)" : "var(--red)";

const KONFIDENZ_LABEL = (score) =>
  score >= 92 ? "Auto-Freigabe möglich" :
  score >= 75 ? "Kurzer Review (15 Min)" :
  score >= 50 ? "Standard-Review" : "Manuell erforderlich";

const fallId = (f) => f?.id || f?.fall_id || f?._id || "";

// ══════════════════════════════════════════════════════════
// AUTOPILOT TAB
// ══════════════════════════════════════════════════════════

const AutopilotTab = () => {
  const [mandanten,  setMandanten]  = useState([]);
  const [faelleAktiv, setFaelleAktiv]= useState([]);
  const [faelleHist,  setFaelleHist]= useState([]);
  const [histSteuerTtl, setHistSteuerTtl] = useState(30);
  const [stats,      setStats]      = useState(null);
  const [processing, setProcessing] = useState(false);
  const [selectedM,  setSelectedM]  = useState("");
  const [steuerart,  setSteuerart]  = useState("ESt");
  const [jahr,       setJahr]       = useState(new Date().getFullYear()-1);
  const [toast,      setToast]      = useState(null);
  const [aktiverFall,setAktiverFall]= useState(null);

  const showToast = (t,type="success") => { setToast({t,type}); setTimeout(()=>setToast(null),5000); };

  const laden = useCallback(async () => {
    try {
      const [m, fa, fh, s] = await Promise.allSettled([
        api("/mandanten"),
        api("/steuer/faelle?pool=aktiv"),
        api("/steuer/faelle?pool=historie"),
        api("/steuer/statistiken"),
      ]);
      if(m.status==="fulfilled") {
        const raw = m.value?.data||[];
        setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
      }
      if(fa.status==="fulfilled") setFaelleAktiv(fa.value?.faelle||[]);
      if(fh.status==="fulfilled") {
        const v = fh.value;
        setFaelleHist(v?.faelle||[]);
        setHistSteuerTtl(Number(v?.historie_ttl_tage)||30);
      }
      if(s.status==="fulfilled") setStats(s.value);
    } catch(e){console.error(e);}
  },[]);

  useEffect(()=>{laden();},[laden]);

  const starte = async () => {
    if(!selectedM) { showToast("Bitte Mandanten wählen","warn"); return; }
    setProcessing(true);
    try {
      const fall = await api("/steuer/verarbeiten",{
        method:"POST",
        body:JSON.stringify({mandant:selectedM,jahr,steuerart}),
      });
      setAktiverFall(fall);
      showToast(`✓ Steuerfall verarbeitet — Konfidenz: ${fall.konfidenz_score}%`);
      await laden();
    } catch(e){showToast(e.message,"error");}
    finally{setProcessing(false);}
  };

  const freigeben = async (fallId) => {
    try {
      await api(`/steuer/${fallId}/freigeben?freigegeben_von=Steuerberater`,{method:"POST"});
      showToast("✓ Steuerfall freigegeben");
      setAktiverFall(null);
      await laden();
    } catch(e){showToast(e.message,"error");}
  };

  const inHistorie = async (fallId) => {
    try {
      await api(`/steuer/${fallId}/historie`,{method:"POST"});
      showToast("In Historie gelegt");
      await laden();
    } catch(e){showToast(e.message,"error");}
  };

  const steuerFallWiederherstellen = async (fallId) => {
    try {
      await api(`/steuer/${fallId}/wiederherstellen`,{method:"POST"});
      showToast("Steuerfall wieder aktiv");
      await laden();
    } catch(e){showToast(e.message,"error");}
  };

  const steuerFallLoeschen = async (fallId) => {
    if (!window.confirm("Steuerfall endgültig löschen?")) return;
    try {
      await api(`/steuer/${fallId}`,{method:"DELETE"});
      showToast("Gelöscht", "warn");
      await laden();
    } catch(e){showToast(e.message,"error");}
  };

  const inp = (style={}) => ({
    background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
    color:"var(--text)",padding:"8px 11px",fontSize:13,
    fontFamily:"'DM Sans',sans-serif",outline:"none",...style,
  });

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
        fontSize:13,border:`1px solid ${toast.type==="error"?"var(--red)":"var(--green)"}44`,
        borderLeft:`3px solid ${toast.type==="error"?"var(--red)":"var(--green)"}`}}>
        {toast.t}</div>}

      {/* Statistiken */}
      {stats&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:22}}>
          {[
            {l:"Fälle verarbeitet",    v:stats.faelle_gesamt,         c:"var(--blue)"},
            {l:"Freigegeben",          v:stats.faelle_freigegeben,    c:"var(--green)"},
            {l:"Ø Konfidenz",          v:`${stats.durchschnitt_konfidenz}%`, c:"var(--accent)"},
            {l:"Gesparte Stunden",     v:`${stats.gespar_stunden_schätzung}h`, c:"var(--purple)"},
          ].map((s,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
              borderRadius:12,padding:"14px 16px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
                letterSpacing:"0.07em",marginBottom:4}}>{s.l}</div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:24,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>
      )}

      {/* Neuer Steuerfall */}
      <div style={{background:"var(--bg2)",border:`1px solid var(--border)`,
        borderRadius:14,padding:20,marginBottom:22}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
          color:"var(--accent)",marginBottom:14}}>
          🤖 Neuen Steuerfall automatisch verarbeiten
        </div>
        <div style={{fontSize:13,color:"var(--text2)",marginBottom:14,lineHeight:1.7}}>
          Das System sammelt alle Daten, berechnet die Steuer, erstellt das ELSTER XML
          und gibt einen Konfidenz-Score. Bei &gt;92%: fast kein manueller Aufwand.
        </div>
        <div style={{display:"flex",gap:10,flexWrap:"wrap",marginBottom:14}}>
          <select value={selectedM} onChange={e=>setSelectedM(e.target.value)} style={inp({flex:2})}>
            <option value="">— Mandant wählen —</option>
            {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
          </select>
          <select value={steuerart} onChange={e=>setSteuerart(e.target.value)} style={inp()}>
            {["ESt","USt","GewSt","KSt"].map(s=><option key={s} value={s}>{s}</option>)}
          </select>
          <input type="number" value={jahr}
            onChange={e=>setJahr(parseInt(e.target.value))}
            min={2020} max={2026} style={inp({width:90})} />
        </div>
        <Btn onClick={starte} loading={processing} variant="primary" size="lg">
          🤖 Steuerfall automatisch verarbeiten
        </Btn>
        {processing&&(
          <div style={{marginTop:12,color:"var(--text3)",fontSize:13}}>
            Sammle Daten → KI analysiert → ELSTER vorbereiten...
          </div>
        )}
      </div>

      {/* Aktiver Fall */}
      {aktiverFall&&(
        <div style={{background:"var(--bg2)",border:`1px solid ${KONFIDENZ_FARBE(aktiverFall.konfidenz_score)}40`,
          borderRadius:14,padding:20,marginBottom:22,
          borderLeft:`4px solid ${KONFIDENZ_FARBE(aktiverFall.konfidenz_score)}`}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:14}}>
            <div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:"var(--text)"}}>
                {aktiverFall.mandant} — {aktiverFall.steuerart} {aktiverFall.jahr}
              </div>
              <div style={{fontSize:12,color:"var(--text3)",marginTop:3}}>{aktiverFall.empfehlung_text}</div>
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:28,
                color:KONFIDENZ_FARBE(aktiverFall.konfidenz_score)}}>
                {aktiverFall.konfidenz_score}%
              </div>
              <div style={{fontSize:11,color:KONFIDENZ_FARBE(aktiverFall.konfidenz_score)}}>
                {KONFIDENZ_LABEL(aktiverFall.konfidenz_score)}
              </div>
            </div>
          </div>

          {/* Steuer-Ergebnis */}
          {aktiverFall.ki_analyse?.steuerberechnung&&(
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10,marginBottom:14}}>
              {[
                {l:"Nachzahlung/Erstattung",
                 v:fmt(aktiverFall.ki_analyse.steuerberechnung.nachzahlung_oder_erstattung),
                 c:aktiverFall.ist_nachzahlung?"var(--red)":"var(--green)"},
                {l:"Einkommensteuer",
                 v:fmt(aktiverFall.ki_analyse.steuerberechnung.einkommensteuer||0),
                 c:"var(--text)"},
                {l:"Solidaritätszuschlag",
                 v:fmt(aktiverFall.ki_analyse.steuerberechnung.solidaritaetszuschlag||0),
                 c:"var(--text)"},
              ].map((x,i)=>(
                <div key={i} style={{background:"var(--bg3)",borderRadius:8,padding:"10px 12px"}}>
                  <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
                    letterSpacing:"0.06em",marginBottom:3}}>{x.l}</div>
                  <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:x.c}}>{x.v}</div>
                </div>
              ))}
            </div>
          )}

          {/* Optimierungen */}
          {aktiverFall.ki_analyse?.optimierungen?.length>0&&(
            <div style={{marginBottom:14}}>
              <div style={{fontSize:12,color:"var(--text3)",textTransform:"uppercase",
                letterSpacing:"0.06em",marginBottom:8}}>Steueroptimierungen</div>
              {aktiverFall.ki_analyse.optimierungen.map((o,i)=>(
                <div key={i} style={{background:"color-mix(in srgb, var(--green) 8%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--green) 22%, transparent)",
                  borderRadius:8,padding:"8px 12px",marginBottom:6}}>
                  <div style={{fontWeight:600,color:"var(--green)",fontSize:13}}>
                    💡 {o.titel} — {fmt(o.betrag)} Ersparnis
                  </div>
                  <div style={{fontSize:12,color:"var(--text2)"}}>{o.beschreibung}</div>
                </div>
              ))}
            </div>
          )}

          {/* Nachzahlung → Finanzierung */}
          {aktiverFall.ist_nachzahlung&&aktiverFall.finanzierungsangebot&&(
            <div style={{background:"color-mix(in srgb, var(--orange) 8%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--orange) 22%, transparent)",
              borderRadius:10,padding:"12px 14px",marginBottom:14}}>
              <div style={{fontWeight:600,color:"var(--orange)",fontSize:13,marginBottom:4}}>
                💳 Nachzahlung erkannt — Finanzierungsoptionen verfügbar
              </div>
              <div style={{fontSize:12,color:"var(--text2)"}}>
                Stundungsantrag (§ 222 AO) ist bereits ausgefüllt.
                Günstigste Option: Ratenzahlung beim Finanzamt (1,8% p.a.)
              </div>
            </div>
          )}

          {/* Aktionen */}
          <div style={{display:"flex",gap:8}}>
            {aktiverFall.empfehlung==="auto_freigabe"&&(
              <Btn variant="success" onClick={()=>freigeben(aktiverFall.id)}>
                ✓ Automatisch freigeben ({aktiverFall.konfidenz_score}% Konfidenz)
              </Btn>
            )}
            {aktiverFall.empfehlung!=="auto_freigabe"&&(
              <Btn variant="primary" onClick={()=>freigeben(aktiverFall.id)}>
                ✓ Nach Review freigeben
              </Btn>
            )}
            {aktiverFall.elster_xml_b64&&(
              <Btn variant="ghost" onClick={()=>{
                const b = atob(aktiverFall.elster_xml_b64);
                const blob = new Blob([b],{type:"application/xml"});
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `ELSTER_${aktiverFall.mandant}_${aktiverFall.steuerart}_${aktiverFall.jahr}.xml`;
                a.click();
              }}>⬇ ELSTER XML</Btn>
            )}
          </div>
        </div>
      )}

      {/* Aktive Steuerfälle */}
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,
        color:"var(--text)",marginBottom:12}}>Aktive Steuerfälle</div>

      {faelleAktiv.length===0 ? (
        <div style={{color:"var(--text3)",textAlign:"center",padding:"24px 0"}}>
          Keine aktiven Steuerfälle — neue Fälle erscheinen nach „autom. verarbeiten“.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:8}}>
          {faelleAktiv.map((f,i)=>{
            const kc = KONFIDENZ_FARBE(f.konfidenz_score);
            return (
              <div key={fallId(f) || `aktiv-${i}`} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
                borderRadius:12,padding:"12px 16px",
                display:"flex",alignItems:"center",gap:14,flexWrap:"wrap",
                animation:`fadeUp 0.3s ease ${i*30}ms both`}}>
                <div style={{width:52,height:52,borderRadius:"50%",flexShrink:0,
                  border:`2px solid ${kc}`,display:"flex",alignItems:"center",
                  justifyContent:"center",flexDirection:"column"}}>
                  <div style={{fontSize:14,fontWeight:700,color:kc}}>
                    {f.konfidenz_score}%
                  </div>
                </div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:600,color:"var(--text)",fontSize:14}}>
                    {f.mandant} — {f.steuerart} {f.jahr}
                  </div>
                  <div style={{fontSize:12,color:"var(--text3)"}}>
                    {new Date(f.erstellt_am).toLocaleDateString("de-DE")} ·{" "}
                    {f.status==="freigegeben"
                      ? <span style={{color:"var(--green)"}}>Freigegeben ✓</span>
                      : <span style={{color:"var(--orange)"}}>{f.empfehlung_text}</span>}
                  </div>
                </div>
                {f.status!=="freigegeben"&&(
                  <Btn size="xs" variant="success" disabled={!fallId(f)} onClick={()=>fallId(f) && freigeben(fallId(f))}>Freigeben</Btn>
                )}
                <Btn size="xs" variant="ghost" disabled={!fallId(f)} onClick={()=>fallId(f) && inHistorie(fallId(f))}>📥 In Historie</Btn>
              </div>
            );
          })}
        </div>
      )}

      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,
        color:"var(--text)",margin:"28px 0 12px"}}>Historie</div>
      <div style={{fontSize:12,color:"var(--text3)",marginBottom:12,lineHeight:1.6}}>
        Freigegebene oder von Ihnen archivierte Fälle · automatische Löschung nach{" "}
        <strong>{histSteuerTtl} Tagen</strong> (Einstellungen → Workflow).
      </div>
      {faelleHist.length===0 ? (
        <div style={{color:"var(--text3)",textAlign:"center",padding:"20px 0"}}>
          Keine Einträge in der Historie.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:8}}>
          {faelleHist.map((f,i)=>(
            <div key={fallId(f) || `hist-${i}`} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
              borderRadius:12,padding:"12px 16px",
              display:"flex",alignItems:"center",gap:10,flexWrap:"wrap",
              animation:`fadeUp 0.3s ease ${i*25}ms both`}}>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontWeight:600,color:"var(--text2)",fontSize:14,textDecoration:"line-through"}}>
                  {f.mandant} — {f.steuerart} {f.jahr}
                </div>
                <div style={{fontSize:11,color:"var(--text3)"}}>
                  {typeof f.historie_verbleibend_tage === "number"
                    ? `Noch ca. ${f.historie_verbleibend_tage} Tag${f.historie_verbleibend_tage!==1?"e":""} sichtbar`
                    : ""}
                  {f.status==="freigegeben" && " · Freigegeben"}
                </div>
              </div>
              <Btn size="xs" variant="subtle" disabled={!fallId(f)} onClick={()=>fallId(f) && steuerFallWiederherstellen(fallId(f))}>↩ Wiederherstellen</Btn>
              <Btn size="xs" variant="ghost" disabled={!fallId(f)} onClick={()=>fallId(f) && steuerFallLoeschen(fallId(f))}>Löschen</Btn>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════════════════════════
// FINANZIERUNG TAB
// ══════════════════════════════════════════════════════════

const FinanzierungTab = () => {
  const [mandanten, setMandanten] = useState([]);
  const [form,      setForm]      = useState({
    mandant: "",
    betrag: "",
    steuerart: "ESt",
    frist_datum: "",
  });
  const [angebot,   setAngebot]   = useState(null);
  const [loading,   setLoading]   = useState(false);

  useEffect(()=>{
    api("/mandanten").then(d=>{
      const raw=d?.data||[];
      setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
    }).catch(()=>{});
  },[]);

  const erstelle = async () => {
    const betragNum = parseFloat(String(form.betrag).replace(",", "."));
    if (!String(form.mandant || "").trim() || !Number.isFinite(betragNum) || betragNum <= 0) {
      alert("Bitte Mandant und Betrag eingeben");
      return;
    }
    const payload = {
      mandant: form.mandant,
      betrag: betragNum,
      steuerart: form.steuerart,
      frist_datum: form.frist_datum || "",
    };
    setLoading(true);
    try{
      const a = await api("/finanzierung/angebot",{method:"POST",body:JSON.stringify(payload)});
      setAngebot(a);
    }catch(e){alert(e.message);}
    finally{setLoading(false);}
  };

  const inp = (style={}) => ({
    background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
    color:"var(--text)",padding:"8px 11px",fontSize:13,
    fontFamily:"'DM Sans',sans-serif",outline:"none",...style,
  });

  return (
    <div>
      <div style={{background:"var(--bg2)",border:`1px solid var(--border)`,
        borderRadius:14,padding:20,marginBottom:20}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
          color:"var(--accent)",marginBottom:14}}>
          💳 Finanzierungsangebot erstellen
        </div>
        <div style={{fontSize:13,color:"var(--text2)",marginBottom:14,lineHeight:1.7}}>
          Steuernachzahlung erkannt? Das System erstellt sofort:
          Stundungsantrag (§ 222 AO), Ratenzahlungsoptionen und Partner-Empfehlungen.
        </div>
        <div style={{display:"grid",gridTemplateColumns:"2fr 1fr 1fr",gap:10,marginBottom:12}}>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Mandant</div>
            <select value={form.mandant} onChange={e=>setForm(f=>({...f,mandant:e.target.value}))}
              style={inp({width:"100%"})}>
              <option value="">— wählen —</option>
              {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Nachzahlung (€)</div>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              placeholder="z.B. 12500"
              value={form.betrag}
              onChange={(e) => {
                const next = sanitizeDecimalTyping(e.target.value);
                if (next === null) return;
                setForm((f) => ({ ...f, betrag: next }));
              }}
              style={inp({width:"100%"})}
            />
          </div>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Steuerart</div>
            <select value={form.steuerart}
              onChange={e=>setForm(f=>({...f,steuerart:e.target.value}))}
              style={inp({width:"100%"})}>
              {["ESt","USt","GewSt","KSt"].map(s=><option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>
        <Btn onClick={erstelle} loading={loading} variant="primary">
          💳 Finanzierungsoptionen berechnen
        </Btn>
      </div>

      {angebot&&(
        <div>
          {/* Sofort-Maßnahmen */}
          <div style={{marginBottom:16}}>
            <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
              color:"var(--text)",marginBottom:12}}>Sofort-Maßnahmen</div>
            {angebot.sofort_massnahmen?.map((m,i)=>{
              const bc = m.prioritaet==="kritisch"?"var(--red)":m.prioritaet==="hoch"?"var(--orange)":"var(--blue)";
              return (
                <div key={i} style={{background:bc+"0d",border:`1px solid ${bc}25`,
                  borderRadius:10,padding:"12px 14px",marginBottom:8,
                  display:"flex",gap:12}}>
                  <span style={{fontSize:22,flexShrink:0}}>{m.icon}</span>
                  <div>
                    <div style={{fontWeight:600,color:bc,fontSize:13,marginBottom:3}}>{m.titel}</div>
                    <div style={{fontSize:12,color:"var(--text2)",lineHeight:1.6}}>{m.text}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Stundungsantrag */}
          {angebot.stundungsantrag&&(
            <div style={{marginBottom:16,background:"var(--bg2)",border:`1px solid var(--border)`,
              borderRadius:14,padding:18}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:10}}>
                <div style={{fontFamily:"'DM Serif Display',serif",fontSize:16,color:"var(--accent)"}}>
                  Stundungsantrag (§ 222 AO)
                </div>
                <Btn size="xs" variant="ghost" onClick={()=>{
                  navigator.clipboard.writeText(angebot.stundungsantrag.text);
                  alert("Antrag kopiert!");
                }}>📋 Kopieren</Btn>
              </div>
              <pre style={{fontFamily:"'DM Sans',sans-serif",fontSize:12,
                color:"var(--text2)",lineHeight:1.8,background:"var(--bg3)",
                borderRadius:8,padding:14,maxHeight:200,overflowY:"auto",
                whiteSpace:"pre-wrap"}}>
                {angebot.stundungsantrag.text}
              </pre>
              <div style={{fontSize:11,color:"var(--orange)",marginTop:8}}>
                ⚠ {angebot.stundungsantrag.hinweis}
              </div>
            </div>
          )}

          {/* Finanzierungs-Optionen */}
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
            color:"var(--text)",marginBottom:12}}>Finanzierungsoptionen</div>
          {angebot.optionen?.map((o,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid ${o.empfehlung?"color-mix(in srgb, var(--green) 30%, transparent)":"var(--border)"}`,
              borderRadius:12,padding:"14px 18px",marginBottom:10}}>
              <div style={{display:"flex",justifyContent:"space-between",marginBottom:8}}>
                <div>
                  <div style={{fontWeight:600,color:"var(--text)",fontSize:15}}>
                    {o.name}
                    {o.empfehlung&&<span style={{marginLeft:8,fontSize:11,
                      background:"color-mix(in srgb, var(--green) 16%, var(--bg3))",color:"var(--green)",padding:"2px 8px",
                      borderRadius:10}}>Empfohlen</span>}
                  </div>
                  <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>{o.beschreibung}</div>
                </div>
                <div style={{textAlign:"right",flexShrink:0}}>
                  <div style={{fontFamily:"'DM Serif Display',serif",fontSize:20,color:"var(--accent)"}}>
                    {o.zinssatz}% p.a.
                  </div>
                </div>
              </div>
              <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:8}}>
                {o.raten_optionen?.slice(0,3).map((r,j)=>(
                  <div key={j} style={{background:"var(--bg3)",borderRadius:8,padding:"8px 12px",
                    fontSize:12,color:"var(--text2)"}}>
                    <div style={{color:"var(--text)",fontWeight:600}}>{r.monate} Monate</div>
                    <div>{fmt(r.rate_monatlich)}/Monat</div>
                    <div style={{fontSize:11,color:"var(--text3)"}}>Zinsen: {fmt(r.zinsen_gesamt)}</div>
                  </div>
                ))}
              </div>
              {o.link&&(
                <a href={o.link} target="_blank" rel="noopener noreferrer"
                   style={{fontSize:12,color:"var(--accent)",marginTop:8,display:"block"}}>
                  → {o.name} aufrufen
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════════════════════════
// ML-BUCHUNG TAB
// ══════════════════════════════════════════════════════════

const MLTab = () => {
  const [stats,       setStats]       = useState(null);
  const [lieferanten, setLieferanten] = useState([]);
  const [testInput,   setTestInput]   = useState({
    lieferant: "",
    betrag: "",
    inhalt: "",
    branche: "",
  });
  const [testResult,  setTestResult]  = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [testing,     setTesting]     = useState(false);

  useEffect(()=>{
    Promise.allSettled([api("/ml/statistiken"),api("/ml/lieferanten")]).then(([s,l])=>{
      if(s.status==="fulfilled") setStats(s.value);
      if(l.status==="fulfilled") setLieferanten(l.value?.lieferanten||[]);
      setLoading(false);
    });
  },[]);

  const teste = async () => {
    const betragNum = parseFloat(String(testInput.betrag).replace(",", "."));
    const payload = {
      ...testInput,
      betrag: Number.isFinite(betragNum) ? betragNum : 0,
    };
    setTesting(true);
    try{
      const r = await api("/ml/kategorisieren",{method:"POST",body:JSON.stringify(payload)});
      setTestResult(r);
    }catch(e){alert(e.message);}
    finally{setTesting(false);}
  };

  const inp = (style={}) => ({
    background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
    color:"var(--text)",padding:"8px 11px",fontSize:13,
    fontFamily:"'DM Sans',sans-serif",outline:"none",...style,
  });

  if(loading) return <div style={{color:"var(--text3)",padding:"20px 0"}}>Laden...</div>;

  return (
    <div>
      {stats&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:14,marginBottom:20}}>
          {[
            {l:"Trainings-Buchungen",    v:stats.trainings_buchungen, c:"var(--blue)"},
            {l:"Bekannte Lieferanten",   v:stats.bekannte_lieferanten,c:"var(--green)"},
            {l:"Gelernte Patterns",      v:stats.patterns,           c:"var(--accent)"},
          ].map((s,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
              borderRadius:12,padding:"14px 16px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
                letterSpacing:"0.07em",marginBottom:4}}>{s.l}</div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:24,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{background:"var(--bg2)",border:`1px solid var(--border)`,
        borderRadius:14,padding:20,marginBottom:20}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
          color:"var(--accent)",marginBottom:12}}>🧪 Kategorisierung testen</div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:12}}>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Lieferant</div>
            <input value={testInput.lieferant}
              onChange={e=>setTestInput(f=>({...f,lieferant:e.target.value}))}
              placeholder="z.B. Amazon, Tankstelle Shell..." style={inp({width:"100%"})}/>
          </div>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Betrag (€)</div>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              placeholder="z.B. 49,99"
              value={testInput.betrag}
              onChange={(e) => {
                const next = sanitizeDecimalTyping(e.target.value);
                if (next === null) return;
                setTestInput((f) => ({ ...f, betrag: next }));
              }}
              style={inp({width:"100%"})}
            />
          </div>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Beleg-Inhalt (Stichworte)</div>
            <input value={testInput.inhalt}
              onChange={e=>setTestInput(f=>({...f,inhalt:e.target.value}))}
              placeholder="z.B. Druckerpatronen, Büropapier..." style={inp({width:"100%"})}/>
          </div>
          <div>
            <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Branche (optional)</div>
            <input value={testInput.branche}
              onChange={e=>setTestInput(f=>({...f,branche:e.target.value}))}
              placeholder="z.B. Gastronomie / Lebensmittel" style={inp({width:"100%"})}/>
          </div>
        </div>
        <Btn onClick={teste} loading={testing} variant="primary">🧠 Kategorisieren</Btn>

        {testResult&&(
          <div style={{marginTop:14,background:"var(--bg3)",borderRadius:10,padding:14,
            border:`1px solid var(--border)`}}>
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10}}>
              {[
                {l:"Kategorie",     v:testResult.kategorie_name||testResult.kategorie, c:"var(--accent)"},
                {l:"SKR03-Konto",   v:testResult.skr03_konto,   c:"var(--blue)"},
                {l:"Konfidenz",     v:`${Math.round((testResult.konfidenz||0)*100)}%`,
                 c:testResult.konfidenz>=0.8?"var(--green)":testResult.konfidenz>=0.6?"var(--orange)":"var(--red)"},
              ].map((x,i)=>(
                <div key={i} style={{background:"var(--bg2)",borderRadius:8,padding:"8px 12px"}}>
                  <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
                    letterSpacing:"0.06em",marginBottom:2}}>{x.l}</div>
                  <div style={{fontSize:14,fontWeight:600,color:x.c}}>{x.v}</div>
                </div>
              ))}
            </div>
            <div style={{fontSize:12,color:"var(--text3)",marginTop:10}}>
              Methode: {testResult.methode} · {testResult.begruendung}
            </div>
          </div>
        )}
      </div>

      {/* Bekannte Lieferanten */}
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
        color:"var(--text)",marginBottom:12}}>
        Bekannte Lieferanten ({lieferanten.length})
      </div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(2,1fr)",gap:8}}>
        {lieferanten.slice(0,20).map((l,i)=>(
          <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
            borderRadius:8,padding:"8px 12px",display:"flex",
            justifyContent:"space-between",alignItems:"center"}}>
            <div>
              <div style={{fontSize:13,color:"var(--text)",fontWeight:500}}>{l.lieferant}</div>
              <div style={{fontSize:11,color:"var(--text3)"}}>{l.hauptkategorie}</div>
            </div>
            <div style={{fontSize:11,color:"var(--text3)"}}>
              {l.buchungen||0}×
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function SteuerAutopilot() {
  const [tab, setTab] = useState("autopilot");
  return (
    <div style={{flex:1,background:"var(--bg)",overflowY:"auto",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
      `}</style>
      <div style={{background:"var(--bg2)",borderBottom:`1px solid var(--border)`,
        padding:"20px 32px",position:"sticky",top:0,zIndex:10}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,
          color:"var(--text)",marginBottom:14}}>KI-Automatisierung</div>
        <div style={{display:"flex",gap:4}}>
          {TABS.map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id)} style={{
              display:"flex",alignItems:"center",gap:7,padding:"8px 14px",
              borderRadius:10,border:"none",
              background:tab===t.id?"var(--bg3)":"transparent",
              color:tab===t.id?"var(--accent)":"var(--text2)",
              fontWeight:tab===t.id?600:400,fontSize:13,cursor:"pointer",
              fontFamily:"'DM Sans',sans-serif",
              borderBottom:tab===t.id?`2px solid ${"var(--accent)"}`:"2px solid transparent",
              transition:"all 0.15s"}}>
              <span>{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{padding:"28px 32px"}}>
        {tab==="autopilot"   && <AutopilotTab />}
        {tab==="finanzierung" && <FinanzierungTab />}
        {tab==="ml"          && <MLTab />}
      </div>
    </div>
  );
}