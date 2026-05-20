// ============================================================
// KANZLEI AI — WORKFLOW BAUKASTEN v1.0
// Datei: src/pages/WorkflowBaukasten.js
//
// No-Code Automatisierungs-Editor
// Kanzleien klicken eigene Workflows zusammen — kein Code nötig
// ============================================================

import { useState, useEffect, useCallback } from "react";
import DecimalInput from "../components/DecimalInput";

const BASE = process.env.REACT_APP_API_URL || "/api";
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
  const vs={primary:{background:"var(--accent)",color:"var(--on-accent)",border:"none"},
    ghost:{background:"transparent",color:"var(--text2)",border:`1px solid var(--border2)`},
    subtle:{background:"var(--bg3)",color:"var(--text2)",border:`1px solid var(--border)`},
    success:{background:"color-mix(in srgb, var(--green) 14%, var(--bg3))",color:"var(--green)",border:"1px solid color-mix(in srgb, var(--green) 24%, transparent)"},
    danger:{background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",color:"var(--red)",border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)"}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
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
    background:"var(--bg)", border:`1px solid var(--border2)`, borderRadius:8,
    color:"var(--text)", padding:"8px 11px", fontSize:13,
    fontFamily:"'DM Sans',sans-serif", outline:"none", ...style,
  });

  return (
    <div style={{background:"var(--bg2)",border:`1px solid var(--border)`,
      borderRadius:14,padding:22,marginBottom:20}}>
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
        color:"var(--accent)",marginBottom:16}}>
        + Neue Automatisierungs-Regel
      </div>

      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:14}}>
        <div>
          <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",
            letterSpacing:"0.06em",marginBottom:4}}>Name *</div>
          <input value={name} onChange={e=>setName(e.target.value)}
            placeholder="z.B. Kein Kontakt 7 Tage" style={{...inp(),width:"100%"}} />
        </div>
        <div>
          <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",
            letterSpacing:"0.06em",marginBottom:4}}>Beschreibung</div>
          <input value={beschreibung} onChange={e=>setBeschreibung(e.target.value)}
            placeholder="Was macht diese Regel?" style={{...inp(),width:"100%"}} />
        </div>
      </div>

      {/* WENN (Trigger) */}
      <div style={{background:"var(--bg3)",borderRadius:10,padding:14,marginBottom:10,
        border:`1px solid ${"var(--blue)"}30`}}>
        <div style={{fontWeight:600,color:"var(--blue)",fontSize:13,marginBottom:10}}>
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
              <DecimalInput integer value={trigger.parameter ?? 0} emptyValue={7}
                onChange={v=>setTrigger(t=>({...t,parameter:v}))}
                style={{...inp(),width:80}} />
              <span style={{fontSize:12,color:"var(--text3)"}}>
                {trigger.typ.includes("tage")?"Tage":""}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* DANN (Aktionen) */}
      <div style={{background:"var(--bg3)",borderRadius:10,padding:14,
        border:`1px solid ${"var(--green)"}30`}}>
        <div style={{fontWeight:600,color:"var(--green)",fontSize:13,marginBottom:10}}>
          DANN (Aktionen)
        </div>
        {aktionen.map((a,i)=>(
          <div key={i} style={{display:"flex",gap:8,marginBottom:8,alignItems:"center"}}>
            <span style={{color:"var(--text3)",fontSize:12,flexShrink:0}}>→</span>
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
      const d = await api("/regeln/ausfuehren",{method:"POST"});
      const regeln = d?.regeln_geprueft ?? d?.data?.regeln_geprueft ?? 0;
      const aktionen = d?.aktionen ?? d?.data?.aktionen ?? 0;
      showToast(`✓ Regeln ausgeführt: ${regeln} Regel(n), ${aktionen} Aktion(en)`);
      laden();
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
        background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
        fontSize:13,border:`1px solid ${"var(--green)"}44`,borderLeft:`3px solid ${"var(--green)"}`}}>
        {toast}</div>}

      {/* Stats */}
      {stats && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:14,marginBottom:20}}>
          {[
            {l:"Regeln aktiv",     v:stats.regeln_aktiv,   c:"var(--green)"},
            {l:"Ausführungen",     v:stats.ausfuehrungen,  c:"var(--blue)"},
            {l:"Aktionen gesamt",  v:stats.aktionen_gesamt,c:"var(--accent)"},
            {l:"Regeln gesamt",    v:stats.regeln_gesamt,  c:"var(--text2)"},
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
        <div style={{color:"var(--text3)",padding:"20px 0"}}>Laden...</div>
      ) : regeln.length === 0 ? (
        <div style={{color:"var(--text3)",textAlign:"center",padding:"32px 0"}}>
          <div style={{fontSize:36,marginBottom:12}}>⚙</div>
          Noch keine Regeln — oben eine erstellen oder Standard-Workflows nutzen.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {regeln.map((r,i)=>(
            <div key={r.id} style={{
              background:"var(--bg2)", border:`1px solid ${r.aktiv?"color-mix(in srgb, var(--green) 22%, transparent)":"var(--border)"}`,
              borderRadius:12, padding:"14px 18px",
              opacity:r.aktiv?1:0.5,
              animation:`fadeUp 0.3s ease ${i*40}ms both`,
            }}>
              <div style={{display:"flex",alignItems:"center",gap:12}}>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
                    <span style={{fontWeight:600,color:"var(--text)",fontSize:14}}>{r.name}</span>
                    {r.aktiv
                      ? <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                          background:"color-mix(in srgb, var(--green) 16%, var(--bg3))",color:"var(--green)"}}>AKTIV</span>
                      : <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                          background:"color-mix(in srgb, var(--text3) 18%, var(--bg3))",color:"var(--text3)"}}>INAKTIV</span>
                    }
                  </div>
                  <div style={{fontSize:12,color:"var(--text3)"}}>
                    WENN: {r.trigger?.typ} · DANN: {r.aktionen?.map(a=>a.typ).join(", ")}
                  </div>
                  {r.ausfuehrungen > 0 && (
                    <div style={{fontSize:11,color:"var(--text3)",marginTop:3}}>
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
      const d = await api("/bot/analyse",{method:"POST"});
      const n = d?.neue_fragen ?? d?.data?.neue_fragen ?? 0;
      showToast(`✓ Bot-Analyse fertig: ${n} neue Frage(n)`);
      laden();
    } catch(e){showToast(e.message);}
    finally{setRunning(false);}
  };

  const PRIO_COLORS = {kritisch:"var(--red)",hoch:"var(--orange)",mittel:"var(--blue)",niedrig:"var(--text3)"};

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
        fontSize:13,border:`1px solid ${"var(--green)"}44`,borderLeft:`3px solid ${"var(--green)"}`}}>
        {toast}</div>}

      {/* Statistiken */}
      {stats && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:14,marginBottom:20}}>
          {[
            {l:"Fragen gestellt",     v:stats.fragen_gesamt,      c:"var(--blue)"},
            {l:"Beantwortet",         v:stats.fragen_beantwortet, c:"var(--green)"},
            {l:"Gesparte Telefonate", v:stats.gesparte_telefonate,c:"var(--accent)"},
            {l:"Gesparte Stunden",    v:stats.gesparte_stunden+"h",c:"var(--purple)"},
            {l:"Zeitersparnis (€)",   v:`€${stats.zeitersparnis_euro}`,c:"var(--green)"},
            {l:"Antwortquote",        v:`${stats.antwortquote_prozent}%`,c:"var(--text2)"},
          ].map((s,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,
              borderRadius:12,padding:"14px 16px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",
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
        color:"var(--text)",marginBottom:14}}>
        Offene Bot-Fragen ({fragen.length})
      </div>

      {loading ? (
        <div style={{color:"var(--text3)",padding:"20px 0"}}>Laden...</div>
      ) : fragen.length === 0 ? (
        <div style={{color:"var(--text3)",textAlign:"center",padding:"32px 0"}}>
          <div style={{fontSize:36,marginBottom:12}}>🤖</div>
          Keine offenen Fragen — Bot-Analyse starten um neue zu generieren.
        </div>
      ) : (
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {fragen.slice(0,20).map((f,i)=>{
            const pc = PRIO_COLORS[f.prioritaet]||"var(--text3)";
            return (
              <div key={f.id} style={{
                background:"var(--bg2)",border:`1px solid ${pc}25`,
                borderRadius:12,padding:"14px 18px",
                borderLeft:`3px solid ${pc}`,
                animation:`fadeUp 0.3s ease ${i*30}ms both`,
              }}>
                <div style={{display:"flex",gap:10,alignItems:"flex-start"}}>
                  <span style={{fontSize:20,flexShrink:0}}>{f.icon}</span>
                  <div style={{flex:1}}>
                    <div style={{display:"flex",gap:8,alignItems:"center",marginBottom:4}}>
                      <span style={{fontWeight:600,color:"var(--text)",fontSize:13}}>{f.mandant}</span>
                      <span style={{fontSize:10,padding:"2px 7px",borderRadius:10,
                        background:pc+"20",color:pc}}>{f.prioritaet}</span>
                    </div>
                    <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.6,marginBottom:6}}>
                      {f.text}
                    </div>
                    <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                      {f.antwort_optionen?.slice(0,3).map((opt,j)=>(
                        <span key={j} style={{fontSize:11,padding:"3px 9px",borderRadius:10,
                          background:"var(--bg3)",color:"var(--text3)",border:`1px solid var(--border)`}}>
                          {opt}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={{fontSize:11,color:"var(--text3)",flexShrink:0,textAlign:"right"}}>
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

const leerMaForm = () => ({
  mandant: "",
  mandanten_zusatz: [],
  name: "",
  brutto_monat: 0,
  steuer_klasse: 1,
  wochenstunden: 40,
  urlaubstage: 20,
  steuer_id: "",
  sv_nr: "",
  iban: "",
  sozialversicherung: true,
});

const LohnTab = () => {
  const [mitarbeiter, setMitarbeiter] = useState([]);
  const [abrechnungen,setAbrechnungen]= useState([]);
  const [mandanten,   setMandanten]   = useState([]);
  const [toast,       setToast]       = useState(null);
  const [showForm,    setShowForm]    = useState(false);
  const [editId,      setEditId]      = useState(null);
  const [form,        setForm]        = useState(leerMaForm);
  const [filterMandant, setFilterMandant] = useState("");
  const [monat,       setMonat]       = useState(new Date().toISOString().slice(0,7));

  const showToast = (t) => { setToast(t); setTimeout(()=>setToast(null),3500); };

  const laden = useCallback(async () => {
    try {
      const maUrl = filterMandant
        ? `/lohn/mitarbeiter?mandant=${encodeURIComponent(filterMandant)}`
        : "/lohn/mitarbeiter";
      const abUrl = filterMandant
        ? `/lohn/abrechnungen?mandant=${encodeURIComponent(filterMandant)}&monat=${encodeURIComponent(monat)}`
        : `/lohn/abrechnungen?monat=${encodeURIComponent(monat)}`;
      const [ma,ab,m] = await Promise.allSettled([
        api(maUrl), api(abUrl), api("/mandanten"),
      ]);
      if(ma.status==="fulfilled") setMitarbeiter(ma.value?.mitarbeiter||[]);
      if(ab.status==="fulfilled") setAbrechnungen(ab.value?.abrechnungen||[]);
      if(m.status==="fulfilled") {
        const raw = m.value?.data||[];
        setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
      }
    } catch(e){console.error(e);}
  },[filterMandant, monat]);

  useEffect(()=>{laden();},[laden]);

  const formPayload = () => {
    const mandantenListe = [
      form.mandant.trim(),
      ...(form.mandanten_zusatz || []).filter((m) => m && m !== form.mandant),
    ];
    return {
      mandant: form.mandant.trim(),
      mandanten: mandantenListe,
      name: form.name.trim(),
      brutto_monat: form.brutto_monat,
      steuer_klasse: form.steuer_klasse,
      wochenstunden: form.wochenstunden,
      urlaubstage: form.urlaubstage,
      steuer_id: form.steuer_id?.trim() || "",
      sv_nr: form.sv_nr?.trim() || "",
      iban: form.iban?.trim() || "",
      sozialversicherung: !!form.sozialversicherung,
    };
  };

  const oeffneNeu = () => {
    setEditId(null);
    setForm(leerMaForm());
    setShowForm(true);
  };

  const oeffneBearbeiten = (ma) => {
    const liste = (ma.mandanten && ma.mandanten.length) ? ma.mandanten : [ma.mandant];
    const haupt = ma.mandant || liste[0] || "";
    setEditId(ma.id);
    setForm({
      mandant: haupt,
      mandanten_zusatz: liste.filter((m) => m !== haupt),
      name: ma.name || "",
      brutto_monat: ma.brutto_monat ?? 0,
      steuer_klasse: ma.steuer_klasse ?? 1,
      wochenstunden: ma.wochenstunden ?? 40,
      urlaubstage: ma.urlaubstage ?? 20,
      steuer_id: ma.steuer_id || "",
      sv_nr: ma.sv_nr || "",
      iban: ma.iban || "",
      sozialversicherung: ma.sozialversicherung !== false,
    });
    setShowForm(true);
  };

  const schliesseForm = () => {
    setShowForm(false);
    setEditId(null);
    setForm(leerMaForm());
  };

  const loescheMitarbeiter = async (ma) => {
    if (!window.confirm(`Mitarbeiter „${ma.name}“ wirklich löschen?`)) return;
    try {
      await api(`/lohn/mitarbeiter/${encodeURIComponent(ma.id)}`, { method: "DELETE" });
      showToast("✓ Mitarbeiter gelöscht");
      if (editId === ma.id) schliesseForm();
      laden();
    } catch (e) {
      showToast(e.message);
    }
  };

  const speichereMitarbeiter = async () => {
    if (!form.mandant?.trim()) {
      showToast("Bitte Haupt-Mandant wählen");
      return;
    }
    if (!form.name?.trim()) {
      showToast("Bitte Namen eingeben");
      return;
    }
    try {
      const body = formPayload();
      if (editId) {
        await api(`/lohn/mitarbeiter/${encodeURIComponent(editId)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        showToast("✓ Mitarbeiter gespeichert");
      } else {
        await api("/lohn/mitarbeiter", { method: "POST", body: JSON.stringify(body) });
        showToast("✓ Mitarbeiter angelegt");
      }
      schliesseForm();
      laden();
    } catch (e) {
      showToast(e.message);
    }
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

  const oeffneLohnzettel = async (id) => {
    try {
      const token = localStorage.getItem("kanzlei_token") || localStorage.getItem("token");
      const r = await fetch(`${BASE}/lohn/abrechnung/${encodeURIComponent(id)}/html`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || err.error || `HTTP ${r.status}`);
      }
      const html = await r.text();
      const w = window.open("", "_blank");
      if (!w) {
        showToast("Pop-up blockiert — bitte erlauben");
        return;
      }
      w.document.open();
      w.document.write(html);
      w.document.close();
    } catch (e) {
      showToast(e.message || "Lohnzettel konnte nicht geöffnet werden");
    }
  };

  const inp = (style={}) => ({
    background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,
    color:"var(--text)",padding:"8px 10px",fontSize:13,
    fontFamily:"'DM Sans',sans-serif",outline:"none",width:"100%",...style,
  });

  return (
    <div>
      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",
        fontSize:13,border:`1px solid ${"var(--green)"}44`,borderLeft:`3px solid ${"var(--green)"}`}}>
        {toast}</div>}

      <div style={{display:"flex",gap:10,marginBottom:20,alignItems:"flex-end",flexWrap:"wrap"}}>
        <div>
          <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Mandant filtern</div>
          <select value={filterMandant} onChange={e=>setFilterMandant(e.target.value)} style={{...inp(),width:"auto",minWidth:180}}>
            <option value="">Alle Mandanten</option>
            {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div>
          <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Abrechnungsmonat</div>
          <input type="month" value={monat} onChange={e=>setMonat(e.target.value)}
            style={{...inp(),width:"auto"}}/>
        </div>
        <Btn onClick={showForm ? schliesseForm : oeffneNeu} variant="primary" size="sm">
          {showForm ? "Abbrechen" : "+ Mitarbeiter anlegen"}
        </Btn>
      </div>

      {showForm && (
        <div style={{background:"var(--bg2)",border:`1px solid var(--border2)`,
          borderRadius:14,padding:20,marginBottom:20}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:17,
            color:"var(--accent)",marginBottom:14}}>
            {editId ? "Mitarbeiter bearbeiten" : "Neuer Mitarbeiter"}
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10,marginBottom:12}}>
            <div style={{gridColumn:"1 / -1"}}>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Haupt-Mandant (Lohnbuchhaltung) *</div>
              <select value={form.mandant} onChange={e=>setForm(f=>({...f,mandant:e.target.value}))}
                style={inp()}>
                <option value="">— wählen —</option>
                {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div style={{gridColumn:"1 / -1"}}>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:6}}>
                Weitere Mandanten (optional — z. B. Wechselmandant, Konzern)
              </div>
              <div style={{display:"flex",flexWrap:"wrap",gap:8,maxHeight:120,overflowY:"auto",
                padding:10,border:"1px solid var(--border)",borderRadius:8}}>
                {mandanten.filter(m=>m!==form.mandant).map(m=>{
                  const on = (form.mandanten_zusatz||[]).includes(m);
                  return (
                    <label key={m} style={{display:"flex",alignItems:"center",gap:6,fontSize:12,cursor:"pointer"}}>
                      <input type="checkbox" checked={on}
                        onChange={()=>setForm(f=>{
                          const z = f.mandanten_zusatz||[];
                          return {...f,mandanten_zusatz:on?z.filter(x=>x!==m):[...z,m]};
                        })}/>
                      {m}
                    </label>
                  );
                })}
              </div>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Name *</div>
              <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}
                placeholder="Max Mustermann" style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Brutto/Monat (€) *</div>
              <DecimalInput value={form.brutto_monat} emptyValue={0}
                onChange={v=>setForm(f=>({...f,brutto_monat:v}))}
                style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Steuerklasse</div>
              <select value={form.steuer_klasse}
                onChange={e=>setForm(f=>({...f,steuer_klasse:parseInt(e.target.value)}))}
                style={inp()}>
                {[1,2,3,4,5,6].map(k=><option key={k} value={k}>Klasse {k}</option>)}
              </select>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Wochenstunden</div>
              <DecimalInput value={form.wochenstunden} emptyValue={40}
                onChange={v=>setForm(f=>({...f,wochenstunden:v}))}
                style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Urlaubstage/Jahr</div>
              <input type="number" min={0} max={40} value={form.urlaubstage}
                onChange={e=>setForm(f=>({...f,urlaubstage:parseInt(e.target.value,10)||0}))}
                style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>Steuer-ID</div>
              <input value={form.steuer_id} onChange={e=>setForm(f=>({...f,steuer_id:e.target.value}))}
                placeholder="optional" style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>SV-Nr.</div>
              <input value={form.sv_nr} onChange={e=>setForm(f=>({...f,sv_nr:e.target.value}))}
                placeholder="optional" style={inp()}/>
            </div>
            <div>
              <div style={{fontSize:11,color:"var(--text3)",marginBottom:4}}>IBAN</div>
              <input value={form.iban} onChange={e=>setForm(f=>({...f,iban:e.target.value}))}
                placeholder="optional" style={inp()}/>
            </div>
            <div style={{display:"flex",alignItems:"center",gap:8,paddingTop:22}}>
              <input type="checkbox" id="ma-sv" checked={form.sozialversicherung}
                onChange={e=>setForm(f=>({...f,sozialversicherung:e.target.checked}))}/>
              <label htmlFor="ma-sv" style={{fontSize:12,color:"var(--text2)"}}>Sozialversicherung</label>
            </div>
          </div>
          <div style={{display:"flex",gap:8}}>
            <Btn onClick={speichereMitarbeiter} variant="primary" size="sm">
              {editId ? "Änderungen speichern" : "Speichern"}
            </Btn>
            <Btn onClick={schliesseForm} variant="ghost" size="sm">Abbrechen</Btn>
          </div>
        </div>
      )}

      {/* Mitarbeiter-Liste */}
      <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,
        color:"var(--text)",marginBottom:12}}>
        Mitarbeiter ({mitarbeiter.length})
      </div>

      {mitarbeiter.length === 0 ? (
        <div style={{color:"var(--text3)",textAlign:"center",padding:"32px 0"}}>
          Noch keine Mitarbeiter angelegt
        </div>
      ) : (
        <>
          {/* Batch-Buttons pro Mandant */}
          {[...new Set(mitarbeiter.flatMap(m=>(m.mandanten&&m.mandanten.length)?m.mandanten:[m.mandant]))].map(man=>(
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
                  background:"var(--bg2)",border:`1px solid var(--border)`,
                  borderRadius:12,padding:"12px 16px",
                  display:"flex",alignItems:"center",gap:14,
                  animation:`fadeUp 0.3s ease ${i*30}ms both`,
                }}>
                  <div style={{fontSize:24}}>👤</div>
                  <div style={{flex:1}}>
                    <div style={{fontWeight:600,color:"var(--text)"}}>{ma.name}</div>
                    <div style={{fontSize:12,color:"var(--text3)"}}>
                      {(ma.mandanten&&ma.mandanten.length>1)?ma.mandanten.join(" · "):ma.mandant}
                      {" "}· €{ma.brutto_monat.toLocaleString("de-DE")}/Monat brutto · Kl. {ma.steuer_klasse}
                    </div>
                    {ab && (
                      <div style={{fontSize:12,color:"var(--green)",marginTop:2}}>
                        ✓ {monat}: Netto €{ab.netto.toLocaleString("de-DE")}
                      </div>
                    )}
                  </div>
                  <div style={{display:"flex",gap:6,flexShrink:0,flexWrap:"wrap",justifyContent:"flex-end"}}>
                    <Btn size="xs" variant="ghost" onClick={()=>oeffneBearbeiten(ma)}>
                      Bearbeiten
                    </Btn>
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
          color:"var(--text)",marginBottom:14}}>
          Automation & Tools
        </div>
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