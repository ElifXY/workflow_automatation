// KI-E-Mail: Vorschau, Bearbeiten (Text/HTML), Empfänger, Versand
import { useState, useEffect, useMemo } from "react";
import { getEmailPreview, getEmailAbsender, sendEmail } from "../api";

const emailOk = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((v || "").trim());

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Signatur am Ende des Plain-Texts — steht bereits im HTML-Footer */
function ohneHtmlSignatur(blocks) {
  const copy = [...blocks];
  while (copy.length > 1) {
    const last = copy[copy.length - 1].toLowerCase();
    if (
      last.startsWith("mit freundlichen")
      || (last.includes("@") && copy[copy.length - 1].length < 160)
    ) {
      copy.pop();
    } else {
      break;
    }
  }
  return copy;
}

function plainBloeckeZuHtml(blocks) {
  return blocks
    .map((block, i) => {
      const isAnrede = i === 0 && /^(sehr geehrte|guten tag|hallo|liebe)/i.test(block);
      const style = isAnrede
        ? "font-size:16px;color:#222;margin:0 0 10px;"
        : "font-size:14px;color:#555;margin:0 0 14px;line-height:1.75;";
      const inner = escapeHtml(block).split("\n").join("<br>");
      return `<p style="${style}">${inner}</p>`;
    })
    .join("\n            ");
}

/**
 * Bearbeiteten Plain-Text in die KI-HTML-Vorlage einsetzen (Header, CTA, Footer bleiben).
 */
function mergePlainIntoTemplate(templateHtml, plainText) {
  const tpl = (templateHtml || "").trim();
  if (!tpl || !plainText?.trim()) return tpl;

  if (!tpl.includes("padding:32px")) {
    const blocks = ohneHtmlSignatur(
      plainText.split(/\n\n+/).map((s) => s.trim()).filter(Boolean)
    );
    return `<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:24px;background:#f4f4f5;font-family:'Segoe UI',Arial,sans-serif;">
${plainBloeckeZuHtml(blocks)}
</body></html>`;
  }

  const blocks = ohneHtmlSignatur(
    plainText.split(/\n\n+/).map((s) => s.trim()).filter(Boolean)
  );
  const bodyInner = plainBloeckeZuHtml(blocks);

  const replaced = tpl.replace(
    /(<td style="padding:32px;">)[\s\S]*?(<\/td>)/,
    `$1\n            ${bodyInner}\n          $2`
  );
  return replaced !== tpl ? replaced : tpl;
}

const tabBtn = (active) => ({
  padding: "6px 12px",
  borderRadius: 8,
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
  border: active
    ? "1px solid color-mix(in srgb, var(--accent) 40%, transparent)"
    : "1px solid var(--border2)",
  background: active
    ? "color-mix(in srgb, var(--accent) 14%, var(--bg3))"
    : "transparent",
  color: active ? "var(--accent)" : "var(--text2)",
});

