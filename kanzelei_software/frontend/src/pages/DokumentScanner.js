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
import {
  apiFetch,
  dokumentArchiv,
  dokumentAktualisieren,
  dokumentLoeschen,
  dokumentWiederherstellen,
  dokumentDateiDownload,
  extractDokumenteListe,
} from "../api";
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

const ARCHIV_CACHE_KEY = "kanzlei_dokument_archiv_cache_v1";
const SCANNER_VIEW_KEY = "kanzlei_dokument_scanner_view_v1";

function readArchivCache() {
  try {
    const raw =
      localStorage.getItem(ARCHIV_CACHE_KEY) ||
      sessionStorage.getItem(ARCHIV_CACHE_KEY);
    if (!raw) return { gespeichert: [], geloescht: [] };
    const p = JSON.parse(raw);
    return {
      gespeichert: Array.isArray(p.gespeichert) ? p.gespeichert : [],
      geloescht: Array.isArray(p.geloescht) ? p.geloescht : [],
    };
  } catch {
    return { gespeichert: [], geloescht: [] };
  }
}

function writeArchivCache(gespeichert, geloescht) {
  const payload = JSON.stringify({ gespeichert, geloescht, at: Date.now() });
  try {
    localStorage.setItem(ARCHIV_CACHE_KEY, payload);
    sessionStorage.setItem(ARCHIV_CACHE_KEY, payload);
  } catch {}
}

function restoreArchivFromCache(setArchivListe, setPapierkorb, setScannerView) {
  const c = readArchivCache();
  if (c.gespeichert.length > 0 || c.geloescht.length > 0) {
    setArchivListe(c.gespeichert);
    setPapierkorb(c.geloescht);
    const saved = readScannerView();
    if (saved) setScannerView(saved);
    else if (c.gespeichert.length > 0) setScannerView("archiv");
    return true;
  }
  return false;
}

function readScannerView() {
  try {
    const v = sessionStorage.getItem(SCANNER_VIEW_KEY);
    return v === "archiv" || v === "papierkorb" || v === "scan" ? v : null;
  } catch {
    return null;
  }
}

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

