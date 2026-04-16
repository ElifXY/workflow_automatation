// ============================================================
// KANZLEI AI — WORKFLOW BAUKASTEN v1.0
// Datei: src/pages/WorkflowBaukasten.js
//
// No-Code Automatisierungs-Editor
// Kanzleien klicken eigene Workflows zusammen — kein Code nötig
// ============================================================

import { useState, useEffect, useCallback } from "react";

const C = {
  red:"#e05555",orange:"#e08c45",green:"#5cb87a",blue:"#5b8de8",
  accent:"#c8a96e",purple:"#9b72e8",
  text:"#e8eaf0",text2:"#8b91a0",text3:"#555d6e",
  bg:"#0b0d11",bg2:"#111419",bg3:"#181c24",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.14)",
};

const BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";
const api  = async (url, opts={}) => {
  const token = localStorage.getItem("kanzlei_token");
  const r = await fetch(BASE+url, {...opts, headers:{
    "Content-Type":"application/json",
    ...(token?{Authorization:`Bearer ${token}`}:{}),
    ...(opts.headers||{}),
  }});
  const d = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(d.detail||`${r.status}`);
  return d;
};

const Btn = ({children,onClick,variant="primary",size="md",loading=false,disabled=false,style={}}) => {
  const vs={primary:{background:C.accent,color:"#1a1200",border:"none"},
    ghost:{background:"transparent",color:C.text2,border:`1px solid ${C.border2}`},
    subtle:{background:C.bg3,color:C.text2,border:`1px solid ${C.border}`},
    success:{background:C.green+"18",color:C.green,border:`1px solid ${C.green}30`},
    danger:{background:C.red+"18",color:C.red,border:`1px solid ${C.red}30`}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],
    fontSize:fs[size],fontWeight:500,borderRadius:10,
    cursor:loading||disabled?"not-allowed":"pointer",opacity:loading||disabled?0.5:1,
    transition:"all 0.15s",fontFamily:"'DM Sans',sans-serif",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",
      border:"2px solid currentColor",borderTopColor:"transparent",
      animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

// ── Tabs ─────────────────────────────────────────────────────
const TABS = [
  {id:"regeln",     label:"Workflow-Regeln",   icon:"⚙"},
  {id:"bot",        label:"Proaktiver Bot",    icon:"🤖"},
  {id:"lohn",       label:"Lohnabrechnung",   icon:"💶"},
];

// ══════════════════════════════════════════════════════════
// TAB: WORKFLOW REGELN
// ══════════════════════════════════════════════════════════

const RegelEditor = ({ onSave, verfuegbar }) => {
  const [name,        setName]        = useState("");
  const [beschreibung,setBeschreibung]= useState("");
  const [trigger,     setTrigger]     = useState({typ:"keine_antwort_tage",parameter:7});
  const [aktionen,    setAktionen]    = useState([{typ:"email_senden",parameter:{}}]);
  const [saving,      setSaving]      = useState(false);

  const triggerTypen = Object.entries(verfuegbar?.trigger || {});
  const aktionTypen  = Object.entries(verfuegbar?.aktionen || {});

  const submit = async () => {
    if (!name.trim()) { alert("Bitte Namen eingeben"); return; }
    setSaving(true);
    try {
      await onSave({ name, beschreibung, trigger, aktionen, aktiv:true });
      setName(""); setBeschreibung(""); setAktionen([{typ:"email_senden",parameter:{}}]);
    } catch(e) { alert(e.message); }
    finally { setSaving(false); }
  };

  const inp = (style={}) => ({
    background:C.bg, border:`1px solid ${C.border2}`, borderRadius:8,
    color:C.text, padding:"8px 11px", fontSize:13,
    fontFamily:"'DM Sans',sans-serif", outline:"none", ...style,
  });

  return (
    <div style={{background:C.bg2,border:`1px solid ${C.border}`,
      borderRadius:14,padding:22,marginBottom:20}}>
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
        color:C.accent,marginBottom:16}}>
        + Neue Automatisierungs-Regel
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:14}}>
        <div>
          <div style={{fontSize:11,color:C.text3,textTransform:"uppercase",
            letterSpacing:"0.06em",marginBottom:4}}>Name *</div>
          <input value={name} onChange={e=>setName(e.target.value)}
            placeholder="z.B. Kein Kontakt 7 Tage" style={{...inp(),width:"100%"}} />
        </div>
        <div>
          <div style={{fontSize:11,color:C.text3,textTransform:"uppercase",
            letterSpacing:"0.06em",marginBottom:4}}>Beschreibung</div>
          <input value={beschreibung} onChange={e=>setBeschreibung(e.target.value)}
            placeholder="Was macht diese Regel?" style={{...inp(),width:"100%"}} />
        </div>
      </div>

      {/* WENN (Trigger) */}
      <div style={{background:C.bg3,borderRadius:10,padding:14,marginBottom:10,
        border:`1px solid ${C.blue}30`}}>
        <div style={{fontWeight:600,color:C.blue,fontSize:13,marginBottom:10}}>
          WENN (Trigger)
        </div>
        <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
          <select value={trigger.typ} onChange={e=>setTrigger(t=>({...t,typ:e.target.value}))}
            style={{...inp(),flex:1}}>
            {triggerTypen.map(([k,v])=>(
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          {verfuegbar?.trigger?.[trigger.typ]?.parameter && (
            <div style={{display:"flex",gap:6,alignItems:"center"}}>
              <input type="number" value={trigger.parameter || ""}
                onChange={e=>setTrigger(t=>({...t,parameter:parseInt(e.target.value)||0}))}
                style={{...inp(),width:80}} />
              <span style={{fontSize:12,color:C.text3}}>
                {trigger.typ.includes("tage")?"Tage":""}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* DANN (Aktionen) */}
      <div style={{background:C.bg3,borderRadius:10,padding:14,
        border:`1px solid ${C.green}30`}}>
        <div style={{fontWeight:600,color:C.green,fontSize:13,marginBottom:10}}>
          DANN (Aktionen)
        </div>
        {aktionen.map((a,i)=>(
          <div key={i} style={{display:"flex",gap:8,marginBottom:8,alignItems:"center"}}>
            <span style={{color:C.text3,fontSize:12,flexShrink:0}}>→</span>
            <select value={a.typ} onChange={e=>setAktionen(prev=>
              prev.map((x,idx)=>idx===i?{...x,typ:e.target.value}:x))}
              style={{...inp(),flex:1}}>
              {aktionTypen.map(([k,v])=>(
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
            {aktionen.length > 1 && (
              <Btn size="xs" variant="danger"
                   onClick={()=>setAktionen(prev=>prev.filter((_,idx)=>idx!==i))}>✕</Btn>
            )}
          </div>
        ))}
        <Btn size="xs" variant="ghost"
             onClick={()=>setAktionen(prev=>[...prev,{typ:"email_senden",parameter:{}}])}>
          + Aktion hinzufügen
        </Btn>
      </div>

      <div style={{marginTop:14,display:"flex",gap:8}}>
        <Btn onClick={submit} loading={saving} variant="primary">
          Regel speichern
        </Btn>
      </div>
    </div>
  );
};

const RegelnTab = () => {
  const [regeln,     setRegeln]     = useState([]);
  const [verfuegbar, setVerfuegbar] = useState({trigger:{}, aktionen:{}});
  const [stats,      setStats]      = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [running,    setRunning]    = useState(false);
  const [toast,      setToast]      = useState(null);

  const showToast = (t) => { setToast(t); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    try {
      const [r,v,s] = await Promise.allSettled([
        api("/regeln"), api("/regeln/verfuegbare-trigger"), api("/regeln/statistiken"),
      ]);
      if(r.status==="fulfilled") setRegeln(r.value?.regeln||[]);
      if(v.status==="fulfilled") setVerfuegbar(v.value);
      if(s.status==="fulfilled") setStats(s.value);
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{laden();},[laden]);

  const handleSave = async (data) => {
    await api("/regeln",{method:"POST",body:JSON.stringify(data)});
    showToast("✓ Regel erstellt");
    laden();
  };

  const toggleRegel = async (id, aktiv) => {
    await api(`/regeln/${id}/aktiv?aktiv=${!aktiv}`,{method:"PUT"});
    laden();
  };

  const loeschen = async (id) => {
    if(!window.confirm("Regel löschen?")) return;
    await api(`/regeln/${id}`,{method:"DELETE"});
    laden();
  };

  const ausfuehren = async () => {
    setRunning(true);
    try {
      await api("/regeln/ausfuehren",{method:"POST"});
      showToast("✓ Alle Regeln werden ausgeführt");
    } catch(e){showToast(e.message);}
    finally{setRunning(false);}
  };

  const standardErstellen = async () => {
    const d = await api("/regeln/standard-erstellen",{method:"POST"});
    showToast(`✓ ${d.erstellt?.length||0} Standard-Regeln erstellt`);
    laden();
  };

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
        fontSize:13,border:`1px solid ${C.green}44`,borderLeft:`3px solid ${C.green}`}}>
        {toast}</div>}

      {/* Stats */}
      {stats && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:20}}>
          {[
            {l:"Regeln aktiv",     v:stats.regeln_aktiv,   c:C.green},
            {l:"Ausführungen",     v:stats.ausfuehrungen,  c:C.blue},
            {l:"Aktionen gesamt",  v:stats.aktionen_gesamt,c:C.accent},
            {l:"Regeln gesamt",    v:stats.regeln_gesamt,  c:C.text2},
          ].map((s,i)=>(
            <div key={i} style={{background:C.bg2,border:`1px solid ${C.border}`,
              borderRadius:12,padding:"14px 16px"}}>
              <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",
                letterSpacing:"0.07em",marginBottom:4}}>{s.l}</div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:24,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{display:"flex",gap:8,marginBottom:20}}>
        <Btn onClick={ausfuehren} loading={running} variant="primary" size="sm">
          ▶ Alle Regeln jetzt ausführen
        </Btn>
        <Btn onClick={standardErstellen} variant="ghost" size="sm">
          + Standard-Workflows erstellen
        </Btn>
      </div>

      {!loading && (
        <RegelEditor onSave={handleSave} verfuegbar={verfuegbar} />
      )}

      {/* Regeln Liste */}
      {loading ? (
        <div style={{color:C.text3,padding:"20px 0"}}>Laden...</div>
      ) : regeln.length === 0 ? (
        <div style={{color:C.text3,textAlign:"center",padding:"32px 0"}}>
          <div style={{fontSize:36,marginBottom:12}}>⚙</div>
          Noch keine Regeln — oben eine erstellen oder Standard-Workflows nutzen.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {regeln.map((r,i)=>(
            <div key={r.id} style={{
              background:C.bg2, border:`1px solid ${r.aktiv?C.green+"30":C.border}`,
              borderRadius:12, padding:"14px 18px",
              opacity:r.aktiv?1:0.5,
              animation:`fadeUp 0.3s ease ${i*40}ms both`,
            }}>
              <div style={{display:"flex",alignItems:"center",gap:12}}>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                    <span style={{fontWeight:600,color:C.text,fontSize:14}}>{r.name}</span>
                    {r.aktiv
                      ? <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                          background:C.green+"20",color:C.green}}>AKTIV</span>
                      : <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                          background:C.text3+"20",color:C.text3}}>INAKTIV</span>
                    }
                  </div>
                  <div style={{fontSize:12,color:C.text3}}>
                    WENN: {r.trigger?.typ} · DANN: {r.aktionen?.map(a=>a.typ).join(", ")}
                  </div>
                  {r.ausfuehrungen > 0 && (
                    <div style={{fontSize:11,color:C.text3,marginTop:3}}>
                      {r.ausfuehrungen}× ausgeführt · {r.aktionen_gesamt} Aktionen
                      {r.letzte_ausfuehrung && ` · Zuletzt: ${new Date(r.letzte_ausfuehrung).toLocaleDateString("de-DE")}`}
                    </div>
                  )}
                </div>
                <div style={{display:"flex",gap:6,flexShrink:0}}>
                  <Btn size="xs" variant="ghost"
                       onClick={()=>toggleRegel(r.id, r.aktiv)}>
                    {r.aktiv?"Pause":"Aktivieren"}
                  </Btn>
                  <Btn size="xs" variant="danger" onClick={()=>loeschen(r.id)}>🗑</Btn>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════════════════════════
// TAB: PROAKTIVER BOT
// ══════════════════════════════════════════════════════════

const BotTab = () => {
  const [stats,   setStats]   = useState(null);
  const [fragen,  setFragen]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [toast,   setToast]   = useState(null);

  const showToast = (t) => { setToast(t); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    try {
      const [s,f] = await Promise.allSettled([
        api("/bot/statistiken"), api("/bot/fragen?status=offen"),
      ]);
      if(s.status==="fulfilled") setStats(s.value);
      if(f.status==="fulfilled") setFragen(f.value?.fragen||[]);
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{laden();},[laden]);

  const analyseStarten = async () => {
    setRunning(true);
    try {
      await api("/bot/analyse",{method:"POST"});
      showToast("✓ Bot-Analyse gestartet (läuft im Hintergrund)");
      setTimeout(laden, 3000);
    } catch(e){showToast(e.message);}
    finally{setRunning(false);}
  };

  const PRIO_COLORS = {kritisch:C.red,hoch:C.orange,mittel:C.blue,niedrig:C.text3};

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
        fontSize:13,border:`1px solid ${C.green}44`,borderLeft:`3px solid ${C.green}`}}>
        {toast}</div>}

      {/* Statistiken */}
      {stats && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:14,marginBottom:20}}>
          {[
            {l:"Fragen gestellt",     v:stats.fragen_gesamt,      c:C.blue},
            {l:"Beantwortet",         v:stats.fragen_beantwortet, c:C.green},
            {l:"Gesparte Telefonate", v:stats.gesparte_telefonate,c:C.accent},
            {l:"Gesparte Stunden",    v:stats.gesparte_stunden+"h",c:C.purple},
            {l:"Zeitersparnis (€)",   v:`€${stats.zeitersparnis_euro}`,c:C.green},
            {l:"Antwortquote",        v:`${stats.antwortquote_prozent}%`,c:C.text2},
          ].map((s,i)=>(
            <div key={i} style={{background:C.bg2,border:`1px solid ${C.border}`,
              borderRadius:12,padding:"14px 16px"}}>
              <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",
                letterSpacing:"0.07em",marginBottom:4}}>{s.l}</div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{display:"flex",gap:8,marginBottom:20}}>
        <Btn onClick={analyseStarten} loading={running} variant="primary" size="sm">
          🤖 Bot-Analyse jetzt starten
        </Btn>
        <Btn onClick={laden} variant="ghost" size="sm">↻ Aktualisieren</Btn>
      </div>

      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,
        color:C.text,marginBottom:14}}>
        Offene Bot-Fragen ({fragen.length})
      </div>

      {loading ? (
        <div style={{color:C.text3,padding:"20px 0"}}>Laden...</div>
      ) : fragen.length === 0 ? (
        <div style={{color:C.text3,textAlign:"center",padding:"32px 0"}}>
          <div style={{fontSize:36,marginBottom:12}}>🤖</div>
          Keine offenen Fragen — Bot-Analyse starten um neue zu generieren.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {fragen.slice(0,20).map((f,i)=>{
            const pc = PRIO_COLORS[f.prioritaet]||C.text3;
            return (
              <div key={f.id} style={{
                background:C.bg2,border:`1px solid ${pc}25`,
                borderRadius:12,padding:"14px 18px",
                borderLeft:`3px solid ${pc}`,
                animation:`fadeUp 0.3s ease ${i*30}ms both`,
              }}>
                <div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
                  <span style={{fontSize:20,flexShrink:0}}>{f.icon}</span>
                  <div style={{flex:1}}>
                    <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:4}}>
                      <span style={{fontWeight:600,color:C.text,fontSize:13}}>{f.mandant}</span>
                      <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                        background:pc+"20",color:pc}}>{f.prioritaet}</span>
                    </div>
                    <div style={{fontSize:13,color:C.text2,lineHeight:1.6,marginBottom:6}}>
                      {f.text}
                    </div>
                    <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                      {f.antwort_optionen?.slice(0,3).map((opt,j)=>(
                        <span key={j} style={{fontSize:11,padding:"3px 9px",borderRadius:10,
                          background:C.bg3,color:C.text3,border:`1px solid ${C.border}`}}>
                          {opt}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={{fontSize:11,color:C.text3,flexShrink:0,textAlign:"right"}}>
                    {new Date(f.erstellt_am).toLocaleDateString("de-DE")}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ══════════════════════════════════════════════════════════
// TAB: LOHNABRECHNUNG
// ══════════════════════════════════════════════════════════

const LohnTab = () => {
  const [mitarbeiter, setMitarbeiter] = useState([]);
  const [abrechnungen,setAbrechnungen]= useState([]);
  const [mandanten,   setMandanten]   = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [toast,       setToast]       = useState(null);
  const [showNeu,     setShowNeu]     = useState(false);
  const [form,        setForm]        = useState({mandant:"",name:"",brutto_monat:0,
                                                    steuer_klasse:1,wochenstunden:40});
  const [monat,       setMonat]       = useState(new Date().toISOString().slice(0,7));

  const showToast = (t) => { setToast(t); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    try {
      const [ma,ab,m] = await Promise.allSettled([
        api("/lohn/mitarbeiter"), api("/lohn/abrechnungen"), api("/mandanten"),
      ]);
      if(ma.status==="fulfilled") setMitarbeiter(ma.value?.mitarbeiter||[]);
      if(ab.status==="fulfilled") setAbrechnungen(ab.value?.abrechnungen||[]);
      if(m.status==="fulfilled") {
        const raw = m.value?.data||[];
        setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
      }
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{laden();},[laden]);

  const neuerMitarbeiter = async () => {
    try {
      await api("/lohn/mitarbeiter",{method:"POST",body:JSON.stringify(form)});
      showToast("✓ Mitarbeiter angelegt");
      setShowNeu(false);
      laden();
    } catch(e){showToast(e.message);}
  };

  const abrechnen = async (maId) => {
    try {
      await api(`/lohn/abrechnung/${maId}/${monat}`,{method:"POST"});
      showToast(`✓ Lohnabrechnung ${monat} berechnet`);
      laden();
    } catch(e){showToast(e.message);}
  };

  const batchAbrechnen = async (mandantName) => {
    try {
      const d = await api(`/lohn/batch/${encodeURIComponent(mandantName)}/${monat}`,{method:"POST"});
      showToast(`✓ ${d.anzahl} Abrechnungen erstellt`);
      laden();
    } catch(e){showToast(e.message);}
  };

  const oeffneLohnzettel = (id) => {
    window.open(`${BASE}/lohn/abrechnung/${id}/html`,"_blank");
  };

  const inp = (style={}) => ({
    background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
    color:C.text,padding:"8px 10px",fontSize:13,
    fontFamily:"'DM Sans',sans-serif",outline:"none",width:"100%",...style,
  });

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
        fontSize:13,border:`1px solid ${C.green}44`,borderLeft:`3px solid ${C.green}`}}>
        {toast}</div>}

      <div style={{display:"flex",gap:10,marginBottom:20,alignItems:"center",flexWrap:"wrap"}}>
        <div>
          <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Abrechnungsmonat</div>
          <input type="month" value={monat} onChange={e=>setMonat(e.target.value)}
            style={{...inp(),width:"auto"}}/>
        </div>
        <Btn onClick={()=>setShowNeu(!showNeu)} variant="primary" size="sm">
          + Mitarbeiter anlegen
        </Btn>
      </div>

      {/* Neuer Mitarbeiter Form */}
      {showNeu && (
        <div style={{background:C.bg2,border:`1px solid ${C.border2}`,
          borderRadius:14,padding:20,marginBottom:20}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
            color:C.accent,marginBottom:14}}>Neuer Mitarbeiter</div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10,marginBottom:12}}>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Mandant *</div>
              <select value={form.mandant} onChange={e=>setForm(f=>({...f,mandant:e.target.value}))}
                style={inp()}>
                <option value="">— wählen —</option>
                {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Name *</div>
              <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}
                placeholder="Max Mustermann" style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Brutto/Monat (€) *</div>
              <input type="number" value={form.brutto_monat}
                onChange={e=>setForm(f=>({...f,brutto_monat:parseFloat(e.target.value)||0}))}
                style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Steuerklasse</div>
              <select value={form.steuer_klasse}
                onChange={e=>setForm(f=>({...f,steuer_klasse:parseInt(e.target.value)}))}
                style={inp()}>
                {[1,2,3,4,5,6].map(k=><option key={k} value={k}>Klasse {k}</option>)}
              </select>
            </div>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4}}>Wochenstunden</div>
              <input type="number" value={form.wochenstunden}
                onChange={e=>setForm(f=>({...f,wochenstunden:parseFloat(e.target.value)||40}))}
                style={inp()}/>
            </div>
          </div>
          <div style={{display:"flex",gap:8}}>
            <Btn onClick={neuerMitarbeiter} variant="primary" size="sm">Speichern</Btn>
            <Btn onClick={()=>setShowNeu(false)} variant="ghost" size="sm">Abbrechen</Btn>
          </div>
        </div>
      )}

      {/* Mitarbeiter-Liste */}
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,
        color:C.text,marginBottom:12}}>
        Mitarbeiter ({mitarbeiter.length})
      </div>

      {mitarbeiter.length === 0 ? (
        <div style={{color:C.text3,textAlign:"center",padding:"32px 0"}}>
          Noch keine Mitarbeiter angelegt
        </div>
      ) : (
        <>
          {/* Batch-Buttons pro Mandant */}
          {[...new Set(mitarbeiter.map(m=>m.mandant))].map(man=>(
            <Btn key={man} size="xs" variant="subtle" style={{marginRight:6,marginBottom:10}}
                 onClick={()=>batchAbrechnen(man)}>
              Alle {man.split(" ")[0]} abrechnen
            </Btn>
          ))}

          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            {mitarbeiter.map((ma,i)=>{
              const ab = abrechnungen.find(a=>a.ma_id===ma.id&&a.monat===monat);
              return (
                <div key={ma.id} style={{
                  background:C.bg2,border:`1px solid ${C.border}`,
                  borderRadius:12,padding:"12px 16px",
                  display:"flex",alignItems:"center",gap:14,
                  animation:`fadeUp 0.3s ease ${i*30}ms both`,
                }}>
                  <div style={{fontSize:24}}>👤</div>
                  <div style={{flex:1}}>
                    <div style={{fontWeight:600,color:C.text}}>{ma.name}</div>
                    <div style={{fontSize:12,color:C.text3}}>
                      {ma.mandant} · €{ma.brutto_monat.toLocaleString("de-DE")}/Monat brutto
                      · Kl. {ma.steuer_klasse}
                    </div>
                    {ab && (
                      <div style={{fontSize:12,color:C.green,marginTop:2}}>
                        ✓ {monat}: Netto €{ab.netto.toLocaleString("de-DE")}
                      </div>
                    )}
                  </div>
                  <div style={{display:"flex",gap:6,flexShrink:0}}>
                    {!ab ? (
                      <Btn size="xs" variant="primary" onClick={()=>abrechnen(ma.id)}>
                        Abrechnen
                      </Btn>
                    ) : (
                      <Btn size="xs" variant="success"
                           onClick={()=>oeffneLohnzettel(ab.id)}>
                        📄 Lohnzettel
                      </Btn>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function WorkflowBaukasten() {
  const [tab, setTab] = useState("regeln");

  return (
    <div style={{flex:1,background:C.bg,overflowY:"auto",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}
      `}</style>

      <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,
        padding:"20px 32px",position:"sticky",top:0,zIndex:10}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,
          color:C.text,marginBottom:14}}>
          Automation & Tools
        </div>
        <div style={{display:"flex",gap:4}}>
          {TABS.map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id)} style={{
              display:"flex",alignItems:"center",gap:7,padding:"8px 14px",
              borderRadius:10,border:"none",
              background:tab===t.id?C.bg3:"transparent",
              color:tab===t.id?C.accent:C.text2,
              fontWeight:tab===t.id?600:400,fontSize:13,cursor:"pointer",
              fontFamily:"'DM Sans',sans-serif",
              borderBottom:tab===t.id?`2px solid ${C.accent}`:"2px solid transparent",
              transition:"all 0.15s",
            }}>
              <span>{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{padding:"28px 32px"}}>
        {tab==="regeln"     && <RegelnTab />}
        {tab==="bot"        && <BotTab />}
        {tab==="lohn"       && <LohnTab />}
      </div>
    </div>
  );
}