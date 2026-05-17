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
import { apiFetch } from "../api";
import { useTheme, readCssVar } from "../theme";

/** Typische Dokumenttypen in Steuerkanzleien — label = Anzeige im Dropdown */
const DOK_TYPEN = {
  eingangsrechnung:     { icon: "🧾", label: "Eingangsrechnung",              farbe: "var(--accent)", ordner: "Rechnungen/Eingang" },
  ausgangsrechnung:     { icon: "📤", label: "Ausgangsrechnung",              farbe: "var(--accent)", ordner: "Rechnungen/Ausgang" },
  rechnung:             { icon: "🧾", label: "Rechnung (allgemein)",          farbe: "var(--accent)", ordner: "Rechnungen/Eingang" },
  gutschreibung:        { icon: "↩",  label: "Gutschrift / Gutschreibung",    farbe: "var(--accent)", ordner: "Rechnungen/Eingang" },
  angebot:              { icon: "📝", label: "Angebot / Kostenvoranschlag",   farbe: "var(--text2)",  ordner: "Rechnungen/Eingang" },
  lieferschein:         { icon: "📦", label: "Lieferschein",                  farbe: "var(--text2)",  ordner: "Rechnungen/Eingang" },
  quittung:             { icon: "🧾", label: "Quittung / Kassenbon",          farbe: "var(--accent)", ordner: "Rechnungen/Eingang" },
  bewirtungsbeleg:      { icon: "🍽", label: "Bewirtungsbeleg",               farbe: "var(--accent)", ordner: "Rechnungen/Eingang" },
  reisekosten:          { icon: "✈",  label: "Reisekosten / Fahrtkosten",     farbe: "var(--blue)",   ordner: "Rechnungen/Eingang" },
  kontoauszug:          { icon: "🏦", label: "Kontoauszug",                   farbe: "var(--blue)",   ordner: "Bank/Kontoauszüge" },
  bankbrief:            { icon: "🏦", label: "Bankbrief / Kredit",            farbe: "var(--blue)",   ordner: "Bank/Kontoauszüge" },
  steuerbescheid:       { icon: "⚖",  label: "Steuerbescheid (ESt & Co.)",   farbe: "var(--orange)", ordner: "Steuerbescheide/Einkommensteuer" },
  ust_bescheid:         { icon: "⚖",  label: "Umsatzsteuer-Bescheid / UStVA", farbe: "var(--orange)", ordner: "Steuerbescheide/Umsatzsteuer" },
  gewerbesteuer:        { icon: "⚖",  label: "Gewerbesteuer-Bescheid",        farbe: "var(--orange)", ordner: "Steuerbescheide/Gewerbesteuer" },
  finanzamt:            { icon: "🏛", label: "Schreiben Finanzamt",           farbe: "var(--orange)", ordner: "Korrespondenz/Finanzamt" },
  jahresabschluss:      { icon: "📊", label: "Jahresabschluss",                farbe: "var(--purple)", ordner: "Jahresabschlüsse" },
  bilanz:               { icon: "📊", label: "Bilanz / Buchführung",          farbe: "var(--purple)", ordner: "Jahresabschlüsse" },
  vertrag:              { icon: "📋", label: "Vertrag",                       farbe: "var(--blue)",   ordner: "Verträge" },
  mietvertrag:          { icon: "🏠", label: "Mietvertrag / Immobilie",       farbe: "var(--blue)",   ordner: "Immobilien" },
  vollmacht:            { icon: "✍",  label: "Vollmacht / Vertretung",        farbe: "var(--blue)",   ordner: "Vollmachten" },
  gesellschaftsvertrag: { icon: "🏢", label: "Gesellschaftsvertrag / Satzung", farbe: "var(--blue)",   ordner: "Verträge" },
  handelsregister:      { icon: "🏢", label: "Handelsregisterauszug",         farbe: "var(--blue)",   ordner: "Verträge" },
  kündigung:            { icon: "✂",  label: "Kündigung",                     farbe: "var(--red)",    ordner: "Verträge" },
  protokoll:            { icon: "📑", label: "Protokoll / Gesellschafterbeschluss", farbe: "var(--purple)", ordner: "Jahresabschlüsse" },
  lohnabrechnung:       { icon: "👤", label: "Lohnabrechnung",                farbe: "var(--green)",  ordner: "Lohnbuchhaltung" },
  lohnsteuerbescheinigung: { icon: "👤", label: "Lohnsteuerbescheinigung",   farbe: "var(--green)",  ordner: "Lohnbuchhaltung" },
  rentenbescheid:       { icon: "🏛", label: "Rentenbescheid / Rentenanpassung", farbe: "var(--blue)", ordner: "Sozialversicherung/Rente" },
  sozialversicherung:   { icon: "🩺", label: "Sozialversicherung / Krankenkasse", farbe: "var(--green)", ordner: "Sozialversicherung/Krankenkasse" },
  versicherung:         { icon: "🛡", label: "Versicherung (Police, Schaden)", farbe: "var(--text2)", ordner: "Versicherungen" },
  mahnung:              { icon: "⚠",  label: "Mahnung",                       farbe: "var(--red)",    ordner: "Mahnungen" },
  inkasso:              { icon: "⚠",  label: "Inkasso / Zahlungserinnerung",  farbe: "var(--red)",    ordner: "Mahnungen" },
  korrespondenz:        { icon: "✉",  label: "Korrespondenz (allgemein)",     farbe: "var(--text2)",  ordner: "Korrespondenz/Mandant" },
  formular:             { icon: "📃", label: "Formular / Antrag",             farbe: "var(--text2)",  ordner: "Formulare" },
  sonstiges:            { icon: "📄", label: "Sonstiges",                     farbe: "var(--text3)",  ordner: "Sonstiges" },
};

