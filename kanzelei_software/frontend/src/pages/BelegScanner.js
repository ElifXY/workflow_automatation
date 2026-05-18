// ============================================================
// KANZLEI AI — BELEGSCANNER v1.0
// Datei: src/pages/BelegScanner.js
//
// Das #1 Zeitsparer-Feature:
//   Upload (Drag & Drop / Kamera) → KI analysiert → Buchungsvorschlag
//   Steuerberater: nur noch bestätigen statt manuell eingeben
//
// Spart: 3-5 Min pro Beleg × 50 Belege/Tag = 2-4 Stunden täglich
// ============================================================

import { useState, useRef, useCallback, useEffect } from "react";

const BASE = process.env.REACT_APP_API_URL || "/api";

const apiFetch = async (url, opts = {}) => {
  const token = localStorage.getItem("kanzlei_token");
  const res = await fetch(BASE + url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Fehler ${res.status}`);
  return data;
};

const Btn = ({ children, onClick, variant = "primary", size = "md",
               loading = false, disabled = false, style = {} }) => {
  const vs = {
    primary: { background: "var(--accent)", color: "var(--on-accent)", border: "none" },
    ghost:   { background: "transparent", color: "var(--text2)", border: `1px solid var(--border2)` },
    subtle:  { background: "var(--bg3)", color: "var(--text2)", border: `1px solid var(--border)` },
    success: { background: "color-mix(in srgb, var(--green) 20%, var(--bg3))", color: "var(--green)", border: "1px solid color-mix(in srgb, var(--green) 30%, transparent)" },
    danger:  { background: "color-mix(in srgb, var(--red) 18%, var(--bg3))", color: "var(--red)", border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)" },
  };
  const ss = { xs: "4px 9px", sm: "7px 14px", md: "9px 18px", lg: "12px 24px" };
  const fs = { xs: 11, sm: 13, md: 14, lg: 15 };
  return (
    <button onClick={!loading && !disabled ? onClick : undefined} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: ss[size], fontSize: fs[size], fontWeight: 500,
      borderRadius: 10, cursor: loading || disabled ? "not-allowed" : "pointer",
      opacity: loading || disabled ? 0.5 : 1, transition: "all 0.15s",
      fontFamily: "'DM Sans', sans-serif", ...vs[variant], ...style,
    }}>
      {loading && <span style={{ width: 12, height: 12, borderRadius: "50%",
        border: "2px solid currentColor", borderTopColor: "transparent",
        animation: "spin 0.7s linear infinite", display: "inline-block" }} />}
      {children}
    </button>
  );
};

const Badge = ({ children, color = "var(--accent)" }) => (
  <span style={{
    display: "inline-block", padding: "2px 9px", borderRadius: 20,
    fontSize: 11, fontWeight: 600, letterSpacing: "0.05em",
    textTransform: "uppercase", background: color + "22",
    color, border: `1px solid ${color}33`,
  }}>{children}</span>
);

// ─── Kategorie-Icons ─────────────────────────────────────────
const KAT_ICONS = {
  buero: "🖊", porto: "📦", telefon: "📱", software: "💻",
  hardware: "🖥", miete: "🏢", strom: "⚡", reise: "✈",
  bewirtung: "🍽", kfz: "🚗", benzin: "⛽", personal: "👤",
  versicherung: "🛡", werbung: "📢", weiterbildung: "📚",
  material: "📦", einnahme: "💰", sonstiges: "📄",
};

const KATEGORIEN = [
  "buero", "porto", "telefon", "software", "hardware", "miete",
  "strom", "reise", "bewirtung", "kfz", "benzin", "personal",
  "versicherung", "werbung", "weiterbildung", "material",
  "einnahme", "einnahme_7", "sonstiges",
];

const SKR03_FALLBACK = {
  buero: { soll: "4930", haben: "1200" },
  porto: { soll: "4910", haben: "1200" },
  telefon: { soll: "4920", haben: "1200" },
  software: { soll: "0680", haben: "1200" },
  hardware: { soll: "0680", haben: "1200" },
  miete: { soll: "4210", haben: "1200" },
  strom: { soll: "4240", haben: "1200" },
  reise: { soll: "4670", haben: "1200" },
  bewirtung: { soll: "4650", haben: "1200" },
  kfz: { soll: "4520", haben: "1200" },
  benzin: { soll: "4530", haben: "1200" },
  personal: { soll: "4120", haben: "1700" },
  versicherung: { soll: "4360", haben: "1200" },
  werbung: { soll: "4600", haben: "1200" },
  weiterbildung: { soll: "4900", haben: "1200" },
  material: { soll: "3200", haben: "1200" },
  einnahme: { soll: "1200", haben: "8400" },
  einnahme_7: { soll: "1200", haben: "8300" },
  sonstiges: { soll: "4980", haben: "1200" },
};

function skr03Anzeige(beleg) {
  const kat = (beleg.kategorie || "sonstiges").toLowerCase();
  const fb = SKR03_FALLBACK[kat] || SKR03_FALLBACK.sonstiges;
  return {
    soll: beleg.skr03_soll || fb.soll,
    haben: beleg.skr03_haben || fb.haben,
  };
}

function korrekturPayload(form) {
  const p = {};
  const keys = [
    "mandant", "betrag_brutto", "betrag_netto", "mwst_betrag", "mwst_satz",
    "datum", "lieferant", "rechnungsnummer", "kategorie",
    "skr03_soll", "skr03_haben", "buchungstext", "vorsteuer_abzugsfaehig",
  ];
  for (const k of keys) {
    if (form[k] === undefined || form[k] === null || form[k] === "") continue;
    if (["betrag_brutto", "betrag_netto", "mwst_betrag"].includes(k)) {
      p[k] = Number(form[k]);
    } else if (k === "mwst_satz") {
      p[k] = parseInt(form[k], 10);
    } else {
      p[k] = form[k];
    }
  }
  return p;
}

// ═══════════════════════════════════════════════════════════
// UPLOAD ZONE
// ═══════════════════════════════════════════════════════════

const UploadZone = ({ onDatei, loading }) => {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) onDatei(files);
  }, [onDatei]);

  const handleChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) onDatei(files);
    e.target.value = "";
  };

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !loading && inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? "var(--accent)" : "var(--border2)"}`,
        borderRadius: 16, padding: "48px 32px",
        textAlign: "center", cursor: loading ? "not-allowed" : "pointer",
        background: dragging ? "color-mix(in srgb, var(--accent) 8%, var(--bg3))" : "var(--bg3)",
        transition: "all 0.2s",
      }}>
      <input ref={inputRef} type="file" multiple
             accept=".jpg,.jpeg,.png,.pdf,.webp"
             onChange={handleChange} style={{ display: "none" }} />

      {loading ? (
        <div>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
          <div style={{ fontWeight: 600, color: "var(--accent)", fontSize: 16, marginBottom: 6 }}>
            KI analysiert Belege...
          </div>
          <div style={{ color: "var(--text3)", fontSize: 13 }}>
            Erkennt Beträge, Kategorien und Buchungskonten automatisch
          </div>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 48, marginBottom: 14 }}>📎</div>
          <div style={{ fontWeight: 600, color: "var(--text)", fontSize: 18, marginBottom: 6 }}>
            Belege hier ablegen
          </div>
          <div style={{ color: "var(--text3)", fontSize: 13, marginBottom: 16 }}>
            JPG, PNG, PDF, WebP · Mehrere auf einmal möglich
          </div>
          <Btn variant="ghost" size="sm">Dateien auswählen</Btn>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// BUCHUNGS-VORSCHLAG KARTE
