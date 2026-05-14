import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ThemeQuickSwitch } from "../theme";

const apiBase = (process.env.REACT_APP_API_URL || "/api").replace(/\/$/, "");

const ROLES = [
  { value: "selbststaendig", label: "Selbstständig", help: "Einzelkanzlei ohne Team (empfohlen für Solo)." },
  { value: "steuerberater", label: "Steuerberater", help: "Fachfunktionen, Lohn-Freigabe, Reports." },
  { value: "mitarbeiter", label: "Mitarbeiter", help: "Operative Aufgaben, kein Admin-Bereich." },
];

function registerUrl() {
  return `${apiBase}/register`;
}

function passwordChecks(password, email) {
  const localPart = (email || "").split("@")[0]?.toLowerCase() || "";
  return [
    { ok: password.length >= 12, label: "Mindestens 12 Zeichen" },
    { ok: /[A-Z]/.test(password), label: "Mindestens 1 Großbuchstabe" },
    { ok: /[a-z]/.test(password), label: "Mindestens 1 Kleinbuchstabe" },
    { ok: /\d/.test(password), label: "Mindestens 1 Zahl" },
    { ok: /[^A-Za-z0-9]/.test(password), label: "Mindestens 1 Sonderzeichen" },
    { ok: !/\s/.test(password), label: "Keine Leerzeichen" },
    { ok: !localPart || !password.toLowerCase().includes(localPart), label: "Nicht Teil der E-Mail" },
  ];
}

export default function Register() {
  const location = useLocation();
  const inviteFromUrl = useMemo(() => {
    const q = new URLSearchParams(location.search);
    return (q.get("invite_token") || "").trim();
  }, [location.search]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [role, setRole] = useState("selbststaendig");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const checks = passwordChecks(password, email);
  const strongPassword = checks.every((c) => c.ok);

  const submit = async (e) => {
    e?.preventDefault?.();
    setError("");
    setOk("");

    if (!email.trim()) {
      setError("Bitte E-Mail eingeben.");
      return;
    }
    if (password !== password2) {
      setError("Passwort und Wiederholung stimmen nicht überein.");
      return;
    }
    if (!strongPassword) {
      setError("Passwort erfüllt die Sicherheitsregeln noch nicht.");
      return;
    }

    setLoading(true);
    try {
      const mappedRole = role === "selbststaendig" ? "steuerberater" : role;
      const body = { email: email.trim().toLowerCase(), password, rolle: mappedRole };
      if (inviteFromUrl) body.invite_token = inviteFromUrl;
      const res = await fetch(registerUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = String(data?.detail || data?.error || "").toLowerCase();
        if (detail.includes("invalid")) {
          setError("Registrierung fehlgeschlagen. E-Mail bereits vergeben oder Eingaben ungültig.");
        } else {
          setError(data?.detail || data?.error || "Registrierung konnte nicht abgeschlossen werden.");
        }
        return;
      }

      const verifyRequired = data?.email_verification_required !== false;
      setOk(
        verifyRequired
          ? "Registrierung erfolgreich. Du erhältst gleich eine E-Mail mit Bestätigungslink (ggf. Spam-Ordner). Bitte E-Mail bestätigen und danach anmelden."
          : "Registrierung erfolgreich. Du erhältst optional eine E-Mail mit Bestätigungslink (ggf. Spam-Ordner). Danach kannst du dich anmelden.",
      );
      setTimeout(() => {
        window.location.href = "/login";
      }, 2200);
    } catch {
      setError("Server nicht erreichbar. Bitte Internetverbindung prüfen und es später erneut versuchen.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg)",
      color: "var(--text)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 20,
      fontFamily: "var(--font-body)",
    }}>
      <div style={{
        width: "100%",
        maxWidth: 560,
        border: "1px solid var(--border2)",
        borderRadius: 20,
        background: "var(--bg2)",
        padding: "32px 28px",
      }}>
        <h2 style={{ marginBottom: 8, color: "var(--accent)" }}>Konto erstellen</h2>
        <p style={{ marginBottom: 18, color: "var(--text3)", fontSize: 14 }}>
          {inviteFromUrl
            ? "Sie registrieren sich mit Einladung. Rolle/Kanzlei werden aus dem Token gesetzt."
            : "Beim ersten Konto pro Kanzlei werden Sie automatisch zum Owner. Weitere Rollen vergeben Sie spaeter im Team-Bereich."}
        </p>

        {error ? <div style={{ marginBottom: 12, color: "var(--red)" }}>{error}</div> : null}
        {ok ? <div style={{ marginBottom: 12, color: "var(--green)" }}>{ok}</div> : null}

        <form onSubmit={submit}>
          {!inviteFromUrl && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ marginBottom: 8, fontSize: 13, color: "var(--text2)" }}>Profil</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setRole(r.value)}
                    style={{
                      borderRadius: 10,
                      border: `1px solid ${role === r.value ? "var(--accent)" : "var(--border2)"}`,
                      background: role === r.value
                        ? "color-mix(in srgb, var(--accent) 18%, var(--bg3))"
                        : "var(--bg3)",
                      color: role === r.value ? "var(--accent)" : "var(--text2)",
                      padding: "8px 10px",
                      cursor: "pointer",
                      fontWeight: 600,
                    }}
                    title={r.help}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: "var(--text3)" }}>
                Tipp: Wenn Sie alleine arbeiten, wählen Sie "Selbstständig". Das richtet ein Solo-Setup ein.
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: "var(--text2)", lineHeight: 1.45 }}>
                Admin ist keine Registrierungsrolle — wird vom Owner vergeben.
              </div>
            </div>
          )}

          <input
            type="email"
            autoComplete="email"
            placeholder="E-Mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", marginBottom: 10, borderRadius: 10, padding: 12, border: "1px solid var(--border2)", background: "var(--bg3)", color: "var(--text)" }}
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Passwort"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", marginBottom: 10, borderRadius: 10, padding: 12, border: "1px solid var(--border2)", background: "var(--bg3)", color: "var(--text)" }}
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Passwort wiederholen"
            value={password2}
            onChange={(e) => setPassword2(e.target.value)}
            style={{ width: "100%", marginBottom: 10, borderRadius: 10, padding: 12, border: "1px solid var(--border2)", background: "var(--bg3)", color: "var(--text)" }}
          />

          <div style={{ marginBottom: 12, fontSize: 12, color: "var(--text3)" }}>
            {checks.map((c) => (
              <div key={c.label} style={{ color: c.ok ? "var(--green)" : "var(--text3)" }}>
                {c.ok ? "✓" : "•"} {c.label}
              </div>
            ))}
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              border: "none",
              borderRadius: 10,
              padding: 12,
              background: "var(--accent)",
              color: "var(--on-accent)",
              fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Registrierung..." : "Registrieren"}
          </button>
        </form>

        <div style={{ marginTop: 14, fontSize: 14 }}>
          <Link to="/login" style={{ color: "var(--accent)" }}>Zum Login</Link>
        </div>

        <div style={{ marginTop: 18, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Erscheinungsbild
          </span>
          <ThemeQuickSwitch compact />
        </div>
      </div>
    </div>
  );
}
