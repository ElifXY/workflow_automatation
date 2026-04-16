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

const C = {
  red: "#e05555", orange: "#e08c45", green: "#5cb87a",
  blue: "#5b8de8", accent: "#c8a96e", purple: "#9b72e8",
  text: "#e8eaf0", text2: "#8b91a0", text3: "#555d6e",
  bg: "#0b0d11", bg2: "#111419", bg3: "#181c24",
  border: "rgba(255,255,255,0.07)", border2: "rgba(255,255,255,0.14)",
};

const BASE = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

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
    primary: { background: C.accent, color: "#1a1200", border: "none" },
    ghost:   { background: "transparent", color: C.text2, border: `1px solid ${C.border2}` },
    subtle:  { background: C.bg3, color: C.text2, border: `1px solid ${C.border}` },
    success: { background: C.green + "20", color: C.green, border: `1px solid ${C.green}30` },
    danger:  { background: C.red + "18", color: C.red, border: `1px solid ${C.red}30` },
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

const Badge = ({ children, color = C.accent }) => (
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
        border: `2px dashed ${dragging ? C.accent : C.border2}`,
        borderRadius: 16, padding: "48px 32px",
        textAlign: "center", cursor: loading ? "not-allowed" : "pointer",
        background: dragging ? C.accent + "08" : C.bg3,
        transition: "all 0.2s",
      }}>
      <input ref={inputRef} type="file" multiple
             accept=".jpg,.jpeg,.png,.pdf,.webp"
             onChange={handleChange} style={{ display: "none" }} />

      {loading ? (
        <div>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🤖</div>
          <div style={{ fontWeight: 600, color: C.accent, fontSize: 16, marginBottom: 6 }}>
            KI analysiert Belege...
          </div>
          <div style={{ color: C.text3, fontSize: 13 }}>
            Erkennt Beträge, Kategorien und Buchungskonten automatisch
          </div>
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 48, marginBottom: 14 }}>📎</div>
          <div style={{ fontWeight: 600, color: C.text, fontSize: 18, marginBottom: 6 }}>
            Belege hier ablegen
          </div>
          <div style={{ color: C.text3, fontSize: 13, marginBottom: 16 }}>
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

