import { useEffect, useState, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiFetch, getMandanten, getKpis, getHeute, getEmpfehlungen, extrahiereHeuteEintraege } from "../api";
import { useContentLayoutWidth } from "../useContentLayoutWidth";

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');`;
const CHAT_STORAGE_KEY = "kanzlei_ai_chat_threads_v1";
const CHAT_ACTIVE_KEY = "kanzlei_ai_chat_active_v1";
const THREADS_SIDEBAR_KEY = "kanzlei_ki_threads_open";

function readInitialThreadsSidebarOpen() {
  try {
    const s = localStorage.getItem(THREADS_SIDEBAR_KEY);
    if (s === "1") return true;
    if (s === "0") return false;
  } catch {}
  if (typeof window !== "undefined" && window.innerWidth < 768) return false;
  return true;
}

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

const makeThreadTitle = (text = "") => {
  const t = String(text || "").trim();
  if (!t) return "Neues Gespräch";
  return t.length > 52 ? `${t.slice(0, 52)}…` : t;
};

const newThread = (initialText = "") => {
  const now = Date.now();
  return {
    id: `${now}-${Math.random().toString(36).slice(2, 9)}`,
    title: makeThreadTitle(initialText),
    messages: [],
    createdAt: now,
    updatedAt: now,
    pinned: false,
  };
};

function safeReadThreads() {
  try {
    const raw = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter((t) => t && typeof t === "object" && t.id).map((t) => ({
      id: t.id,
      title: String(t.title || "Gespräch"),
      messages: Array.isArray(t.messages) ? t.messages : [],
      createdAt: Number(t.createdAt || Date.now()),
      updatedAt: Number(t.updatedAt || Date.now()),
      pinned: Boolean(t.pinned),
    }));
  } catch {
    return [];
  }
}

function buildMemoryFromThreads(threads, activeId) {
  const others = (threads || [])
    .filter((t) => t.id !== activeId)
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    .slice(0, 4);
  const lines = [];
  for (const t of others) {
    const lastUser = [...(t.messages || [])].reverse().find((m) => m?.role === "user");
    if (!lastUser?.display && !lastUser?.content) continue;
    const txt = String(lastUser.display || lastUser.content || "").slice(0, 180);
    lines.push(`- ${t.title}: ${txt}`);
  }
  return lines.join("\n");
}

// ─── System-Prompt Generator ─────────────────────────────────
function erstelleSystemPrompt(kontext, memoryText = "") {
  const { mandanten, kpis, heute } = kontext;

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

  return `Du bist der KI-Assistent von Kanzlei Automation — ein hochspezialisierter Steuerberater-Assistent.
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
- Sei direkt und spar dir Einleitungsfloskeln
- Bei lockeren Fragen ("hallo", "wie gehts", plaudern): antworte freundlich und kurz, ohne Datenzwang.
- Wenn für eine konkrete Aussage Daten fehlen: benenne transparent was fehlt und gib sinnvolle nächste Schritte.
- Nutze bei Analysefragen bevorzugt diese Struktur: **Einschätzung**, **Risiko**, **Nächste Schritte**
- Datenschutz: Keine Geheimnisse, Zugangsdaten oder interne Schlüssel ausgeben; sensible Daten nur minimal und zweckgebunden verwenden.

LANGZEIT-KONTEXT AUS FRUEHEREN GESPRAECHEN:
${memoryText || "Keine gespeicherten Notizen aus anderen Gesprächen."}`;
}

function isWeakAssistantAnswer(text = "") {
  const t = String(text || "").trim().toLowerCase();
  if (!t) return true;
  if (t.length < 24) return true;
  return (
    t.includes("nicht genug daten") ||
    t.includes("keine daten") ||
    t.includes("not enough data") ||
    t.includes("insufficient data")
  );
}

