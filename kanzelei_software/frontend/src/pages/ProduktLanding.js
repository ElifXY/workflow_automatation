/**
 * Öffentliche Produktseite — Marketing-Landing (Pass 7 + 9)
 */
import { Link } from "react-router-dom";
import { PRODUCT_HEADLINE, PRODUCT_NAME, PRODUCT_SUBLINE, PRODUCT_TAGLINE } from "../navAccess";
import { ThemeQuickSwitch } from "../theme";

const BULLETS = [
  { icon: "⏰", title: "Automatische Erinnerungen", text: "Mandanten werden rechtzeitig an fehlende Unterlagen erinnert — ohne Telefon-Marathon." },
  { icon: "📂", title: "Dokumente einsammeln", text: "Portal, Upload und Scanner — alles an einem Ort für Ihre Kanzlei." },
  { icon: "🔥", title: "Dashboard: Was brennt?", text: "Rot/Gelb/Grün pro Mandant. Blockierungen und offene Antworten auf einen Blick." },
  { icon: "⚙", title: "Automationen", text: "Eskalation Tag 3→30, Frist-Rettung und ROI-Berichte — konfigurierbar pro Kanzlei." },
  { icon: "📅", title: "Microsoft 365 (Pilot)", text: "Outlook-Kalender verbinden — Termine im Dashboard und Workflow-Abgleich." },
];

const STEPS = [
  { n: "1", title: "Mandanten anlegen", text: "Stammdaten, Betreuer und fehlende Unterlagen definieren." },
  { n: "2", title: "Automation aktivieren", text: "Vorlagen für Erinnerungen, Eskalation und Portal-Bot wählen." },
  { n: "3", title: "Dashboard steuern", text: "Kritische Fälle sehen, erinnern, nachverfolgen — Fälle liegen nicht mehr." },
];

const FAQ = [
  {
    q: "Ersetzt Kanzlei Automation DATEV?",
    a: "Nein. Wir automatisieren Mandanten-Workflows und liefern Exporte zu DATEV — Ihre Fibu bleibt DATEV.",
  },
  {
    q: "Brauchen Mandanten ein neues Portal?",
    a: "Optional: Mandantenportal für Upload, Chat und Bot-Fragen — oder nur E-Mail-Erinnerungen.",
  },
  {
    q: "Was bringt die M365-Anbindung?",
    a: "Pilot: Outlook-Kalender im Dashboard und interne Aufgaben bei Termin-Kollisionen mit offenen Unterlagen.",
  },
  {
    q: "Wo werden Daten gehostet?",
    a: "Deployment für DE/EU — GoBD-konforme Protokollierung, tenantweise getrennte Kanzlei-Daten.",
  },
];

const STATS = [
  { value: "3→30", label: "Eskalationsstufen" },
  { value: "5", label: "Haupt-Tabs statt 20" },
  { value: "0", label: "Telefonate für Standard-Erinnerungen" },
];