const BuchungsKarte = ({ beleg, mandanten, onBestaetigen, onAblehnen, onKorrigieren }) => {
  const [edit, setEdit]     = useState(false);
  const [form, setForm]     = useState({ ...beleg });
  const [saving, setSaving] = useState(false);

  const score       = beleg.vertrauens_score || 0;
  const scoreColor  = score >= 0.8 ? C.green : score >= 0.6 ? C.orange : C.red;
  const scoreLabel  = score >= 0.8 ? "Sicher" : score >= 0.6 ? "Prüfen" : "Unsicher";

  const handleBestaetigen = async () => {
    setSaving(true);
    try {
      await onBestaetigen(beleg.beleg_id, edit ? form : null);
    } finally { setSaving(false); }
  };

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));

  return (
    <div style={{
      background: C.bg2, border: `1px solid ${C.border}`,
      borderRadius: 14, overflow: "hidden",
      animation: "fadeUp 0.35s ease both",
    }}>
      {/* Header */}
      <div style={{
        padding: "14px 18px", background: C.bg3,
        borderBottom: `1px solid ${C.border}`,
        display: "flex", alignItems: "center", gap: 12,
      }}>
        <div style={{ fontSize: 24 }}>
          {KAT_ICONS[beleg.kategorie] || "📄"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, color: C.text, fontSize: 14,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {beleg.dateiname}
          </div>
          <div style={{ fontSize: 12, color: C.text3, marginTop: 2 }}>
            {beleg.lieferant || "Unbekannter Lieferant"} · {beleg.datum}
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: C.accent }}>
            €{Number(beleg.betrag_brutto || 0).toFixed(2)}
          </div>
          <Badge color={scoreColor}>{scoreLabel} {Math.round(score * 100)}%</Badge>
        </div>
      </div>

      {/* Buchungs-Details */}
      {!edit ? (
        <div style={{ padding: "14px 18px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
            {[
              { l: "Kategorie",  v: beleg.kategorie_name || beleg.kategorie },
              { l: "SKR03 Soll", v: beleg.skr03_soll || "—" },
              { l: "SKR03 Haben",v: beleg.skr03_haben || "—" },
              { l: "Netto",      v: `€${Number(beleg.betrag_netto || 0).toFixed(2)}` },
              { l: `MwSt ${beleg.mwst_satz || 19}%`, v: `€${Number(beleg.mwst_betrag || 0).toFixed(2)}` },
              { l: "Vorsteuer",  v: beleg.vorsteuer_abzugsfaehig ? "✓ Abzugsfähig" : "✗ Nicht abzugsfähig",
                                  c: beleg.vorsteuer_abzugsfaehig ? C.green : C.orange },
            ].map(item => (
              <div key={item.l} style={{
                background: C.bg3, borderRadius: 8, padding: "8px 12px",
              }}>
                <div style={{ fontSize: 10, color: C.text3, textTransform: "uppercase",
                               letterSpacing: "0.06em", marginBottom: 3 }}>
                  {item.l}
                </div>
                <div style={{ fontSize: 13, fontWeight: 500,
                               color: item.c || C.text }}>
                  {item.v}
                </div>
              </div>
            ))}
          </div>

          {beleg.buchungstext && (
            <div style={{ fontSize: 12, color: C.text3, marginBottom: 8 }}>
              Buchungstext: <span style={{ color: C.text2 }}>{beleg.buchungstext}</span>
            </div>
          )}

          {beleg.rechnungsnummer && (
            <div style={{ fontSize: 12, color: C.text3, marginBottom: 8 }}>
              Rechnungsnr.: <span style={{ color: C.text2 }}>{beleg.rechnungsnummer}</span>
            </div>
          )}

          {beleg.notiz && (
            <div style={{
              background: C.orange + "12", border: `1px solid ${C.orange}25`,
              borderRadius: 8, padding: "8px 12px", marginBottom: 12,
              fontSize: 12, color: C.orange,
            }}>
              ⚠ {beleg.notiz}
            </div>
          )}

          {/* Mandant zuordnen */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: C.text3, marginBottom: 4 }}>Mandant</div>
            <select
              value={form.mandant || ""}
              onChange={e => setForm(p => ({ ...p, mandant: e.target.value }))}
              style={{
                background: C.bg, border: `1px solid ${C.border2}`,
                borderRadius: 8, color: form.mandant ? C.text : C.text3,
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

          {/* Aktionen */}
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={handleBestaetigen} loading={saving} variant="success" size="sm"
                 disabled={!form.mandant}>
              ✓ Buchung bestätigen
            </Btn>
            <Btn onClick={() => setEdit(true)} variant="ghost" size="sm">
              ✏ Korrigieren
            </Btn>
            <Btn onClick={() => onAblehnen(beleg.beleg_id)} variant="danger" size="sm">
              ✕
            </Btn>
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
              { k: "datum",          l: "Datum",       type: "date" },
              { k: "lieferant",      l: "Lieferant",   type: "text" },
              { k: "rechnungsnummer",l: "Rechnungsnr.",type: "text" },
              { k: "skr03_soll",     l: "SKR03 Soll",  type: "text" },
              { k: "skr03_haben",    l: "SKR03 Haben", type: "text" },
              { k: "buchungstext",   l: "Buchungstext",type: "text" },
            ].map(f => (
              <div key={f.k}>
                <div style={{ fontSize: 10, color: C.text3, textTransform: "uppercase",
                               letterSpacing: "0.06em", marginBottom: 3 }}>{f.l}</div>
                <input type={f.type} value={form[f.k] || ""}
                       onChange={e => set(f.k, f.type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)}
                       style={{
                         width: "100%", background: C.bg, border: `1px solid ${C.border2}`,
                         borderRadius: 8, color: C.text, padding: "7px 10px",
                         fontSize: 13, outline: "none", fontFamily: "'DM Sans', sans-serif",
                       }} />
              </div>
            ))}
            <div>
              <div style={{ fontSize: 10, color: C.text3, textTransform: "uppercase",
                             letterSpacing: "0.06em", marginBottom: 3 }}>Kategorie</div>
              <select value={form.kategorie || "sonstiges"}
                      onChange={e => set("kategorie", e.target.value)}
                      style={{
                        width: "100%", background: C.bg, border: `1px solid ${C.border2}`,
                        borderRadius: 8, color: C.text, padding: "7px 10px",
                        fontSize: 13, outline: "none", fontFamily: "'DM Sans', sans-serif",
                      }}>
                {KATEGORIEN.map(k => (
                  <option key={k} value={k}>{KAT_ICONS[k]} {k}</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Btn onClick={handleBestaetigen} loading={saving} variant="success" size="sm">
              ✓ Korrigiert bestätigen
            </Btn>
            <Btn onClick={() => setEdit(false)} variant="ghost" size="sm">Abbrechen</Btn>
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// STATISTIK-STRIP
// ═══════════════════════════════════════════════════════════

const StatistikStrip = ({ stats }) => {
  if (!stats) return null;
  const items = [
    { l: "Belege gesamt",    v: stats.gesamt_belege || 0,                     c: C.blue },
    { l: "Offen",            v: stats.vorschlaege_offen || 0,                  c: C.orange },
    { l: "Bestätigt",        v: stats.bestaetigt || 0,                         c: C.green },
    { l: "Ausgaben",         v: `€${(stats.total_ausgaben || 0).toLocaleString("de")}`, c: C.red },
    { l: "Vorsteuer",        v: `€${(stats.total_vorsteuer || 0).toLocaleString("de")}`,c: C.accent },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${items.length}, 1fr)`, gap: 12, marginBottom: 24 }}>
      {items.map((item, i) => (
        <div key={i} style={{
          background: C.bg2, border: `1px solid ${C.border}`,
          borderRadius: 12, padding: "14px 16px",
          animation: `fadeUp 0.4s ease ${i * 50}ms both`,
        }}>
          <div style={{ fontSize: 10, color: C.text3, textTransform: "uppercase",
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
  const [filter,      setFilter]      = useState("alle"); // alle | vorschlag | bestaetigt
  const [toast,       setToast]       = useState(null);
  const [selectedMandant, setSelectedMandant] = useState("");

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
      await ladeAlles();
    }
  };

  // ── Bestätigen ─────────────────────────────────────────────
  const handleBestaetigen = async (belegId, korrekturen = null) => {
    await apiFetch(`/belege/${belegId}/bestaetigen`, {
      method: "POST",
      body: JSON.stringify(korrekturen || {}),
    });
    showToast("✓ Buchung bestätigt und gebucht");
    await ladeAlles();
    setBelege(prev => prev.filter(b => b.beleg_id !== belegId || korrekturen));
  };

  // ── Ablehnen ───────────────────────────────────────────────
  const handleAblehnen = async (belegId) => {
    if (!window.confirm("Buchungsvorschlag ablehnen?")) return;
    await apiFetch(`/belege/${belegId}/ablehnen`, { method: "POST" }).catch(() => {});
    setBelege(prev => prev.filter(b => b.beleg_id !== belegId));
    showToast("Vorschlag abgelehnt", "warn");
  };

  const gefiltert = belege.filter(b =>
    filter === "alle" ? true :
    filter === "vorschlag" ? b.status === "vorschlag" :
    b.status === "bestaetigt"
  );

  return (
    <div style={{
      flex: 1, background: C.bg, overflowY: "auto",
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes fadeUp  { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @keyframes slideIn { from { transform:translateX(100%); opacity:0; } to { transform:translateX(0); opacity:1; } }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
      `}</style>

      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          background: C.bg3, borderRadius: 12, padding: "12px 18px",
          color: C.text, fontSize: 13, fontWeight: 500,
          border: `1px solid ${toast.type === "error" ? C.red : C.green}44`,
          borderLeft: `3px solid ${toast.type === "error" ? C.red : C.green}`,
          animation: "slideIn 0.25s ease",
        }}>{toast.text}</div>
      )}

      {/* Header */}
      <div style={{
        background: C.bg2, borderBottom: `1px solid ${C.border}`,
        padding: "20px 32px", display: "flex", alignItems: "center",
        gap: 16, position: "sticky", top: 0, zIndex: 10,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 22,
                         color: C.text }}>
            Belegscanner
          </div>
          <div style={{ fontSize: 12, color: C.text3, marginTop: 2 }}>
            KI erkennt Beträge, Kategorien und Buchungskonten automatisch
          </div>
        </div>

        <select value={selectedMandant} onChange={e => setSelectedMandant(e.target.value)}
          style={{
            background: C.bg3, border: `1px solid ${C.border2}`,
            borderRadius: 10, color: selectedMandant ? C.accent : C.text3,
            padding: "7px 12px", fontSize: 13, fontFamily: "'DM Sans', sans-serif",
            outline: "none",
          }}>
          <option value="">Alle Mandanten</option>
          {mandanten.map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        <div style={{ display: "flex", gap: 6 }}>
          {["alle", "vorschlag", "bestaetigt"].map(f => (
            <Btn key={f} size="sm" variant={filter === f ? "subtle" : "ghost"}
                 onClick={() => setFilter(f)}
                 style={{ textTransform: "capitalize" }}>
              {f === "alle" ? "Alle" : f === "vorschlag" ? `Offen (${belege.filter(b => b.status === "vorschlag").length})` : "Gebucht"}
            </Btn>
          ))}
        </div>
      </div>

      <div style={{ padding: "28px 32px" }}>
        <StatistikStrip stats={stats} />

        <UploadZone onDatei={handleDateien} loading={loading} />

        {gefiltert.length > 0 && (
          <div style={{ marginTop: 24 }}>
            <div style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "center", marginBottom: 14,
            }}>
              <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: 18, color: C.text }}>
                {filter === "vorschlag"
                  ? `${gefiltert.length} Buchungsvorschlag${gefiltert.length !== 1 ? "e" : ""} zur Prüfung`
                  : `${gefiltert.length} Belege`}
              </div>
              {filter === "vorschlag" && gefiltert.length > 1 && (
                <Btn variant="success" size="sm"
                     onClick={async () => {
                       if (!window.confirm(`Alle ${gefiltert.length} Vorschläge bestätigen?`)) return;
                       for (const b of gefiltert.filter(b => b.mandant)) {
                         await handleBestaetigen(b.beleg_id);
                       }
                     }}>
                  ✓ Alle bestätigen
                </Btn>
              )}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {gefiltert.map(beleg => (
                <BuchungsKarte
                  key={beleg.beleg_id}
                  beleg={beleg}
                  mandanten={mandanten}
                  onBestaetigen={handleBestaetigen}
                  onAblehnen={handleAblehnen}
                  onKorrigieren={() => {}}
                />
              ))}
            </div>
          </div>
        )}

        {gefiltert.length === 0 && !loading && belege.length === 0 && (
          <div style={{
            textAlign: "center", padding: "48px 0",
            color: C.text3, fontSize: 14, marginTop: 24,
          }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
            Noch keine Belege verarbeitet.<br />
            Lade deinen ersten Beleg hoch — die KI erledigt den Rest.
          </div>
        )}
      </div>
    </div>
  );
}