// ============================================================
// KANZLEI AI — RECHNUNGEN PAGE v1.0
// Datei: src/pages/Rechnungen.js
// Honorarrechnungen erstellen, verwalten, Mahnwesen
// ============================================================

import { useState, useEffect, useCallback } from "react";

const C = {
  red:"#e05555",orange:"#e08c45",green:"#5cb87a",blue:"#5b8de8",
  accent:"#c8a96e",text:"#e8eaf0",text2:"#8b91a0",text3:"#555d6e",
  bg:"#0b0d11",bg2:"#111419",bg3:"#181c24",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.14)",
};

const BASE   = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";
const apiFetch = async (url, opts={}) => {
  const token = localStorage.getItem("kanzlei_token");
  const res = await fetch(BASE+url, {
    ...opts, headers:{"Content-Type":"application/json",
    ...(token?{Authorization:`Bearer ${token}`}:{}), ...(opts.headers||{})},
  });
  const d = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(d.detail||`Fehler ${res.status}`);
  return d;
};

const Btn=({children,onClick,variant="primary",size="md",loading=false,disabled=false,style={}})=>{
  const vs={primary:{background:C.accent,color:"#1a1200",border:"none"},
    ghost:{background:"transparent",color:C.text2,border:`1px solid ${C.border2}`},
    subtle:{background:C.bg3,color:C.text2,border:`1px solid ${C.border}`},
    success:{background:C.green+"20",color:C.green,border:`1px solid ${C.green}30`},
    danger:{background:C.red+"18",color:C.red,border:`1px solid ${C.red}30`}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
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

const Badge=({children,color=C.accent})=>(
  <span style={{display:"inline-block",padding:"2px 9px",borderRadius:20,
    fontSize:11,fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
    background:color+"22",color,border:`1px solid ${color}33`}}>{children}</span>
);

const STATUS_CONFIG = {
  offen:    {label:"Offen",    color:C.blue},
  bezahlt:  {label:"Bezahlt",  color:C.green},
  mahnung1: {label:"Mahnung 1",color:C.orange},
  mahnung2: {label:"Mahnung 2",color:C.red},
  storno:   {label:"Storniert",color:C.text3},
};

const STBVV_POSITIONEN_LISTE = [
  {id:"buchfuehrung_monat", label:"Buchführung (monatlich)", preis:150},
  {id:"jahresabschluss",    label:"Jahresabschluss",          preis:800},
  {id:"einkommensteuer",    label:"Einkommensteuererklärung", preis:400},
  {id:"umsatzsteuer",       label:"Umsatzsteuererklärung",    preis:200},
  {id:"ustvoa",             label:"USt-Voranmeldung",         preis:60},
  {id:"gewerbesteuer",      label:"Gewerbesteuererklärung",   preis:200},
  {id:"lohnbuchhaltung",    label:"Lohnbuchhaltung",          preis:40},
  {id:"steuerberatung",     label:"Beratung (Std.)",          preis:150},
  {id:"sonstige",           label:"Sonstige Leistung",        preis:0},
];

// ── Neue Rechnung erstellen ───────────────────────────────
function NeueRechnungForm({mandanten, onErstellt, onClose}) {
  const [mandant, setMandant]     = useState("");
  const [positionen, setPositionen] = useState([{
    bezeichnung:"", menge:1, einzelpreis:0, mwst_satz:19, einheit:"pauschal"
  }]);
  const [faelligTage, setFaelligTage] = useState(14);
  const [notiz, setNotiz]         = useState("");
  const [loading, setLoading]     = useState(false);

  const addPos = () => setPositionen(p => [...p, {
    bezeichnung:"",menge:1,einzelpreis:0,mwst_satz:19,einheit:"pauschal"
  }]);

  const updatePos = (i, field, val) => setPositionen(p =>
    p.map((pos, idx) => idx===i ? {...pos,[field]:val} : pos)
  );
  const removePos = (i) => setPositionen(p => p.filter((_,idx)=>idx!==i));

  const addStbvv = (pos) => setPositionen(p => [...p, {
    bezeichnung: pos.label, menge:1, einzelpreis:pos.preis,
    mwst_satz:19, einheit:"pauschal",
  }]);

  const gesamt = positionen.reduce((s,p) => {
    const n = p.menge*p.einzelpreis;
    return s + n + n*p.mwst_satz/100;
  }, 0);

  const submit = async () => {
    if(!mandant || positionen.some(p=>!p.bezeichnung||p.einzelpreis<=0)) {
      alert("Bitte alle Felder ausfüllen"); return;
    }
    setLoading(true);
    try {
      const r = await apiFetch("/rechnungen", {
        method:"POST",
        body:JSON.stringify({mandant, positionen, faellig_tage:faelligTage, notiz}),
      });
      onErstellt(r);
    } catch(e){alert(e.message);}
    finally{setLoading(false);}
  };

  const inp = (style={}) => ({
    background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,
    color:C.text,padding:"7px 10px",fontSize:13,outline:"none",
    fontFamily:"'DM Sans',sans-serif",...style,
  });

  return (
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.75)",
      display:"flex",alignItems:"center",justifyContent:"center",zIndex:1000}}>
      <div style={{background:C.bg2,border:`1px solid ${C.border2}`,
        borderRadius:16,width:"min(700px,95vw)",maxHeight:"90vh",
        display:"flex",flexDirection:"column",overflow:"hidden"}}>
        <div style={{padding:"20px 24px",borderBottom:`1px solid ${C.border}`,
          display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:20,color:C.accent}}>
            Neue Honorarrechnung
          </div>
          <Btn variant="ghost" size="sm" onClick={onClose}>✕</Btn>
        </div>

        <div style={{flex:1,overflowY:"auto",padding:"20px 24px"}}>
          {/* Mandant & Fälligkeit */}
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:16}}>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.06em"}}>Mandant *</div>
              <select value={mandant} onChange={e=>setMandant(e.target.value)} style={{...inp(),width:"100%"}}>
                <option value="">— Mandant wählen —</option>
                {mandanten.map(m=><option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <div style={{fontSize:11,color:C.text3,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.06em"}}>Zahlungsziel (Tage)</div>
              <input type="number" value={faelligTage} min={1} max={90}
                onChange={e=>setFaelligTage(parseInt(e.target.value))}
                style={{...inp(),width:"100%"}} />
            </div>
          </div>

          {/* StBVV Schnellauswahl */}
          <div style={{marginBottom:16}}>
            <div style={{fontSize:11,color:C.text3,marginBottom:8,textTransform:"uppercase",letterSpacing:"0.06em"}}>
              StBVV Schnellauswahl
            </div>
            <div style={{display:"flex",flexWrap:"wrap",gap:6}}>
              {STBVV_POSITIONEN_LISTE.map(p=>(
                <Btn key={p.id} size="xs" variant="ghost" onClick={()=>addStbvv(p)}>
                  + {p.label} {p.preis>0?`(€${p.preis})`:""}
                </Btn>
              ))}
            </div>
          </div>

          {/* Positionen */}
          <div style={{marginBottom:12}}>
            <div style={{fontSize:11,color:C.text3,marginBottom:8,textTransform:"uppercase",letterSpacing:"0.06em"}}>Positionen</div>
            {positionen.map((pos,i)=>(
              <div key={i} style={{display:"grid",gridTemplateColumns:"3fr 1fr 1fr 1fr auto",
                gap:8,marginBottom:8,alignItems:"center"}}>
                <input placeholder="Bezeichnung" value={pos.bezeichnung}
                  onChange={e=>updatePos(i,"bezeichnung",e.target.value)}
                  style={{...inp()}} />
                <input type="number" placeholder="Menge" value={pos.menge} min={0.5} step={0.5}
                  onChange={e=>updatePos(i,"menge",parseFloat(e.target.value)||1)}
                  style={{...inp()}} />
                <input type="number" placeholder="€/Einheit" value={pos.einzelpreis} min={0}
                  onChange={e=>updatePos(i,"einzelpreis",parseFloat(e.target.value)||0)}
                  style={{...inp()}} />
                <select value={pos.mwst_satz} onChange={e=>updatePos(i,"mwst_satz",parseInt(e.target.value))}
                  style={{...inp()}}>
                  <option value={19}>19% MwSt</option>
                  <option value={7}>7% MwSt</option>
                  <option value={0}>0% MwSt</option>
                </select>
                <Btn size="xs" variant="danger" onClick={()=>removePos(i)} disabled={positionen.length<=1}>✕</Btn>
              </div>
            ))}
            <Btn size="xs" variant="ghost" onClick={addPos}>+ Position</Btn>
          </div>

          {/* Notiz */}
          <div>
            <div style={{fontSize:11,color:C.text3,marginBottom:4,textTransform:"uppercase",letterSpacing:"0.06em"}}>Notiz</div>
            <textarea value={notiz} onChange={e=>setNotiz(e.target.value)} rows={2}
              placeholder="Optionale Anmerkungen..."
              style={{...inp(),width:"100%",resize:"vertical"}} />
          </div>
        </div>

        <div style={{padding:"16px 24px",borderTop:`1px solid ${C.border}`,
          display:"flex",justifyContent:"space-between",alignItems:"center"}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:20,color:C.accent}}>
            Gesamt: €{gesamt.toFixed(2)}
          </div>
          <div style={{display:"flex",gap:8}}>
            <Btn onClick={onClose} variant="ghost">Abbrechen</Btn>
            <Btn onClick={submit} loading={loading} variant="primary">
              Rechnung erstellen
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Rechnungs-Liste ───────────────────────────────────────
export default function Rechnungen() {
  const [rechnungen, setRechnungen] = useState([]);
  const [mahnungen,  setMahnungen]  = useState([]);
  const [stats,      setStats]      = useState(null);
  const [mandanten,  setMandanten]  = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [showNeu,    setShowNeu]    = useState(false);
  const [filter,     setFilter]     = useState("alle");
  const [toast,      setToast]      = useState(null);

  const showToast = (text,type="success") => {
    setToast({text,type});
    setTimeout(()=>setToast(null),3500);
  };

  const laden = useCallback(async () => {
    try {
      const [r,s,m,mahn] = await Promise.allSettled([
        apiFetch("/rechnungen"), apiFetch("/rechnungen/statistiken"),
        apiFetch("/mandanten"), apiFetch("/rechnungen/mahnungen"),
      ]);
      if(r.status==="fulfilled") setRechnungen(r.value?.rechnungen||[]);
      if(s.status==="fulfilled") setStats(s.value);
      if(m.status==="fulfilled") {
        const raw=m.value?.data||[];
        setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
      }
      if(mahn.status==="fulfilled") setMahnungen(mahn.value?.mahnungen||[]);
    } catch(e){console.error(e);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{laden();},[laden]);

  const handleBezahlt = async (id) => {
    const betrag = prompt("Bezahlter Betrag (€):");
    if(!betrag) return;
    try {
      await apiFetch(`/rechnungen/${id}/bezahlt`, {
        method:"POST", body:JSON.stringify({betrag:parseFloat(betrag)}),
      });
      showToast("✓ Zahlung erfasst");
      laden();
    } catch(e){showToast(e.message,"error");}
  };

  const handleMahnung = async (rechnungId) => {
    try {
      await apiFetch(`/rechnungen/${rechnungId}/mahnung`, {method:"POST"});
      showToast("Mahnung erstellt");
      laden();
    } catch(e){showToast(e.message,"error");}
  };

  const handleEmail = async (r) => {
    try {
      await apiFetch(`/rechnungen/${r.id}/email`, {method:"POST"});
      showToast(`Rechnung an ${r.mandant_email||r.mandant} gesendet`);
    } catch(e){showToast(e.message,"error");}
  };

  const gefiltert = rechnungen.filter(r =>
    filter==="alle" ? true : r.status===filter
  );

  if(loading) return (
    <div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",background:C.bg}}>
      <div style={{width:36,height:36,borderRadius:"50%",border:`2px solid ${C.border2}`,
        borderTopColor:C.accent,animation:"spin 0.7s linear infinite"}}/>
    </div>
  );

  return (
    <div style={{flex:1,background:C.bg,overflowY:"auto",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}} @keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px} ::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}
      `}</style>

      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,
        background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,
        fontSize:13,fontWeight:500,animation:"fadeUp 0.25s ease",
        border:`1px solid ${toast.type==="error"?C.red:C.green}44`,
        borderLeft:`3px solid ${toast.type==="error"?C.red:C.green}`}}>{toast.text}</div>}

      {/* Header */}
      <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,padding:"20px 32px",
        display:"flex",alignItems:"center",gap:16,position:"sticky",top:0,zIndex:10}}>
        <div style={{flex:1}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,color:C.text}}>
            Honorarrechnungen
          </div>
          <div style={{fontSize:12,color:C.text3,marginTop:2}}>
            Erstellen · Versenden · Mahnwesen · Zahlungseingang
          </div>
        </div>
        <div style={{display:"flex",gap:6}}>
          {["alle","offen","bezahlt","mahnung1","mahnung2"].map(f=>(
            <Btn key={f} size="sm" variant={filter===f?"subtle":"ghost"}
              onClick={()=>setFilter(f)} style={{textTransform:"capitalize"}}>
              {STATUS_CONFIG[f]?.label||"Alle"}
              {f!=="alle"&&<span style={{marginLeft:4,color:STATUS_CONFIG[f]?.color}}>
                ({rechnungen.filter(r=>r.status===f).length})
              </span>}
            </Btn>
          ))}
        </div>
        <Btn onClick={()=>setShowNeu(true)} variant="primary">+ Neue Rechnung</Btn>
      </div>

      <div style={{padding:"28px 32px"}}>
        {/* Stats */}
        {stats&&(
          <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:16,marginBottom:24}}>
            {[
              {l:"Offene Forderungen",v:`€${(stats.offene_forderungen||0).toLocaleString("de")}`,c:C.orange},
              {l:"Bezahlter Umsatz",  v:`€${(stats.bezahlter_umsatz||0).toLocaleString("de")}`,  c:C.green},
              {l:"Überfällig",        v:`€${(stats.ueberfaellig_betrag||0).toLocaleString("de")}`,c:C.red},
              {l:"Offene Rechnungen", v:stats.offen||0, c:C.blue},
            ].map((s,i)=>(
              <div key={i} style={{background:C.bg2,border:`1px solid ${C.border}`,
                borderRadius:14,padding:"18px 20px",animation:`fadeUp 0.4s ease ${i*60}ms both`}}>
                <div style={{fontSize:11,color:C.text3,textTransform:"uppercase",
                  letterSpacing:"0.07em",marginBottom:6}}>{s.l}</div>
                <div style={{fontFamily:"'DM Serif Display',serif",fontSize:26,color:s.c}}>{s.v}</div>
              </div>
            ))}
          </div>
        )}

        {/* Mahnungen Alert */}
        {mahnungen.length>0&&(
          <div style={{background:C.red+"10",border:`1px solid ${C.red}25`,
            borderRadius:12,padding:"14px 18px",marginBottom:20}}>
            <div style={{color:C.red,fontWeight:600,fontSize:14,marginBottom:8}}>
              ⚠ {mahnungen.length} überfällige Rechnung(en) — Mahnung empfohlen
            </div>
            {mahnungen.slice(0,3).map((m,i)=>(
              <div key={i} style={{display:"flex",justifyContent:"space-between",
                alignItems:"center",padding:"6px 0",borderTop:`1px solid ${C.border}`}}>
                <span style={{fontSize:13,color:C.text2}}>
                  {m.mandant} — {m.rechnungsnummer} — €{m.betrag.toFixed(2)} ({m.tage_ueberfaellig}d)
                </span>
                <Btn size="xs" variant="danger" onClick={()=>handleMahnung(m.rechnung_id)}>
                  Mahnung senden
                </Btn>
              </div>
            ))}
          </div>
        )}

        {/* Rechnungs-Tabelle */}
        <div style={{background:C.bg2,border:`1px solid ${C.border}`,
          borderRadius:14,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{borderBottom:`1px solid ${C.border}`}}>
                {["Nummer","Mandant","Datum","Fällig","Betrag","Status",""].map(h=>(
                  <th key={h} style={{padding:"10px 16px",textAlign:"left",
                    fontSize:11,fontWeight:600,color:C.text3,
                    textTransform:"uppercase",letterSpacing:"0.07em"}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {gefiltert.length===0&&(
                <tr><td colSpan={7} style={{padding:"32px",textAlign:"center",color:C.text3}}>
                  Keine Rechnungen gefunden
                </td></tr>
              )}
              {gefiltert.map((r,i)=>{
                const cfg=STATUS_CONFIG[r.status]||{label:r.status,color:C.text3};
                const istUeberfaellig = r.status==="offen" &&
                  new Date(r.faellig_bis)<new Date();
                return (
                  <tr key={r.id} style={{borderBottom:`1px solid ${C.border}`,
                    background:i%2?`rgba(255,255,255,0.01)`:"transparent",
                    animation:`fadeUp 0.3s ease ${i*30}ms both`}}>
                    <td style={{padding:"12px 16px",fontSize:13,fontWeight:600,
                      color:C.accent}}>{r.rechnungsnummer}</td>
                    <td style={{padding:"12px 16px",fontSize:13,color:C.text}}>{r.mandant}</td>
                    <td style={{padding:"12px 16px",fontSize:12,color:C.text2}}>
                      {new Date(r.datum).toLocaleDateString("de-DE")}
                    </td>
                    <td style={{padding:"12px 16px",fontSize:12,
                      color:istUeberfaellig?C.red:C.text2}}>
                      {new Date(r.faellig_bis).toLocaleDateString("de-DE")}
                      {istUeberfaellig&&" ⚠"}
                    </td>
                    <td style={{padding:"12px 16px",fontSize:14,fontWeight:600,color:C.text}}>
                      €{r.gesamt_brutto.toFixed(2)}
                    </td>
                    <td style={{padding:"12px 16px"}}>
                      <Badge color={cfg.color}>{cfg.label}</Badge>
                    </td>
                    <td style={{padding:"12px 16px"}}>
                      <div style={{display:"flex",gap:6}}>
                        {r.status==="offen"&&<>
                          <Btn size="xs" variant="success" onClick={()=>handleBezahlt(r.id)}>✓ Bezahlt</Btn>
                          {r.mandant_email&&<Btn size="xs" variant="ghost" onClick={()=>handleEmail(r)}>✉</Btn>}
                        </>}
                        {(r.status==="offen"||r.status==="mahnung1")&&
                          <Btn size="xs" variant="danger" onClick={()=>handleMahnung(r.id)}>Mahnung</Btn>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showNeu&&(
        <NeueRechnungForm mandanten={mandanten}
          onErstellt={r=>{setShowNeu(false);showToast(`✓ ${r.rechnungsnummer} erstellt`);laden();}}
          onClose={()=>setShowNeu(false)} />
      )}
    </div>
  );
}