const DOK_TYP_ALIASES = {
  rechnung_eingang: "eingangsrechnung",
  eingang: "eingangsrechnung",
  ausgang: "ausgangsrechnung",
  rechnung_ausgang: "ausgangsrechnung",
  kassenbon: "quittung",
  beleg: "quittung",
  bescheid: "steuerbescheid",
  est_bescheid: "steuerbescheid",
  ustva: "ust_bescheid",
  umsatzsteuer: "ust_bescheid",
  gewst: "gewerbesteuer",
  rente: "rentenbescheid",
  rentenversicherung: "rentenbescheid",
  rentenanpassung: "rentenbescheid",
  krankenkasse: "sozialversicherung",
  kv: "sozialversicherung",
  police: "versicherung",
  satzung: "gesellschaftsvertrag",
  hr: "handelsregister",
  mahnwesen: "mahnung",
  antrag: "formular",
  immobilie: "mietvertrag",
  grundbuch: "mietvertrag",
};

const ORDNER = [
  "Rechnungen/Eingang", "Rechnungen/Ausgang",
  "Bank/Kontoauszüge",
  "Steuerbescheide/Einkommensteuer", "Steuerbescheide/Umsatzsteuer", "Steuerbescheide/Gewerbesteuer",
  "Jahresabschlüsse", "Lohnbuchhaltung", "Verträge", "Vollmachten", "Immobilien",
  "Sozialversicherung/Rente", "Sozialversicherung/Krankenkasse", "Versicherungen",
  "Korrespondenz/Finanzamt", "Korrespondenz/Mandant",
  "Mahnungen", "Formulare", "Sonstiges",
];