function buildDataFallbackAnswer(userText, kontext, selectedMandant) {
  const q = String(userText || "").toLowerCase();
  const kpis = Array.isArray(kontext?.kpis) ? kontext.kpis : [];
  const mandanten = kontext?.mandanten || {};
  const heute = Array.isArray(kontext?.heute) ? kontext.heute : [];

  const byPriority = kpis
    .slice()
    .sort((a, b) => {
      const rank = (s) => (s === "KRITISCH" ? 3 : s === "WICHTIG" ? 2 : 1);
      const ra = rank(String(a?.status || ""));
      const rb = rank(String(b?.status || ""));
      if (ra !== rb) return rb - ra;
      const oa = Number(a?.aufgaben_ueberfaellig || 0);
      const ob = Number(b?.aufgaben_ueberfaellig || 0);
      if (oa !== ob) return ob - oa;
      return Number(a?.tage_ohne_antwort || 0) - Number(b?.tage_ohne_antwort || 0);
    });

  const top = byPriority.slice(0, 5);
  const kritisch = byPriority.filter((x) => String(x?.status || "") === "KRITISCH").length;
  const wichtig = byPriority.filter((x) => String(x?.status || "") === "WICHTIG").length;

  if (q.includes("aufmerksamkeit") || q.includes("prior") || q.includes("heute")) {
    if (!top.length) {
      return `**Einschaetzung**\nAktuell sind noch keine KPI-Daten geladen.\n\n**Naechste Schritte**\n- Bitte kurz Dashboard/KPI neu laden\n- Dann nenne ich dir sofort die Top-Prioritaeten`;
    }
    const lines = top.map((k, idx) => {
      const n = k?.mandant || `Mandant ${idx + 1}`;
      const s = k?.status || "UNBEKANNT";
      const o = Number(k?.aufgaben_ueberfaellig || 0);
      const d = Number(k?.tage_ohne_antwort || 0);
      return `${idx + 1}. **${n}** - Status: ${s}, Ueberfaellige Aufgaben: ${o}, Tage ohne Antwort: ${d}`;
    });
    return `**Einschaetzung**\nDie dringendsten Faelle kommen aus Status, Ueberfaelligkeit und fehlender Rueckmeldung.\n\n**Top-Prioritaet heute**\n${lines.join("\n")}\n\n**Risiko**\n- Kritisch: ${kritisch}\n- Wichtig: ${wichtig}\n\n**Naechste Schritte**\n- Zuerst die Top 2 sofort kontaktieren\n- Danach Fristen bei kritischen Mandanten absichern`;
  }

  if (selectedMandant) {
    const m = mandanten[selectedMandant] || {};
    return `**Einschaetzung**\nIch habe den Fokus auf **${selectedMandant}** gesetzt.\n\n**Aktuelle Daten**\n- Umsatz: €${Number(m?.umsatz || 0).toLocaleString("de-DE")}\n- Branche: ${m?.branche || "nicht hinterlegt"}\n\n**Naechste Schritte**\n- Wenn du magst, erstelle ich direkt einen konkreten 7-Tage-Aktionsplan fuer ${selectedMandant}.`;
  }

  const mandCount = Object.keys(mandanten || {}).length;
  return `Ich bin da und arbeite mit deinen Kanzlei-Daten.\n\n**Aktueller Stand**\n- Mandanten: ${mandCount}\n- KPI-Eintraege: ${kpis.length}\n- Heute-Punkte: ${heute.length}\n\nWenn du willst, starte ich direkt mit:\n- Priorisierung der kritischsten Mandanten\n- Fristen-Risiko-Check fuer diese Woche\n- 5 konkrete Aktionen fuer heute`;
}

function stripTraceMeta(text = "") {
  return String(text || "")
    .replace(/\n*\s*trace:\s*`?[\w-]{8,}`?\s*$/i, "")
    .trim();
}