// ═══════════════════════════════════════════════════════════

const BuchungsKarte = ({ beleg, mandanten, gebucht, defaultMandant = "", onBestaetigen, onAblehnen, onLoeschen }) => {
  const [edit, setEdit]     = useState(false);
  const [form, setForm]     = useState({ ...beleg });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm({
      ...beleg,
      mandant: beleg.mandant || defaultMandant || "",
    });
    setEdit(false);
  }, [beleg.beleg_id, beleg.id, beleg.status, beleg.mandant, beleg.bestaetigt_am, defaultMandant]);

  const score       = beleg.vertrauens_score || 0;
  const scoreColor  = score >= 0.8 ? "var(--green)" : score >= 0.6 ? "var(--orange)" : "var(--red)";
  const scoreLabel  = score >= 0.8 ? "Sicher" : score >= 0.6 ? "Prüfen" : "Unsicher";
  const skr = skr03Anzeige(beleg);

  const handleSpeichern = async () => {
    if (!gebucht && !form.mandant) return;
    setSaving(true);
    try {
      await onBestaetigen(readBelegId(beleg), korrekturPayload(form));
      if (!gebucht) setEdit(false);
    } finally { setSaving(false); }
  };

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  return (
    <div style={{
      background: "var(--bg2)", border: `1px solid var(--border)`,
      borderRadius: 14, overflow: "hidden",
      animation: "fadeUp 0.35s ease both",
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 18px", background: "var(--bg3)",
        borderBottom: `1px solid var(--border)`,
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <div style={{ fontSize: 24 }}>
          {KAT_ICONS[beleg.kategorie] || "📄"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, color: "var(--text)", fontSize: 14,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {beleg.dateiname}
          </div>
          <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>
            {gebucht && beleg.mandant ? (
              <span style={{ color: "var(--accent)", fontWeight: 600 }}>{beleg.mandant}</span>
            ) : null}
            {gebucht && beleg.mandant ? " · " : ""}
            {beleg.lieferant || "Unbekannter Lieferant"} · {beleg.datum || "—"}
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: "var(--accent)" }}>
            €{Number(beleg.betrag_brutto || 0).toFixed(2)}
          </div>
          {gebucht ? (
            <Badge color="var(--green)">✓ Gebucht</Badge>
          ) : (
            <Badge color={scoreColor}>{scoreLabel} {Math.round(score * 100)}%</Badge>
          )}
        </div>
      </div>

      {/* Buchungs-Details */}
      {!edit ? (
        <div style={{ padding: "14px 18px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
            {[
              { l: "Kategorie",  v: beleg.kategorie_name || beleg.kategorie },
              { l: "SKR03 Soll", v: skr.soll },
              { l: "SKR03 Haben", v: skr.haben },
              { l: "Netto",      v: `€${Number(beleg.betrag_netto || 0).toFixed(2)}` },
              { l: `MwSt ${beleg.mwst_satz || 19}%`, v: `€${Number(beleg.mwst_betrag || 0).toFixed(2)}` },
              { l: "Vorsteuer",  v: beleg.vorsteuer_abzugsfaehig ? "✓ Abzugsfähig" : "✗ Nicht abzugsfähig",
                                  c: beleg.vorsteuer_abzugsfaehig ? "var(--green)" : "var(--orange)" },
            ].map(item => (
              <div key={item.l} style={{
                background: "var(--bg3)", borderRadius: 8, padding: "8px 12px",
              }}>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase",
                               letterSpacing: "0.06em", marginBottom: 3 }}>
                  {item.l}
                </div>
                <div style={{ fontSize: 13, fontWeight: 500,
                               color: item.c || "var(--text)" }}>
                  {item.v}
                </div>
              </div>
            ))}
          </div>

          {beleg.buchungstext && (
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>
              Buchungstext: <span style={{ color: "var(--text2)" }}>{beleg.buchungstext}</span>
            </div>
          )}

          {beleg.rechnungsnummer && (
            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 8 }}>
              Rechnungsnr.: <span style={{ color: "var(--text2)" }}>{beleg.rechnungsnummer}</span>
            </div>
          )}

          {beleg.notiz && (
            <div style={{
              background: "color-mix(in srgb, var(--orange) 12%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--orange) 25%, transparent)",
              borderRadius: 8, padding: "8px 12px", marginBottom: 12,
              fontSize: 12, color: "var(--orange)",
            }}>
              ⚠ {beleg.notiz}
            </div>
          )}
          {!gebucht && Array.isArray(beleg.unsichere_felder) && beleg.unsichere_felder.length > 0 && (
            <div style={{
              background: "color-mix(in srgb, var(--orange) 12%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--orange) 25%, transparent)",
              borderRadius: 8, padding: "8px 12px", marginBottom: 12,
              fontSize: 12, color: "var(--orange)",
            }}>
              Bitte prüfen: {beleg.unsichere_felder.slice(0, 6).join(", ")}
            </div>
          )}

          {gebucht ? (
            <div style={{
              marginBottom: 12, padding: "10px 12px", borderRadius: 8,
              background: "color-mix(in srgb, var(--green) 10%, var(--bg3))",
              border: "1px solid color-mix(in srgb, var(--green) 28%, transparent)",
            }}>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                Mandant
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--green)" }}>
                {beleg.mandant || "—"}
              </div>
              {beleg.bestaetigt_am && (
                <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4 }}>
                  Gebucht am {String(beleg.bestaetigt_am).slice(0, 10)}
                </div>
              )}
            </div>
          ) : (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "var(--text3)", marginBottom: 4 }}>Mandant</div>
              <select
                value={form.mandant || ""}
                onChange={e => setForm(p => ({ ...p, mandant: e.target.value }))}
                style={{
                  background: "var(--bg)", border: `1px solid var(--border2)`,
                  borderRadius: 8, color: form.mandant ? "var(--text)" : "var(--text3)",
                  padding: "7px 11px", fontSize: 13,
                  fontFamily: "'DM Sans', sans-serif", outline: "none",
                  width: "100%",
                }}>
                <option value="">— Mandant wählen —</option>
                {mandanten.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {!gebucht && (
              <>
                <Btn onClick={handleSpeichern} loading={saving} variant="success" size="sm"
                     disabled={!form.mandant}>
                  ✓ Buchung bestätigen
                </Btn>
                <Btn onClick={() => onAblehnen(readBelegId(beleg))} variant="danger" size="sm">
                  ✕ Ablehnen
                </Btn>
              </>
            )}
            <Btn onClick={() => setEdit(true)} variant="ghost" size="sm">
              ✏ Korrigieren
            </Btn>
            {gebucht && onLoeschen && (
              <Btn size="sm" variant="danger" onClick={() => onLoeschen(readBelegId(beleg))}>
                🗑 Löschen
              </Btn>
            )}
          </div>
        </div>
      ) : (
        /* Edit-Modus */
        <div style={{ padding: "14px 18px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
            {[
              { k: "betrag_brutto",  l: "Brutto (€)", type: "number" },
              { k: "betrag_netto",   l: "Netto (€)",  type: "number" },
              { k: "mwst_betrag",    l: "MwSt (€)",   type: "number" },
              { k: "mwst_satz",      l: "MwSt %",     type: "number" },
              { k: "datum",          l: "Datum",       type: "date" },
              { k: "lieferant",      l: "Lieferant",   type: "text" },
              { k: "rechnungsnummer",l: "Rechnungsnr.",type: "text" },
              { k: "skr03_soll",     l: "SKR03 Soll",  type: "text" },
              { k: "skr03_haben",    l: "SKR03 Haben", type: "text" },
              { k: "buchungstext",   l: "Buchungstext",type: "text" },
            ].map(f => (
              <div key={f.k}>
                <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase",
                               letterSpacing: "0.06em", marginBottom: 3 }}>{f.l}</div>
                <input type={f.type} value={form[f.k] || ""}
                       onChange={e => set(f.k, f.type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)}
                       style={{
                         width: "100%", background: "var(--bg)", border: `1px solid var(--border2)`,
                         borderRadius: 8, color: "var(--text)", padding: "7px 10px",
                         fontSize: 13, outline: "none", fontFamily: "'DM Sans', sans-serif",
                       }} />
              </div>
            ))}
            <div>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase",
                             letterSpacing: "0.06em", marginBottom: 3 }}>Kategorie</div>
              <select value={form.kategorie || "sonstiges"}
                      onChange={e => set("kategorie", e.target.value)}
                      style={{
                        width: "100%", background: "var(--bg)", border: `1px solid var(--border2)`,
                        borderRadius: 8, color: "var(--text)", padding: "7px 10px",
                        fontSize: 13, outline: "none", fontFamily: "'DM Sans', sans-serif",
                      }}>
                {KATEGORIEN.map(k => (
                  <option key={k} value={k}>{KAT_ICONS[k]} {k}</option>
                ))}
              </select>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase",
                             letterSpacing: "0.06em", marginBottom: 3 }}>Mandant</div>
              <select value={form.mandant || ""} onChange={e => set("mandant", e.target.value)}
                style={{
                  width: "100%", background: "var(--bg)", border: `1px solid var(--border2)`,
                  borderRadius: 8, color: "var(--text)", padding: "7px 10px",
                  fontSize: 13, outline: "none", fontFamily: "'DM Sans', sans-serif",
                }}>
                <option value="">— Mandant —</option>
                {mandanten.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={handleSpeichern} loading={saving} variant="success" size="sm"
                 disabled={!gebucht && !form.mandant}>
              {gebucht ? "✓ Änderungen speichern" : "✓ Korrigiert bestätigen"}
            </Btn>
            <Btn onClick={() => { setEdit(false); setForm({ ...beleg }); }} variant="ghost" size="sm">
              Abbrechen
            </Btn>
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// STATISTIK-STRIP
// ═══════════════════════════════════════════════════════════

const ARCHIV_STATUS = new Set(["abgelehnt", "rejected", "declined", "verworfen"]);

/** Archiv / abgelehnt — Synonyme + Zeitstempel (wie Backend) */
function belegArchiviert(b) {
  if (b.abgelehnt_am) return true;
  const s = String(b.status ?? "").trim().toLowerCase();
  return ARCHIV_STATUS.has(s);
}

/** Vergleichbar mit core/beleg_service._beleg_workflow_status */
function belegWorkflowStatus(b) {
  const s = String(b.status ?? "").trim().toLowerCase();
  if (!s || ["neu", "entwurf", "draft"].includes(s)) return "vorschlag";
  return s;
}

/** Nur echte Workflow-States: offen, gebucht, manueller Entwurf */
function belegInPipeline(b) {
  return ["vorschlag", "bestaetigt", "manuell"].includes(belegWorkflowStatus(b));
}

function readBelegId(b) {
  return b?.beleg_id || b?.id || b?._id || "";
}

const StatistikStrip = ({ stats, belege = null }) => {
  if (!stats) return null;
  const liste = Array.isArray(belege) ? belege : null;
  const aktivListe = liste
    ? liste.filter((b) => !belegArchiviert(b) && belegInPipeline(b)).length
    : null;
  const archivListe = liste ? liste.filter(belegArchiviert).length : null;
  const aktiv = aktivListe != null ? aktivListe : (stats.gesamt_belege || 0);
  const abgelehnt = archivListe != null ? archivListe : (stats.abgelehnt || 0);
  const items = [
    { l: "Belege aktiv",     v: aktiv,                                          c: "var(--blue)" },
    ...(abgelehnt > 0
      ? [{ l: "Abgelehnt (Archiv)", v: abgelehnt, c: "var(--text3)" }]
      : []),
    { l: "Zur Prüfung",       v: stats.vorschlaege_offen || 0,                  c: "var(--orange)" },
    { l: "Gebucht",          v: stats.bestaetigt || 0,                         c: "var(--green)" },
    { l: "Ausgaben",         v: `€${(stats.total_ausgaben || 0).toLocaleString("de")}`, c: "var(--red)" },
    { l: "Vorsteuer",        v: `€${(stats.total_vorsteuer || 0).toLocaleString("de")}`,c: "var(--accent)" },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${items.length}, 1fr)`, gap: 12, marginBottom: 24 }}>
      {items.map((item, i) => (
        <div key={i} style={{
          background: "var(--bg2)", border: `1px solid var(--border)`,
          borderRadius: 12, padding: "14px 16px",
          animation: `fadeUp 0.4s ease ${i * 50}ms both`,
        }}>
          <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase",
                         letterSpacing: "0.08em", marginBottom: 5 }}>{item.l}</div>
          <div style={{ fontFamily: "'DM Serif Display', serif",
                         fontSize: 22, color: item.c }}>{item.v}</div>
        </div>
      ))}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function BelegScanner() {
  const [belege,      setBelege]      = useState([]);
  const [stats,       setStats]       = useState(null);
  const [mandanten,   setMandanten]   = useState([]);
  const [loading,     setLoading]     = useState(false);
  const [filter,      setFilter]      = useState("scannen"); // scannen | bestaetigt
  const [toast,       setToast]       = useState(null);
  const [selectedMandant, setSelectedMandant] = useState("");
  const [archivMode,  setArchivMode] = useState(false);
  const [archivListe, setArchivListe] = useState([]);

  const showToast = useCallback((text, type = "success") => {
    setToast({ text, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const ladeAlles = useCallback(async () => {
    try {
      const [b, s, m] = await Promise.allSettled([
        apiFetch(`/belege${selectedMandant ? `?mandant=${encodeURIComponent(selectedMandant)}` : ""}`),
        apiFetch(`/belege/statistiken${selectedMandant ? `?mandant=${encodeURIComponent(selectedMandant)}` : ""}`),
        apiFetch("/mandanten"),
      ]);
      if (b.status === "fulfilled") setBelege(b.value?.belege || []);
      if (s.status === "fulfilled") setStats(s.value);
      if (m.status === "fulfilled") {
        const raw = m.value?.data || [];
        setMandanten(Array.isArray(raw) ? raw.map(x => x.name) : Object.keys(raw));
      }
    } catch (e) { console.error(e); }
  }, [selectedMandant]);

  useEffect(() => { ladeAlles(); }, [ladeAlles]);

  const ladeArchiv = useCallback(async () => {
    try {
      const q = [`status=${encodeURIComponent("abgelehnt")}`];
      if (selectedMandant) q.push(`mandant=${encodeURIComponent(selectedMandant)}`);
      const r = await apiFetch(`/belege?${q.join("&")}`);
      setArchivListe(Array.isArray(r.belege) ? r.belege : []);
    } catch (e) {
      console.error(e);
      setArchivListe([]);
      showToast(e.message || "Archiv konnte nicht geladen werden", "error");
    }
  }, [selectedMandant, showToast]);

  useEffect(() => {
    if (archivMode) ladeArchiv();
  }, [archivMode, ladeArchiv]);

  const handleRestoreArchiv = async (bid) => {
    try {
      await apiFetch(`/belege/${encodeURIComponent(bid)}/wiederherstellen`, { method: "POST" });
      showToast("Beleg wiederhergestellt");
      await Promise.all([ladeArchiv(), ladeAlles()]);
    } catch (e) { showToast(e.message, "error"); }
  };

  const handleDeleteArchiv = async (bid) => {
    if (!window.confirm("Archiv-Eintrag endgültig löschen?")) return;
    try {
      await apiFetch(`/belege/${encodeURIComponent(bid)}`, { method: "DELETE" });
      showToast("Gelöscht", "warn");
      await Promise.all([ladeArchiv(), ladeAlles()]);
    } catch (e) { showToast(e.message, "error"); }
  };

  const handleArchivAllesLoeschen = async () => {
    if (!window.confirm("Alle abgelehnten Belege im Archiv wirklich endgültig löschen?")) return;
    try {
      const q = selectedMandant ? `?mandant=${encodeURIComponent(selectedMandant)}` : "";
      await apiFetch(`/belege/archiv/leeren${q}`, { method: "POST" });
      showToast("Archiv geleert", "warn");
      await Promise.all([ladeArchiv(), ladeAlles()]);
    } catch (e) { showToast(e.message, "error"); }
  };

  // ── Belege hochladen & analysieren ────────────────────────
  const handleDateien = async (files) => {
    setLoading(true);
    const neueBelege = [];

    for (const datei of files) {
      try {
        const b64 = await new Promise((res, rej) => {
          const reader = new FileReader();
          reader.onload  = () => res(reader.result.split(",")[1]);
          reader.onerror = () => rej(new Error("Lesen fehlgeschlagen"));
          reader.readAsDataURL(datei);
        });

        const result = await apiFetch("/belege/analysieren", {
          method: "POST",
          body: JSON.stringify({
            dateiname:  datei.name,
            inhalt_b64: b64,
            mandant:    selectedMandant || "",
          }),
        });

        neueBelege.push(result);
        showToast(`✓ ${datei.name} analysiert`);

      } catch (e) {
        showToast(`Fehler bei ${datei.name}: ${e.message}`, "error");
      }
    }

    setLoading(false);
    if (neueBelege.length > 0) {
      setBelege(prev => [...neueBelege, ...prev]);
      setFilter("scannen");
      await ladeAlles();
    }
  };

  // ── Bestätigen ─────────────────────────────────────────────
  const handleBestaetigen = async (bid, korrekturen = null) => {
    const id = String(bid || "").trim();
    if (!id) {
      showToast("Beleg-ID fehlt — bitte Seite neu laden", "error");
      return;
    }
    const existing = belege.find((b) => readBelegId(b) === id);
    const warGebucht = existing && belegWorkflowStatus(existing) === "bestaetigt";
    const payload = korrekturen && typeof korrekturen === "object" ? { ...korrekturen } : {};
    if (!payload.mandant && existing?.mandant) payload.mandant = existing.mandant;
    try {
      const updated = await apiFetch(`/belege/${encodeURIComponent(id)}/bestaetigen`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setBelege((prev) =>
        prev.map((b) => (readBelegId(b) === id ? { ...b, ...updated } : b))
      );
      if (warGebucht) {
        showToast("✓ Änderungen gespeichert");
      } else {
        showToast(`✓ Gebucht für „${updated.mandant || payload.mandant}“ — jetzt unter Tab „Gebucht“ sichtbar`);
        setFilter("bestaetigt");
      }
      ladeAlles().catch((e) => console.error(e));
    } catch (e) {
      showToast(`Speichern fehlgeschlagen: ${e.message}`, "error");
      throw e;
    }
  };

  const handleLoeschenGebucht = async (bid) => {
    const id = String(bid || "").trim();
    if (!id) return;
    if (
      !window.confirm(
        "Beleg ins Archiv verschieben?\n\nEr verschwindet unter „Gebucht“. Im Archiv können Sie ihn wiederherstellen oder endgültig löschen."
      )
    ) {
      return;
    }
    try {
      await apiFetch(`/belege/${encodeURIComponent(id)}/ablehnen`, { method: "POST" });
      setBelege((prev) => prev.filter((b) => readBelegId(b) !== id));
      showToast("Beleg ins Archiv verschoben — unter „Archiv“ verwalten", "warn");
      await Promise.all([ladeArchiv(), ladeAlles()]);
    } catch (e) {
      showToast(`Archivieren fehlgeschlagen: ${e.message}`, "error");
    }
  };

  // ── Ablehnen ───────────────────────────────────────────────
  const handleAblehnen = async (bid) => {
    if (!window.confirm("Buchungsvorschlag ablehnen?")) return;
    const id = String(bid || "").trim();
    if (!id) {
      showToast("Beleg-ID fehlt — bitte Seite neu laden", "error");
      return;
    }
    try {
      await apiFetch(`/belege/${encodeURIComponent(id)}/ablehnen`, { method: "POST" });
      setBelege((prev) => prev.filter((b) => readBelegId(b) !== id));
      showToast("Ins Archiv verschoben — unter „Archiv“ verwalten", "warn");
      await Promise.all([ladeArchiv(), ladeAlles()]);
    } catch (e) {
      showToast(`Ablehnen fehlgeschlagen: ${e.message}`, "error");
    }
  };

  const offeneBelege = belege.filter(
    (b) => !belegArchiviert(b) && ["vorschlag", "manuell"].includes(belegWorkflowStatus(b))
  );
  const gebuchteBelege = belege.filter(
    (b) => !belegArchiviert(b) && belegWorkflowStatus(b) === "bestaetigt"
  );
  const gefiltert = filter === "bestaetigt" ? gebuchteBelege : offeneBelege;

  return (
    <div style={{
      flex: 1, background: "var(--bg)", overflowY: "auto",
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes fadeUp  { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @keyframes slideIn { from { transform:translateX(100%); opacity:0; } to { transform:translateX(0); opacity:1; } }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }
      `}</style>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          background: "var(--bg3)", borderRadius: 12, padding: "12px 18px",
          color: "var(--text)", fontSize: 13, fontWeight: 500,
          border: `1px solid ${toast.type === "error" ? "var(--red)" : "var(--green)"}44`,
          borderLeft: `3px solid ${toast.type === "error" ? "var(--red)" : "var(--green)"}`,
          animation: "slideIn 0.25s ease",
        }}>{toast.text}</div>
      )}

      {/* Header */}
      <div style={{
        background: "var(--bg2)", borderBottom: `1px solid var(--border)`,
        padding: "20px 32px", display: "flex", alignItems: "center",
        gap: 16, position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 22,
                         color: "var(--text)" }}>
            Belegscanner
          </div>
          <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>
            KI erkennt Beträge, Kategorien und Buchungskonten automatisch
          </div>
        </div>

        <select value={selectedMandant} onChange={e => setSelectedMandant(e.target.value)}
          style={{
            background: "var(--bg3)", border: `1px solid var(--border2)`,
            borderRadius: 10, color: selectedMandant ? "var(--accent)" : "var(--text3)",
            padding: "7px 12px", fontSize: 13, fontFamily: "'DM Sans', sans-serif",
            outline: "none",
          }}>
          <option value="">Alle Mandanten</option>
          {mandanten.map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <Btn
            size="sm"
            variant={archivMode ? "subtle" : "ghost"}
            onClick={() => setArchivMode((v) => !v)}
          >
            {archivMode ? "← Scanner" : "Archiv"}
          </Btn>
          {!archivMode && [
            { id: "scannen", label: `Scannen (${offeneBelege.length})` },
            { id: "bestaetigt", label: `Gebucht (${gebuchteBelege.length})` },
          ].map((t) => (
            <Btn key={t.id} size="sm" variant={filter === t.id ? "subtle" : "ghost"}
                 onClick={() => setFilter(t.id)}>
              {t.label}
            </Btn>
          ))}
        </div>
      </div>

      <div style={{ padding: "28px 32px" }}>
        {!archivMode && (<>
        <StatistikStrip stats={stats} belege={belege} />

        {filter === "scannen" && (
          <>
            <UploadZone onDatei={handleDateien} loading={loading} />
            {offeneBelege.length > 0 && (
              <div style={{
                marginTop: 16, fontSize: 13, color: "var(--text2)", lineHeight: 1.5,
                padding: "10px 14px", borderRadius: 10,
                background: "color-mix(in srgb, var(--accent) 8%, var(--bg3))",
                border: "1px solid color-mix(in srgb, var(--accent) 22%, transparent)",
              }}>
                Nach dem Scan: unten <strong>Mandant wählen</strong>, dann{" "}
                <strong>Buchung bestätigen</strong>, <strong>korrigieren</strong> oder <strong>ablehnen</strong>.
                Bestätigte Belege erscheinen nur unter <strong>Gebucht</strong>.
              </div>
            )}
          </>
        )}

        {gefiltert.length > 0 && (
          <div style={{ marginTop: filter === "scannen" ? 20 : 0 }}>
            <div style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "center", marginBottom: 14,
            }}>
              <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 18, color: "var(--text)" }}>
                {filter === "bestaetigt"
                  ? `${gefiltert.length} gebuchte${gefiltert.length !== 1 ? "" : "r"} Beleg${gefiltert.length !== 1 ? "e" : ""}`
                  : `${gefiltert.length} gescannte${gefiltert.length !== 1 ? "" : "r"} Beleg${gefiltert.length !== 1 ? "e" : ""} zur Prüfung`}
              </div>
              {filter === "scannen" && gefiltert.length > 1 && selectedMandant && (
                <Btn variant="success" size="sm"
                     onClick={async () => {
                       if (!window.confirm(`Alle ${gefiltert.length} Vorschläge für „${selectedMandant}“ bestätigen?`)) return;
                       for (const b of gefiltert) {
                         const bid = readBelegId(b);
                         if (!bid) continue;
                         await handleBestaetigen(bid, { mandant: selectedMandant });
                       }
                     }}>
                  ✓ Alle bestätigen
                </Btn>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {gefiltert.map((beleg, idx) => (
                <BuchungsKarte
                  key={readBelegId(beleg) || `${beleg.dateiname || "beleg"}-${idx}`}
                  beleg={beleg}
                  mandanten={mandanten}
                  gebucht={filter === "bestaetigt"}
                  defaultMandant={selectedMandant}
                  onBestaetigen={handleBestaetigen}
                  onAblehnen={handleAblehnen}
                  onLoeschen={filter === "bestaetigt" ? handleLoeschenGebucht : undefined}
                />
              ))}
            </div>
          </div>
        )}

        {gefiltert.length === 0 && !loading && (
          <div style={{
            textAlign: "center", padding: "48px 0",
            color: "var(--text3)", fontSize: 14, marginTop: 24,
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>{filter === "bestaetigt" ? "✓" : "📄"}</div>
            {filter === "bestaetigt"
              ? "Noch keine gebuchten Belege. Bestätigen Sie Vorschläge unter „Scannen“."
              : belege.length === 0
                ? <>Noch keine Belege verarbeitet.<br />Lade deinen ersten Beleg hoch — die KI erledigt den Rest.</>
                : "Keine offenen Vorschläge — alle Belege sind gebucht oder archiviert."}
          </div>
        )}
        </>)}

        {archivMode && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              flexWrap: "wrap", gap: 12, marginBottom: 16,
            }}>
              <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 18, color: "var(--text)" }}>
                Archiv ({archivListe.length})
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Btn size="sm" variant="danger" disabled={archivListe.length === 0}
                     onClick={handleArchivAllesLoeschen}>
                  Alle löschen
                </Btn>
                <Btn size="sm" variant="ghost" onClick={() => ladeArchiv()}>⟳ Aktualisieren</Btn>
              </div>
            </div>

            <div style={{ fontSize: 12, color: "var(--text3)", marginBottom: 14, lineHeight: 1.5 }}>
              Abgelehnte oder aus „Gebucht“ entfernte Belege. Hier können Sie sie{" "}
              <strong>wiederherstellen</strong> oder <strong>endgültig löschen</strong>.
            </div>

            {archivListe.length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text3)", fontSize: 14 }}>
                Keine archivierten Belege.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {archivListe.map((b, idx) => {
                  const bid = readBelegId(b);
                  return (
                  <div key={bid || `archiv-${idx}`} style={{
                    background: "var(--bg2)", border: `1px solid var(--border)`,
                    borderRadius: 12, padding: "12px 16px",
                    display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
                  }}>
                    <div style={{ fontSize: 22 }}>{KAT_ICONS[b.kategorie] || "📄"}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{b.dateiname}</div>
                      <div style={{ fontSize: 12, color: "var(--text3)" }}>
                        {b.lieferant || "—"} · €{Number(b.betrag_brutto || 0).toFixed(2)}
                        {b.abgelehnt_am && <> · Archiv seit {String(b.abgelehnt_am).slice(0, 10)}</>}
                      </div>
                    </div>
                    <Btn size="xs" variant="success" disabled={!bid} onClick={() => bid && handleRestoreArchiv(bid)}>Wiederherstellen</Btn>
                    <Btn size="xs" variant="ghost" disabled={!bid} onClick={() => bid && handleDeleteArchiv(bid)}>Löschen</Btn>
                  </div>
                )})}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}