function mapDoktyp(raw) {
  const t = String(raw || "sonstiges").trim().toLowerCase().replace(/\s+/g, "_");
  if (DOK_TYPEN[t]) return t;
  if (DOK_TYP_ALIASES[t]) return DOK_TYP_ALIASES[t];
  if (/rente|rentenversicherung|rentenanpassung/.test(t)) return "rentenbescheid";
  if (/finanzamt|fa_|steuerbescheid|einkommensteuer/.test(t)) return t.includes("ust") || t.includes("umsatz") ? "ust_bescheid" : t.includes("gewerbe") ? "gewerbesteuer" : t.includes("finanzamt") ? "finanzamt" : "steuerbescheid";
  if (/lohnsteuer|lohnsteuerbescheinigung/.test(t)) return "lohnsteuerbescheinigung";
  if (/lohn|gehalt/.test(t)) return "lohnabrechnung";
  if (/krankenkasse|sozialversicherung|kv_/.test(t)) return "sozialversicherung";
  if (/ausgang/.test(t)) return "ausgangsrechnung";
  if (/eingang|eingangsrechnung/.test(t)) return "eingangsrechnung";
  return "sonstiges";
}

/** API liefert dokumenttyp/zusammenfassung — UI nutzt doktyp/ki_zusammenfassung. */
function normalisiereDokumentScan(raw, mandanten = []) {
  const r = raw && typeof raw === "object" ? raw : {};
  const doktyp = mapDoktyp(r.doktyp || r.dokumenttyp);
  let ordner = String(r.ordner || r.ordner_kategorie || "").trim();
  if (!ordner || ordner.includes("_")) {
    ordner = (DOK_TYPEN[doktyp] || DOK_TYPEN.sonstiges).ordner;
  }
  if (!ORDNER.includes(ordner)) {
    const hit = ORDNER.find((o) => o.toLowerCase().includes(ordner.toLowerCase().split("/")[0]));
    ordner = hit || ordner || "Sonstiges";
  }
  const hinweis = String(r.mandant_hinweis || r.mandant || "").trim();
  let mandant = "";
  if (hinweis && hinweis.toLowerCase() !== "unbekannt") {
    const hit = (mandanten || []).find(
      (m) => m.toLowerCase() === hinweis.toLowerCase() || hinweis.toLowerCase().includes(m.toLowerCase())
    );
    mandant = hit || "";
  }
  const konfidenz = r.konfidenz ?? r.vertrauens_score;
  return {
    ...r,
    id: r.id || r.dok_id || `${Date.now()}-${Math.random()}`,
    dok_id: r.dok_id || r.id,
    dateiname: r.dateiname || "",
    doktyp,
    ordner,
    mandant,
    mandant_hinweis: hinweis,
    datum: r.datum || "",
    absender: r.absender || r.lieferant || "",
    betrag: r.betrag != null && r.betrag !== "" ? r.betrag : "",
    ki_zusammenfassung: r.ki_zusammenfassung || r.zusammenfassung || "",
    konfidenz: konfidenz != null ? Number(konfidenz) : null,
    unsichere_felder: Array.isArray(r.unsichere_felder) ? r.unsichere_felder : [],
    frist: r.frist || "",
    aufgabe: r.aufgabe || (Array.isArray(r.naechste_schritte) ? r.naechste_schritte[0] : "") || "",
    inhalt_b64: r.inhalt_b64,
    ordner_pfad: r.ordner_pfad,
  };
}

