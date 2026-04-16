// ============================================================
// KANZLEI AI — MANDANT DETAIL PAGE v2.0
// Vollständige Mandantenakte
//
// Features:
//   ✓ Stammdaten + Score + Status auf einen Blick
//   ✓ Aufgaben: Erstellen, Toggle, Löschen, Priorität, Kategorie
//   ✓ Dokumente: Anfordern, Als erhalten markieren
//   ✓ KI Email-Vorschau + direktes Senden
//   ✓ Steuer-Simulation (Was-wäre-wenn)
//   ✓ Kommunikations-Timeline
//   ✓ Antwort-Tracking (letzte_antwort aktualisieren)
//   ✓ One-Click Workflows (Monatsabschluss, Jahresabschluss, Onboarding)
//   ✓ Vollständiger Mandanten-Report
// ============================================================

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";

import {
  getMandant,
  getMandanten,
  getAufgabenMandant,
  addAufgabeAPI,
  toggleAufgabeAPI,
  deleteAufgabeAPI,
  getDokumente,
  dokumentAnfordern,
  dokumentErhalten,
  getEmailPreview,
  sendEmail,
  mandantAntwortEmpfangen,
  getSimulation,
  getMandantReport,
  workflowMonatsabschluss,
  workflowJahresabschluss,
  workflowOnboarding,
  getTimeline,
  getKommunikation,
  addKommunikation,
  exportExcel,
  exportDatev,
  exportElster,
  exportKomplett,
  generierePortalToken,
} from "../api";

// ─── Design Tokens (konsistent mit App.js) ──────────────────
const C = {
  red: "#e05555", orange: "#e08c45", green: "#5cb87a",
  blue: "#5b8de8", accent: "#c8a96e", text: "#e8eaf0",
  text2: "#8b91a0", text3: "#555d6e", bg: "#0b0d11",
  bg2: "#111419", bg3: "#181c24",
  border: "rgba(255,255,255,0.07)",
  border2: "rgba(255,255,255,0.12)",
};

const PRIO_COLORS = {
  kritisch: C.red, hoch: C.orange,
  normal: C.blue, niedrig: C.text3,
};

// ═══════════════════════════════════════════════════════════
// PRIMITIVE COMPONENTS
// ═══════════════════════════════════════════════════════════

const Badge = ({ children, color = C.accent, style = {} }) => (
  <span style={{
    display: "inline-block", padding: "2px 9px", borderRadius: 20,
    fontSize: 11, fontWeight: 600, letterSpacing: "0.04em",
    textTransform: "uppercase", background: color + "22",
    color, border: `1px solid ${color}33`, ...style,
  }}>
    {children}
  </span>
);

const Btn = ({ children, onClick, variant = "primary", size = "md",
               disabled = false, loading = false, style = {}, title }) => {
  const sizes = { xs: "4px 9px", sm: "6px 13px", md: "9px 18px", lg: "12px 24px" };
  const fsize = { xs: 11, sm: 13, md: 14, lg: 15 };
  const variants = {
    primary: { background: C.accent, color: "#1a1200", border: "none" },
    danger:  { background: C.red + "18", color: C.red, border: `1px solid ${C.red}30` },
    ghost:   { background: "transparent", color: C.text2, border: `1px solid ${C.border2}` },
    subtle:  { background: C.bg3, color: C.text2, border: `1px solid ${C.border}` },
    success: { background: C.green + "20", color: C.green, border: `1px solid ${C.green}30` },
  };
  return (
    <button onClick={!disabled && !loading ? onClick : undefined} title={title}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: sizes[size], fontSize: fsize[size], fontWeight: 500,
        borderRadius: 10, cursor: disabled || loading ? "not-allowed" : "pointer",
        opacity: disabled || loading ? 0.5 : 1,
        transition: "all 0.15s ease", whiteSpace: "nowrap",
        fontFamily: "'DM Sans', sans-serif",
        ...variants[variant], ...style,
      }}>
      {loading && <span style={{ width: 12, height: 12, borderRadius: "50%",
        border: "2px solid currentColor", borderTopColor: "transparent",
        animation: "spin 0.7s linear infinite", display: "inline-block" }} />}
      {children}
    </button>
  );
};

const Input = ({ placeholder, value, onChange, onKeyDown, type = "text",
                 disabled = false, style = {} }) => (
  <input type={type} placeholder={placeholder} value={value} disabled={disabled}
    onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown}
    style={{
      width: "100%", background: C.bg, border: `1px solid ${C.border2}`,
      borderRadius: 10, color: C.text, padding: "9px 13px", fontSize: 14,
      outline: "none", fontFamily: "'DM Sans', sans-serif", ...style,
    }}
    onFocus={e => e.target.style.borderColor = C.accent}
    onBlur={e => e.target.style.borderColor = C.border2}
  />
);

const Card = ({ children, style = {} }) => (
  <div style={{
    background: C.bg2, border: `1px solid ${C.border}`,
    borderRadius: 14, padding: 20, ...style,
  }}>
    {children}
  </div>
);

