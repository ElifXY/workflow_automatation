// ============================================================
// KANZLEI AI — KI-ASSISTENT v1.0
// Datei: src/pages/KIAssistent.js
//
// Das KILLER-FEATURE: Echter KI-Chat mit vollem Mandantenkontext
// Steuerberater fragt: "Was ist die beste Strategie für Müller?"
// KI antwortet mit echten Daten aus dem System
//
// Powered by: OpenAI GPT-4o mini
// Kontext: Mandantendaten, Aufgaben, Fristen, Scores live injiziert
// ============================================================

import { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { getMandanten, getKpis, getHeute, getEmpfehlungen } from "../api";

// FIX: BASE_URL für Backend-Proxy (CORS-Problem gelöst)
const BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";


const C = {
  red: "#e05555", orange: "#e08c45", green: "#5cb87a",
  blue: "#5b8de8", accent: "#c8a96e", purple: "#9b72e8",
  text: "#e8eaf0", text2: "#8b91a0", text3: "#555d6e",
  bg: "#0b0d11", bg2: "#111419", bg3: "#181c24",
  border: "rgba(255,255,255,0.07)", border2: "rgba(255,255,255,0.13)",
};

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');`;

// ─── Vorgefertigte Prompts ────────────────────────────────────
const QUICK_PROMPTS = [
  { icon: "⚡", text: "Welche Mandanten brauchen heute sofortige Aufmerksamkeit?" },
  { icon: "💰", text: "Wie kann ich den Umsatz pro Mandant steigern? Analysiere meine Top-Mandanten." },
  { icon: "📊", text: "Erstelle mir eine Zusammenfassung der kritischsten Fristen dieser Woche." },
  { icon: "🧾", text: "Welche Mandanten haben die größten Steuerspar-Potenziale? Analysiere ihre Daten." },
  { icon: "📧", text: "Welche Mandanten sollte ich heute kontaktieren und warum?" },
  { icon: "⚖",  text: "Erkläre mir die aktuellen Compliance-Risiken in meiner Kanzlei." },
  { icon: "📈", text: "Wie entwickelt sich mein Kanzlei-Umsatz? Was sind Optimierungsmöglichkeiten?" },
  { icon: "🔍", text: "Finde alle Mandanten mit überfälligen Aufgaben und priorisiere sie." },
];

// ─── System-Prompt Generator ─────────────────────────────────
function erstelleSystemPrompt(kontext) {
  const { mandanten, kpis, heute, empfehlungen } = kontext;

  const mandantenList = Object.entries(mandanten || {}).slice(0, 30).map(([name, m]) => {
    const kpi = (kpis || []).find(k => k.mandant === name) || {};
    return `- ${name}: Umsatz €${m.umsatz || 0}, Status: ${kpi.status || "?"}, Score: ${Math.round(kpi.score || 0)}, Tage ohne Antwort: ${kpi.tage_ohne_antwort || 0}, Überfällige Aufgaben: ${kpi.aufgaben_ueberfaellig || 0}`;
  }).join("\n");

  const heuteList = (heute || []).slice(0, 10).map(h =>
    `- ${h.text} (${h.label})`
  ).join("\n");

  const kritischCount = (kpis || []).filter(k => k.status === "KRITISCH").length;
  const wichtigCount  = (kpis || []).filter(k => k.status === "WICHTIG").length;
  const totalUmsatz   = Object.values(mandanten || {}).reduce((s, m) => s + (m.umsatz || 0), 0);

  return `Du bist der KI-Assistent von Kanzlei AI — ein hochspezialisierter Steuerberater-Assistent.
Du hast Zugriff auf alle aktuellen Kanzlei-Daten und hilfst dem Steuerberater bei:
- Mandanten-Analyse und Priorisierung
- Steueroptimierung und Beratung
- Fristen- und Compliance-Management
- Geschäftsstrategie und Effizienzsteigerung

AKTUELLE KANZLEI-DATEN (Stand: ${new Date().toLocaleString("de-DE")}):

ÜBERSICHT:
- Mandanten gesamt: ${Object.keys(mandanten || {}).length}
- Gesamtumsatz: €${totalUmsatz.toLocaleString("de-DE")}
- Kritische Mandanten: ${kritischCount}
- Wichtige Mandanten: ${wichtigCount}

MANDANTEN:
${mandantenList || "Keine Mandanten geladen"}

HEUTE DRINGEND:
${heuteList || "Keine dringenden Punkte"}

VERHALTEN:
- Antworte präzise, professionell und auf Deutsch
- Nutze die echten Mandantennamen aus den Daten
- Gib konkrete, umsetzbare Empfehlungen
- Bei Steuerfragen: Weise auf Einzelfallprüfung hin
- Formatiere Antworten mit Markdown (**fett**, Listen, etc.)
- Du kennst den deutschen Steuerkontext (EStG, UStG, AO, GewStG)
- Sei direkt und spar dir Einleitungsfloskeln`;
}

// ─── Markdown Renderer (minimal, kein externes Package) ──────
function renderMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, `<code style="background:${C.bg3};padding:2px 6px;border-radius:4px;font-family:'DM Mono',monospace;font-size:12px;color:${C.accent}">$1</code>`)
    .replace(/^### (.+)$/gm, `<div style="font-size:14px;font-weight:600;color:${C.text};margin:12px 0 6px">$1</div>`)
    .replace(/^## (.+)$/gm,  `<div style="font-size:16px;font-weight:700;color:${C.accent};margin:14px 0 8px;font-family:'DM Serif Display',serif">$1</div>`)
    .replace(/^# (.+)$/gm,   `<div style="font-size:18px;font-weight:700;color:${C.accent};margin:16px 0 10px;font-family:'DM Serif Display',serif">$1</div>`)
    .replace(/^- (.+)$/gm,   `<div style="display:flex;gap:8px;margin:3px 0"><span style="color:${C.accent};flex-shrink:0">·</span><span>$1</span></div>`)
    .replace(/^\d+\. (.+)$/gm,(match, p1, offset, str) => {
      const num = str.slice(0, offset).match(/^\d+\. /gm)?.length + 1 || 1;
      return `<div style="display:flex;gap:8px;margin:3px 0"><span style="color:${C.text3};flex-shrink:0;min-width:16px">${num}.</span><span>${p1}</span></div>`;
    })
    .replace(/\n\n/g, '<div style="height:8px"></div>')
    .replace(/\n/g,   "");
}

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function KIAssistent() {
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [kontext,     setKontext]     = useState({});
  const [kontextLaden,setKontextLaden]= useState(true);
  const [selectedMandant, setSelectedMandant] = useState("");
  const [streaming,   setStreaming]   = useState(false);

  const messagesEndRef = useRef(null);
  const inputRef       = useRef(null);
  const abortRef       = useRef(null);

  // ── Kontext laden ─────────────────────────────────────────
  useEffect(() => {
    Promise.allSettled([
      getMandanten(),
      getKpis(),
      getHeute(),
      getEmpfehlungen(),
    ]).then(([m, k, h, e]) => {
      const mandantenRaw = m.status === "fulfilled" ? m.value : {};
      // API gibt { data: [...] } oder { data: {...} }
      let mandantenDict = {};
      if (mandantenRaw?.data) {
        if (Array.isArray(mandantenRaw.data)) {
          mandantenRaw.data.forEach(man => { mandantenDict[man.name] = man; });
        } else {
          mandantenDict = mandantenRaw.data;
        }
      }

      setKontext({
        mandanten:     mandantenDict,
        kpis:          k.status === "fulfilled" ? (k.value || []) : [],
        heute:         h.status === "fulfilled" ? (h.value || []) : [],
        empfehlungen:  e.status === "fulfilled" ? (e.value || []) : [],
      });
      setKontextLaden(false);
    });
  }, []);

  // ── Auto-Scroll ───────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Nachricht senden ──────────────────────────────────────
  const sendeNachricht = useCallback(async (promptText) => {
    const text = promptText || input.trim();
    if (!text || loading) return;

    setInput("");
    setLoading(true);
    setStreaming(true);

    // Mandanten-Kontext zu Frage hinzufügen wenn ausgewählt
    const augmentedText = selectedMandant
      ? `[Kontext: Mandant "${selectedMandant}"] ${text}`
      : text;

    const newMessages = [
      ...messages,
      { role: "user", content: augmentedText, display: text },
    ];
    setMessages(newMessages);

    // Platzhalter für Streaming-Antwort
    setMessages(prev => [...prev, {
      role: "assistant", content: "", streaming: true
    }]);

    try {
      const systemPrompt = erstelleSystemPrompt(kontext);

      // Konversations-History für Backend (max. 20 Nachrichten)
      const history = newMessages.slice(-20).map(m => ({
        role:    m.role,
        content: m.content,
      }));

      // Backend-Proxy statt direkter OpenAI-Call (CORS-Problem behoben)
      const token = localStorage.getItem("kanzlei_token");
      const response = await fetch(`${BASE_URL}/ki/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        signal: (abortRef.current = new AbortController()).signal,
        body: JSON.stringify({
          messages:  history,
          system:    systemPrompt,
          max_tokens: 1500,
          mandant:   selectedMandant || null,
        }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        const msg = err?.detail || err?.error?.message || `API Fehler ${response.status}`;
        // Hilfreiche Fehlermeldung wenn API-Key fehlt
        if (response.status === 500 && msg.includes("OPENAI_API_KEY")) {
          throw new Error("OPENAI_API_KEY fehlt in .env — Bitte in der .env Datei eintragen und Server neu starten.");
        }
        throw new Error(msg);
      }

      const data    = await response.json();

      // OpenAI gibt content direkt als String zurück (nicht als Array)
      const content = data.content || "Keine Antwort erhalten.";

      // Streaming-Platzhalter ersetzen
      setMessages(prev => [
        ...prev.slice(0, -1),
        { role: "assistant", content, streaming: false }
      ]);

    } catch (err) {
      if (err.name === "AbortError") {
        setMessages(prev => prev.slice(0, -1));
        return;
      }
      setMessages(prev => [
        ...prev.slice(0, -1),
        {
          role: "assistant",
          content: `**Fehler:** ${err.message}\n\nTipp: Stelle sicher dass das Backend läuft (Port 8000) und OPENAI_API_KEY in der .env gesetzt ist.`,
          error: true,
        }
      ]);
    } finally {
      setLoading(false);
      setStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, messages, loading, kontext, selectedMandant]);

  const stoppeGenerierung = () => {
    abortRef.current?.abort();
    setLoading(false);
    setStreaming(false);
  };

  const clearChat = () => {
    setMessages([]);
    setInput("");
    inputRef.current?.focus();
  };

  const mandantenListe = Object.keys(kontext.mandanten || {}).sort();

  // ═══════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════

  return (
    <div style={{
      flex: 1, display: "flex", flexDirection: "column",
      background: C.bg, fontFamily: "'DM Sans', sans-serif",
      height: "100%",
    }}>
      <style>{`
        ${FONTS}
        @keyframes spin     { to { transform: rotate(360deg); } }
        @keyframes fadeUp   { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @keyframes blink    { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes shimmer  { 0%{opacity:0.4} 50%{opacity:1} 100%{opacity:0.4} }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
        textarea { resize: none; }
        textarea:focus { outline: none; }
      `}</style>

      {/* ── HEADER ── */}
      <div style={{
        background: C.bg2, borderBottom: `1px solid ${C.border}`,
        padding: "16px 28px", display: "flex", alignItems: "center",
        gap: 16, position: "sticky", top: 0, zIndex: 10, flexShrink: 0,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: "'DM Serif Display', serif", fontSize: 20,
            color: C.text, display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%", background: C.green,
              display: "inline-block", boxShadow: `0 0 8px ${C.green}`,
              flexShrink: 0,
              animation: kontextLaden ? "shimmer 1.5s ease infinite" : "none",
            }} />
            KI-Assistent
          </div>
          <div style={{ fontSize: 12, color: C.text3, marginTop: 2 }}>
            {kontextLaden
              ? "Lade Kanzlei-Daten..."
              : `${Object.keys(kontext.mandanten || {}).length} Mandanten · ${(kontext.kpis || []).filter(k => k.status === "KRITISCH").length} kritisch · Echtzeit-Kontext aktiv`}
          </div>
        </div>

        {/* Mandanten-Filter */}
        <select value={selectedMandant} onChange={e => setSelectedMandant(e.target.value)}
          style={{
            background: C.bg3, border: `1px solid ${C.border2}`,
            borderRadius: 10, color: selectedMandant ? C.accent : C.text3,
            padding: "7px 12px", fontSize: 13, fontFamily: "'DM Sans', sans-serif",
            outline: "none", maxWidth: 220,
          }}>
          <option value="">Alle Mandanten</option>
          {mandantenListe.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        {messages.length > 0 && (
          <button onClick={clearChat} style={{
            background: "transparent", border: `1px solid ${C.border2}`,
            borderRadius: 10, color: C.text3, padding: "7px 13px",
            fontSize: 13, cursor: "pointer", fontFamily: "'DM Sans', sans-serif",
          }}>
            Neues Gespräch
          </button>
        )}
      </div>

      {/* ── CHAT BEREICH ── */}
      <div style={{
        flex: 1, overflowY: "auto", padding: "24px 0",
      }}>
        {/* Willkommens-Screen */}
        {messages.length === 0 && (
          <div style={{ padding: "0 28px", maxWidth: 760, margin: "0 auto" }}>
            <div style={{
              fontFamily: "'DM Serif Display', serif", fontSize: 32,
              color: C.text, marginBottom: 8, lineHeight: 1.2,
              animation: "fadeUp 0.5s ease",
            }}>
              Wie kann ich helfen?
            </div>
            <div style={{
              color: C.text3, fontSize: 15, marginBottom: 36,
              animation: "fadeUp 0.5s ease 0.1s both",
            }}>
              Ich habe Zugriff auf alle deine Mandantendaten, Fristen und KPIs.
              Frag mich alles — von Steueroptimierung bis zur Mandanten-Priorisierung.
            </div>

            {/* Quick Prompts */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: 10, animation: "fadeUp 0.5s ease 0.2s both",
            }}>
              {QUICK_PROMPTS.map((p, i) => (
                <button key={i} onClick={() => sendeNachricht(p.text)}
                  style={{
                    background: C.bg2, border: `1px solid ${C.border}`,
                    borderRadius: 12, padding: "14px 16px",
                    textAlign: "left", cursor: "pointer",
                    color: C.text2, fontSize: 13, lineHeight: 1.5,
                    fontFamily: "'DM Sans', sans-serif",
                    transition: "all 0.15s",
                    display: "flex", gap: 10, alignItems: "flex-start",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = C.accent + "50";
                    e.currentTarget.style.background  = C.bg3;
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = C.border;
                    e.currentTarget.style.background  = C.bg2;
                  }}>
                  <span style={{ fontSize: 18, flexShrink: 0 }}>{p.icon}</span>
                  <span>{p.text}</span>
                </button>
              ))}
            </div>

            {/* Mandanten-Schnellzugriff wenn KI kritische hat */}
            {(kontext.kpis || []).filter(k => k.status === "KRITISCH").length > 0 && (
              <div style={{
                marginTop: 24, background: C.red + "10",
                border: `1px solid ${C.red}25`, borderRadius: 12,
                padding: "14px 16px", animation: "fadeUp 0.5s ease 0.3s both",
              }}>
                <div style={{ fontSize: 13, color: C.red, fontWeight: 600, marginBottom: 8 }}>
                  ⚠ {(kontext.kpis || []).filter(k => k.status === "KRITISCH").length} kritische Mandanten
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {(kontext.kpis || []).filter(k => k.status === "KRITISCH").slice(0, 5).map(k => (
                    <button key={k.mandant}
                      onClick={() => sendeNachricht(`Analysiere den kritischen Mandanten "${k.mandant}" und gib mir eine genaue Handlungsempfehlung.`)}
                      style={{
                        background: C.red + "15", border: `1px solid ${C.red}30`,
                        borderRadius: 8, padding: "5px 12px", cursor: "pointer",
                        color: C.red, fontSize: 12, fontFamily: "'DM Sans', sans-serif",
                      }}>
                      {k.mandant}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Nachrichten */}
        <div style={{ maxWidth: 760, margin: "0 auto", padding: "0 28px" }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: "flex", gap: 14,
              marginBottom: 20, flexDirection: "row",
              animation: `fadeUp 0.3s ease`,
            }}>
              {/* Avatar */}
              <div style={{
                width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                background: msg.role === "user" ? C.bg3 : C.accent + "20",
                border: `1px solid ${msg.role === "user" ? C.border2 : C.accent + "40"}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14,
              }}>
                {msg.role === "user" ? "◉" : "◈"}
              </div>

              {/* Inhalt */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 11, color: C.text3, marginBottom: 6,
                  textTransform: "uppercase", letterSpacing: "0.07em",
                }}>
                  {msg.role === "user" ? "Du" : "Kanzlei KI"}
                </div>

                {msg.streaming ? (
                  <div style={{ color: C.text2, fontSize: 14, lineHeight: 1.7 }}>
                    <span style={{ animation: "shimmer 1.2s ease infinite" }}>
                      ···
                    </span>
                  </div>
                ) : (
                  <div style={{
                    color: msg.error ? C.red : msg.role === "user" ? C.text : C.text2,
                    fontSize: 14, lineHeight: 1.8,
                    background: msg.role === "user" ? C.bg3 : "transparent",
                    padding: msg.role === "user" ? "12px 14px" : "0",
                    borderRadius: msg.role === "user" ? 12 : 0,
                    border: msg.role === "user" ? `1px solid ${C.border}` : "none",
                  }}
                    dangerouslySetInnerHTML={{
                      __html: msg.role === "assistant"
                        ? renderMarkdown(msg.display || msg.content)
                        : msg.display || msg.content
                    }}
                  />
                )}

                {/* Mandanten-Links in Antworten */}
                {msg.role === "assistant" && !msg.streaming && mandantenListe.some(m =>
                  (msg.content || "").includes(m)
                ) && (
                  <div style={{
                    marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap"
                  }}>
                    {mandantenListe.filter(m =>
                      (msg.content || "").includes(m)
                    ).slice(0, 4).map(m => (
                      <Link key={m} to={`/mandant/${encodeURIComponent(m)}`}
                        style={{
                          fontSize: 11, color: C.accent,
                          background: C.accent + "15",
                          border: `1px solid ${C.accent}30`,
                          borderRadius: 6, padding: "2px 9px",
                          textDecoration: "none",
                        }}>
                        → {m}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ── INPUT BEREICH ── */}
      <div style={{
        background: C.bg2, borderTop: `1px solid ${C.border}`,
        padding: "16px 28px", flexShrink: 0,
      }}>
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          <div style={{
            display: "flex", gap: 12, alignItems: "flex-end",
            background: C.bg3, border: `1px solid ${C.border2}`,
            borderRadius: 14, padding: "10px 14px",
            transition: "border 0.15s",
          }}
            onFocus={() => {}}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendeNachricht();
                }
              }}
              placeholder={selectedMandant
                ? `Frage zu ${selectedMandant}...`
                : "Frage stellen... (Enter zum Senden, Shift+Enter = Zeilenumbruch)"
              }
              rows={1}
              style={{
                flex: 1, background: "transparent", border: "none",
                color: C.text, fontSize: 14, fontFamily: "'DM Sans', sans-serif",
                lineHeight: 1.6, maxHeight: 120, overflowY: "auto",
                padding: 0,
              }}
              onInput={e => {
                e.target.style.height = "auto";
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
              }}
            />

            {streaming ? (
              <button onClick={stoppeGenerierung} style={{
                background: C.red + "20", border: `1px solid ${C.red}30`,
                borderRadius: 10, padding: "8px 14px", cursor: "pointer",
                color: C.red, fontSize: 13, fontFamily: "'DM Sans', sans-serif",
                flexShrink: 0,
              }}>
                ⏹ Stopp
              </button>
            ) : (
              <button
                onClick={() => sendeNachricht()}
                disabled={!input.trim() || loading || kontextLaden}
                style={{
                  background: input.trim() && !loading ? C.accent : C.bg,
                  border: `1px solid ${input.trim() && !loading ? C.accent : C.border2}`,
                  borderRadius: 10, padding: "8px 16px", cursor: "pointer",
                  color: input.trim() && !loading ? "#1a1200" : C.text3,
                  fontSize: 13, fontWeight: 600,
                  fontFamily: "'DM Sans', sans-serif", flexShrink: 0,
                  transition: "all 0.15s",
                  opacity: loading ? 0.6 : 1,
                }}>
                {loading
                  ? <span style={{ width: 16, height: 16, borderRadius: "50%",
                      border: "2px solid currentColor", borderTopColor: "transparent",
                      animation: "spin 0.7s linear infinite", display: "inline-block" }} />
                  : "Senden →"}
              </button>
            )}
          </div>

          <div style={{
            display: "flex", justifyContent: "space-between",
            marginTop: 8, fontSize: 11, color: C.text3,
          }}>
            <span>
              {kontextLaden
                ? "Lade Kanzlei-Daten..."
                : `Kontext: ${Object.keys(kontext.mandanten || {}).length} Mandanten live geladen`}
            </span>
            <span>Powered by GPT-4o mini (OpenAI)</span>
          </div>
        </div>
      </div>
    </div>
  );
}