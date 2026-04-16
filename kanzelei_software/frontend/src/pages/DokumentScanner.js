// ============================================================
// KANZLEI AI — DOKUMENT SCANNER v1.0
// Datei: src/pages/DokumentScanner.js
//
// KI scannt jedes hochgeladene Dokument und:
//   ✓ Erkennt Dokumenttyp automatisch
//   ✓ Liest Metadaten (Datum, Betrag, Absender)
//   ✓ Schlägt Ordner vor — alles editierbar
//   ✓ Ordnet Mandant zu
//   ✓ Erstellt direkt Aufgaben
//   ✓ Digitale Unterschrift (Signatur-Pad)
// ============================================================

import { useState, useRef, useCallback, useEffect } from "react";

const C = {
  red:"#e05555",orange:"#e08c45",green:"#5cb87a",blue:"#5b8de8",
  accent:"#c8a96e",purple:"#9b72e8",
  text:"#e8eaf0",text2:"#8b91a0",text3:"#555d6e",
  bg:"#0b0d11",bg2:"#111419",bg3:"#181c24",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.14)",
};
const BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

const apiFetch = async (url,opts={}) => {
  const token = localStorage.getItem("kanzlei_token");
  const res = await fetch(BASE+url,{
    ...opts,headers:{"Content-Type":"application/json",
    ...(token?{Authorization:`Bearer ${token}`}:{}),
    ...(opts.headers||{})},
  });
  const d = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(d.detail||`Fehler ${res.status}`);
  return d;
};

const DOK_TYPEN = {
  rechnung:       {icon:"🧾",farbe:C.accent, ordner:"Rechnungen/Eingang"},
  kontoauszug:    {icon:"🏦",farbe:C.blue,   ordner:"Bank/Kontoauszüge"},
  steuerbescheid: {icon:"⚖", farbe:C.orange, ordner:"Steuerbescheide"},
  jahresabschluss:{icon:"📊",farbe:C.purple, ordner:"Jahresabschlüsse"},
  vertrag:        {icon:"📋",farbe:C.blue,   ordner:"Verträge"},
  lohnabrechnung: {icon:"👤",farbe:C.green,  ordner:"Lohnbuchhaltung"},
  mahnung:        {icon:"⚠", farbe:C.red,    ordner:"Mahnungen"},
  korrespondenz:  {icon:"✉", farbe:C.text2,  ordner:"Korrespondenz"},
  sonstiges:      {icon:"📄",farbe:C.text3,  ordner:"Sonstiges"},
};

const ORDNER = [
  "Rechnungen/Eingang","Rechnungen/Ausgang",
  "Bank/Kontoauszüge","Steuerbescheide/Einkommensteuer",
  "Steuerbescheide/Umsatzsteuer","Steuerbescheide/Gewerbesteuer",
  "Jahresabschlüsse","Lohnbuchhaltung","Verträge",
  "Korrespondenz/Finanzamt","Korrespondenz/Mandant",
  "Mahnungen","Sonstiges",
];

