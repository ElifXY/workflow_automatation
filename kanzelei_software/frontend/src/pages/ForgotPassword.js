import { useState } from "react";
import { Link } from "react-router-dom";
import { authPasswortForgot } from "../api";
import { ThemeQuickSwitch } from "../theme";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Bitte E-Mail eingeben");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authPasswortForgot(email.trim().toLowerCase());
      setDone(true);
    } catch (err) {
      setError(err?.message || "Anfrage fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, fontFamily: "var(--font-body)" }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border2)", borderRadius: 18, padding: "36px", width: "100%", maxWidth: 430 }}>
        <h2 style={{ color: "var(--accent)", marginBottom: 8 }}>Passwort vergessen</h2>
        <p style={{ color: "var(--text3)", marginBottom: 20 }}>Wir senden dir einen sicheren Reset-Link per E-Mail.</p>
        {done ? (
          <div style={{ background: "color-mix(in srgb, var(--green) 12%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--green) 30%, transparent)", borderRadius: 10, color: "var(--green)", padding: "12px 14px" }}>
            Falls die E-Mail existiert, wurde ein Link versendet.
          </div>
        ) : (
          <form onSubmit={submit}>
            {error && <div style={{ marginBottom: 10, color: "var(--red)" }}>{error}</div>}
            <input
              type="email"
              placeholder="name@kanzlei.de"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)", borderRadius: 10, color: "var(--text)", padding: "11px 14px", marginBottom: 12 }}
            />
            <button
              type="submit"
              disabled={loading}
              style={{ width: "100%", background: "var(--accent)", color: "var(--on-accent)", border: "none", borderRadius: 10, padding: "11px 14px", fontWeight: 700, opacity: loading ? 0.7 : 1 }}
            >
              {loading ? "Sende..." : "Reset-Link senden"}
            </button>
          </form>
        )}
        <div style={{ marginTop: 16 }}>
          <Link to="/login" style={{ color: "var(--accent)" }}>Zurück zum Login</Link>
        </div>
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Erscheinungsbild</span>
          <ThemeQuickSwitch compact />
        </div>
      </div>
    </div>
  );
}
