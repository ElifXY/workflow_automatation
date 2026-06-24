// ============================================================
// KANZLEI AI — LOGIN PAGE v1.0
// Datei: src/pages/Login.js
// ============================================================

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  extractLoginPayload,
  loginUser,
  markAuthLoginGrace,
  parseAuthApiError,
  pickBearerFromAuthBody,
} from "../api";
import { ThemeQuickSwitch } from "../theme";
import { PRODUCT_HEADLINE, PRODUCT_SUBLINE } from "../navAccess";

const apiBase = (process.env.REACT_APP_API_URL || "/api").replace(/\/$/, "");
const LOGIN_TIMEOUT_MS = 30000;

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const identityRef = useRef(null);
  const passRef = useRef(null);
  const [showPass, setShowPass] = useState(false);
  const [expectedRole, setExpectedRole] = useState("");
  const expectedRoleHint =
    expectedRole === "selbststaendig"
      ? "Selbstständig (Einzelkanzlei) gewählt"
      : expectedRole
      ? `Rolle gewählt: ${expectedRole}`
      : "Rolle übersprungen";
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resendInfo, setResendInfo] = useState("");

  const readLoginFields = () => ({
    idVal: (identityRef.current?.value || "").trim(),
    passVal: (passRef.current?.value || "").trim(),
  });

  const friendlyAuthError = (msg) => {
    const m = String(msg || "").toLowerCase();
    if (m.includes("e-mail oder passwort falsch") || m.includes("benutzername oder passwort falsch")) {
      return "E-Mail oder Passwort falsch. Bitte Zugangsdaten prüfen oder „Passwort vergessen“ nutzen.";
    }
    if (m.includes("oauth token-fehler (microsoft)")) {
      return "Microsoft-Anmeldung ist gerade nicht verfügbar. Bitte E-Mail und Passwort verwenden oder ein Konto anlegen.";
    }
    if (m.includes("e-mail noch nicht bestätigt")) {
      return "E-Mail noch nicht bestätigt. Bitte den Link in der Verifizierungs-Mail öffnen.";
    }
    if (m.includes("fehler 502") || m.includes("nicht erreichbar")) {
      return "Der Server antwortet gerade nicht. Bitte in ein paar Minuten erneut versuchen.";
    }
    return msg || "Anmeldung fehlgeschlagen";
  };

  useEffect(() => {
    if (passRef.current) {
      passRef.current.type = showPass ? "text" : "password";
    }
  }, [showPass]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search || "");
    const code = (params.get("code") || "").trim();
    const oauthOk = (params.get("oauth") || "").trim() === "ok";
    if (!oauthOk || !code) return;
    let active = true;
    (async () => {
      try {
        const res = await fetch(`${apiBase}/auth/oauth/exchange`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(parseAuthApiError(data, res.status));
        }
        if (!active) return;
        const payload = extractLoginPayload(data);
        const access = pickBearerFromAuthBody(payload) || pickBearerFromAuthBody(data);
        if (!access) {
          throw new Error("OAuth-Anmeldung ohne Zugangs-Token");
        }
        const refresh = payload.refresh_token || data.refresh_token || "";
        const role = payload.role || payload.rolle || data.role || "assistent";
        const email = payload.email || data.email || "";
        markAuthLoginGrace();
        localStorage.setItem("kanzlei_token", access);
        localStorage.setItem("token", access);
        if (refresh) localStorage.setItem("kanzlei_refresh_token", refresh);
        localStorage.setItem("kanzlei_rolle", role);
        localStorage.setItem("role", role);
        if (email) localStorage.setItem("kanzlei_user", email);
        window.history.replaceState({}, document.title, window.location.pathname);
        if (onLogin) onLogin();
        window.location.replace("/");
        return;
      } catch (err) {
        if (!active) return;
        setError(friendlyAuthError(err?.message));
      }
    })();
    return () => {
      active = false;
    };
  }, [onLogin, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    const { idVal, passVal } = readLoginFields();
    setLoading(true);
    setError("");
    setResendInfo("");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);
    try {
      await loginUser({
        identity: idVal,
        password: passVal,
        signal: controller.signal,
      });
      if (onLogin) onLogin();
      window.location.replace("/");
      return;
    } catch (err) {
      if (err?.name === "AbortError") {
        setError("Zeitüberschreitung — bitte Seite neu laden und erneut versuchen.");
      } else if (err?.verifyPending) {
        setResendInfo("verify-pending");
        setError(friendlyAuthError(err?.message));
      } else {
        setError(friendlyAuthError(err?.message));
      }
    } finally {
      clearTimeout(timeoutId);
      setLoading(false);
    }
  };

  const resendVerification = async () => {
    const email = readLoginFields().idVal.toLowerCase();
    if (!email.includes("@")) {
      setError("Bitte eine E-Mail eingeben, um die Verifizierung erneut zu senden.");
      return;
    }
    try {
      const res = await fetch(`${apiBase}/auth/email/resend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(parseAuthApiError(data, res.status));
        return;
      }
      setResendInfo("sent");
    } catch {
      setError("Server nicht erreichbar. Bitte später erneut versuchen.");
    }
  };

  return (
    <div style={{
      minHeight:"100vh", background:"var(--bg)", display:"flex",
      alignItems:"center", justifyContent:"center", padding:20,
      fontFamily:"var(--font-body)",
      backgroundImage:`radial-gradient(ellipse at 25% 25%, color-mix(in srgb, var(--accent) 10%, transparent) 0%, transparent 50%),
                       radial-gradient(ellipse at 75% 75%, color-mix(in srgb, var(--blue) 8%, transparent) 0%, transparent 50%)`,
    }}>
      <style>{`
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        input:focus{border-color:var(--accent)!important;outline:none}
      `}</style>

      <div style={{
        display:"flex", flexWrap:"wrap", gap:40, width:"100%", maxWidth:960,
        alignItems:"center", justifyContent:"center",
      }}>
        <div style={{ flex:"1 1 300px", maxWidth:420, animation:"fadeUp 0.5s ease" }}>
          <div style={{ fontFamily:"var(--font-head)", fontSize:34, color:"var(--accent)", lineHeight:1.15, marginBottom:12 }}>
            Kanzlei Automation
          </div>
          <div style={{ fontSize:16, color:"var(--text)", fontWeight:600, marginBottom:10, lineHeight:1.4 }}>
            {PRODUCT_HEADLINE}
          </div>
          <div style={{ fontSize:14, color:"var(--text2)", lineHeight:1.65, marginBottom:20 }}>
            {PRODUCT_SUBLINE}
          </div>
          <ul style={{ margin:0, paddingLeft:18, color:"var(--text2)", fontSize:13, lineHeight:1.8 }}>
            <li>Automatische Erinnerungen an Mandanten</li>
            <li>Dokumente einsammeln — ohne Telefon-Marathon</li>
            <li>Dashboard: Was brennt heute?</li>
            <li>Mandanten-Portal inklusive</li>
          </ul>
        </div>

      <div style={{
        background:"var(--bg2)", border:"1px solid var(--border2)",
        borderRadius:20, padding:"40px 36px", width:"100%", maxWidth:420,
        boxShadow:"var(--shadow-modal)", animation:"fadeUp 0.5s ease",
        flex:"1 1 300px",
      }}>
        <div style={{marginBottom:28}}>
          <div style={{fontFamily:"var(--font-head)",fontSize:22,color:"var(--text)",lineHeight:1.2,marginBottom:6}}>
            Anmelden
          </div>
          <div style={{fontSize:13,color:"var(--text3)"}}>Zugang für Ihre Kanzlei</div>
        </div>

        {error && (
          <div style={{
            background:"color-mix(in srgb, var(--red) 12%, var(--bg3))",
            border:"1px solid color-mix(in srgb, var(--red) 35%, transparent)",
            borderRadius:10,padding:"10px 14px",color:"var(--red)",
            fontSize:13,marginBottom:16,
          }}>
            {error}
            {resendInfo === "verify-pending" && (
              <div style={{ marginTop: 8 }}>
                <button type="button" onClick={resendVerification} style={{
                  border:"1px solid color-mix(in srgb, var(--red) 45%, transparent)",
                  background:"transparent",color:"var(--text)",borderRadius:8,
                  padding:"6px 10px",cursor:"pointer",
                }}>
                  Verifizierungs-Mail erneut senden
                </button>
              </div>
            )}
            {resendInfo === "sent" && (
              <div style={{ marginTop: 8, color: "var(--green)" }}>Verifizierungs-Mail wurde gesendet.</div>
            )}
          </div>
        )}

        <form onSubmit={submit} autoComplete="on">
          <div style={{ marginBottom: 14, border:"1px solid var(--border2)", background:"var(--bg3)",
            borderRadius:12, padding:"12px 12px 10px" }}>
            <div style={{ fontSize: 13, color: "var(--text2)", fontWeight: 700, marginBottom: 4 }}>
              Zugangstyp (optional)
            </div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>
              Nur zur Orientierung — blockiert die Anmeldung nicht.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { id: "admin", label: "Admin" },
                { id: "steuerberater", label: "Steuerberater" },
                { id: "mitarbeiter", label: "Mitarbeiter" },
                { id: "selbststaendig", label: "Selbstständig" },
              ].map((r) => (
                <button key={r.id} type="button" onClick={() => setExpectedRole(r.id)} style={{
                  borderRadius:10,
                  border:`1px solid ${expectedRole === r.id ? "var(--accent)" : "var(--border2)"}`,
                  background: expectedRole === r.id ? "color-mix(in srgb, var(--accent) 18%, var(--bg3))" : "var(--bg3)",
                  color: expectedRole === r.id ? "var(--accent)" : "var(--text2)",
                  padding:"8px 10px",cursor:"pointer",fontSize:12,fontWeight:600,
                }}>
                  {r.label}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div style={{ fontSize: 12, color: "var(--text3)" }}>{expectedRoleHint}</div>
              <button type="button" onClick={() => setExpectedRole("")} style={{
                borderRadius:8,border:"1px solid var(--border2)",background:"transparent",
                color:"var(--text3)",padding:"4px 8px",fontSize:12,cursor:"pointer",
              }}>
                Überspringen
              </button>
            </div>
          </div>

          <div style={{marginBottom:14}}>
            <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:5}}>
              E-Mail oder Benutzername
            </div>
            <input ref={identityRef} type="text" name="username" defaultValue=""
              placeholder="name@kanzlei.de" autoComplete="username"
              style={{width:"100%",background:"var(--bg3)",border:"1px solid var(--border2)",
                borderRadius:10,color:"var(--text)",padding:"11px 14px",fontSize:14}} />
          </div>

          <div style={{marginBottom:14}}>
            <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:5}}>
              Passwort
            </div>
            <div style={{ position: "relative" }}>
              <input ref={passRef} type="password" name="password" defaultValue=""
                placeholder="Passwort eingeben" autoComplete="current-password"
                style={{width:"100%",background:"var(--bg3)",border:"1px solid var(--border2)",
                  borderRadius:10,color:"var(--text)",padding:"11px 80px 11px 14px",fontSize:14}} />
              <button type="button" onClick={() => setShowPass((s) => !s)} style={{
                position:"absolute",right:8,top:"50%",transform:"translateY(-50%)",
                border:"1px solid var(--border2)",background:"var(--bg2)",color:"var(--text2)",
                borderRadius:8,padding:"4px 8px",fontSize:11,cursor:"pointer",
              }}>
                {showPass ? "Aus" : "An"}
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading} style={{
            width:"100%",background:"var(--accent)",color:"var(--on-accent)",border:"none",
            borderRadius:10,padding:"12px",fontSize:15,fontWeight:600,
            cursor:loading?"not-allowed":"pointer",opacity:loading?0.7:1,marginTop:8,
          }}>
            {loading ? "Anmelden…" : "Anmelden"}
          </button>
        </form>

        <div style={{ marginTop: 14, background:"var(--bg3)", border:"1px solid var(--border2)",
          borderRadius:12, padding:"12px 14px", display:"flex", alignItems:"center",
          justifyContent:"space-between", gap:12 }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text2)", fontWeight: 600 }}>Noch kein Konto?</div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>Kostenlos registrieren.</div>
          </div>
          <a href="/register" style={{
            background:"var(--accent)",color:"var(--on-accent)",borderRadius:10,
            padding:"9px 13px",fontSize:13,fontWeight:700,textDecoration:"none",
          }}>
            Registrieren
          </a>
        </div>

        <div style={{ marginTop: 14, display: "grid", gap: 8 }}>
          <a href={`${apiBase}/auth/oauth/google/start?redirect_to=${encodeURIComponent("/login")}`}
            style={{ color:"var(--text)", border:"1px solid var(--border2)", borderRadius:10,
              padding:"10px 12px", textAlign:"center", background:"var(--bg3)", textDecoration:"none" }}>
            Mit Google anmelden
          </a>
          <a href={`${apiBase}/auth/oauth/microsoft/start?redirect_to=${encodeURIComponent("/login")}`}
            style={{ color:"var(--text)", border:"1px solid var(--border2)", borderRadius:10,
              padding:"10px 12px", textAlign:"center", background:"var(--bg3)", textDecoration:"none" }}>
            Mit Microsoft anmelden
          </a>
        </div>

        <div style={{marginTop:20,fontSize:12,color:"var(--text3)",lineHeight:1.6,textAlign:"center"}}>
          <a href="/forgot-password" style={{ color: "var(--accent)", fontWeight: 600 }}>Passwort vergessen?</a>
          <div style={{ marginTop: 8 }}>
            Bei Problemen wenden Sie sich an Ihre Kanzlei oder unseren Support.
          </div>
        </div>

        <div style={{ marginTop: 14, fontSize: 12, textAlign: "center" }}>
          <a href="/produkt" style={{ color: "var(--accent)", fontWeight: 600 }}>Mehr über das Produkt →</a>
        </div>

        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text3)" }}>Erscheinungsbild</span>
          <ThemeQuickSwitch compact />
        </div>
      </div>
      </div>
    </div>
  );
}