const Btn = ({children,onClick,variant="primary",size="md",loading=false,disabled=false,style={}}) => {
  const vs={primary:{background:C.accent,color:"#1a1200",border:"none"},
    ghost:{background:"transparent",color:C.text2,border:`1px solid ${C.border2}`},
    subtle:{background:C.bg3,color:C.text2,border:`1px solid ${C.border}`},
    success:{background:C.green+"20",color:C.green,border:`1px solid ${C.green}30`},
    danger:{background:C.red+"18",color:C.red,border:`1px solid ${C.red}30`}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],fontSize:fs[size],
    fontWeight:500,borderRadius:10,cursor:loading||disabled?"not-allowed":"pointer",
    opacity:loading||disabled?0.5:1,transition:"all 0.15s",
    fontFamily:"'DM Sans',sans-serif",...vs[variant],...style}}>
    {loading&&<span style={{width:12,height:12,borderRadius:"50%",border:"2px solid currentColor",
      borderTopColor:"transparent",animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
    {children}
  </button>;
};

// ─── Signatur-Pad ─────────────────────────────────────────────
const SignaturPad = ({onSave,onClose}) => {
  const canvasRef=useRef(null);
  const [drawing,setDrawing]=useState(false);
  const [hasSig,setHasSig]=useState(false);

  useEffect(()=>{
    const c=canvasRef.current;
    if(!c) return;
    const ctx=c.getContext("2d");
    ctx.fillStyle=C.bg3; ctx.fillRect(0,0,c.width,c.height);
  },[]);

  const getPos=(e,c)=>{
    const r=c.getBoundingClientRect();
    const t=e.touches?.[0]||e;
    return {x:t.clientX-r.left,y:t.clientY-r.top};
  };
  const start=(e)=>{e.preventDefault();const c=canvasRef.current;const ctx=c.getContext("2d");const p=getPos(e,c);ctx.beginPath();ctx.moveTo(p.x,p.y);setDrawing(true);setHasSig(true);};
  const move=(e)=>{if(!drawing)return;e.preventDefault();const c=canvasRef.current;const ctx=c.getContext("2d");const p=getPos(e,c);ctx.lineTo(p.x,p.y);ctx.strokeStyle=C.accent;ctx.lineWidth=2.5;ctx.lineCap="round";ctx.stroke();};
  const end=()=>setDrawing(false);
  const clear=()=>{const c=canvasRef.current;c.getContext("2d").clearRect(0,0,c.width,c.height);setHasSig(false);};

  return (
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.8)",
      display:"flex",alignItems:"center",justifyContent:"center",zIndex:2000}}>
      <div style={{background:C.bg2,border:`1px solid ${C.border2}`,borderRadius:16,padding:24,width:"min(500px,95vw)"}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:20,color:C.accent,marginBottom:4}}>
          Digitale Unterschrift
        </div>
        <div style={{fontSize:12,color:C.text3,marginBottom:16}}>Mit Maus oder Finger unterschreiben</div>
        <canvas ref={canvasRef} width={460} height={160}
          style={{border:`1px solid ${C.accent}40`,borderRadius:10,width:"100%",height:160,display:"block",touchAction:"none",cursor:"crosshair"}}
          onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
          onTouchStart={start} onTouchMove={move} onTouchEnd={end}/>
        <div style={{display:"flex",gap:8,marginTop:14,justifyContent:"space-between"}}>
          <div style={{display:"flex",gap:8}}>
            <Btn size="sm" variant="ghost" onClick={clear}>Löschen</Btn>
            <Btn size="sm" variant="ghost" onClick={onClose}>Abbrechen</Btn>
          </div>
          <Btn size="sm" variant="primary" disabled={!hasSig}
            onClick={()=>onSave(canvasRef.current.toDataURL("image/png"))}>
            Speichern
          </Btn>
        </div>
      </div>
    </div>
  );
};

