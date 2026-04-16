// ============================================================
// KANZLEI AI — LOGIN PAGE v1.0
// Datei: src/pages/Login.js
// ============================================================

import { useState } from "react";

const C = {
  accent:"#c8a96e",text:"#e8eaf0",text2:"#8b91a0",text3:"#555d6e",
  bg:"#0b0d11",bg2:"#111419",bg3:"#181c24",red:"#e05555",green:"#5cb87a",
  border:"rgba(255,255,255,0.07)",border2:"rgba(255,255,255,0.14)",
};
const BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function Login({ onLogin }) {
  const [user,    setUser]    = useState("");
  const [pass,    setPass]    = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!user || !pass) { setError("Bitte alle Felder ausfüllen"); return; }
    setLoading(true); setError("");
    try {
      const res  = await fetch(`${BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benutzername: user, passwort: pass }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Login fehlgeschlagen"); return; }
      localStorage.setItem("kanzlei_token",   data.token);
      localStorage.setItem("kanzlei_user",    data.anzeigename || data.benutzer);
      localStorage.setItem("kanzlei_rolle",   data.rolle);
      onLogin(data);
    } catch (err) {
      setError("Server nicht erreichbar — Backend gestartet?");
    } finally { setLoading(false); }
  };

  return (
    <div style={{
      minHeight:"100vh", background:C.bg, display:"flex",
      alignItems:"center", justifyContent:"center", padding:20,
      fontFamily:"'DM Sans',sans-serif",
      backgroundImage:`radial-gradient(ellipse at 25% 25%, rgba(200,169,110,0.06) 0%, transparent 50%),
                       radial-gradient(ellipse at 75% 75%, rgba(91,141,232,0.04) 0%, transparent 50%)`,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        input:focus{border-color:#c8a96e!important;outline:none}
      `}</style>

      <div style={{
        background:C.bg2, border:`1px solid ${C.border2}`,
        borderRadius:20, padding:"48px 44px", width:"100%", maxWidth:420,
        boxShadow:"0 20px 60px rgba(0,0,0,0.6)",
        animation:"fadeUp 0.5s ease",
      }}>
        {/* Logo */}
        <div style={{marginBottom:36}}>
          <div style={{fontFamily:"'DM Serif Display',serif",fontSize:30,
                        color:C.accent,lineHeight:1.1,marginBottom:6}}>
            Kanzlei AI
          </div>
          <div style={{fontSize:13,color:C.text3}}>
            Steuerberater Suite — Anmelden
          </div>
        </div>

        {error && (
          <div style={{background:C.red+"15",border:`1px solid ${C.red}33`,
            borderRadius:10,padding:"10px 14px",color:C.red,
            fontSize:13,marginBottom:16}}>
            {error}
          </div>
        )}

        <form onSubmit={submit}>
          {[
            {label:"Benutzername",   val:user, set:setUser, type:"text",     ph:"steuerberater"},
            {label:"Passwort",       val:pass, set:setPass, type:"password", ph:"••••••••"},
          ].map(f => (
            <div key={f.label} style={{marginBottom:14}}>
              <div style={{fontSize:11,color:C.text3,textTransform:"uppercase",
                            letterSpacing:"0.07em",marginBottom:5}}>{f.label}</div>
              <input type={f.type} value={f.val} placeholder={f.ph}
                onChange={e => f.set(e.target.value)}
                style={{width:"100%",background:C.bg3,border:`1px solid ${C.border2}`,
                  borderRadius:10,color:C.text,padding:"11px 14px",fontSize:14,
                  fontFamily:"'DM Sans',sans-serif",transition:"border 0.15s"}} />
            </div>
          ))}

          <button type="submit" disabled={loading} style={{
            width:"100%",background:C.accent,color:"#1a1200",border:"none",
            borderRadius:10,padding:"12px",fontSize:15,fontWeight:600,
            cursor:loading?"not-allowed":"pointer",
            opacity:loading?0.7:1,marginTop:8,
            display:"flex",alignItems:"center",justifyContent:"center",gap:8,
            fontFamily:"'DM Sans',sans-serif",
          }}>
            {loading && <span style={{width:16,height:16,borderRadius:"50%",
              border:"2px solid #1a1200",borderTopColor:"transparent",
              animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
            {loading ? "Anmelden..." : "Anmelden"}
          </button>
        </form>

        <div style={{marginTop:24,padding:"16px",background:C.bg3,
          borderRadius:10,fontSize:12,color:C.text3,lineHeight:1.7}}>
          <strong style={{color:C.text2}}>Erster Start?</strong><br/>
          Erstelle deinen Admin-Account unter:<br/>
          <code style={{color:C.accent,fontSize:11}}>
            POST /auth/registrieren
          </code><br/>
          Oder: <code style={{color:C.accent,fontSize:11}}>python seed_demo.py</code>
        </div>
      </div>
    </div>
  );
}