function MockDashboard() {
  return (
    <div style={{
      marginTop: 32, padding: 20, borderRadius: 16, background: "var(--bg2)",
      border: "1px solid var(--border)", boxShadow: "var(--shadow-soft, 0 8px 32px rgba(0,0,0,.12))",
    }}>
      <div style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
        Dashboard-Vorschau
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 14 }}>
        {[
          { l: "Kritisch", v: "3", c: "var(--red)" },
          { l: "Blockiert", v: "7", c: "var(--orange)" },
          { l: "Heute fällig", v: "2", c: "var(--text)" },
          { l: "Outlook heute", v: "4", c: "var(--blue)" },
        ].map((s) => (
          <div key={s.l} style={{ padding: 12, borderRadius: 10, background: "var(--bg3)", border: "1px solid var(--border2)" }}>
            <div style={{ fontSize: 10, color: "var(--text3)" }}>{s.l}</div>
            <div style={{ fontSize: 22, fontFamily: "var(--font-head)", color: s.c, marginTop: 4 }}>{s.v}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {["Müller GmbH — 12 Tage ohne Antwort", "Schmidt — fehlende Lohnunterlagen"].map((row) => (
          <div key={row} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10,
            padding: "10px 12px", borderRadius: 10, background: "var(--bg3)", fontSize: 12,
            borderLeft: "3px solid var(--orange)",
          }}>
            <span>{row}</span>
            <span style={{ color: "var(--accent)", fontWeight: 600, flexShrink: 0 }}>Erinnern</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProduktLanding() {
  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)", fontFamily: "var(--font-body)",
      color: "var(--text)",
    }}>
      <header style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "20px max(20px, env(safe-area-inset-right)) 20px max(20px, env(safe-area-inset-left))",
        borderBottom: "1px solid var(--border)", background: "var(--bg2)",
      }}>
        <div style={{ fontFamily: "var(--font-head)", fontSize: 20, color: "var(--accent)" }}>
          {PRODUCT_NAME}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <ThemeQuickSwitch compact />
          <Link to="/login" style={{
            padding: "8px 14px", borderRadius: 10, border: "1px solid var(--border2)",
            color: "var(--text2)", textDecoration: "none", fontSize: 13, fontWeight: 600,
          }}>
            Anmelden
          </Link>
          <Link to="/register" style={{
            padding: "8px 14px", borderRadius: 10, background: "var(--accent)",
            color: "var(--on-accent)", textDecoration: "none", fontSize: 13, fontWeight: 600,
          }}>
            Kostenlos testen
          </Link>
        </div>
      </header>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "48px 24px 64px" }}>
        <p style={{ fontSize: 12, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text3)", marginBottom: 12 }}>
          {PRODUCT_TAGLINE}
        </p>
        <h1 style={{
          fontFamily: "var(--font-head)", fontSize: "clamp(28px, 5vw, 42px)",
          lineHeight: 1.15, margin: "0 0 16px", color: "var(--text)",
        }}>
          {PRODUCT_HEADLINE}
        </h1>
        <p style={{ fontSize: 17, color: "var(--text2)", lineHeight: 1.65, maxWidth: 640, marginBottom: 24 }}>
          {PRODUCT_SUBLINE}
        </p>

        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginBottom: 32 }}>
          {STATS.map((s) => (
            <div key={s.label}>
              <div style={{ fontFamily: "var(--font-head)", fontSize: 28, color: "var(--accent)" }}>{s.value}</div>
              <div style={{ fontSize: 12, color: "var(--text3)" }}>{s.label}</div>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 32 }}>
          <Link to="/register" style={{
            padding: "14px 24px", borderRadius: 12, background: "var(--accent)",
            color: "var(--on-accent)", textDecoration: "none", fontWeight: 700, fontSize: 15,
          }}>
            Jetzt starten
          </Link>
          <Link to="/login" style={{
            padding: "14px 24px", borderRadius: 12, border: "1px solid var(--border2)",
            color: "var(--text)", textDecoration: "none", fontWeight: 600, fontSize: 15,
          }}>
            Bereits Kunde — anmelden
          </Link>
        </div>

        <MockDashboard />

        <h2 style={{ fontFamily: "var(--font-head)", fontSize: 22, margin: "48px 0 20px" }}>So funktioniert es</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 40 }}>
          {STEPS.map((s) => (
            <div key={s.n} style={{ padding: 18, borderRadius: 14, background: "var(--bg2)", border: "1px solid var(--border)" }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%", background: "var(--accent)", color: "var(--on-accent)",
                display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13, marginBottom: 10,
              }}>
                {s.n}
              </div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{s.title}</div>
              <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.55 }}>{s.text}</div>
            </div>
          ))}
        </div>

        <h2 style={{ fontFamily: "var(--font-head)", fontSize: 22, margin: "0 0 20px" }}>Was Sie bekommen</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
          {BULLETS.map((b) => (
            <div key={b.title} style={{
              padding: 20, borderRadius: 14, background: "var(--bg2)",
              border: "1px solid var(--border)",
            }}>
              <div style={{ fontSize: 24, marginBottom: 10 }}>{b.icon}</div>
              <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6 }}>{b.title}</div>
              <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.55 }}>{b.text}</div>
            </div>
          ))}
        </div>

        <h2 style={{ fontFamily: "var(--font-head)", fontSize: 22, margin: "48px 0 20px" }}>Häufige Fragen</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 40 }}>
          {FAQ.map((f) => (
            <details key={f.q} style={{
              padding: "14px 18px", borderRadius: 12, background: "var(--bg2)", border: "1px solid var(--border)",
            }}>
              <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 14 }}>{f.q}</summary>
              <p style={{ margin: "10px 0 0", fontSize: 13, color: "var(--text2)", lineHeight: 1.6 }}>{f.a}</p>
            </details>
          ))}
        </div>

        <div style={{
          marginTop: 24, padding: 24, borderRadius: 16,
          background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, var(--bg2)), var(--bg2))",
          border: "1px solid color-mix(in srgb, var(--accent) 22%, transparent)",
          textAlign: "center",
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
            Für Steuerkanzleien, die Mandanten-Workflows automatisieren wollen — nicht die Fibu ersetzen.
          </div>
          <div style={{ fontSize: 13, color: "var(--text3)", marginBottom: 16 }}>
            DATEV-Export · Mandanten-Portal · GoBD-konform · Hosting in DE/EU · M365-Pilot
          </div>
          <Link to="/register" style={{
            display: "inline-block", padding: "12px 22px", borderRadius: 10, background: "var(--accent)",
            color: "var(--on-accent)", textDecoration: "none", fontWeight: 700, fontSize: 14,
          }}>
            Kostenlos testen →
          </Link>
        </div>
      </main>

      <footer style={{
        padding: "24px", textAlign: "center", fontSize: 12, color: "var(--text3)",
        borderTop: "1px solid var(--border)",
      }}>
        © {new Date().getFullYear()} {PRODUCT_NAME}
      </footer>
    </div>
  );
}