export default function KiEmailComposer({
  mandantName,
  mandantEmail = "",
  compact = false,
  onSent,
}) {
  const [preview, setPreview] = useState(null);
  const [original, setOriginal] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [empfaenger, setEmpfaenger] = useState(mandantEmail || "");
  const [betreff, setBetreff] = useState("");
  const [editText, setEditText] = useState("");
  const [editHtml, setEditHtml] = useState("");
  const [inhaltTab, setInhaltTab] = useState("vorschau"); // vorschau | text | html
  const [textGeaendert, setTextGeaendert] = useState(false);
  const [htmlGeaendert, setHtmlGeaendert] = useState(false);
  const [gesendet, setGesendet] = useState(false);
  const [kiGeneriert, setKiGeneriert] = useState(false);
  const [fehler, setFehler] = useState(null);
  const [absenderInfo, setAbsenderInfo] = useState(null);

  useEffect(() => {
    setEmpfaenger(mandantEmail || "");
  }, [mandantEmail, mandantName]);

  useEffect(() => {
    let cancelled = false;
    getEmailAbsender()
      .then((d) => {
        if (!cancelled && d) {
          setAbsenderInfo({
            anzeige: d.from_header || d.display_name || "",
            name: d.display_name || "",
            email: d.from_email || "",
            build: d.build || "",
          });
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [mandantName]);

  const basisHtml = original?.html || preview?.email_html || "";

  const vorschauHtml = useMemo(() => {
    if (htmlGeaendert && editHtml.trim()) return editHtml;
    if (textGeaendert) return mergePlainIntoTemplate(basisHtml, editText);
    return basisHtml || "";
  }, [htmlGeaendert, editHtml, textGeaendert, editText, basisHtml]);

  const applyPreview = (d) => {
    setPreview(d);
    if (d.absender_anzeige || d.absender_name) {
      setAbsenderInfo({
        anzeige: d.absender_anzeige || d.absender_name || "",
        name: d.absender_name || "",
        email: d.absender_email || "",
        build: d.build || absenderInfo?.build || "",
      });
    }
    setOriginal({
      text: d.email_text || "",
      html: d.email_html || "",
      betreff: d.betreff || "",
    });
    setEditText(d.email_text || "");
    setEditHtml(d.email_html || "");
    setTextGeaendert(false);
    setHtmlGeaendert(false);
    setBetreff(d.betreff || `Mitteilung — ${mandantName}`);
    setKiGeneriert(!!d.ki_generiert);
    setInhaltTab("vorschau");
  };

  const ladeVorschau = async () => {
    setLoading(true);
    setFehler(null);
    try {
      const d = await getEmailPreview(mandantName);
      applyPreview(d);
      if (!empfaenger.trim() && d.empfaenger) {
        setEmpfaenger(d.empfaenger);
      }
    } catch (e) {
      setFehler(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const zuruecksetzen = () => {
    if (!original) return;
    setEditText(original.text);
    setEditHtml(original.html);
    setBetreff(original.betreff);
    setTextGeaendert(false);
    setHtmlGeaendert(false);
    setInhaltTab("vorschau");
  };

  const handleSenden = async () => {
    const to = empfaenger.trim();
    if (!emailOk(to)) {
      alert("Bitte eine gültige E-Mail-Adresse eingeben oder die Mandanten-Adresse übernehmen.");
      return;
    }
    const finalText = editText.trim() || preview?.email_text || "";
    const tpl = original?.html || preview?.email_html || "";
    let finalHtml = tpl;
    if (htmlGeaendert) {
      finalHtml = editHtml.trim();
    } else if (textGeaendert) {
      finalHtml = mergePlainIntoTemplate(tpl, editText);
    }

    setSending(true);
    setFehler(null);
    try {
      await sendEmail(mandantName, {
        empfaenger: to,
        betreff: betreff || preview?.betreff || null,
        email_html: finalHtml || null,
        email_text: finalText || null,
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

  const geaendert = textGeaendert || htmlGeaendert;

  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.55, marginBottom: 12 }}>
        {kiGeneriert
          ? "Anrede, Betreff und Formulierung wurden von der KI erstellt (OpenAI). Sie können alles vor dem Versand anpassen."
          : "E-Mail wird für den Mandanten formuliert (Vorlage, falls keine KI konfiguriert ist). Unter „Text“ oder „HTML“ können Sie den Inhalt anpassen."}
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

      <div style={{
        marginBottom: 12, padding: "10px 12px", borderRadius: 10,
        background: "var(--bg3)", border: "1px solid var(--border)",
      }}>
        <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4,
          textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Absender (im Postfach des Empfängers)
        </div>
        <div style={{ fontSize: 14, color: "var(--text)", fontWeight: 500 }}>
          {absenderInfo?.anzeige || absenderInfo?.name || "— wird geladen …"}
        </div>
        {absenderInfo?.email ? (
          <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>{absenderInfo.email}</div>
        ) : null}
        <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6, lineHeight: 1.5 }}>
          Ändern unter Einstellungen → Kanzlei-Daten → „Name im Postfach des Empfängers“
        </div>
      </div>

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
            <div style={{
              display: "flex", flexWrap: "wrap", alignItems: "center",
              justifyContent: "space-between", gap: 8, marginBottom: 8,
            }}>
              <div style={{ fontSize: 11, color: "var(--text3)",
                textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Inhalt
                {kiGeneriert && !geaendert && (
                  <span style={{
                    marginLeft: 8, padding: "2px 8px", borderRadius: 6, fontSize: 10,
                    textTransform: "none", letterSpacing: 0,
                    background: "color-mix(in srgb, var(--accent) 14%, transparent)",
                    color: "var(--accent)",
                  }}>
                    KI
                  </span>
                )}
                {geaendert && (
                  <span style={{ color: "var(--accent)", textTransform: "none", letterSpacing: 0 }}>
                    (bearbeitet)
                  </span>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button type="button" style={tabBtn(inhaltTab === "vorschau")} onClick={() => setInhaltTab("vorschau")}>
                  Vorschau
                </button>
                <button type="button" style={tabBtn(inhaltTab === "text")} onClick={() => setInhaltTab("text")}>
                  Text bearbeiten
                </button>
                <button type="button" style={tabBtn(inhaltTab === "html")} onClick={() => setInhaltTab("html")}>
                  HTML
                </button>
                {geaendert && (
                  <button
                    type="button"
                    onClick={zuruecksetzen}
                    style={{
                      ...tabBtn(false),
                      color: "var(--orange)",
                    }}
                  >
                    KI-Text wiederherstellen
                  </button>
                )}
              </div>
            </div>

            {inhaltTab === "vorschau" && (
              <div style={{
                border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden",
                background: "#f4f4f5", maxHeight: compact ? 320 : 420,
              }}>
                <iframe
                  title="E-Mail-Vorschau"
                  srcDoc={vorschauHtml}
                  sandbox=""
                  style={{
                    width: "100%", height: compact ? 300 : 400, border: "none",
                    background: "#fff",
                  }}
                />
              </div>
            )}

            {inhaltTab === "text" && (
              <textarea
                value={editText}
                onChange={(e) => {
                  setEditText(e.target.value);
                  setTextGeaendert(true);
                  if (!htmlGeaendert) {
                    setEditHtml(mergePlainIntoTemplate(basisHtml, e.target.value));
                  }
                }}
                rows={compact ? 12 : 16}
                placeholder="E-Mail-Text…"
                style={{
                  width: "100%",
                  background: "var(--bg)",
                  border: `1px solid ${textGeaendert ? "color-mix(in srgb, var(--accent) 50%, var(--border))" : "var(--border)"}`,
                  borderRadius: 10,
                  color: "var(--text)",
                  padding: "12px 14px",
                  fontSize: 13,
                  lineHeight: 1.75,
                  fontFamily: "var(--font-body)",
                  resize: "vertical",
                  outline: "none",
                  boxSizing: "border-box",
                  minHeight: 200,
                }}
              />
            )}

            {inhaltTab === "html" && (
              <textarea
                value={editHtml}
                onChange={(e) => {
                  setEditHtml(e.target.value);
                  setHtmlGeaendert(true);
                }}
                rows={compact ? 14 : 18}
                spellCheck={false}
                style={{
                  width: "100%",
                  background: "var(--bg)",
                  border: `1px solid ${htmlGeaendert ? "color-mix(in srgb, var(--accent) 50%, var(--border))" : "var(--border)"}`,
                  borderRadius: 10,
                  color: "var(--text2)",
                  padding: "12px 14px",
                  fontSize: 11,
                  lineHeight: 1.5,
                  fontFamily: "ui-monospace, Consolas, monospace",
                  resize: "vertical",
                  outline: "none",
                  boxSizing: "border-box",
                  minHeight: 220,
                }}
              />
            )}

            {inhaltTab === "text" && (
              <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 6 }}>
                Absätze mit einer Leerzeile trennen. Unter „Vorschau“ sehen Sie das Ergebnis.
              </div>
            )}
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
              onClick={() => { setPreview(null); setFehler(null); setOriginal(null); }}
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
