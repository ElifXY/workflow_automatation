// ============================================================
// KANZLEI AI — LOGIN PAGE v1.0
// Datei: src/pages/Login.js
// ============================================================

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ThemeQuickSwitch } from "../theme";

const apiBase = (process.env.REACT_APP_API_URL || "/api").replace(/\/$/, "");
const LOGIN_TIMEOUT_MS = 30000;

/** Login liefert Session-Token + optional JWT — Session hat Vorrang (Redis), JWT kann fehlschlagen. */
function pickAuthToken(payload) {
  const access = String(payload?.access_token || "").trim();
  const session = String(payload?.token || "").trim();
  const isJwt = (t) => t.split(".").length === 3 && t.length > 40;
  const isSession = (t) => t.length >= 32;
  if (isSession(session)) return session;
  if (isJwt(access)) return access;
  if (isSession(access)) return access;
  return session || access;
}

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
  const [error,   setError]   = useState("");
  const [resendInfo, setResendInfo] = useState("");

  const readLoginFields = () => ({
    idVal: (identityRef.current?.value || "").trim(),
    passVal: (passRef.current?.value || "").trim(),
  });

  const friendlyAuthError = (msg) => {
    const m = String(msg || "").toLowerCase();
    if (m.includes("e-mail oder passwort falsch") || m.includes("benutzername oder passwort falsch")) {
      return "E-Mail oder Passwort falsch. Gespeichertes Passwort im Browser löschen oder Feld leeren und neu eintippen.";
    }
    if (m.includes("oauth token-fehler (microsoft)")) {
      return "Microsoft-Anmeldung aktuell nicht verfügbar (OAuth-Konfiguration). Das liegt nicht an fehlender Registrierung. Bitte nutze vorübergehend E-Mail/Passwort oder erstelle zuerst ein Konto über 'Konto erstellen'.";
    }
    if (m.includes("e-mail noch nicht bestätigt")) {
      return "E-Mail noch nicht bestätigt. Bitte Verifizierungs-Mail öffnen oder erneut anfordern.";
    }
    return msg || "Anmeldung fehlgeschlagen";
  };

  // Gespeichertes Browser-Passwort beim Öffnen leeren — Wert kommt direkt aus dem Eingabefeld beim Absenden.
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (passRef.current) passRef.current.value = "";
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

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
          throw new Error(data?.error || data?.detail || "OAuth Login fehlgeschlagen");
        }
        if (!active) return;
        const access = pickAuthToken(data);
        if (!access) {
          throw new Error("OAuth Login fehlgeschlagen (kein Token)");
        }
        const refresh = data.refresh_token || "";
        const role = data.role || "assistent";
        const email = data.email || "";
        localStorage.setItem("kanzlei_token", access);
        localStorage.setItem("token", access);
        if (refresh) localStorage.setItem("kanzlei_refresh_token", refresh);
        localStorage.setItem("kanzlei_rolle", role);
        localStorage.setItem("role", role);
        if (email) localStorage.setItem("kanzlei_user", email);
        window.history.replaceState({}, document.title, window.location.pathname);
        onLogin({ access_token: access, refresh_token: refresh, role, email, oauth: true });
        navigate("/", { replace: true });
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
    if (!idVal || !passVal) {
      setError("Bitte E-Mail und Passwort eingeben.");
      return;
    }
    setLoading(true);
    setError("");
    setResendInfo("");
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);
    try {
      const isEmail = idVal.includes("@");
      const body = isEmail
        ? { email: idVal.toLowerCase(), password: passVal }
        : { benutzername: idVal, passwort: passVal };
      const res = await fetch(`${apiBase}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const raw =
          data?.error ??
          data?.detail ??
          (Array.isArray(data?.details) ? data.details.map((x) => x?.msg || x).join(" ") : "");
        const detail = String(raw || "Login fehlgeschlagen");
        if (detail.toLowerCase().includes("e-mail noch nicht bestätigt")) {
          setResendInfo("verify-pending");
        }
        setError(friendlyAuthError(detail));
        return;
      }
      const payload = data && data.data && typeof data.data === "object" ? data.data : data;
      const token = pickAuthToken(payload);
      if (!token) {
        setError("Anmeldung fehlgeschlagen. Bitte versuchen Sie es später erneut oder kontaktieren Sie den Support.");
        return;
      }
      localStorage.setItem("kanzlei_token", token);
      localStorage.setItem("token", token);
      if (payload.refresh_token) localStorage.setItem("kanzlei_refresh_token", payload.refresh_token);
      localStorage.setItem("kanzlei_user", payload.anzeigename || payload.benutzer || payload.benutzername || idVal);
      const role = payload.role || payload.rolle;
      const normalizedRole = String(role || "").toLowerCase();
      const normalizedExpected = String(expectedRole || "").toLowerCase();
      const roleMatches =
        !normalizedExpected ||
        normalizedExpected === "selbststaendig" ||
        normalizedRole === normalizedExpected ||
        (normalizedExpected === "mitarbeiter" && normalizedRole === "assistent") ||
        (normalizedExpected === "assistent" && normalizedRole === "mitarbeiter");
      if (!roleMatches && normalizedRole) {
        localStorage.removeItem("kanzlei_token");
        localStorage.removeItem("token");
        localStorage.removeItem("kanzlei_refresh_token");
        setError(`Dieses Konto ist als „${role}“ angelegt. Bitte „Überspringen“ wählen oder „Steuerberater“ als Zugangstyp.`);
        return;
      }
      localStorage.setItem("kanzlei_rolle", role);
      localStorage.setItem("role", role);
      onLogin(payload);
      navigate("/", { replace: true });
    } catch (err) {
      if (err?.name === "AbortError") {
        setError("Zeitüberschreitung — der Server antwortet nicht. VPN/Netzwerk prüfen oder Seite neu laden.");
      } else {
        setError("Server nicht erreichbar. Bitte Internetverbindung prüfen und es später erneut versuchen.");
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
        setError(data?.detail || "Verifizierungs-Mail konnte nicht gesendet werden.");
        return;
      }
      setResendInfo("sent");
    } catch {
      setError("Server nicht erreichbar. Bitte Internetverbindung prüfen und es später erneut versuchen.");
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
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        input:focus{border-color:var(--accent)!important;outline:none}
      `}</style>

      <div style={{
        background:"var(--bg2)", border:"1px solid var(--border2)",
        borderRadius:20, padding:"48px 44px", width:"100%", maxWidth:420,
        boxShadow:"var(--shadow-modal)",
        animation:"fadeUp 0.5s ease",
      }}>
        <div style={{marginBottom:36}}>
          <div style={{fontFamily:"var(--font-head)",fontSize:30,
                        color:"var(--accent)",lineHeight:1.1,marginBottom:6}}>
            Kanzlei AI
          </div>
          <div style={{fontSize:13,color:"var(--text3)"}}>
            Steuerberater Suite — Anmelden
          </div>
        </div>

        {error && (
          <div style={{
            background:"color-mix(in srgb, var(--red) 12%, var(--bg3))",
            border:"1px solid color-mix(in srgb, var(--red) 35%, transparent)",
            borderRadius:10,padding:"10px 14px",color:"var(--red)",
            fontSize:13,marginBottom:16}}>
            {error}
            {resendInfo === "verify-pending" && (
              <div style={{ marginTop: 8 }}>
                <button
                  type="button"
                  onClick={resendVerification}
                  style={{
                    border: "1px solid color-mix(in srgb, var(--red) 45%, transparent)",
                    background: "transparent",
                    color: "var(--text)",
                    borderRadius: 8,
                    padding: "6px 10px",
                    cursor: "pointer",
                  }}
                >
                  Verifizierungs-Mail erneut senden
                </button>
              </div>
            )}
            {resendInfo === "sent" && (
              <div style={{ marginTop: 8, color: "var(--green)" }}>
                Verifizierungs-Mail wurde gesendet.
              </div>
            )}
          </div>
        )}

        <form onSubmit={submit} autoComplete="on">
          <div
            style={{
              marginBottom: 14,
              border: "1px solid var(--border2)",
              background: "var(--bg3)",
              borderRadius: 12,
              padding: "12px 12px 10px",
            }}
          >
            <div style={{ fontSize: 13, color: "var(--text2)", fontWeight: 700, marginBottom: 4 }}>
              Zugangstyp waehlen (optional)
            </div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>
              Hilft bei der richtigen Konto-Zuordnung beim Login.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { id: "admin", label: "Admin" },
                { id: "steuerberater", label: "Steuerberater" },
                { id: "mitarbeiter", label: "Mitarbeiter" },
                { id: "selbststaendig", label: "Selbstständig" },
              ].map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setExpectedRole(r.id)}
                  style={{
                    borderRadius: 10,
                    border: `1px solid ${expectedRole === r.id ? "var(--accent)" : "var(--border2)"}`,
                    background: expectedRole === r.id
                      ? "color-mix(in srgb, var(--accent) 18%, var(--bg3))"
                      : "var(--bg3)",
                    color: expectedRole === r.id ? "var(--accent)" : "var(--text2)",
                    padding: "8px 10px",
                    cursor: "pointer",
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div style={{ fontSize: 12, color: "var(--text3)" }}>{expectedRoleHint}</div>
              <button
                type="button"
                onClick={() => setExpectedRole("")}
                style={{
                  borderRadius: 8,
                  border: "1px solid var(--border2)",
                  background: "transparent",
                  color: "var(--text3)",
                  padding: "4px 8px",
                  fontSize: 12,
                  cursor: "pointer",
                }}
              >
                Überspringen
              </button>
            </div>
          </div>
          <div style={{marginBottom:14}}>
            <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",
                          letterSpacing:"0.07em",marginBottom:5}}>E-Mail</div>
            <input
              ref={identityRef}
              type="email"
              name="email"
              defaultValue=""
              placeholder="name@kanzlei.de"
              autoComplete="username"
              readOnly
              onFocus={(e) => e.target.removeAttribute("readOnly")}
              style={{width:"100%",background:"var(--bg3)",border:"1px solid var(--border2)",
                borderRadius:10,color:"var(--text)",padding:"11px 14px",fontSize:14,
                fontFamily:"var(--font-body)",transition:"border 0.15s"}} />
          </div>

          <div style={{marginBottom:14}}>
            <div style={{fontSize:11,color:"var(--text3)",textTransform:"uppercase",
                          letterSpacing:"0.07em",marginBottom:5}}>Passwort</div>
            <div style={{ position: "relative" }}>
              <input
                ref={passRef}
                type="password"
                name="password"
                defaultValue=""
                placeholder="Passwort eingeben"
                autoComplete="current-password"
                readOnly
                onFocus={(e) => e.target.removeAttribute("readOnly")}
                style={{width:"100%",background:"var(--bg3)",border:"1px solid var(--border2)",
                  borderRadius:10,color:"var(--text)",padding:"11px 80px 11px 14px",fontSize:14,
                  fontFamily:"var(--font-body)",transition:"border 0.15s"}} />
              <button
                type="button"
                onClick={() => setShowPass((s) => !s)}
                style={{
                  position: "absolute",
                  right: 8,
                  top: "50%",
                  transform: "translateY(-50%)",
                  border: "1px solid var(--border2)",
                  background: "var(--bg2)",
                  color: "var(--text2)",
                  borderRadius: 8,
                  padding: "4px 8px",
                  fontSize: 11,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                aria-label={showPass ? "Passwort ausblenden" : "Passwort anzeigen"}
                title={showPass ? "Passwort ausblenden" : "Passwort anzeigen"}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                  <path d="M2 12C3.7 8.4 7.3 6 12 6C16.7 6 20.3 8.4 22 12C20.3 15.6 16.7 18 12 18C7.3 18 3.7 15.6 2 12Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                  <circle cx="12" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.8" />
                  {showPass ? <path d="M4 4L20 20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/> : null}
                </svg>
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading} style={{
            width:"100%",background:"var(--accent)",color:"var(--on-accent)",border:"none",
            borderRadius:10,padding:"12px",fontSize:15,fontWeight:600,
            cursor:loading?"not-allowed":"pointer",
            opacity:loading?0.7:1,marginTop:8,
            display:"flex",alignItems:"center",justifyContent:"center",gap:8,
            fontFamily:"var(--font-body)",
          }}>
            {loading && <span style={{width:16,height:16,borderRadius:"50%",
              border:"2px solid var(--on-accent)",borderTopColor:"transparent",
              animation:"spin 0.7s linear infinite",display:"inline-block"}}/>}
            {loading ? "Anmelden..." : "Anmelden"}
          </button>
        </form>

        <div style={{
          marginTop: 14,
          background: "var(--bg3)",
          border: "1px solid var(--border2)",
          borderRadius: 12,
          padding: "12px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}>
          <div>
            <div style={{ fontSize: 13, color: "var(--text2)", fontWeight: 600 }}>Noch kein Konto?</div>
            <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>Erstelle ein Konto.</div>
          </div>
          <a href="/register" style={{
              background: "var(--accent)",
              color: "var(--on-accent)",
              border: "none",
              borderRadius: 10,
              padding: "9px 13px",
              fontSize: 13,
              fontWeight: 700,
              textDecoration: "none",
              whiteSpace: "nowrap",
            }}>
            Jetzt registrieren
          </a>
        </div>

        <div style={{ marginTop: 14, display: "grid", gap: 8 }}>
          <a href={`${apiBase}/auth/oauth/google/start?redirect_to=${encodeURIComponent("/login")}`} style={{ color: "var(--text)", border: "1px solid var(--border2)", borderRadius: 10, padding: "10px 12px", textAlign: "center", background: "var(--bg3)" }}>
            Mit Google anmelden
          </a>
          <a href={`${apiBase}/auth/oauth/microsoft/start?redirect_to=${encodeURIComponent("/login")}`} style={{ color: "var(--text)", border: "1px solid var(--border2)", borderRadius: 10, padding: "10px 12px", textAlign: "center", background: "var(--bg3)" }}>
            Mit Microsoft anmelden
          </a>
        </div>

        <div style={{marginTop:24,padding:"16px",background:"var(--bg3)",
          borderRadius:10,fontSize:12,color:"var(--text3)",lineHeight:1.7}}>
          <strong style={{color:"var(--text2)"}}>Sicher anmelden</strong><br/>
          Zugriff nur für aktive Konten. Passwort-Regel bei Registrierung/Reset: mindestens 12 Zeichen mit Groß-/Kleinbuchstabe, Zahl und Sonderzeichen.
          <div style={{ marginTop: 10 }}>
            <a href="/forgot-password" style={{ color: "var(--accent)" }}>Passwort vergessen</a>
          </div>
        </div>

        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Erscheinungsbild
          </span>
          <ThemeQuickSwitch compact />
        </div>
      </div>
    </div>
  );
}