const Btn = ({children,onClick,variant="primary",size="md",loading=false,disabled=false,style={}}) => {
  const vs={primary:{background:"var(--accent)",color:"var(--on-accent)",border:"none"},
    ghost:{background:"transparent",color:"var(--text2)",border:`1px solid var(--border2)`},
    subtle:{background:"var(--bg3)",color:"var(--text2)",border:`1px solid var(--border)`},
    success:{background:"color-mix(in srgb, var(--green) 16%, var(--bg3))",color:"var(--green)",border:"1px solid color-mix(in srgb, var(--green) 24%, transparent)"},
    danger:{background:"color-mix(in srgb, var(--red) 14%, var(--bg3))",color:"var(--red)",border:"1px solid color-mix(in srgb, var(--red) 24%, transparent)"}};
  const ss={xs:"4px 9px",sm:"7px 14px",md:"9px 18px"};
  const fs={xs:11,sm:13,md:14};
  return <button onClick={!loading&&!disabled?onClick:undefined} style={{
    display:"inline-flex",alignItems:"center",gap:6,padding:ss[size],fontSize:fs[size],
    fontWeight:500,borderRadius:10,cursor:loading||disabled?"not-allowed":"pointer",
    opacity:loading||disabled?0.5:1,transition:"all 0.15s",
    fontFamily:"var(--font-body)",...vs[variant],...style}}>
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
  const { resolved } = useTheme();

  useEffect(()=>{
    const c=canvasRef.current;
    if(!c) return;
    const ctx=c.getContext("2d");
    const bg = readCssVar("--bg3") || readCssVar("--bg2") || readCssVar("--bg");
    ctx.fillStyle = bg;
    ctx.fillRect(0,0,c.width,c.height);
  },[resolved]);

  const getPos=(e,c)=>{
    const r=c.getBoundingClientRect();
    const t=e.touches?.[0]||e;
    return {x:t.clientX-r.left,y:t.clientY-r.top};
  };
  const start=(e)=>{e.preventDefault();const c=canvasRef.current;const ctx=c.getContext("2d");const p=getPos(e,c);ctx.beginPath();ctx.moveTo(p.x,p.y);setDrawing(true);setHasSig(true);};
  const move=(e)=>{if(!drawing)return;e.preventDefault();const c=canvasRef.current;const ctx=c.getContext("2d");const p=getPos(e,c);ctx.lineTo(p.x,p.y);ctx.strokeStyle=readCssVar("--accent")||readCssVar("--text");ctx.lineWidth=2.5;ctx.lineCap="round";ctx.stroke();};
  const end=()=>setDrawing(false);
  const clear=()=>{const c=canvasRef.current;if(!c)return;const ctx=c.getContext("2d");const bg=readCssVar("--bg3")||readCssVar("--bg2")||readCssVar("--bg");ctx.fillStyle=bg;ctx.fillRect(0,0,c.width,c.height);setHasSig(false);};

  return (
    <div style={{position:"fixed",inset:0,background:"var(--overlay-scrim)",
      display:"flex",alignItems:"center",justifyContent:"center",zIndex:2000}}>
      <div style={{background:"var(--bg2)",border:`1px solid var(--border2)`,borderRadius:16,padding:24,width:"min(500px,95vw)"}}>
        <div style={{fontFamily:"var(--font-head)",fontSize:20,color:"var(--accent)",marginBottom:4}}>
          Digitale Unterschrift
        </div>
        <div style={{fontSize:12,color:"var(--text3)",marginBottom:16}}>Mit Maus oder Finger unterschreiben</div>
        <canvas ref={canvasRef} width={460} height={160}
          style={{border:"1px solid color-mix(in srgb, var(--accent) 35%, transparent)",borderRadius:10,width:"100%",height:160,display:"block",touchAction:"none",cursor:"crosshair"}}
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
  const inp=(extra={})=>({background:"var(--bg)",border:`1px solid var(--border2)`,borderRadius:8,color:"var(--text)",padding:"7px 11px",fontSize:13,outline:"none",fontFamily:"var(--font-body)",...extra});

  const handleSpeichern=async()=>{setSaving(true);try{await onSpeichern({...dok,...form,signatur});}finally{setSaving(false);}};

  return (
    <div style={{background:"var(--bg2)",border:`1px solid var(--border)`,borderRadius:14,overflow:"hidden",animation:"fadeUp 0.35s ease both"}}>
      <div style={{padding:"14px 18px",background:"var(--bg3)",borderBottom:`1px solid var(--border)`,
        display:"flex",alignItems:"center",gap:12,cursor:"pointer"}} onClick={()=>setExpanded(p=>!p)}>
        <div style={{fontSize:26}}>{typInfo.icon}</div>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:600,color:"var(--text)",fontSize:14,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{dok.dateiname}</div>
          <div style={{fontSize:11,color:"var(--text3)",marginTop:2}}>{form.ordner}{form.mandant&&` · ${form.mandant}`}</div>
        </div>
        <div style={{display:"flex",gap:8,alignItems:"center",flexShrink:0}}>
          {dok.konfidenz!=null&&<span style={{fontSize:11,color:typInfo.farbe,fontWeight:600,background:`color-mix(in srgb, ${typInfo.farbe} 14%, var(--bg3))`,padding:"3px 9px",borderRadius:20,border:`1px solid color-mix(in srgb, ${typInfo.farbe} 22%, transparent)`}}>{Math.round(dok.konfidenz*100)}% sicher</span>}
          <span style={{color:"var(--text3)"}}>{expanded?"▲":"▼"}</span>
        </div>
      </div>

      {expanded&&(
        <div style={{padding:"16px 18px"}}>
          {Array.isArray(dok.unsichere_felder) && dok.unsichere_felder.length > 0 && (
            <div style={{background:"color-mix(in srgb, var(--orange) 12%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--orange) 24%, transparent)",borderRadius:10,padding:"8px 12px",marginBottom:12,fontSize:12,color:"var(--orange)"}}>
              Unsichere Felder: {dok.unsichere_felder.slice(0, 6).join(", ")}. Bitte vor dem Speichern prüfen.
            </div>
          )}
          {dok.ki_zusammenfassung&&(
            <div style={{background:"color-mix(in srgb, var(--accent) 8%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--accent) 18%, transparent)",borderRadius:10,padding:"10px 14px",marginBottom:14}}>
              <div style={{fontSize:11,color:"var(--accent)",fontWeight:600,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>KI-Analyse</div>
              <div style={{fontSize:13,color:"var(--text2)",lineHeight:1.7}}>{dok.ki_zusammenfassung}</div>
            </div>
          )}
          {dok.mandant_hinweis && !form.mandant && (
            <div style={{fontSize:12,color:"var(--orange)",marginBottom:12,lineHeight:1.6}}>
              Im Dokument erkannt: <strong>{dok.mandant_hinweis}</strong> — bitte einen Mandanten aus Ihrer Liste wählen
              (ggf. zuerst unter „Mandanten“ anlegen).
            </div>
          )}

          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:12}}>
            {[
              {k:"doktyp",l:"Dokumenttyp",type:"select",opts:Object.keys(DOK_TYPEN)},
              {k:"mandant",l:"Mandant",type:"select",opts:mandanten,blank:"— Mandant —"},
              {k:"ordner",l:"Ziel-Ordner",type:"select",opts:ORDNER},
              {k:"datum",l:"Datum",type:"date"},
              {k:"absender",l:"Absender",type:"text",ph:"Absender..."},
              {k:"betrag",l:"Betrag (€)",type:"number",ph:"0.00"},
            ].map(f=>(
              <div key={f.k}>
                <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>{f.l}</div>
                {f.type==="select"?(
                  <select value={form[f.k]} onChange={e=>set(f.k,e.target.value)} style={{...inp(),width:"100%",color:form[f.k]?"var(--text)":"var(--text3)"}}>
                    {f.blank&&<option value="">{f.blank}</option>}
                    {(f.k==="mandant"?mandanten:f.opts).map(o=><option key={o} value={o}>{f.k==="doktyp"?`${DOK_TYPEN[o]?.icon||"📄"} ${DOK_TYPEN[o]?.label||o}`:o}</option>)}
                  </select>
                ):(
                  <input type={f.type} value={form[f.k]} placeholder={f.ph||""}
                    onChange={e=>set(f.k,e.target.value)} style={{...inp(),width:"100%"}}/>
                )}
              </div>
            ))}
          </div>

          <div style={{marginBottom:10}}>
            <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Aufgabe erstellen (optional)</div>
            <div style={{display:"flex",gap:8}}>
              <input value={form.aufgabe} onChange={e=>set("aufgabe",e.target.value)}
                placeholder="Aufgabe aus diesem Dokument..." style={{...inp(),flex:1}}/>
              <input type="date" value={form.frist} onChange={e=>set("frist",e.target.value)} style={{...inp(),width:150}}/>
            </div>
          </div>

          <div style={{marginBottom:12}}>
            <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>Notiz</div>
            <input value={form.notiz} onChange={e=>set("notiz",e.target.value)}
              placeholder="Optionale Notiz..." style={{...inp(),width:"100%"}}/>
          </div>

          {signatur&&(
            <div style={{marginBottom:12,padding:"10px 14px",background:"color-mix(in srgb, var(--green) 10%, var(--bg3))",border:"1px solid color-mix(in srgb, var(--green) 22%, transparent)",borderRadius:8}}>
              <div style={{fontSize:12,color:"var(--green)",marginBottom:4}}>✓ Digitale Unterschrift</div>
              <img src={signatur} alt="sig" style={{height:36,maxWidth:"100%",objectFit:"contain"}}/>
            </div>
          )}

          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <Btn onClick={handleSpeichern} loading={saving} variant="success" size="sm" disabled={!form.mandant}>
              ✓ Speichern → {form.ordner}
            </Btn>
            <Btn onClick={()=>setShowSig(true)} variant="ghost" size="sm">✍ Unterschrift</Btn>
            <Btn onClick={()=>onAblehnen(dok.id)} variant="danger" size="sm">✕</Btn>
          </div>
          {!form.mandant&&<div style={{fontSize:11,color:"var(--orange)",marginTop:6}}>⚠ Mandant zuordnen um zu speichern</div>}
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
        const norm=normalisiereDokumentScan({dateiname:datei.name,...result},mandanten);
        setDokumente(p=>[norm,...p]);
        showToast(`✓ "${datei.name}" analysiert`);
      }catch(e){
        const fallback=normalisiereDokumentScan({dateiname:datei.name,doktyp:"sonstiges",ordner:"Sonstiges",mandant:"",ki_zusammenfassung:`KI nicht verfügbar: ${e.message}. Bitte manuell ausfüllen.`,konfidenz:0},mandanten);
        setDokumente(p=>[fallback,...p]);
        showToast(`"${datei.name}" ohne KI hinzugefügt`,"warn");
      }
    }
    setLoading(false);
    if(fileRef.current) fileRef.current.value="";
  };

  const handleSpeichern = async (dok) => {
    try{
      const jahr=(dok.datum||"").slice(0,4)||String(new Date().getFullYear());
      const ordnerPfad=dok.ordner_pfad||`${dok.mandant}/${jahr}/${dok.ordner||"Sonstiges"}`;
      await apiFetch("/dokumente/speichern",{method:"POST",body:JSON.stringify({
        dok_id:String(dok.dok_id||dok.id||Date.now()),
        dateiname:dok.dateiname,
        dokumenttyp:dok.doktyp||dok.dokumenttyp||"sonstiges",
        mandant:dok.mandant,
        datum:dok.datum||null,
        frist:dok.frist||null,
        lieferant:dok.absender||dok.lieferant||"",
        ordner_pfad:ordnerPfad,
        ordner_kategorie:dok.ordner||"Sonstiges",
        jahr:parseInt(jahr,10)||new Date().getFullYear(),
        notiz:dok.notiz||"",
        inhalt_b64:dok.inhalt_b64,
        aufgabe_anlegen:!!(dok.aufgabe&&dok.frist),
      })});
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
    <div style={{flex:1,background:"var(--bg)",overflowY:"auto",fontFamily:"var(--font-body)"}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');@keyframes spin{to{transform:rotate(360deg)}}@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}`}</style>

      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",fontSize:13,fontWeight:500,animation:"slideIn 0.25s ease",border:`1px solid ${toast.type==="error"?"var(--red)":toast.type==="warn"?"var(--orange)":"var(--green)"}44`,borderLeft:`3px solid ${toast.type==="error"?"var(--red)":toast.type==="warn"?"var(--orange)":"var(--green)"}`}}>{toast.text}</div>}

      <div style={{background:"var(--bg2)",borderBottom:`1px solid var(--border)`,padding:"20px 32px",position:"sticky",top:0,zIndex:10}}>
        <div style={{fontFamily:"var(--font-head)",fontSize:22,color:"var(--text)"}}>Dokument-Scanner</div>
        <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>KI erkennt Typ · schlägt Ordner vor · alles editierbar vor dem Speichern · digitale Unterschrift</div>
      </div>

      <div style={{padding:"28px 32px"}}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16,marginBottom:24}}>
          {[{l:"Zu prüfen",v:dokumente.length,c:dokumente.length>0?"var(--orange)":"var(--text3)"},{l:"Gespeichert",v:gespeichert.length,c:"var(--green)"},{l:"Mandanten",v:mandanten.length,c:"var(--blue)"}].map((s,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,borderRadius:12,padding:"16px 18px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.08em",marginBottom:5}}>{s.l}</div>
              <div style={{fontFamily:"var(--font-head)",fontSize:26,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>

        <div onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();handleDateien(e.dataTransfer.files);}}
          onClick={()=>!loading&&fileRef.current?.click()}
          style={{border:`2px dashed var(--border2)`,borderRadius:16,padding:"48px 32px",textAlign:"center",cursor:loading?"not-allowed":"pointer",background:"var(--bg3)",marginBottom:24}}>
          <input ref={fileRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.xml,.txt" onChange={e=>handleDateien(e.target.files)} style={{display:"none"}}/>
          {loading?(<div><div style={{fontSize:40,marginBottom:12}}>🤖</div><div style={{fontWeight:600,color:"var(--accent)",fontSize:16}}>KI analysiert...</div></div>):(<div>
            <div style={{fontSize:48,marginBottom:14}}>📂</div>
            <div style={{fontWeight:600,color:"var(--text)",fontSize:18,marginBottom:6}}>Dokumente hier ablegen oder klicken</div>
            <div style={{color:"var(--text3)",fontSize:13}}>PDF, JPG, PNG, DOCX, XLSX · Mehrere gleichzeitig möglich</div>
          </div>)}
        </div>

        {dokumente.length>0&&(
          <div style={{marginBottom:24}}>
            <div style={{fontFamily:"var(--font-head)",fontSize:18,color:"var(--text)",marginBottom:14}}>
              {dokumente.length} Dokument{dokumente.length!==1?"e":""} zur Prüfung
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              {dokumente.map(dok=><DokumentKarte key={dok.id} dok={dok} mandanten={mandanten} onSpeichern={handleSpeichern} onAblehnen={id=>setDokumente(p=>p.filter(d=>d.id!==id))}/>)}
            </div>
          </div>
        )}

        {gespeichert.length>0&&(
          <div>
            <div style={{fontFamily:"var(--font-head)",fontSize:18,color:"var(--text)",marginBottom:14}}>✓ Gespeichert ({gespeichert.length})</div>
            <div style={{display:"flex",flexDirection:"column",gap:8}}>
              {gespeichert.map((d,i)=>(
                <div key={i} style={{display:"flex",alignItems:"center",gap:12,padding:"10px 14px",background:"var(--bg2)",border:`1px solid ${"var(--green)"}25`,borderRadius:10}}>
                  <span style={{fontSize:20}}>{DOK_TYPEN[d.doktyp]?.icon||"📄"}</span>
                  <div style={{flex:1}}><div style={{fontSize:13,color:"var(--text)",fontWeight:500}}>{d.dateiname}</div><div style={{fontSize:11,color:"var(--text3)"}}>{d.ordner}{d.mandant&&` · ${d.mandant}`}</div></div>
                  <span style={{fontSize:11,color:"var(--green)"}}>✓</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {dokumente.length===0&&gespeichert.length===0&&!loading&&(
          <div style={{textAlign:"center",padding:"48px 0",color:"var(--text3)"}}>
            <div style={{fontSize:40,marginBottom:12}}>🗂</div>
            Noch keine Dokumente hochgeladen.<br/>
            <span style={{fontSize:12,marginTop:8,display:"block"}}>Die KI erkennt u. a. Rechnungen, Steuer- und Rentenbescheide, Verträge, Lohn, Versicherung, Vollmachten.</span>
          </div>
        )}
      </div>
    </div>
  );
}