import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authPasswortReset } from "../api";
import { ThemeQuickSwitch } from "../theme";

export default function ResetPassword() {
  const [search] = useSearchParams();
  const token = useMemo(() => (search.get("token") || "").trim(), [search]);
  const [neuesPasswort, setNeuesPasswort] = useState("");
  const [bestaetigen, setBestaetigen] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!token) {
      setError("Reset-Token fehlt");
      return;
    }
    if (!neuesPasswort || neuesPasswort.length < 12) {
      setError("Passwort muss mindestens 12 Zeichen haben");
      return;
    }
    if (neuesPasswort !== bestaetigen) {
      setError("Passwörter stimmen nicht überein");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authPasswortReset({ token, neues_passwort: neuesPasswort, bestaetigen });
      setDone(true);
    } catch (err) {
      setError(err?.message || "Zurücksetzen fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, fontFamily: "var(--font-body)" }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border2)", borderRadius: 18, padding: "36px", width: "100%", maxWidth: 430 }}>
        <h2 style={{ color: "var(--accent)", marginBottom: 8 }}>Neues Passwort setzen</h2>
        <p style={{ color: "var(--text3)", marginBottom: 20 }}>Lege ein neues, sicheres Passwort fest.</p>
        {done ? (
          <div style={{ background: "color-mix(in srgb, var(--green) 12%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--green) 30%, transparent)", borderRadius: 10, color: "var(--green)", padding: "12px 14px" }}>
            Passwort erfolgreich aktualisiert.
          </div>
        ) : (
          <form onSubmit={submit}>
            {error && <div style={{ marginBottom: 10, color: "var(--red)" }}>{error}</div>}
            <input
              type="password"
              placeholder="Neues Passwort"
              value={neuesPasswort}
              onChange={(e) => setNeuesPasswort(e.target.value)}
              style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)", borderRadius: 10, color: "var(--text)", padding: "11px 14px", marginBottom: 12 }}
            />
            <input
              type="password"
              placeholder="Passwort bestätigen"
              value={bestaetigen}
              onChange={(e) => setBestaetigen(e.target.value)}
              style={{ width: "100%", background: "var(--bg3)", border: "1px solid var(--border2)", borderRadius: 10, color: "var(--text)", padding: "11px 14px", marginBottom: 12 }}
            />
            <button
              type="submit"
              disabled={loading}
              style={{ width: "100%", background: "var(--accent)", color: "var(--on-accent)", border: "none", borderRadius: 10, padding: "11px 14px", fontWeight: 700, opacity: loading ? 0.7 : 1 }}
            >
              {loading ? "Speichere..." : "Passwort aktualisieren"}
            </button>
          </form>
        )}
        <div style={{ marginTop: 16 }}>
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