// ─── Dokument-Karte (editierbar) ─────────────────────────────
const DokumentKarte = ({dok,mandanten,onSpeichern,onAblehnen}) => {
  const [form,setForm]=useState({
    doktyp:dok.doktyp||"sonstiges",
    ordner:dok.ordner||"Sonstiges",
    mandant:dok.mandant||"",
    datum:dok.datum||"",
    absender:dok.absender||"",
    betrag:dok.betrag||"",
    notiz:dok.notiz||"",
    aufgabe:dok.aufgabe||"",
    frist:dok.frist||"",
  });
  const [expanded,setExpanded]=useState(true);
  const [saving,setSaving]=useState(false);
  const [showSig,setShowSig]=useState(false);
  const [signatur,setSignatur]=useState(null);
  const set=(k,v)=>setForm(p=>({...p,[k]:v}));
  const typInfo=DOK_TYPEN[form.doktyp]||DOK_TYPEN.sonstiges;
  const inp=(extra={})=>({background:C.bg,border:`1px solid ${C.border2}`,borderRadius:8,color:C.text,padding:"7px 11px",fontSize:13,outline:"none",fontFamily:"'DM Sans',sans-serif",...extra});

  const handleSpeichern=async()=>{setSaving(true);try{await onSpeichern({...dok,...form,signatur});}finally{setSaving(false);}};

  return (
    <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:14,overflow:"hidden",animation:"fadeUp 0.35s ease both"}}>
      <div style={{padding:"14px 18px",background:C.bg3,borderBottom:`1px solid ${C.border}`,
        display:"flex",alignItems:"center",gap:12,cursor:"pointer"}} onClick={()=>setExpanded(p=>!p)}>
        <div style={{fontSize:26}}>{typInfo.icon}</div>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:600,color:C.text,fontSize:14,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{dok.dateiname}</div>
          <div style={{fontSize:11,color:C.text3,marginTop:2}}>{form.ordner}{form.mandant&&` · ${form.mandant}`}</div>
        </div>
        <div style={{display:"flex",gap:8,alignItems:"center",flexShrink:0}}>
          {dok.konfidenz!=null&&<span style={{fontSize:11,color:typInfo.farbe,fontWeight:600,background:typInfo.farbe+"18",padding:"3px 9px",borderRadius:20,border:`1px solid ${typInfo.farbe}25`}}>{Math.round(dok.konfidenz*100)}% sicher</span>}
          <span style={{color:C.text3}}>{expanded?"▲":"▼"}</span>
        </div>
      </div>

      {expanded&&(
        <div style={{padding:"16px 18px"}}>
          {dok.ki_zusammenfassung&&(
            <div style={{background:C.accent+"0d",border:`1px solid ${C.accent}20`,borderRadius:10,padding:"10px 14px",marginBottom:14}}>
              <div style={{fontSize:11,color:C.accent,fontWeight:600,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>KI-Analyse</div>
              <div style={{fontSize:13,color:C.text2,lineHeight:1.7}}>{dok.ki_zusammenfassung}</div>
            </div>
          )}

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:12}}>
            {[
              {k:"doktyp",l:"Dokumenttyp",type:"select",opts:Object.keys(DOK_TYPEN)},
              {k:"mandant",l:"Mandant",type:"select",opts:["..."].concat(mandanten),blank:"— Mandant —"},
              {k:"ordner",l:"Ziel-Ordner",type:"select",opts:ORDNER},
              {k:"datum",l:"Datum",type:"date"},
              {k:"absender",l:"Absender",type:"text",ph:"Absender..."},
              {k:"betrag",l:"Betrag (€)",type:"number",ph:"0.00"},
            ].map(f=>(
              <div key={f.k}>
                <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>{f.l}</div>
                {f.type==="select"?(
                  <select value={form[f.k]} onChange={e=>set(f.k,e.target.value)} style={{...inp(),width:"100%",color:form[f.k]?C.text:C.text3}}>
                    {f.blank&&<option value="">{f.blank}</option>}
                    {(f.k==="mandant"?mandanten:f.opts).map(o=><option key={o} value={o}>{f.k==="doktyp"?`${DOK_TYPEN[o]?.icon||"📄"} ${o}`:o}</option>)}
                  </select>
                ):(
                  <input type={f.type} value={form[f.k]} placeholder={f.ph||""}
                    onChange={e=>set(f.k,e.target.value)} style={{...inp(),width:"100%"}}/>
                )}
              </div>
            ))}
          </div>

          <div style={{marginBottom:10}}>
            <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Aufgabe erstellen (optional)</div>
            <div style={{display:"flex",gap:8}}>
              <input value={form.aufgabe} onChange={e=>set("aufgabe",e.target.value)}
                placeholder="Aufgabe aus diesem Dokument..." style={{...inp(),flex:1}}/>
              <input type="date" value={form.frist} onChange={e=>set("frist",e.target.value)} style={{...inp(),width:150}}/>
            </div>
          </div>

          <div style={{marginBottom:12}}>
            <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Notiz</div>
            <input value={form.notiz} onChange={e=>set("notiz",e.target.value)}
              placeholder="Optionale Notiz..." style={{...inp(),width:"100%"}}/>
          </div>

          {signatur&&(
            <div style={{marginBottom:12,padding:"10px 14px",background:C.green+"10",border:`1px solid ${C.green}25`,borderRadius:8}}>
              <div style={{fontSize:12,color:C.green,marginBottom:4}}>✓ Digitale Unterschrift</div>
              <img src={signatur} alt="sig" style={{height:36,filter:"brightness(0) invert(1) sepia(1) saturate(5)"}}/>
            </div>
          )}

          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <Btn onClick={handleSpeichern} loading={saving} variant="success" size="sm" disabled={!form.mandant}>
              ✓ Speichern → {form.ordner}
            </Btn>
            <Btn onClick={()=>setShowSig(true)} variant="ghost" size="sm">✍ Unterschrift</Btn>
            <Btn onClick={()=>onAblehnen(dok.id)} variant="danger" size="sm">✕</Btn>
          </div>
          {!form.mandant&&<div style={{fontSize:11,color:C.orange,marginTop:6}}>⚠ Mandant zuordnen um zu speichern</div>}
        </div>
      )}
      {showSig&&<SignaturPad onSave={sig=>{setSignatur(sig);setShowSig(false);}} onClose={()=>setShowSig(false)}/>}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function DokumentScanner() {
  const [dokumente,  setDokumente]  = useState([]);
  const [gespeichert,setGespeichert]= useState([]);
  const [mandanten,  setMandanten]  = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [toast,      setToast]      = useState(null);
  const fileRef = useRef(null);

  const showToast = useCallback((text,type="success")=>{
    setToast({text,type}); setTimeout(()=>setToast(null),4000);
  },[]);

  useEffect(()=>{
    apiFetch("/mandanten").then(d=>{
      const raw=d?.data||[];
      setMandanten(Array.isArray(raw)?raw.map(x=>x.name):Object.keys(raw));
    }).catch(()=>{});
  },[]);

  const handleDateien = async (files) => {
    setLoading(true);
    for(const datei of Array.from(files)){
      try{
        const b64=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result.split(",")[1]);r.onerror=()=>rej();r.readAsDataURL(datei);});
        const result=await apiFetch("/dokumente/analysieren",{method:"POST",body:JSON.stringify({dateiname:datei.name,inhalt_b64:b64,dateityp:datei.type})});
        setDokumente(p=>[{id:Date.now()+Math.random(),dateiname:datei.name,...result},...p]);
        showToast(`✓ "${datei.name}" analysiert`);
      }catch(e){
        setDokumente(p=>[{id:Date.now()+Math.random(),dateiname:datei.name,doktyp:"sonstiges",ordner:"Sonstiges",mandant:"",ki_zusammenfassung:`KI nicht verfügbar: ${e.message}. Bitte manuell zuordnen.`,konfidenz:0},...p]);
        showToast(`"${datei.name}" ohne KI hinzugefügt`,"warn");
      }
    }
    setLoading(false);
    if(fileRef.current) fileRef.current.value="";
  };

  const handleSpeichern = async (dok) => {
    try{
      await apiFetch("/dokumente/speichern",{method:"POST",body:JSON.stringify(dok)});
      if(dok.aufgabe&&dok.mandant&&dok.frist){
        await apiFetch(`/mandanten/${encodeURIComponent(dok.mandant)}/aufgaben`,{
          method:"POST",body:JSON.stringify({beschreibung:dok.aufgabe,frist:dok.frist,prioritaet:"normal",kategorie:dok.doktyp})
        }).catch(()=>{});
      }
      setGespeichert(p=>[dok,...p]);
      setDokumente(p=>p.filter(d=>d.id!==dok.id));
      showToast(`✓ "${dok.dateiname}" → ${dok.ordner}`);
    }catch(e){showToast(`Fehler: ${e.message}`,"error");}
  };

  return(
    <div style={{flex:1,background:C.bg,overflowY:"auto",fontFamily:"'DM Sans',sans-serif"}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');@keyframes spin{to{transform:rotate(360deg)}}@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:4px}`}</style>

      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,background:C.bg3,borderRadius:12,padding:"12px 18px",color:C.text,fontSize:13,fontWeight:500,animation:"slideIn 0.25s ease",border:`1px solid ${toast.type==="error"?C.red:toast.type==="warn"?C.orange:C.green}44`,borderLeft:`3px solid ${toast.type==="error"?C.red:toast.type==="warn"?C.orange:C.green}`}}>{toast.text}</div>}

      <div style={{background:C.bg2,borderBottom:`1px solid ${C.border}`,padding:"20px 32px",position:"sticky",top:0,zIndex:10}}>
        <div style={{fontFamily:"'DM Serif Display',serif",fontSize:22,color:C.text}}>Dokument-Scanner</div>
        <div style={{fontSize:12,color:C.text3,marginTop:2}}>KI erkennt Typ · schlägt Ordner vor · alles editierbar vor dem Speichern · digitale Unterschrift</div>
      </div>

      <div style={{padding:"28px 32px"}}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16,marginBottom:24}}>
          {[{l:"Zu prüfen",v:dokumente.length,c:dokumente.length>0?C.orange:C.text3},{l:"Gespeichert",v:gespeichert.length,c:C.green},{l:"Mandanten",v:mandanten.length,c:C.blue}].map((s,i)=>(
            <div key={i} style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:12,padding:"16px 18px"}}>
              <div style={{fontSize:10,color:C.text3,textTransform:"uppercase",letterSpacing:"0.08em",marginBottom:5}}>{s.l}</div>
              <div style={{fontFamily:"'DM Serif Display',serif",fontSize:26,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>

        <div onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();handleDateien(e.dataTransfer.files);}}
          onClick={()=>!loading&&fileRef.current?.click()}
          style={{border:`2px dashed ${C.border2}`,borderRadius:16,padding:"48px 32px",textAlign:"center",cursor:loading?"not-allowed":"pointer",background:C.bg3,marginBottom:24}}>
          <input ref={fileRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.xml,.txt" onChange={e=>handleDateien(e.target.files)} style={{display:"none"}}/>
          {loading?(<div><div style={{fontSize:40,marginBottom:12}}>🤖</div><div style={{fontWeight:600,color:C.accent,fontSize:16}}>KI analysiert...</div></div>):(<div>
            <div style={{fontSize:48,marginBottom:14}}>📂</div>
            <div style={{fontWeight:600,color:C.text,fontSize:18,marginBottom:6}}>Dokumente hier ablegen oder klicken</div>
            <div style={{color:C.text3,fontSize:13}}>PDF, JPG, PNG, DOCX, XLSX · Mehrere gleichzeitig möglich</div>
          </div>)}
        </div>

        {dokumente.length>0&&(
          <div style={{marginBottom:24}}>
            <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:C.text,marginBottom:14}}>
              {dokumente.length} Dokument{dokumente.length!==1?"e":""} zur Prüfung
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              {dokumente.map(dok=><DokumentKarte key={dok.id} dok={dok} mandanten={mandanten} onSpeichern={handleSpeichern} onAblehnen={id=>setDokumente(p=>p.filter(d=>d.id!==id))}/>)}
            </div>
          </div>
        )}

        {gespeichert.length>0&&(
          <div>
            <div style={{fontFamily:"'DM Serif Display',serif",fontSize:18,color:C.text,marginBottom:14}}>✓ Gespeichert ({gespeichert.length})</div>
            <div style={{display:"flex",flexDirection:"column",gap:8}}>
              {gespeichert.map((d,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",background:C.bg2,border:`1px solid ${C.green}25`,borderRadius:10}}>
                  <span style={{fontSize:20}}>{DOK_TYPEN[d.doktyp]?.icon||"📄"}</span>
                  <div style={{flex:1}}><div style={{fontSize:13,color:C.text,fontWeight:500}}>{d.dateiname}</div><div style={{fontSize:11,color:C.text3}}>{d.ordner}{d.mandant&&` · ${d.mandant}`}</div></div>
                  <span style={{fontSize:11,color:C.green}}>✓</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {dokumente.length===0&&gespeichert.length===0&&!loading&&(
          <div style={{textAlign:"center",padding:"48px 0",color:C.text3}}>
            <div style={{fontSize:40,marginBottom:12}}>🗂</div>
            Noch keine Dokumente hochgeladen.<br/>
            <span style={{fontSize:12,marginTop:8,display:"block"}}>Die KI erkennt: Rechnungen, Bescheide, Verträge, Kontoauszüge und mehr.</span>
          </div>
        )}
      </div>
    </div>
  );
}