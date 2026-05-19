// KI-E-Mail: Vorschau (HTML), Empfänger wählbar, Versand
import { useState, useEffect } from "react";
import { getEmailPreview, sendEmail } from "../api";

const emailOk = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((v || "").trim());

export default function KiEmailComposer({
  mandantName,
  mandantEmail = "",
  compact = false,
  onSent,
}) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [empfaenger, setEmpfaenger] = useState(mandantEmail || "");
  const [betreff, setBetreff] = useState("");
  const [gesendet, setGesendet] = useState(false);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    setEmpfaenger(mandantEmail || "");
  }, [mandantEmail, mandantName]);

  const ladeVorschau = async () => {
    setLoading(true);
    setFehler(null);
    try {
      const d = await getEmailPreview(mandantName);
      setPreview(d);
      setBetreff(d.betreff || `Mitteilung — ${mandantName}`);
      if (!empfaenger.trim() && d.empfaenger) {
        setEmpfaenger(d.empfaenger);
      }
    } catch (e) {
      setFehler(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleSenden = async () => {
    const to = empfaenger.trim();
    if (!emailOk(to)) {
      alert("Bitte eine gültige E-Mail-Adresse eingeben oder die Mandanten-Adresse übernehmen.");
      return;
    }
    setSending(true);
    setFehler(null);
    try {
      await sendEmail(mandantName, {
        empfaenger: to,
        betreff: betreff || preview?.betreff || null,
        email_html: preview?.email_html || null,
        email_text: preview?.email_text || null,
        force: true,
      });
      setGesendet(true);
      setTimeout(() => setGesendet(false), 5000);
      onSent?.(to);
    } catch (e) {
      setFehler(e.message || String(e));
    } finally {
      setSending(false);
    }
  };

  const inputStyle = {
    width: "100%",
    background: "var(--bg)",
    border: "1px solid var(--border)",
    borderRadius: 10,
    color: "var(--text)",
    padding: "10px 12px",
    fontSize: 13,
    fontFamily: "var(--font-body)",
    outline: "none",
    boxSizing: "border-box",
  };

  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.55, marginBottom: 12 }}>
        Professionelle E-Mail an den Mandanten — mit Ihrem Kanzlei-Namen (Einstellungen),
        Anrede nach Ansprechpartner und offenen Punkten aus dem System.
      </div>

      {gesendet && (
        <div style={{
          fontSize: 12, color: "var(--green)", marginBottom: 12,
          background: "color-mix(in srgb, var(--green) 12%, transparent)",
          border: "1px solid color-mix(in srgb, var(--green) 30%, transparent)",
          borderRadius: 8, padding: "8px 12px",
        }}>
          E-Mail wurde an {empfaenger} zur Zustellung eingereiht.
        </div>
      )}
      {fehler && (
        <div style={{
          fontSize: 12, color: "var(--red)", marginBottom: 12,
          background: "color-mix(in srgb, var(--red) 12%, transparent)",
          borderRadius: 8, padding: "8px 12px",
        }}>
          {fehler}
        </div>
      )}

      {!preview ? (
        <button
          type="button"
          onClick={ladeVorschau}
          disabled={loading}
          style={{
            padding: "9px 16px", borderRadius: 10, border: "1px solid var(--border2)",
            background: "var(--bg3)", color: "var(--text)", cursor: loading ? "wait" : "pointer",
            fontSize: 13,
          }}
        >
          {loading ? "Wird erstellt…" : "KI-E-Mail generieren"}
        </button>
      ) : (
        <>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4,
              textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Senden an
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                type="email"
                placeholder="name@firma.de"
                value={empfaenger}
                onChange={(e) => setEmpfaenger(e.target.value)}
                style={{ ...inputStyle, flex: "1 1 200px" }}
              />
              {mandantEmail && mandantEmail !== empfaenger && (
                <button
                  type="button"
                  onClick={() => setEmpfaenger(mandantEmail)}
                  style={{
                    padding: "9px 12px", borderRadius: 10, fontSize: 12,
                    border: "1px solid var(--border2)", background: "var(--bg3)",
                    color: "var(--accent)", cursor: "pointer", whiteSpace: "nowrap",
                  }}
                >
                  Mandanten-E-Mail
                </button>
              )}
            </div>
            {!mandantEmail && (
              <div style={{ fontSize: 11, color: "var(--orange)", marginTop: 6 }}>
                Keine E-Mail im Mandantenstamm — bitte Adresse eingeben.
              </div>
            )}
          </div>

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4,
              textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Betreff
            </div>
            <input
              type="text"
              value={betreff}
              onChange={(e) => setBetreff(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6,
              textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Vorschau (so erhält der Mandant die E-Mail)
            </div>
            <div style={{
              border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden",
              background: "#f4f4f5", maxHeight: compact ? 320 : 420,
            }}>
              <iframe
                title="E-Mail-Vorschau"
                srcDoc={preview.email_html || preview.email_text || ""}
                sandbox=""
                style={{
                  width: "100%", height: compact ? 300 : 400, border: "none",
                  background: "#fff",
                }}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={handleSenden}
              disabled={sending || !emailOk(empfaenger)}
              style={{
                padding: "10px 18px", borderRadius: 10, border: "none",
                background: "var(--accent)", color: "var(--on-accent)",
                fontWeight: 600, fontSize: 13,
                cursor: sending || !emailOk(empfaenger) ? "not-allowed" : "pointer",
                opacity: sending || !emailOk(empfaenger) ? 0.6 : 1,
              }}
            >
              {sending ? "Wird gesendet…" : `Senden an ${empfaenger || "…"}`}
            </button>
            <button
              type="button"
              onClick={ladeVorschau}
              disabled={loading}
              style={{
                padding: "10px 14px", borderRadius: 10,
                border: "1px solid var(--border2)", background: "transparent",
                color: "var(--text2)", fontSize: 13, cursor: "pointer",
              }}
            >
              Neu generieren
            </button>
            <button
              type="button"
              onClick={() => { setPreview(null); setFehler(null); }}
              style={{
                padding: "10px 14px", borderRadius: 10,
                border: "1px solid var(--border2)", background: "transparent",
                color: "var(--text3)", fontSize: 13, cursor: "pointer",
              }}
            >
              Schließen
            </button>
          </div>
        </>
      )}
    </div>
  );
}
