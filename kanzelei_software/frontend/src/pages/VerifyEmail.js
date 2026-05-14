import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authEmailVerify } from "../api";
import { ThemeQuickSwitch } from "../theme";

export default function VerifyEmail() {
  const [search] = useSearchParams();
  const token = useMemo(() => (search.get("token") || "").trim(), [search]);
  const [status, setStatus] = useState("loading");
  const [msg, setMsg] = useState("E-Mail wird bestätigt...");

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!token) {
        if (!alive) return;
        setStatus("error");
        setMsg("Verifizierungs-Token fehlt.");
        return;
      }
      try {
        await authEmailVerify(token);
        if (!alive) return;
        setStatus("ok");
        setMsg("E-Mail erfolgreich bestätigt. Du kannst dich jetzt anmelden.");
      } catch (err) {
        if (!alive) return;
        setStatus("error");
        setMsg(err?.message || "Verifizierung fehlgeschlagen.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, fontFamily: "var(--font-body)" }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border2)", borderRadius: 16, maxWidth: 520, width: "100%", padding: 28 }}>
        <h2 style={{ color: "var(--accent)", marginBottom: 10 }}>E-Mail-Verifizierung</h2>
        <p style={{ color: status === "error" ? "var(--red)" : status === "ok" ? "var(--green)" : "var(--text2)" }}>{msg}</p>
        <div style={{ marginTop: 14 }}>
          <Link to="/login" style={{ color: "var(--accent)" }}>Zum Login</Link>
        </div>
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Erscheinungsbild</span>
          <ThemeQuickSwitch compact />
        </div>
      </div>
    </div>
  );
}