// ─── Markdown Renderer (minimal, kein externes Package) ──────
function renderMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, `<code style="background:${"var(--bg3)"};padding:2px 6px;border-radius:4px;font-family:'DM Mono',monospace;font-size:12px;color:${"var(--accent)"}">$1</code>`)
    .replace(/^### (.+)$/gm, `<div style="font-size:14px;font-weight:600;color:${"var(--text)"};margin:12px 0 6px">$1</div>`)
    .replace(/^## (.+)$/gm,  `<div style="font-size:16px;font-weight:700;color:${"var(--accent)"};margin:14px 0 8px;font-family:'DM Serif Display',serif">$1</div>`)
    .replace(/^# (.+)$/gm,   `<div style="font-size:18px;font-weight:700;color:${"var(--accent)"};margin:16px 0 10px;font-family:'DM Serif Display',serif">$1</div>`)
    .replace(/^- (.+)$/gm,   `<div style="display:flex;gap:8px;margin:3px 0"><span style="color:${"var(--accent)"};flex-shrink:0">·</span><span>$1</span></div>`)
    .replace(/^\d+\. (.+)$/gm,(match, p1, offset, str) => {
      const num = str.slice(0, offset).match(/^\d+\. /gm)?.length + 1 || 1;
      return `<div style="display:flex;gap:8px;margin:3px 0"><span style="color:${"var(--text3)"};flex-shrink:0;min-width:16px">${num}.</span><span>${p1}</span></div>`;
    })
    .replace(/\n\n/g, '<div style="height:8px"></div>')
    .replace(/\n/g,   "");
}

// ═══════════════════════════════════════════════════════════
// HAUPT-COMPONENT
// ═══════════════════════════════════════════════════════════

export default function KIAssistent() {
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [messages,    setMessages]    = useState([]);
  const [input,       setInput]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [kontext,     setKontext]     = useState({});
  const [kontextLaden,setKontextLaden]= useState(true);
  const [selectedMandant, setSelectedMandant] = useState("");
  const [streaming,   setStreaming]   = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [threadsSidebarOpen, setThreadsSidebarOpen] = useState(readInitialThreadsSidebarOpen);

  const messagesEndRef = useRef(null);
  const inputRef       = useRef(null);
  const abortRef       = useRef(null);
  const syncReadyRef   = useRef(false);
  const syncTimerRef   = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let first = [];
      try {
        const remote = await apiFetch("/ki/chats");
        const arr = Array.isArray(remote?.threads) ? remote.threads : [];
        first = arr.length ? arr : [];
        const remoteActive = String(remote?.active_id || "");
        if (!first.length) first = safeReadThreads();
        if (!first.length) first = [newThread()];
        const preferred = remoteActive || localStorage.getItem(CHAT_ACTIVE_KEY) || first[0].id;
        const active = first.find((t) => t.id === preferred) ? preferred : first[0].id;
        if (cancelled) return;
        setThreads(first);
        setActiveThreadId(active);
        const at = first.find((t) => t.id === active) || first[0];
        setMessages(at.messages || []);
      } catch {
        first = safeReadThreads();
        if (!first.length) first = [newThread()];
        const preferred = localStorage.getItem(CHAT_ACTIVE_KEY) || first[0].id;
        const active = first.find((t) => t.id === preferred) ? preferred : first[0].id;
        if (cancelled) return;
        setThreads(first);
        setActiveThreadId(active);
        const at = first.find((t) => t.id === active) || first[0];
        setMessages(at.messages || []);
      } finally {
        if (!cancelled) syncReadyRef.current = true;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeThreadId) return;
    const active = threads.find((t) => t.id === activeThreadId);
    if (active) setMessages(active.messages || []);
  }, [activeThreadId, threads]);

  useEffect(() => {
    if (!threads.length) return;
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(threads));
      if (activeThreadId) localStorage.setItem(CHAT_ACTIVE_KEY, activeThreadId);
    } catch {}
  }, [threads, activeThreadId]);

  useEffect(() => {
    if (!syncReadyRef.current) return;
    if (!threads.length) return;
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    syncTimerRef.current = setTimeout(() => {
      apiFetch("/ki/chats", {
        method: "PUT",
        body: JSON.stringify({ threads, active_id: activeThreadId }),
      }).catch(() => {});
    }, 500);
    return () => {
      if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    };
  }, [threads, activeThreadId]);

  useEffect(() => {
    try {
      localStorage.setItem(THREADS_SIDEBAR_KEY, threadsSidebarOpen ? "1" : "0");
    } catch {}
  }, [threadsSidebarOpen]);

  const updateActiveThread = useCallback((nextMessages, titleCandidate = "") => {
    setThreads((prev) => prev.map((t) => {
      if (t.id !== activeThreadId) return t;
      const title = (t.title && t.title !== "Neues Gespräch")
        ? t.title
        : makeThreadTitle(titleCandidate || nextMessages.find((m) => m.role === "user")?.display || "");
      return {
        ...t,
        title,
        messages: nextMessages,
        updatedAt: Date.now(),
      };
    }));
    setMessages(nextMessages);
  }, [activeThreadId]);

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
        heute:         h.status === "fulfilled" ? extrahiereHeuteEintraege(h.value) : [],
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
    if (!text || loading || !activeThreadId) return;

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
    updateActiveThread(newMessages, text);

    // Platzhalter für Streaming-Antwort
    const withPlaceholder = [...newMessages, {
      role: "assistant", content: "", streaming: true
    }];
    updateActiveThread(withPlaceholder, text);

    try {
      const memoryText = buildMemoryFromThreads(threads, activeThreadId);
      const systemPrompt = erstelleSystemPrompt(kontext, memoryText);

      // Konversations-History für Backend (max. 20 Nachrichten)
      const history = newMessages.slice(-20).map((m) => ({
        role: m.role,
        content: String(m.content || "").slice(0, 1200),
      }));

      // Backend-Proxy statt direkter OpenAI-Call (CORS-Problem behoben)
      const response = await apiFetch("/ki/chat", {
        method: "POST",
        signal: (abortRef.current = new AbortController()).signal,
        body: JSON.stringify({
          messages:  history,
          system:    systemPrompt,
          max_tokens: 1200,
          mandant:   selectedMandant || null,
        }),
      });
      const data = response || {};

      // OpenAI gibt content direkt als String zurück (nicht als Array)
      const contentRaw = data.content || "Keine Antwort erhalten.";
      const content = isWeakAssistantAnswer(contentRaw)
        ? buildDataFallbackAnswer(text, kontext, selectedMandant)
        : contentRaw;
      // Streaming-Platzhalter ersetzen
      const doneMessages = [...withPlaceholder.slice(0, -1), { role: "assistant", content, streaming: false }];
      updateActiveThread(doneMessages, text);

    } catch (err) {
      if (err.name === "AbortError") {
        updateActiveThread(withPlaceholder.slice(0, -1), text);
        return;
      }
      const status = Number(err?.status || 0);
      const contactHint = "Bitte wenden Sie sich an Ihre IT oder den Administrator der Kanzlei.";
      const quotaHint = `Das Nutzungskontingent ist erreicht. ${contactHint}`;
      const keyHint = `Der KI-Dienst konnte nicht authentifiziert werden. ${contactHint}`;
      const genericHint = `Der KI-Dienst ist vorübergehend nicht verfügbar. ${contactHint}`;
      const hint = status === 402 ? quotaHint : status === 401 ? keyHint : genericHint;
      const failedMessages = [
        ...withPlaceholder.slice(0, -1),
        {
          role: "assistant",
          content: `**Fehler:** ${err.message}\n\n${hint}`,
          error: true,
        }
      ];
      updateActiveThread(failedMessages, text);
    } finally {
      setLoading(false);
      setStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, messages, loading, kontext, selectedMandant, threads, activeThreadId, updateActiveThread]);

  const stoppeGenerierung = () => {
    abortRef.current?.abort();
    setLoading(false);
    setStreaming(false);
  };

  const clearChat = () => {
    const n = newThread();
    setThreads((prev) => [n, ...prev]);
    setActiveThreadId(n.id);
    setMessages([]);
    setInput("");
    inputRef.current?.focus();
  };

  const openThread = useCallback((id) => {
    if (!id) return;
    setActiveThreadId(id);
    setInput("");
    setTimeout(() => inputRef.current?.focus(), 0);
  }, []);

  const deleteThread = useCallback((id) => {
    setThreads((prev) => {
      const next = prev.filter((t) => t.id !== id);
      if (next.length === 0) {
        const created = newThread();
        setActiveThreadId(created.id);
        setMessages([]);
        return [created];
      }
      if (id === activeThreadId) {
        setActiveThreadId(next[0].id);
      }
      return next;
    });
  }, [activeThreadId]);

  const togglePinThread = useCallback((id) => {
    setThreads((prev) => prev.map((t) => (t.id === id ? { ...t, pinned: !t.pinned, updatedAt: Date.now() } : t)));
  }, []);

  const renameThread = useCallback((id) => {
    const t = threads.find((x) => x.id === id);
    if (!t) return;
    const raw = window.prompt("Titel für Gespräch", t.title || "Gespräch");
    if (raw === null) return;
    const nextTitle = makeThreadTitle(raw);
    setThreads((prev) => prev.map((x) => (x.id === id ? { ...x, title: nextTitle, updatedAt: Date.now() } : x)));
  }, [threads]);

  const mandantenListe = Object.keys(kontext.mandanten || {}).sort();
  const lw = useContentLayoutWidth();
  const narrow = lw < 768;
  const padX = narrow ? 14 : 28;

  const pickThread = useCallback(
    (id) => {
      openThread(id);
      if (narrow) setThreadsSidebarOpen(false);
    },
    [openThread, narrow]
  );

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    if (!narrow || !threadsSidebarOpen) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [narrow, threadsSidebarOpen]);

  const activeThreadTitle =
    threads.find((t) => t.id === activeThreadId)?.title?.trim() || "Gespräch";

  const threadListSection = (
    <>
      <div style={{ padding: "14px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <button
          type="button"
          onClick={clearChat}
          style={{
            width: "100%",
            background: "var(--accent)",
            color: "var(--on-accent)",
            border: "none",
            borderRadius: 10,
            padding: "9px 12px",
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          + Neues Gespräch
        </button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", padding: "10px 8px", minHeight: 0 }}>
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Verläufe suchen..."
          style={{
            width: "100%",
            marginBottom: 8,
            borderRadius: 8,
            border: "1px solid var(--border2)",
            background: "var(--bg3)",
            color: "var(--text)",
            padding: "7px 9px",
            fontSize: 12,
            fontFamily: "'DM Sans', sans-serif",
          }}
        />
        {threads
          .slice()
          .filter((t) => {
            const q = searchQuery.trim().toLowerCase();
            if (!q) return true;
            const body = `${t.title || ""} ${(t.messages || []).slice(-4).map((m) => m.display || m.content || "").join(" ")}`.toLowerCase();
            return body.includes(q);
          })
          .sort((a, b) => {
            if (!!a.pinned !== !!b.pinned) return a.pinned ? -1 : 1;
            return (b.updatedAt || 0) - (a.updatedAt || 0);
          })
          .map((t) => {
            const active = t.id === activeThreadId;
            return (
              <div
                key={t.id}
                style={{
                  marginBottom: 6,
                  borderRadius: 10,
                  border: `1px solid ${active ? "color-mix(in srgb, var(--accent) 40%, transparent)" : "var(--border)"}`,
                  background: active ? "var(--bg3)" : "transparent",
                  padding: "8px 10px",
                }}
              >
                <button
                  type="button"
                  onClick={() => pickThread(t.id)}
                  style={{
                    width: "100%",
                    border: "none",
                    background: "transparent",
                    color: active ? "var(--accent)" : "var(--text2)",
                    textAlign: "left",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                    fontFamily: "'DM Sans', sans-serif",
                  }}
                >
                  {t.pinned ? "📌 " : ""}{t.title || "Gespräch"}
                </button>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "var(--text3)" }}>
                    {new Date(t.updatedAt || Date.now()).toLocaleDateString("de-DE")}
                  </span>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <button
                      type="button"
                      onClick={() => renameThread(t.id)}
                      style={{
                        border: "none",
                        background: "transparent",
                        color: "var(--text3)",
                        fontSize: 11,
                        cursor: "pointer",
                      }}
                    >
                      Umben.
                    </button>
                    <button
                      type="button"
                      onClick={() => togglePinThread(t.id)}
                      style={{
                        border: "none",
                        background: "transparent",
                        color: t.pinned ? "var(--accent)" : "var(--text3)",
                        fontSize: 11,
                        cursor: "pointer",
                      }}
                    >
                      {t.pinned ? "Lösen" : "Pin"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const ok = window.confirm("Diesen Chat wirklich löschen?");
                        if (ok) deleteThread(t.id);
                      }}
                      style={{
                        border: "none",
                        background: "transparent",
                        color: "var(--text3)",
                        fontSize: 11,
                        cursor: "pointer",
                      }}
                    >
                      Löschen
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
      </div>
    </>
  );

  // ═══════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════

  return (
    <div style={{
      flex: 1, display: "flex", flexDirection: narrow ? "column" : "row",
      background: "var(--bg)", fontFamily: "'DM Sans', sans-serif",
      minHeight: 0, minWidth: 0, maxWidth: "100%", overflow: "hidden",
    }}>
      <style>{`
        ${FONTS}
        @keyframes spin     { to { transform: rotate(360deg); } }
        @keyframes fadeUp   { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
        @keyframes blink    { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes shimmer  { 0%{opacity:0.4} 50%{opacity:1} 100%{opacity:0.4} }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }
        textarea { resize: none; }
        textarea:focus { outline: none; }
      `}</style>

      {!narrow && threadsSidebarOpen ? (
        <aside
          style={{
            width: 260,
            borderRight: "1px solid var(--border)",
            background: "var(--bg2)",
            display: "flex",
            flexDirection: "column",
            flexShrink: 0,
            minHeight: 0,
            height: "100%",
            overflow: "hidden",
          }}
        >
          {threadListSection}
        </aside>
      ) : null}

      {narrow && threadsSidebarOpen ? (
        <>
          <div
            role="presentation"
            onClick={() => setThreadsSidebarOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.38)",
              zIndex: 40,
            }}
          />
          <aside
            style={{
              position: "fixed",
              left: 0,
              top: 0,
              bottom: 0,
              width: "min(92vw, 300px)",
              maxWidth: "100%",
              zIndex: 50,
              background: "var(--bg2)",
              borderRight: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
              boxShadow: "4px 0 24px rgba(0,0,0,0.12)",
            }}
          >
            <div
              style={{
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                padding: "12px 12px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text)" }}>Verläufe</span>
              <button
                type="button"
                onClick={() => setThreadsSidebarOpen(false)}
                aria-label="Verläufe schließen"
                style={{
                  border: "none",
                  background: "var(--bg3)",
                  color: "var(--text2)",
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  cursor: "pointer",
                  fontSize: 18,
                  lineHeight: 1,
                  fontFamily: "'DM Sans', sans-serif",
                }}
              >
                ×
              </button>
            </div>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
              {threadListSection}
            </div>
          </aside>
        </>
      ) : null}

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, overflow: "hidden" }}>
      {/* ── Schnell-Leiste Verläufe ── */}
      <div
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: `10px ${padX}px`,
          borderBottom: "1px solid var(--border)",
          background: "var(--bg2)",
          position: "sticky",
          top: 0,
          zIndex: 12,
        }}
      >
        <button
          type="button"
          onClick={() => setThreadsSidebarOpen((o) => !o)}
          aria-expanded={threadsSidebarOpen}
          style={{
            flexShrink: 0,
            border: "1px solid var(--border2)",
            background: "var(--bg3)",
            color: "var(--text)",
            borderRadius: 10,
            padding: "7px 11px",
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          {threadsSidebarOpen ? "Verläufe «" : "Verläufe »"}
        </button>
        <span
          title={activeThreadTitle}
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text2)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {activeThreadTitle}
        </span>
        <button
          type="button"
          onClick={clearChat}
          style={{
            flexShrink: 0,
            border: "none",
            background: "var(--accent)",
            color: "var(--on-accent)",
            borderRadius: 10,
            padding: "7px 12px",
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          + Neu
        </button>
      </div>

      {/* ── HEADER ── */}
      <div style={{
        background: "var(--bg2)", borderBottom: `1px solid var(--border)`,
        padding: `14px ${padX}px`, display: "flex", alignItems: "flex-start",
        flexWrap: "wrap", gap: 12, flexShrink: 0,
      }}>
        <div style={{ flex: "1 1 200px", minWidth: 0 }}>
          <div style={{
            fontFamily: "'DM Serif Display', serif", fontSize: narrow ? 18 : 20,
            color: "var(--text)", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
          }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%", background: "var(--green)",
              display: "inline-block", boxShadow: `0 0 8px ${"var(--green)"}`,
              flexShrink: 0,
              animation: kontextLaden ? "shimmer 1.5s ease infinite" : "none",
            }} />
            KI-Assistent
          </div>
          <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 2 }}>
            {kontextLaden
              ? "Lade Kanzlei-Daten..."
              : `${Object.keys(kontext.mandanten || {}).length} Mandanten · ${(kontext.kpis || []).filter(k => k.status === "KRITISCH").length} kritisch · Echtzeit-Kontext aktiv`}
          </div>
        </div>

        {/* Mandanten-Filter */}
        <select value={selectedMandant} onChange={e => setSelectedMandant(e.target.value)}
          style={{
            background: "var(--bg3)", border: `1px solid var(--border2)`,
            borderRadius: 10, color: selectedMandant ? "var(--accent)" : "var(--text3)",
            padding: "7px 12px", fontSize: 13, fontFamily: "'DM Sans', sans-serif",
            outline: "none", maxWidth: narrow ? "100%" : 220,
            flex: narrow ? "1 1 100%" : "0 1 auto",
            minWidth: 0,
          }}>
          <option value="">Alle Mandanten</option>
          {mandantenListe.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        {messages.length > 0 ? <span style={{ fontSize: 11, color: "var(--text3)", flex: "1 1 100%" }}>Verlauf wird gespeichert</span> : null}
      </div>

      {/* ── CHAT BEREICH ── */}
      <div style={{
        flex: 1, overflowY: "auto", padding: narrow ? "16px 0" : "24px 0", minHeight: 0, minWidth: 0,
      }}>
        {/* Willkommens-Screen */}
        {messages.length === 0 && (
          <div style={{ padding: `0 ${padX}px`, maxWidth: 760, margin: "0 auto", boxSizing: "border-box" }}>
            <div style={{
              fontFamily: "'DM Serif Display', serif", fontSize: narrow ? 24 : 32,
              color: "var(--text)", marginBottom: 8, lineHeight: 1.2,
              animation: "fadeUp 0.5s ease",
            }}>
              Wie kann ich helfen?
            </div>
            <div style={{
              color: "var(--text3)", fontSize: 15, marginBottom: 36,
              animation: "fadeUp 0.5s ease 0.1s both",
            }}>
              Ich habe Zugriff auf alle deine Mandantendaten, Fristen und KPIs.
              Frag mich alles — von Steueroptimierung bis zur Mandanten-Priorisierung.
            </div>

            {/* Quick Prompts */}
            <div style={{
              display: "grid", gridTemplateColumns: narrow ? "minmax(0,1fr)" : "1fr 1fr",
              gap: 10, animation: "fadeUp 0.5s ease 0.2s both",
            }}>
              {QUICK_PROMPTS.map((p, i) => (
                <button key={i} onClick={() => sendeNachricht(p.text)}
                  style={{
                    background: "var(--bg2)", border: `1px solid var(--border)`,
                    borderRadius: 12, padding: "14px 16px",
                    textAlign: "left", cursor: "pointer",
                    color: "var(--text2)", fontSize: 13, lineHeight: 1.5,
                    fontFamily: "'DM Sans', sans-serif",
                    transition: "all 0.15s",
                    display: "flex", gap: 10, alignItems: "flex-start",
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.borderColor = "color-mix(in srgb, var(--accent) 50%, transparent)";
                    e.currentTarget.style.background  = "var(--bg3)";
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.background  = "var(--bg2)";
                  }}>
                  <span style={{ fontSize: 18, flexShrink: 0 }}>{p.icon}</span>
                  <span>{p.text}</span>
                </button>
              ))}
            </div>

            {/* Mandanten-Schnellzugriff wenn KI kritische hat */}
            {(kontext.kpis || []).filter(k => k.status === "KRITISCH").length > 0 && (
              <div style={{
                marginTop: 24, background: "color-mix(in srgb, var(--red) 10%, var(--bg3))",
                border: "1px solid color-mix(in srgb, var(--red) 25%, transparent)", borderRadius: 12,
                padding: "14px 16px", animation: "fadeUp 0.5s ease 0.3s both",
              }}>
                <div style={{ fontSize: 13, color: "var(--red)", fontWeight: 600, marginBottom: 8 }}>
                  ⚠ {(kontext.kpis || []).filter(k => k.status === "KRITISCH").length} kritische Mandanten
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {(kontext.kpis || []).filter(k => k.status === "KRITISCH").slice(0, 5).map(k => (
                    <button key={k.mandant}
                      onClick={() => sendeNachricht(`Analysiere den kritischen Mandanten "${k.mandant}" und gib mir eine genaue Handlungsempfehlung.`)}
                      style={{
                        background: "color-mix(in srgb, var(--red) 15%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)",
                        borderRadius: 8, padding: "5px 12px", cursor: "pointer",
                        color: "var(--red)", fontSize: 12, fontFamily: "'DM Sans', sans-serif",
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
        <div style={{ maxWidth: 760, margin: "0 auto", padding: `0 ${padX}px`, boxSizing: "border-box" }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: "flex", gap: 14,
              marginBottom: 20, flexDirection: "row",
              animation: `fadeUp 0.3s ease`,
            }}>
              {/* Avatar */}
              <div style={{
                width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                background: msg.role === "user" ? "var(--bg3)" : "color-mix(in srgb, var(--accent) 20%, var(--bg3))",
                border: msg.role === "user" ? "1px solid var(--border2)" : "1px solid color-mix(in srgb, var(--accent) 35%, transparent)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14,
              }}>
                {msg.role === "user" ? "◉" : "◈"}
              </div>

              {/* Inhalt */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 11, color: "var(--text3)", marginBottom: 6,
                  textTransform: "uppercase", letterSpacing: "0.07em",
                }}>
                  {msg.role === "user" ? "Du" : "Kanzlei KI"}
                </div>

                {msg.streaming ? (
                  <div style={{ color: "var(--text2)", fontSize: 14, lineHeight: 1.7 }}>
                    <span style={{ animation: "shimmer 1.2s ease infinite" }}>
                      ···
                    </span>
                  </div>
                ) : (
                  <div style={{
                    color: msg.error ? "var(--red)" : msg.role === "user" ? "var(--text)" : "var(--text2)",
                    fontSize: 14, lineHeight: 1.8,
                    background: msg.role === "user" ? "var(--bg3)" : "transparent",
                    padding: msg.role === "user" ? "12px 14px" : "0",
                    borderRadius: msg.role === "user" ? 12 : 0,
                    border: msg.role === "user" ? `1px solid var(--border)` : "none",
                  }}
                    dangerouslySetInnerHTML={{
                      __html: msg.role === "assistant"
                        ? renderMarkdown(stripTraceMeta(msg.display || msg.content))
                        : msg.display || msg.content
                    }}
                  />
                )}

                {/* Mandanten-Links in Antworten */}
                {msg.role === "assistant" && !msg.streaming && mandantenListe.some(m =>
                  stripTraceMeta(msg.content || "").includes(m)
                ) && (
                  <div style={{
                    marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap"
                  }}>
                    {mandantenListe.filter(m =>
                      stripTraceMeta(msg.content || "").includes(m)
                    ).slice(0, 4).map(m => (
                      <Link key={m} to={`/mandant/${encodeURIComponent(m)}`}
                        style={{
                          fontSize: 11, color: "var(--accent)",
                          background: "color-mix(in srgb, var(--accent) 15%, var(--bg3))",
                          border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
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
        background: "var(--bg2)", borderTop: `1px solid var(--border)`,
        padding: `14px ${padX}px`, flexShrink: 0,
      }}>
        <div style={{ maxWidth: 760, margin: "0 auto", boxSizing: "border-box" }}>
          <div style={{
            display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap",
            background: "var(--bg3)", border: `1px solid var(--border2)`,
            borderRadius: 14, padding: "10px 12px",
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
                flex: "1 1 160px", minWidth: 0, background: "transparent", border: "none",
                color: "var(--text)", fontSize: 14, fontFamily: "'DM Sans', sans-serif",
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
                background: "color-mix(in srgb, var(--red) 20%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)",
                borderRadius: 10, padding: "8px 14px", cursor: "pointer",
                color: "var(--red)", fontSize: 13, fontFamily: "'DM Sans', sans-serif",
                flexShrink: 0,
              }}>
                ⏹ Stopp
              </button>
            ) : (
              <button
                onClick={() => sendeNachricht()}
                disabled={!input.trim() || loading || kontextLaden}
                style={{
                  background: input.trim() && !loading ? "var(--accent)" : "var(--bg)",
                  border: input.trim() && !loading ? "1px solid var(--accent)" : "1px solid var(--border2)",
                  borderRadius: 10, padding: "8px 16px", cursor: "pointer",
                  color: input.trim() && !loading ? "var(--on-accent)" : "var(--text3)",
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

          {kontextLaden ? (
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text3)" }}>
              Lade Kanzlei-Daten…
            </div>
          ) : null}
        </div>
      </div>
      </div>
    </div>
  );
}