const SectionTitle = ({ children, action }) => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                marginBottom: 14 }}>
    <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 17,
                  color: C.text, letterSpacing: "-0.01em" }}>
      {children}
    </div>
    {action}
  </div>
);

const Spinner = ({ size = 24 }) => (
  <div style={{
    width: size, height: size, borderRadius: "50%",
    border: `2px solid ${C.border2}`, borderTopColor: C.accent,
    animation: "spin 0.7s linear infinite", display: "inline-block",
  }} />
);

const Toast = ({ text, type = "success" }) => {
  const tc = { success: C.green, error: C.red, info: C.blue, warn: C.orange };
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 9999,
      background: C.bg3, border: `1px solid ${(tc[type] || C.accent)}44`,
      borderLeft: `3px solid ${tc[type] || C.accent}`,
      borderRadius: 12, padding: "12px 18px", color: C.text,
      fontSize: 13, fontWeight: 500, boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
      animation: "slideUp 0.25s ease",
    }}>
      {text}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// AUFGABEN SECTION — BUGFIX + EMAIL EDITOR
// ═══════════════════════════════════════════════════════════

const AufgabenSection = ({ name, aufgaben, onToggle, onDelete, onRefresh }) => {
  const [beschreibung, setBeschreibung] = useState("");
  const [frist, setFrist]               = useState("");
  const [prioritaet, setPrio]           = useState("normal");
  const [kategorie, setKategorie]       = useState("");
  const [adding, setAdding]             = useState(false);
  const [addError, setAddError]         = useState("");  // BUG FIX: Error-Anzeige
  const [filter, setFilter]             = useState("offen");

  const handleAdd = async () => {
    // BUG FIX: Validierung mit sichtbarem Feedback statt stilles Fehlschlagen
    if (!beschreibung.trim()) { setAddError("Beschreibung fehlt"); return; }
    if (!frist)               { setAddError("Frist fehlt — bitte Datum wählen"); return; }
    setAddError("");
    setAdding(true);
    try {
      await addAufgabeAPI(name, {
        beschreibung: beschreibung.trim(),
        frist,
        prioritaet,
        kategorie: kategorie.trim() || undefined,
      });
      setBeschreibung(""); setFrist(""); setPrio("normal"); setKategorie("");
      await onRefresh(); // BUG FIX: onRefresh korrekt awaiten
    } catch (e) {
      setAddError(e.message || "Aufgabe konnte nicht gespeichert werden");
    } finally { setAdding(false); }
  };

  const jetzt    = new Date();
  const filtered = aufgaben.filter(a => {
    if (filter === "offen")   return !a.erledigt;
    if (filter === "erledigt") return a.erledigt;
    return true;
  });

  const getFristInfo = (fristStr, erledigt) => {
    if (erledigt) return { label: "Erledigt", color: C.green, tage: null };
    if (!fristStr) return { label: "Kein Datum", color: C.text3, tage: null };
    const f    = new Date(fristStr);
    const diff = Math.round((f - jetzt) / 86400000);
    if (diff < 0)  return { label: `${Math.abs(diff)}d überfällig`, color: C.red,    tage: diff };
    if (diff === 0) return { label: "Heute fällig",                 color: C.red,    tage: 0 };
    if (diff <= 1)  return { label: "Morgen fällig",                color: C.orange, tage: 1 };
    if (diff <= 7)  return { label: `in ${diff} Tagen`,             color: C.orange, tage: diff };
    return { label: `in ${diff} Tagen`, color: C.text3, tage: diff };
  };

  return (
    <Card>
      <SectionTitle action={
        <div style={{ display: "flex", gap: 6 }}>
          {["offen", "erledigt", "alle"].map(f => (
            <Btn key={f} size="xs" variant={filter === f ? "subtle" : "ghost"}
                 onClick={() => setFilter(f)} style={{ textTransform: "capitalize" }}>
              {f}
            </Btn>
          ))}
        </div>
      }>
        Aufgaben & Fristen
        <Badge color={C.accent} style={{ marginLeft: 10, fontSize: 10 }}>
          {aufgaben.filter(a => !a.erledigt).length} offen
        </Badge>
      </SectionTitle>

      {/* Neue Aufgabe */}
      <div style={{
        background: C.bg3, border: `1px solid ${addError ? C.red + "50" : C.border}`,
        borderRadius: 12, padding: "14px 16px", marginBottom: 16,
        transition: "border 0.2s",
      }}>
        <div style={{ fontSize: 11, color: C.text3, textTransform: "uppercase",
                      letterSpacing: "0.07em", marginBottom: 10 }}>
          Neue Aufgabe
        </div>

        {/* BUG FIX: Fehler-Anzeige */}
        {addError && (
          <div style={{
            background: C.red + "15", border: `1px solid ${C.red}30`,
            borderRadius: 8, padding: "8px 12px", marginBottom: 10,
            fontSize: 12, color: C.red, display: "flex",
            alignItems: "center", gap: 6,
          }}>
            ⚠ {addError}
          </div>
        )}

        {/* BUG FIX: Responsive Layout — Beschreibung oben, Datum + Button unten */}
        <Input placeholder="Beschreibung der Aufgabe..."
               value={beschreibung}
               onChange={v => { setBeschreibung(v); if (addError) setAddError(""); }}
               onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleAdd()}
               style={{ marginBottom: 8 }} />

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <div style={{ flex: "0 0 auto" }}>
            <input type="date" value={frist}
                   onChange={e => { setFrist(e.target.value); if (addError) setAddError(""); }}
                   style={{
                     background: C.bg, border: `1px solid ${!frist && addError ? C.red + "60" : C.border2}`,
                     borderRadius: 10, color: frist ? C.text : C.text3,
                     padding: "9px 11px", fontSize: 14, outline: "none",
                     fontFamily: "'DM Sans', sans-serif",
                   }} />
          </div>
          <Btn onClick={handleAdd} loading={adding} variant="primary">
            + Aufgabe hinzufügen
          </Btn>
        </div>

        {/* Priorität & Kategorie */}
        <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ fontSize: 11, color: C.text3 }}>Priorität:</span>
            {Object.entries(PRIO_COLORS).map(([p, c]) => (
              <Btn key={p} size="xs" variant={prioritaet === p ? "subtle" : "ghost"}
                   onClick={() => setPrio(p)} style={{ color: c, textTransform: "capitalize" }}>
                {p}
              </Btn>
            ))}
          </div>
          <Input placeholder="Kategorie (optional)" value={kategorie}
                 onChange={setKategorie}
                 style={{ maxWidth: 180, padding: "5px 10px", fontSize: 12 }} />
        </div>
      </div>

      {/* Aufgaben-Liste */}
      {filtered.length === 0 ? (
        <div style={{ textAlign: "center", padding: "24px 0", color: C.text3, fontSize: 13 }}>
          {filter === "offen" ? "Keine offenen Aufgaben ✓" :
           filter === "erledigt" ? "Noch nichts erledigt" : "Keine Aufgaben vorhanden"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filtered.map((a, i) => {
            const fi = getFristInfo(a.frist, a.erledigt);
            const pc = PRIO_COLORS[a.prioritaet] || C.text3;
            return (
              <div key={a.id} style={{
                display: "flex", alignItems: "flex-start", gap: 12,
                padding: "12px 14px",
                background: a.erledigt ? "transparent" : C.bg,
                border: `1px solid ${a.erledigt ? C.border : fi.tage !== null && fi.tage < 3 ? fi.color + "44" : C.border2}`,
                borderRadius: 10, opacity: a.erledigt ? 0.55 : 1,
                transition: "all 0.15s ease",
                animation: `fadeUp 0.3s ease ${i * 30}ms both`,
              }}>
                <input type="checkbox" checked={!!a.erledigt}
                       onChange={() => onToggle(a.id)}
                       style={{ marginTop: 3, cursor: "pointer", accentColor: C.accent, flexShrink: 0 }} />

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 500, color: C.text, fontSize: 14,
                    textDecoration: a.erledigt ? "line-through" : "none",
                  }}>
                    {a.beschreibung}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 5, flexWrap: "wrap", alignItems: "center" }}>
                    {a.frist && (
                      <span style={{ fontSize: 12, color: C.text3 }}>
                        📅 {new Date(a.frist).toLocaleDateString("de-DE")}
                      </span>
                    )}
                    <Badge color={fi.color} style={{ fontSize: 10 }}>{fi.label}</Badge>
                    {a.prioritaet && a.prioritaet !== "normal" && (
                      <Badge color={pc} style={{ fontSize: 10 }}>{a.prioritaet}</Badge>
                    )}
                    {a.kategorie && (
                      <Badge color={C.text3} style={{ fontSize: 10 }}>{a.kategorie}</Badge>
                    )}
                  </div>
                </div>

                <Btn size="xs" variant="danger" title="Aufgabe löschen"
                     onClick={() => onDelete(a.id)} style={{ flexShrink: 0, opacity: 0.6 }}>
                  ✕
                </Btn>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// DOKUMENTE SECTION
// ═══════════════════════════════════════════════════════════

const DokumenteSection = ({ name, dokumente, onRefresh }) => {
  const [neuesDok, setNeuesDok]     = useState("");
  const [adding, setAdding]         = useState(false);
  const [erhaltenId, setErhaltenId] = useState(null);

  const handleAnfordern = async () => {
    if (!neuesDok.trim()) return;
    setAdding(true);
    try {
      await dokumentAnfordern(name, neuesDok.trim());
      setNeuesDok("");
      await onRefresh();
    } catch (e) { alert(e.message); }
    finally { setAdding(false); }
  };

  const handleErhalten = async (dokName) => {
    setErhaltenId(dokName);
    try {
      await dokumentErhalten(name, dokName);
      await onRefresh();
    } catch (e) { alert(e.message); }
    finally { setErhaltenId(null); }
  };

  const haeufige = [
    "Kontoauszüge", "Einkommensnachweise", "Rechnungen",
    "Versicherungsnachweise", "Verträge", "Lohnabrechnung",
    "Kfz-Belege", "Spendenbescheinigungen",
  ];

  return (
    <Card>
      <SectionTitle>
        Dokumente
        {dokumente.length > 0 && (
          <Badge color={C.orange} style={{ marginLeft: 10, fontSize: 10 }}>
            {dokumente.length} fehlend
          </Badge>
        )}
      </SectionTitle>

      {/* Fehlende Dokumente */}
      {dokumente.length === 0 ? (
        <div style={{ fontSize: 13, color: C.text3, marginBottom: 14, padding: "8px 0" }}>
          Alle Dokumente vollständig ✓
        </div>
      ) : (
        <div style={{ marginBottom: 16, display: "flex", flexDirection: "column", gap: 6 }}>
          {dokumente.map((dok, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "10px 14px", background: C.bg,
              border: `1px solid ${C.orange}33`, borderRadius: 10,
              animation: `fadeUp 0.3s ease ${i * 40}ms both`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ color: C.orange, fontSize: 14 }}>▲</span>
                <span style={{ fontSize: 13, color: C.text }}>{dok}</span>
              </div>
              <Btn size="xs" variant="success"
                   loading={erhaltenId === dok}
                   onClick={() => handleErhalten(dok)}>
                Erhalten ✓
              </Btn>
            </div>
          ))}
        </div>
      )}

      {/* Schnellauswahl häufige Dokumente */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 11, color: C.text3, marginBottom: 6,
                      textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Häufig angefordert
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {haeufige.map(d => (
            <Btn key={d} size="xs" variant="ghost" onClick={() => setNeuesDok(d)}>
              {d}
            </Btn>
          ))}
        </div>
      </div>

      {/* Manuell anfordern */}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Input placeholder="Dokument anfordern..." value={neuesDok}
               onChange={setNeuesDok}
               onKeyDown={e => e.key === "Enter" && handleAnfordern()} />
        <Btn onClick={handleAnfordern} loading={adding} variant="primary" size="md"
             style={{ whiteSpace: "nowrap" }}>
          Anfordern
        </Btn>
      </div>
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// EMAIL SECTION
// ═══════════════════════════════════════════════════════════

const EmailSection = ({ name, email }) => {
  const [preview,    setPreview]    = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [sending,    setSending]    = useState(false);
  const [gesendet,   setGesendet]   = useState(false);
  const [editMode,   setEditMode]   = useState(false);
  const [editText,   setEditText]   = useState("");
  const [betreff,    setBetreff]    = useState("");

  const ladeVorschau = async () => {
    setLoading(true);
    try {
      const d = await getEmailPreview(name);
      setPreview(d);
      setEditText(d.email_text || "");
      setBetreff(`Kanzlei Mitteilung — ${name} — ${new Date().toLocaleDateString("de-DE")}`);
    } catch (e) {
      setPreview({ email_text: "Vorschau nicht verfügbar: " + e.message, empfaenger: "" });
      setEditText("Vorschau nicht verfügbar: " + e.message);
    } finally { setLoading(false); }
  };

  const handleSenden = async () => {
    if (!email) { alert("Kein E-Mail für diesen Mandanten hinterlegt."); return; }
    setSending(true);
    try {
      // FIX: email_text (nicht emailText) — Backend erwartet snake_case
      await sendEmail(name, {
        email_text: editMode ? editText : (preview?.email_text || null),
        betreff:    betreff || null,
        force:      true,
      });
      setGesendet(true);
      setTimeout(() => setGesendet(false), 4000);
    } catch (e) { alert(e.message); }
    finally { setSending(false); }
  };

  const handleKiNeu = async () => {
    setLoading(true);
    setEditMode(false);
    try {
      const d = await getEmailPreview(name);
      setPreview(d);
      setEditText(d.email_text || "");
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <Card>
      <SectionTitle>KI-Email</SectionTitle>

      {!email && (
        <div style={{
          fontSize: 12, color: C.orange, marginBottom: 12,
          background: C.orange + "15", border: `1px solid ${C.orange}30`,
          borderRadius: 8, padding: "8px 12px",
        }}>
          ⚠ Keine E-Mail-Adresse hinterlegt
        </div>
      )}

      {gesendet && (
        <div style={{
          fontSize: 12, color: C.green, marginBottom: 12,
          background: C.green + "15", border: `1px solid ${C.green}30`,
          borderRadius: 8, padding: "8px 12px",
        }}>
          ✓ Email wurde versendet
        </div>
      )}

      {!preview ? (
        <Btn onClick={ladeVorschau} loading={loading} variant="ghost" size="sm">
          KI-Email generieren
        </Btn>
      ) : (
        <>
          {/* Betreff */}
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: C.text3, marginBottom: 4,
                          textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Betreff
            </div>
            <Input
              placeholder="Betreff..."
              value={betreff}
              onChange={setBetreff}
            />
          </div>

          {/* Email-Text — editierbar */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 6 }}>
              <div style={{ fontSize: 11, color: C.text3, textTransform: "uppercase",
                             letterSpacing: "0.06em" }}>
                Email-Text {editMode && <span style={{ color: C.accent }}>(bearbeitet)</span>}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <Btn size="xs" variant={editMode ? "subtle" : "ghost"}
                     onClick={() => { setEditMode(!editMode); if (!editMode) setEditText(preview.email_text); }}>
                  {editMode ? "✓ Bearbeitung" : "✏ Bearbeiten"}
                </Btn>
                <Btn size="xs" variant="ghost" onClick={handleKiNeu} loading={loading}>
                  ⟳ KI neu
                </Btn>
              </div>
            </div>

            {editMode ? (
              <textarea
                value={editText}
                onChange={e => setEditText(e.target.value)}
                rows={10}
                style={{
                  width: "100%", background: C.bg,
                  border: `1px solid ${C.accent}66`,
                  borderRadius: 10, color: C.text,
                  padding: "12px 14px", fontSize: 13,
                  fontFamily: "'DM Sans', sans-serif",
                  lineHeight: 1.8, resize: "vertical", outline: "none",
                }}
              />
            ) : (
              <pre style={{
                whiteSpace: "pre-wrap", fontFamily: "'DM Sans', sans-serif",
                fontSize: 12, color: C.text2, lineHeight: 1.8,
                background: C.bg, border: `1px solid ${C.border}`,
                borderRadius: 10, padding: "12px 14px",
                maxHeight: 240, overflowY: "auto",
                cursor: "text",
              }}
                onClick={() => setEditMode(true)}
                title="Klicken zum Bearbeiten">
                {editText || preview.email_text}
              </pre>
            )}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Btn onClick={handleSenden} loading={sending} variant="primary" size="sm"
                 disabled={!email}>
              ✉ Senden an {preview.empfaenger || email || "?"}
            </Btn>
            <Btn onClick={() => { setPreview(null); setEditText(""); setEditMode(false); }}
                 variant="ghost" size="sm">
              Schließen
            </Btn>
          </div>

          <div style={{ fontSize: 11, color: C.text3, marginTop: 8 }}>
            Klicke auf den Text oder „Bearbeiten" um die Email anzupassen
          </div>
        </>
      )}
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// SIMULATION SECTION
// ═══════════════════════════════════════════════════════════

const SimulationSection = ({ name }) => {
  const [form, setForm] = useState({
    investition: "", zusatz_einnahmen: "",
    abschreibungen: "", sonderausgaben: "",
  });
  const [ergebnis, setErgebnis]   = useState(null);
  const [loading, setLoading]     = useState(false);

  const handleSim = async () => {
    setLoading(true);
    try {
      const payload = Object.fromEntries(
        Object.entries(form).map(([k, v]) => [k, parseFloat(v) || 0])
      );
      const d = await getSimulation(name, payload);
      setErgebnis(d.simulation);
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  const felder = [
    { key: "investition",       label: "Geplante Investition (€)" },
    { key: "zusatz_einnahmen",  label: "Zusatzeinnahmen (€)" },
    { key: "abschreibungen",    label: "Abschreibungen (€)" },
    { key: "sonderausgaben",    label: "Sonderausgaben (€)" },
  ];

  return (
    <Card>
      <SectionTitle>Steuer-Simulation</SectionTitle>
      <div style={{ fontSize: 12, color: C.text3, marginBottom: 14 }}>
        Was-wäre-wenn Analyse — Steuerlast bei veränderten Parametern
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
        {felder.map(f => (
          <div key={f.key}>
            <div style={{ fontSize: 11, color: C.text3, marginBottom: 4 }}>{f.label}</div>
            <Input placeholder="0" value={form[f.key]} type="number"
                   onChange={v => setForm(p => ({ ...p, [f.key]: v }))} />
          </div>
        ))}
      </div>

      <Btn onClick={handleSim} loading={loading} variant="primary" size="sm">
        Simulation starten
      </Btn>

      {ergebnis && (
        <div style={{
          marginTop: 14, background: C.bg, border: `1px solid ${C.border}`,
          borderRadius: 10, padding: 14,
        }}>
          {[
            ["Basis-Gewinn",          ergebnis.basis_gewinn,        C.text2],
            ["Simulierter Gewinn",    ergebnis.simulierter_gewinn,  C.blue],
            ["Steuerlast aktuell",    ergebnis.steuerlast_aktuell,  C.orange],
            ["Steuerlast simuliert",  ergebnis.steuerlast_simuliert,C.green],
            ["Steuerersparnis",       ergebnis.steuerersparnis,
             ergebnis.steuerersparnis > 0 ? C.green : C.red],
          ].map(([label, wert, farbe]) => (
            <div key={label} style={{
              display: "flex", justifyContent: "space-between", alignItems: "baseline",
              padding: "6px 0", borderBottom: `1px solid ${C.border}`,
            }}>
              <span style={{ fontSize: 12, color: C.text3 }}>{label}</span>
              <span style={{ fontSize: 14, fontWeight: 600, color: farbe }}>
                €{(wert || 0).toLocaleString("de-DE", { minimumFractionDigits: 2 })}
              </span>
            </div>
          ))}
          <div style={{ fontSize: 11, color: C.text3, marginTop: 10 }}>
            {ergebnis.hinweis}
          </div>
        </div>
      )}
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// WORKFLOWS SECTION
// ═══════════════════════════════════════════════════════════

const WorkflowSection = ({ name, onRefresh }) => {
  const [loading, setLoading] = useState(null);
  const [result, setResult]   = useState(null);

  const jetzt = new Date();
  const monat = jetzt.getMonth() + 1;
  const jahr  = jetzt.getFullYear();

  const workflows = [
    {
      id:    "monatsabschluss",
      label: "Monatsabschluss",
      desc:  `Alle Aufgaben für ${monat}/${jahr} automatisch anlegen`,
      icon:  "▦", color: C.blue,
      fn:    () => workflowMonatsabschluss(name, monat, jahr),
    },
    {
      id:    "jahresabschluss",
      label: "Jahresabschluss",
      desc:  `Jahresabschluss ${jahr} vorbereiten`,
      icon:  "◈", color: C.accent,
      fn:    () => workflowJahresabschluss(name, jahr),
    },
    {
      id:    "onboarding",
      label: "Onboarding",
      desc:  "Standard-Erstaufgaben für neuen Mandanten anlegen",
      icon:  "◉", color: C.green,
      fn:    () => workflowOnboarding(name),
    },
  ];

  const triggerWorkflow = async (wf) => {
    if (!window.confirm(`"${wf.label}" Workflow starten für ${name}?`)) return;
    setLoading(wf.id);
    setResult(null);
    try {
      const data = await wf.fn();
      setResult({ id: wf.id, ...data });
      await onRefresh();
    } catch (e) {
      setResult({ id: wf.id, status: "fehler", fehler: e.message });
    } finally { setLoading(null); }
  };

  return (
    <Card>
      <SectionTitle>One-Click Workflows</SectionTitle>
      <div style={{ fontSize: 12, color: C.text3, marginBottom: 14 }}>
        Standardaufgaben automatisch anlegen — spart bis zu 30 Minuten pro Workflow
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {workflows.map(wf => (
          <div key={wf.id} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 14px", background: C.bg,
            border: `1px solid ${C.border}`, borderRadius: 10,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: wf.color + "20", display: "flex",
                alignItems: "center", justifyContent: "center",
                fontSize: 16, color: wf.color, flexShrink: 0,
              }}>
                {wf.icon}
              </div>
              <div>
                <div style={{ fontWeight: 600, color: C.text, fontSize: 14 }}>{wf.label}</div>
                <div style={{ fontSize: 12, color: C.text3, marginTop: 2 }}>{wf.desc}</div>
              </div>
            </div>
            <Btn size="sm" variant="subtle" loading={loading === wf.id}
                 onClick={() => triggerWorkflow(wf)}>
              Starten
            </Btn>
          </div>
        ))}
      </div>

      {result && result.status === "ok" && (
        <div style={{
          marginTop: 14, background: C.green + "10", border: `1px solid ${C.green}30`,
          borderRadius: 10, padding: "12px 14px",
        }}>
          <div style={{ color: C.green, fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
            ✓ {result.aufgaben_erstellt} Aufgaben wurden erstellt
          </div>
          {result.aufgaben?.map((a, i) => (
            <div key={i} style={{ fontSize: 12, color: C.text3, padding: "2px 0" }}>
              · {a}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function MandantDetail() {
  const { name: encodedName } = useParams();
  const name     = decodeURIComponent(encodedName || "");
  const navigate = useNavigate();

  const [mandant,   setMandant]   = useState(null);
  const [aufgaben,  setAufgaben]  = useState([]);
  const [dokumente, setDokumente] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [toast,     setToast]     = useState(null);
  const [antwortLoading, setAntwortLoading] = useState(false);

  const showToast = useCallback((text, type = "success") => {
    setToast({ text, type });
    setTimeout(() => setToast(null), 3500);
  }, []);

  // ── Daten laden ────────────────────────────────────────
  const ladeMandant = useCallback(async () => {
    try {
      const d = await getMandant(name);
      setMandant(d);
    } catch (e) {
      // Fallback: alle Mandanten laden und filtern (wenn /mandanten/{name} nicht verfügbar)
      try {
        const all = await getMandanten();
        const m   = all?.data?.find(x => x.name === name);
        setMandant(m || null);
      } catch { setMandant(null); }
    }
  }, [name]);

  const ladeAufgaben = useCallback(async () => {
    try {
      const d = await getAufgabenMandant(name);
      setAufgaben(d?.aufgaben || []);
    } catch { setAufgaben([]); }
  }, [name]);

  const ladeDokumente = useCallback(async () => {
    try {
      const d = await getDokumente(name);
      setDokumente(d?.fehlende_dokumente || []);
    } catch { setDokumente([]); }
  }, [name]);

  const ladeAlles = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    await Promise.allSettled([ladeMandant(), ladeAufgaben(), ladeDokumente()]);
    if (initial) setLoading(false);
  }, [ladeMandant, ladeAufgaben, ladeDokumente]);

  useEffect(() => { ladeAlles(true); }, [ladeAlles]);

  // ── Aufgaben-Aktionen ──────────────────────────────────
  const handleToggle = async (id) => {
    setAufgaben(p => p.map(a => a.id === id ? { ...a, erledigt: !a.erledigt } : a));
    try {
      await toggleAufgabeAPI(id);
      showToast("Status geändert");
    } catch (e) {
      showToast(e.message, "error");
      await ladeAufgaben();
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Aufgabe wirklich löschen?")) return;
    setAufgaben(p => p.filter(a => a.id !== id));
    try {
      await deleteAufgabeAPI(id);
      showToast("Aufgabe gelöscht", "warn");
    } catch (e) {
      showToast(e.message, "error");
      await ladeAufgaben();
    }
  };

  // ── Antwort registrieren ───────────────────────────────
  const handleAntwort = async () => {
    setAntwortLoading(true);
    try {
      await mandantAntwortEmpfangen(name);
      showToast("Antwort registriert — Erinnerungs-Timer zurückgesetzt");
      await ladeMandant();
    } catch (e) { showToast(e.message, "error"); }
    finally { setAntwortLoading(false); }
  };

  // ── Loading & Not Found ────────────────────────────────
  if (loading) return (
    <div style={{
      minHeight: "100vh", background: C.bg,
      display: "flex", alignItems: "center", justifyContent: "center",
      flexDirection: "column", gap: 16,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
        @keyframes slideUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0b0d11; }
      `}</style>
      <Spinner size={36} />
      <div style={{ color: C.text3, fontFamily: "'DM Sans', sans-serif" }}>
        Lade Mandantenakte...
      </div>
    </div>
  );

  if (!mandant) return (
    <div style={{
      minHeight: "100vh", background: C.bg, padding: 40,
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #0b0d11; }
      `}</style>
      <div style={{ color: C.red, fontSize: 18, marginBottom: 12 }}>
        Mandant nicht gefunden: „{name}"
      </div>
      <Btn onClick={() => navigate("/")} variant="ghost">← Zurück zum Dashboard</Btn>
    </div>
  );

  // ── Score & Status ─────────────────────────────────────
  const score    = mandant.score_details?.score ?? mandant.score ?? 0;
  const status   = score >= 12000 ? "KRITISCH" : score >= 5000 ? "WICHTIG" : "OK";
  const statusC  = { KRITISCH: C.red, WICHTIG: C.orange, OK: C.green }[status];
  const tage     = mandant.score_details?.tage ?? mandant.tage_ohne_antwort ?? 0;

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "'DM Sans', sans-serif" }}>

      {/* Fonts + Animations */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes fadeUp  { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }
        @keyframes slideUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        @keyframes pulse   { 0%,100%{opacity:1} 50%{opacity:.4} }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
      `}</style>

      {/* ── HEADER ── */}
      <div style={{
        background: C.bg2, borderBottom: `1px solid ${C.border}`,
        padding: "20px 36px", display: "flex", alignItems: "center", gap: 16,
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <Btn onClick={() => navigate("/")} variant="ghost" size="sm">← Dashboard</Btn>

        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: "'DM Serif Display', serif", fontSize: 24, color: C.text,
            letterSpacing: "-0.01em",
          }}>
            {name}
          </div>
          <div style={{ color: C.text3, fontSize: 12, marginTop: 2, display: "flex", gap: 12 }}>
            {mandant.email && <span>✉ {mandant.email}</span>}
            {mandant.telefon && <span>📞 {mandant.telefon}</span>}
            {mandant.branche && <span>◈ {mandant.branche}</span>}
          </div>
        </div>

        {/* Status + Aktionen */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ textAlign: "right" }}>
            <Badge color={statusC} style={{ fontSize: 11 }}>{status}</Badge>
            <div style={{ fontSize: 11, color: C.text3, marginTop: 4 }}>
              Score: {Math.round(score).toLocaleString("de")}
            </div>
          </div>

          <Btn onClick={handleAntwort} loading={antwortLoading} variant="success" size="sm"
               title="Letzte Antwort auf heute setzen — stoppt Erinnerungs-Emails">
            ✓ Antwort erhalten
          </Btn>

          <Btn onClick={() => ladeAlles()} variant="ghost" size="sm">⟳</Btn>
        </div>
      </div>

      {/* ── CONTENT ── */}
      <div style={{ padding: "28px 36px" }}>

        {/* Warnung wenn kein Kontakt seit 7+ Tagen */}
        {tage >= 7 && (
          <div style={{
            background: C.orange + "12", border: `1px solid ${C.orange}35`,
            borderRadius: 12, padding: "12px 18px", marginBottom: 20,
            display: "flex", alignItems: "center", gap: 12,
            animation: "fadeUp 0.3s ease",
          }}>
            <span style={{ color: C.orange, fontSize: 18 }}>⚠</span>
            <div>
              <span style={{ color: C.orange, fontWeight: 600, fontSize: 13 }}>
                Seit {tage} Tagen keine Rückmeldung
              </span>
              <span style={{ color: C.text3, fontSize: 12, marginLeft: 8 }}>
                Automatische Erinnerung aktiv
              </span>
            </div>
            <Btn onClick={handleAntwort} variant="ghost" size="xs"
                 style={{ marginLeft: "auto" }} loading={antwortLoading}>
              Als beantwortet markieren
            </Btn>
          </div>
        )}

        {/* 2-Spalten Layout */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 20, alignItems: "start" }}>

          {/* LINKE SPALTE: Aufgaben */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <AufgabenSection
              name={name} aufgaben={aufgaben}
              onToggle={handleToggle} onDelete={handleDelete}
              onRefresh={ladeAufgaben}
            />
            <SimulationSection name={name} />
          </div>

          {/* RECHTE SPALTE: Stammdaten + Dokumente + Email + Workflows */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Stammdaten */}
            <Card>
              <SectionTitle>Stammdaten</SectionTitle>
              {[
                ["Jahresumsatz", `€${(mandant.umsatz || 0).toLocaleString("de-DE")}`, C.accent],
                ["E-Mail",       mandant.email   || "—", null],
                ["Telefon",      mandant.telefon || "—", null],
                ["Branche",      mandant.branche || "—", null],
                ["Steuer-ID",    mandant.steuer_id || "—", null],
                ["Aufgaben offen",    mandant.aufgaben_offen ?? aufgaben.filter(a=>!a.erledigt).length, null],
                ["Aufgaben erledigt", mandant.aufgaben_erledigt ?? aufgaben.filter(a=>a.erledigt).length, C.green],
                ["Letzter Kontakt",   tage > 0 ? `vor ${tage} Tagen` : "Heute", tage >= 7 ? C.orange : null],
              ].map(([label, value, color]) => (
                <div key={label} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "baseline",
                  padding: "7px 0", borderBottom: `1px solid ${C.border}`,
                }}>
                  <span style={{ fontSize: 12, color: C.text3, flexShrink: 0 }}>{label}</span>
                  <span style={{
                    fontSize: 13, fontWeight: 500,
                    color: color || C.text, textAlign: "right",
                    maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {String(value)}
                  </span>
                </div>
              ))}

              {mandant.notizen && (
                <div style={{ marginTop: 12, fontSize: 12, color: C.text2,
                              lineHeight: 1.7, borderTop: `1px solid ${C.border}`,
                              paddingTop: 10 }}>
                  {mandant.notizen}
                </div>
              )}
            </Card>

            <DokumenteSection
              name={name} dokumente={dokumente} onRefresh={ladeDokumente}
            />

            <EmailSection name={name} email={mandant.email} />

            <WorkflowSection name={name} onRefresh={ladeAlles} />

            {/* Export Section */}
            <Card>
              <SectionTitle>Export & DATEV</SectionTitle>
              <div style={{ fontSize: 12, color: C.text3, marginBottom: 12 }}>
                Alle Formate direkt als Download
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { label: "📊 Excel-Report",        fn: () => exportExcel(name),          desc: "Stammdaten, Aufgaben, Kommunikation" },
                  { label: "🏛 DATEV Buchungsstapel", fn: () => exportDatev(name),          desc: "EXTF v700 — direkt importierbar" },
                  { label: "⚖ ELSTER UStVA XML",     fn: () => exportElster(name, "UStVA"), desc: "ERiC Transfer-Format" },
                  { label: "📦 Komplett-Paket ZIP",   fn: () => exportKomplett(name),       desc: "DATEV + ELSTER + Excel + CSV" },
                ].map((ex, i) => (
                  <div key={i} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "8px 12px", background: C.bg,
                    border: `1px solid ${C.border}`, borderRadius: 8,
                  }}>
                    <div>
                      <div style={{ fontSize: 13, color: C.text, fontWeight: 500 }}>{ex.label}</div>
                      <div style={{ fontSize: 11, color: C.text3 }}>{ex.desc}</div>
                    </div>
                    <Btn size="xs" variant="ghost"
                         onClick={() => ex.fn().catch(e => showToast(e.message, "error"))}>
                      ⬇
                    </Btn>
                  </div>
                ))}
              </div>
            </Card>

            {/* Portal Token */}
            <Card>
              <SectionTitle>Mandantenportal</SectionTitle>
              <div style={{ fontSize: 12, color: C.text3, marginBottom: 12 }}>
                Zugangslink für den Mandanten generieren
              </div>
              {mandant.email ? (
                <Btn variant="subtle" size="sm"
                     onClick={async () => {
                       const key = prompt("Admin-Key eingeben:");
                       if (!key) return;
                       try {
                         const d = await generierePortalToken(name, key);
                         await navigator.clipboard.writeText(d.link);
                         showToast("✓ Link in Zwischenablage kopiert", "success");
                       } catch (e) { showToast(e.message, "error"); }
                     }}
                     style={{ width: "100%", justifyContent: "center" }}>
                  🔗 Portal-Link generieren & kopieren
                </Btn>
              ) : (
                <div style={{ fontSize: 12, color: C.orange }}>
                  ⚠ E-Mail-Adresse fehlt — bitte ergänzen
                </div>
              )}
            </Card>

          </div>
        </div>
      </div>

      {/* Toast */}
      {toast && <Toast text={toast.text} type={toast.type} />}
    </div>
  );
}