// ─── Archiv-Zeile (gespeicherte Dokumente) ─────────────────
const ArchivZeile = ({ dok, mandanten, papierkorb, onRefresh, showToast }) => {
  const [edit, setEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const typ = mapDoktyp(dok.dokumenttyp || dok.doktyp);
  const typInfo = DOK_TYPEN[typ] || DOK_TYPEN.sonstiges;
  const [form, setForm] = useState({
    doktyp: typ,
    mandant: dok.mandant || "",
    ordner: dok.ordner_kategorie || dok.ordner || typInfo.ordner,
    datum: dok.datum || "",
    absender: dok.lieferant || dok.absender || "",
    betrag: dok.betrag ?? "",
    notiz: dok.notiz || "",
    ki_zusammenfassung: dok.ki_zusammenfassung || "",
  });
  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  const inp = (extra = {}) => ({
    background: "var(--bg)",
    border: `1px solid var(--border2)`,
    borderRadius: 8,
    color: "var(--text)",
    padding: "7px 11px",
    fontSize: 13,
    outline: "none",
    fontFamily: "var(--font-body)",
    ...extra,
  });

  const speichernMeta = async () => {
    setSaving(true);
    try {
      const jahr = (form.datum || "").slice(0, 4) || String(dok.jahr || new Date().getFullYear());
      await dokumentAktualisieren(dokId, {
        dokumenttyp: form.doktyp,
        mandant: form.mandant,
        datum: form.datum || null,
        lieferant: form.absender,
        ordner_kategorie: form.ordner,
        ordner_pfad: `${form.mandant}/${jahr}/${form.ordner}`,
        jahr: parseInt(jahr, 10),
        notiz: form.notiz,
        betrag: form.betrag === "" ? null : Number(form.betrag),
        ki_zusammenfassung: form.ki_zusammenfassung,
      });
      showToast("Änderungen gespeichert");
      setEdit(false);
      onRefresh();
    } catch (e) {
      showToast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ background: "var(--bg2)", border: `1px solid var(--border)`, borderRadius: 12, padding: "12px 16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 22 }}>{typInfo.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, color: "var(--text)", fontSize: 14 }}>{dok.dateiname}</div>
          <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>
            {dok.mandant || "—"} · {DOK_TYPEN[typ]?.label || typ} · {dok.ordner_pfad || form.ordner}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {!papierkorb && (
            <>
              <Btn size="xs" variant="ghost" onClick={() => dokumentDateiDownload(dok.dok_id, dok.dateiname).catch((e) => showToast(e.message, "error"))}>
                ⬇ Öffnen
              </Btn>
              <Btn size="xs" variant="ghost" onClick={() => setEdit((p) => !p)}>{edit ? "Schließen" : "✏ Bearbeiten"}</Btn>
              <Btn size="xs" variant="danger" onClick={async () => {
                if (!window.confirm("In Papierkorb legen?")) return;
                try {
                  await dokumentLoeschen(dok.dok_id, false);
                  showToast("In Papierkorb gelegt", "warn");
                  onRefresh();
                } catch (e) { showToast(e.message, "error"); }
              }}>🗑</Btn>
            </>
          )}
          {papierkorb && (
            <>
              <Btn size="xs" variant="success" disabled={!dokId} onClick={async () => {
                try {
                  await dokumentWiederherstellen(dokId);
                  showToast("Wiederhergestellt");
                  onRefresh();
                } catch (e) { showToast(e.message, "error"); }
              }}>↩ Wiederherstellen</Btn>
              <Btn size="xs" variant="danger" onClick={async () => {
                if (!window.confirm("Endgültig löschen?")) return;
                try {
                  await dokumentLoeschen(dokId, true);
                  showToast("Endgültig gelöscht", "warn");
                  onRefresh();
                } catch (e) { showToast(e.message, "error"); }
              }}>✕ Endgültig</Btn>
            </>
          )}
        </div>
      </div>
      {edit && !papierkorb && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid var(--border)` }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <select value={form.doktyp} onChange={(e) => set("doktyp", e.target.value)} style={{ ...inp(), width: "100%" }}>
              {Object.keys(DOK_TYPEN).map((o) => (
                <option key={o} value={o}>{DOK_TYPEN[o].icon} {DOK_TYPEN[o].label}</option>
              ))}
            </select>
            <select value={form.mandant} onChange={(e) => set("mandant", e.target.value)} style={{ ...inp(), width: "100%" }}>
              <option value="">— Mandant —</option>
              {mandanten.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <select value={form.ordner} onChange={(e) => set("ordner", e.target.value)} style={{ ...inp(), width: "100%" }}>
              {ORDNER.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <input type="date" value={form.datum} onChange={(e) => set("datum", e.target.value)} style={{ ...inp(), width: "100%" }} />
            <input value={form.absender} onChange={(e) => set("absender", e.target.value)} placeholder="Absender" style={{ ...inp(), width: "100%" }} />
            <input type="number" value={form.betrag} onChange={(e) => set("betrag", e.target.value)} placeholder="Betrag" style={{ ...inp(), width: "100%" }} />
          </div>
          <input value={form.notiz} onChange={(e) => set("notiz", e.target.value)} placeholder="Notiz" style={{ ...inp(), width: "100%", marginBottom: 8 }} />
          <Btn size="sm" variant="success" loading={saving} onClick={speichernMeta}>Speichern</Btn>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function DokumentScanner({ tabActive = true }) {
  const archivCache = readArchivCache();
  const [dokumente,  setDokumente]  = useState([]);
  const [archivListe, setArchivListe] = useState(archivCache.gespeichert);
  const [papierkorb, setPapierkorb] = useState(archivCache.geloescht);
  const [mandanten,  setMandanten]  = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [archivLaden, setArchivLaden] = useState(false);
  const [view,       setView]       = useState(() => {
    const saved = readScannerView();
    if (saved) return saved;
    return archivCache.gespeichert.length > 0 ? "archiv" : "scan";
  });
  const [archivSuche, setArchivSuche] = useState("");
  const [toast,      setToast]      = useState(null);
  const fileRef = useRef(null);
  const archivSucheRef = useRef(archivSuche);
  archivSucheRef.current = archivSuche;

  const setScannerView = useCallback((next) => {
    setView(next);
    try {
      sessionStorage.setItem(SCANNER_VIEW_KEY, next);
    } catch {}
  }, []);

  const showToast = useCallback((text,type="success")=>{
    setToast({text,type}); setTimeout(()=>setToast(null),4000);
  },[]);

  const ladeArchiv = useCallback(async (silent = false) => {
    setArchivLaden(true);
    const cached = readArchivCache();
    try {
      const q = archivSucheRef.current.trim();
      const [a, p] = await Promise.all([
        dokumentArchiv(null, null, q || null, "gespeichert"),
        dokumentArchiv(null, null, q || null, "geloescht"),
      ]);
      const gespeichert = extractDokumenteListe(a);
      const geloescht = extractDokumenteListe(p);

      if (gespeichert.length > 0 || geloescht.length > 0) {
        setArchivListe(gespeichert);
        setPapierkorb(geloescht);
        writeArchivCache(gespeichert, geloescht);
      } else if (cached.gespeichert.length > 0 || cached.geloescht.length > 0) {
        setArchivListe(cached.gespeichert);
        setPapierkorb(cached.geloescht);
        if (!silent) {
          showToast(
            "Server-Archiv leer — zeige zuletzt gespeicherte Dokumente. Bitte API deployen (git pull + docker build).",
            "warn"
          );
        }
      } else {
        setArchivListe([]);
        setPapierkorb([]);
        writeArchivCache([], []);
      }
    } catch (e) {
      console.error(e);
      restoreArchivFromCache(setArchivListe, setPapierkorb, setScannerView);
      if (!silent) {
        const msg = e?.status === 404
          ? "Archiv-API nicht gefunden — zeige lokalen Zwischenspeicher."
          : (e.message || "Archiv konnte nicht geladen werden");
        showToast(msg, "error");
      }
    } finally {
      setArchivLaden(false);
    }
  }, [showToast, setScannerView]);

  useEffect(() => {
    apiFetch("/mandanten").then(d => {
      const raw = d?.data || [];
      setMandanten(Array.isArray(raw) ? raw.map(x => x.name) : Object.keys(raw));
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!tabActive) return;
    restoreArchivFromCache(setArchivListe, setPapierkorb, setScannerView);
    ladeArchiv(true);
  }, [tabActive, ladeArchiv, setScannerView]);

  const handleDateien = async (files) => {
    setLoading(true);
    for(const datei of Array.from(files)){
      try{
        const b64=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result.split(",")[1]);r.onerror=()=>rej();r.readAsDataURL(datei);});
        const result=await apiFetch("/dokumente/analysieren",{method:"POST",body:JSON.stringify({dateiname:datei.name,inhalt_b64:b64,dateityp:datei.type})});
        const norm=normalisiereDokumentScan({dateiname:datei.name,inhalt_b64:b64,...result},mandanten);
        setDokumente(p=>[norm,...p]);
        showToast(`✓ "${datei.name}" analysiert`);
      }catch(e){
        const fallback=normalisiereDokumentScan({dateiname:datei.name,inhalt_b64:b64,doktyp:"sonstiges",ordner:"Sonstiges",mandant:"",ki_zusammenfassung:`KI nicht verfügbar: ${e.message}. Bitte manuell ausfüllen.`,konfidenz:0},mandanten);
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
      const dokId=String(dok.dok_id||dok.id||`dok-${Date.now()}`);
      const archivEintrag={
        dok_id:dokId,
        dateiname:dok.dateiname,
        dokumenttyp:dok.doktyp||dok.dokumenttyp||"sonstiges",
        mandant:dok.mandant,
        datum:dok.datum||null,
        ordner_pfad:ordnerPfad,
        ordner_kategorie:dok.ordner||"Sonstiges",
        jahr:parseInt(jahr,10)||new Date().getFullYear(),
        lieferant:dok.absender||dok.lieferant||"",
        betrag:dok.betrag===""||dok.betrag==null?null:Number(dok.betrag),
        notiz:dok.notiz||"",
        ki_zusammenfassung:dok.ki_zusammenfassung||"",
        gespeichert_am:new Date().toISOString(),
        status:"gespeichert",
      };
      setArchivListe(prev=>{
        const next=[archivEintrag,...prev.filter(x=>String(x.dok_id||x.id)!==dokId)];
        const pb=readArchivCache().geloescht;
        writeArchivCache(next,pb);
        return next;
      });
      setScannerView("archiv");
      await apiFetch("/dokumente/speichern",{method:"POST",body:JSON.stringify({
        dok_id:dokId,
        dateiname:dok.dateiname,
        dokumenttyp:archivEintrag.dokumenttyp,
        mandant:dok.mandant,
        datum:dok.datum||null,
        frist:dok.frist||null,
        lieferant:archivEintrag.lieferant,
        ordner_pfad:ordnerPfad,
        ordner_kategorie:archivEintrag.ordner_kategorie,
        jahr:archivEintrag.jahr,
        notiz:dok.notiz||"",
        inhalt_b64:dok.inhalt_b64,
        aufgabe_anlegen:!!(dok.aufgabe&&dok.frist),
        ki_zusammenfassung:archivEintrag.ki_zusammenfassung,
        betrag:archivEintrag.betrag,
      })});
      if(dok.aufgabe&&dok.mandant&&dok.frist){
        await apiFetch(`/mandanten/${encodeURIComponent(dok.mandant)}/aufgaben`,{
          method:"POST",body:JSON.stringify({beschreibung:dok.aufgabe,frist:dok.frist,prioritaet:"normal",kategorie:dok.doktyp})
        }).catch(()=>{});
      }
      setDokumente(p=>p.filter(d=>d.id!==dok.id));
      await ladeArchiv(true);
      showToast(`✓ "${dok.dateiname}" → ${dok.ordner}`);
    }catch(e){showToast(`Fehler: ${e.message}`,"error");}
  };

  return(
    <div style={{flex:1,background:"var(--bg)",overflowY:"auto",fontFamily:"var(--font-body)"}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');@keyframes spin{to{transform:rotate(360deg)}}@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}`}</style>

      {toast&&<div style={{position:"fixed",bottom:24,right:24,zIndex:9999,background:"var(--bg3)",borderRadius:12,padding:"12px 18px",color:"var(--text)",fontSize:13,fontWeight:500,animation:"slideIn 0.25s ease",border:`1px solid ${toast.type==="error"?"var(--red)":toast.type==="warn"?"var(--orange)":"var(--green)"}44`,borderLeft:`3px solid ${toast.type==="error"?"var(--red)":toast.type==="warn"?"var(--orange)":"var(--green)"}`}}>{toast.text}</div>}

      <div style={{background:"var(--bg2)",borderBottom:`1px solid var(--border)`,padding:"20px 32px",position:"sticky",top:0,zIndex:10}}>
        <div style={{fontFamily:"var(--font-head)",fontSize:22,color:"var(--text)"}}>Dokument-Scanner</div>
        <div style={{fontSize:12,color:"var(--text3)",marginTop:2}}>KI erkennt Typ · Archiv: öffnen, bearbeiten, Papierkorb</div>
        <div style={{display:"flex",gap:6,marginTop:12,flexWrap:"wrap"}}>
          {[
            {id:"scan",label:"📥 Scannen"},
            {id:"archiv",label:`📁 Archiv (${archivListe.length})`},
            {id:"papierkorb",label:`🗑 Papierkorb (${papierkorb.length})`},
          ].map(t=>(
            <button key={t.id} onClick={()=>setScannerView(t.id)} style={{
              padding:"7px 14px",borderRadius:10,border:"none",cursor:"pointer",fontSize:13,
              background:view===t.id?"var(--bg3)":"transparent",
              color:view===t.id?"var(--accent)":"var(--text2)",
              fontWeight:view===t.id?600:400,fontFamily:"var(--font-body)",
            }}>{t.label}</button>
          ))}
        </div>
      </div>

      <div style={{padding:"28px 32px"}}>
        <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:16,marginBottom:24}}>
          {[{l:"Zu prüfen",v:dokumente.length,c:dokumente.length>0?"var(--orange)":"var(--text3)"},{l:"Im Archiv",v:archivListe.length,c:"var(--green)"},{l:"Mandanten",v:mandanten.length,c:"var(--blue)"}].map((s,i)=>(
            <div key={i} style={{background:"var(--bg2)",border:`1px solid var(--border)`,borderRadius:12,padding:"16px 18px"}}>
              <div style={{fontSize:10,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.08em",marginBottom:5}}>{s.l}</div>
              <div style={{fontFamily:"var(--font-head)",fontSize:26,color:s.c}}>{s.v}</div>
            </div>
          ))}
        </div>

        {view==="scan"&&archivListe.length>0&&(
          <div style={{
            marginBottom:16,padding:"12px 16px",borderRadius:12,
            background:"color-mix(in srgb, var(--green) 10%, var(--bg3))",
            border:"1px solid color-mix(in srgb, var(--green) 22%, transparent)",
            display:"flex",alignItems:"center",justifyContent:"space-between",gap:12,flexWrap:"wrap",
          }}>
            <span style={{fontSize:13,color:"var(--text2)"}}>
              {archivListe.length} gespeicherte{archivListe.length===1?"s":""} Dokument{archivListe.length!==1?"e":""} im Archiv
              {archivLaden ? " · wird aktualisiert…" : ""}
            </span>
            <Btn size="sm" variant="success" onClick={()=>setScannerView("archiv")}>📁 Zum Archiv</Btn>
          </div>
        )}

        {view==="scan"&&(
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
        )}

        {view==="scan"&&dokumente.length>0&&(
          <div style={{marginBottom:24}}>
            <div style={{fontFamily:"var(--font-head)",fontSize:18,color:"var(--text)",marginBottom:14}}>
              {dokumente.length} Dokument{dokumente.length!==1?"e":""} zur Prüfung
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              {dokumente.map(dok=><DokumentKarte key={dok.id} dok={dok} mandanten={mandanten} onSpeichern={handleSpeichern} onAblehnen={id=>setDokumente(p=>p.filter(d=>d.id!==id))}/>)}
            </div>
          </div>
        )}

        {view==="archiv"&&(
          <div>
            <div style={{display:"flex",gap:10,marginBottom:16,flexWrap:"wrap",alignItems:"center"}}>
              <input
                value={archivSuche}
                onChange={e=>setArchivSuche(e.target.value)}
                onKeyDown={e=>e.key==="Enter"&&ladeArchiv()}
                placeholder="Suche (Dateiname, Mandant, Absender…)"
                style={{flex:1,minWidth:200,background:"var(--bg2)",border:`1px solid var(--border)`,borderRadius:10,padding:"10px 14px",color:"var(--text)",fontSize:13,outline:"none"}}
              />
              <Btn size="sm" variant="ghost" onClick={ladeArchiv}>Aktualisieren</Btn>
            </div>
            {archivListe.length===0?(
              <div style={{textAlign:"center",padding:"40px 0",color:"var(--text3)"}}>Noch keine gespeicherten Dokumente.</div>
            ):(
              <div style={{display:"flex",flexDirection:"column",gap:10}}>
                {archivListe.map(dok=>(
                  <ArchivZeile key={dok.dok_id||dok.id||dok.dateiname} dok={dok} mandanten={mandanten} papierkorb={false} onRefresh={ladeArchiv} showToast={showToast}/>
                ))}
              </div>
            )}
          </div>
        )}

        {view==="papierkorb"&&(
          <div>
            {papierkorb.length===0?(
              <div style={{textAlign:"center",padding:"40px 0",color:"var(--text3)"}}>Papierkorb ist leer.</div>
            ):(
              <div style={{display:"flex",flexDirection:"column",gap:10}}>
                {papierkorb.map(dok=>(
                  <ArchivZeile key={dok.dok_id||dok.id||dok.dateiname} dok={dok} mandanten={mandanten} papierkorb onRefresh={ladeArchiv} showToast={showToast}/>
                ))}
              </div>
            )}
          </div>
        )}

        {view==="scan"&&dokumente.length===0&&!loading&&archivListe.length===0&&!archivLaden&&(
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