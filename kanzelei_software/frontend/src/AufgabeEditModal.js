import { useEffect, useState } from "react";

const PRIO_KEYS = ["niedrig", "normal", "hoch", "kritisch"];

/**
 * Modal: Aufgabe bearbeiten (alle Felder auf einmal, kein prompt-Ketten).
 * @param {boolean} open
 * @param {object|null} task — muss id, beschreibung (oder text), frist, optional mandant, frist_uhrzeit, prioritaet, kategorie, notiz
 * @param {string[]} mandantenListe — für Dropdown wenn allowMandantChange
 * @param {boolean} allowMandantChange
 * @param {() => void} onClose
 * @param {(payload: object) => Promise<void>} onSave — PUT-Body ohne id
 */
export default function AufgabeEditModal({
  open,
  task,
  mandantenListe = [],
  allowMandantChange = false,
  onClose,
  onSave,
}) {
  const [mandant, setMandant] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [frist, setFrist] = useState("");
  const [fristUhrzeit, setFristUhrzeit] = useState("");
  const [prioritaet, setPrioritaet] = useState("normal");
  const [kategorie, setKategorie] = useState("");
  const [notiz, setNotiz] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!open || !task) return;
    setErr("");
    setMandant(task.mandant || "");
    let b = (task.beschreibung != null ? String(task.beschreibung) : "").trim();
    if (!b && task.text) {
      const t = String(task.text);
      const idx = t.indexOf("->");
      b = idx >= 0 ? t.slice(idx + 2).trim() : t.trim();
    }
    setBeschreibung(b);
    setFrist(task.frist || "");
    setFristUhrzeit(task.frist_uhrzeit || "");
    setPrioritaet(String(task.prioritaet || "normal").toLowerCase());
    setKategorie(task.kategorie || "");
    setNotiz(task.notiz || "");
  }, [open, task]);

  if (!open || !task) return null;

  const btnBase = {
    fontFamily: "var(--font-body, system-ui, sans-serif)",
    fontSize: 14,
    cursor: "pointer",
    borderRadius: 10,
    padding: "10px 18px",
    border: "1px solid var(--border2)",
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr("");
    const besch = String(beschreibung || "").trim();
    const fr = String(frist || "").trim();
    if (!besch) {
      setErr("Beschreibung ist erforderlich.");
      return;
    }
    if (!fr) {
      setErr("Frist (Datum) ist erforderlich.");
      return;
    }
    const mand = String(mandant || "").trim();
    if (allowMandantChange && !mand) {
      setErr("Bitte Mandant wählen.");
      return;
    }

    const payload = {
      beschreibung: besch,
      frist: fr,
      frist_uhrzeit: String(fristUhrzeit || "").trim(),
      prioritaet: PRIO_KEYS.includes(prioritaet) ? prioritaet : "normal",
      kategorie: String(kategorie || "").trim(),
      notiz: String(notiz || "").trim(),
    };
    if (allowMandantChange && mand) payload.mandant = mand;

    setSaving(true);
    try {
      await onSave(payload);
      onClose();
    } catch (ex) {
      setErr(ex?.message || "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  };

  const inp = {
    width: "100%",
    background: "var(--bg)",
    border: "1px solid var(--border2)",
    borderRadius: 10,
    color: "var(--text)",
    padding: "10px 12px",
    fontSize: 14,
    outline: "none",
    fontFamily: "var(--font-body, system-ui, sans-serif)",
    boxSizing: "border-box",
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--overlay-scrim, rgba(0,0,0,0.45))",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10050,
        padding: 16,
      }}
      onClick={(e) => e.target === e.currentTarget && !saving && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="aufgabe-edit-title"
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: "var(--bg2)",
          border: "1px solid var(--border2)",
          borderRadius: 16,
          width: "min(520px, 100%)",
          maxHeight: "90vh",
          overflow: "auto",
          boxShadow: "var(--shadow-elev, 0 12px 40px rgba(0,0,0,0.25))",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: "18px 20px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div id="aufgabe-edit-title" style={{ fontWeight: 700, fontSize: 17, color: "var(--text)" }}>
            Aufgabe bearbeiten
          </div>
          <button
            type="button"
            onClick={() => !saving && onClose()}
            style={{ ...btnBase, background: "var(--bg3)", color: "var(--text2)", padding: "6px 12px" }}
          >
            ✕
          </button>
        </div>

        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          {err ? (
            <div
              style={{
                background: "color-mix(in srgb, var(--red) 12%, var(--bg3))",
                border: "1px solid color-mix(in srgb, var(--red) 25%, transparent)",
                borderRadius: 10,
                padding: "10px 12px",
                color: "var(--red)",
                fontSize: 13,
              }}
            >
              {err}
            </div>
          ) : null}

          {allowMandantChange ? (
            <div>
              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
                MANDANT
              </div>
              <select value={mandant} onChange={(e) => setMandant(e.target.value)} style={{ ...inp, cursor: "pointer" }}>
                <option value="">— wählen —</option>
                {[...new Set([...mandantenListe, mandant].filter(Boolean))]
                  .sort((x, y) => x.localeCompare(y))
                  .map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
              </select>
            </div>
          ) : null}

          <div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
              BESCHREIBUNG
            </div>
            <input value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} style={inp} />
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 160px" }}>
              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
                FRIST
              </div>
              <input type="date" value={frist} onChange={(e) => setFrist(e.target.value)} style={{ ...inp, colorScheme: "dark" }} />
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
                UHRZEIT (OPTIONAL)
              </div>
              <input type="time" value={fristUhrzeit} onChange={(e) => setFristUhrzeit(e.target.value)} style={{ ...inp, colorScheme: "dark" }} />
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 8, letterSpacing: "0.06em" }}>
              PRIORITÄT
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {PRIO_KEYS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPrioritaet(p)}
                  style={{
                    ...btnBase,
                    background: prioritaet === p ? "color-mix(in srgb, var(--accent) 22%, var(--bg3))" : "var(--bg3)",
                    color: prioritaet === p ? "var(--accent)" : "var(--text2)",
                    fontWeight: prioritaet === p ? 600 : 400,
                    textTransform: "capitalize",
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
              KATEGORIE (OPTIONAL)
            </div>
            <input value={kategorie} onChange={(e) => setKategorie(e.target.value)} placeholder="z. B. Steuer" style={inp} />
          </div>

          <div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 6, letterSpacing: "0.06em" }}>
              NOTIZ (OPTIONAL)
            </div>
            <textarea
              value={notiz}
              onChange={(e) => setNotiz(e.target.value)}
              rows={2}
              style={{ ...inp, resize: "vertical", minHeight: 64 }}
            />
          </div>
        </div>

        <div
          style={{
            padding: "14px 20px 18px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 10,
            justifyContent: "flex-end",
          }}
        >
          <button type="button" disabled={saving} onClick={onClose} style={{ ...btnBase, background: "var(--bg3)", color: "var(--text2)" }}>
            Abbrechen
          </button>
          <button
            type="submit"
            disabled={saving}
            style={{
              ...btnBase,
              background: "var(--accent)",
              color: "var(--bg, #111)",
              fontWeight: 600,
              borderColor: "color-mix(in srgb, var(--accent) 40%, transparent)",
            }}
          >
            {saving ? "…" : "Speichern"}
          </button>
        </div>
      </form>
    </div>
  );
}
