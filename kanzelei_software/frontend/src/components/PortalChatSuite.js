import React, { useCallback, useEffect, useState } from "react";
import { getMandanten, getPortalChatInbox } from "../api";
import PortalChat from "./PortalChat";

const fmtZeitKurz = (iso) => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const heute = new Date();
    if (d.toDateString() === heute.toDateString()) {
      return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
  } catch {
    return "";
  }
};

const initialen = (name) => {
  const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] || "?").toUpperCase();
};

const previewLabel = (row) => {
  const t = (row?.letzte_nachricht || "").trim();
  if (!t) return "Noch kein Chat — tippen zum Starten";
  const s = row?.letzter_sender;
  const prefix = s === "mandant" ? "" : s === "kanzlei" ? "Sie: " : "";
  return prefix + t;
};

/**
 * WhatsApp-ähnliche Mandanten-Übersicht + Chat (alle Mandanten, nicht nur KPI-Liste).
 */
export default function PortalChatSuite({
  selectedMandant,
  onSelectMandant,
  showToast,
  isMobile,
  onInboxChange,
}) {
  const [inbox, setInbox] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [mobileShowChat, setMobileShowChat] = useState(false);

  const laden = useCallback(async () => {
    setLoading(true);
    try {
      const [inboxRes, mandRes] = await Promise.allSettled([
        getPortalChatInbox(),
        getMandanten(),
      ]);
      let rows = [];
      if (inboxRes.status === "fulfilled") {
        const d = inboxRes.value?.data || inboxRes.value;
        rows = Array.isArray(d?.inbox) ? d.inbox : [];
      }
      if (mandRes.status === "fulfilled") {
        const raw = mandRes.value;
        let liste = [];
        if (Array.isArray(raw?.data)) liste = raw.data;
        else if (raw?.data && typeof raw.data === "object" && !Array.isArray(raw.data)) {
          liste = Object.entries(raw.data).map(([name, v]) => ({ name, ...v }));
        } else if (Array.isArray(raw)) liste = raw;
        else if (raw && typeof raw === "object") {
          liste = Object.entries(raw).map(([name, v]) => ({ name, ...v }));
        }
        const namen = new Set(
          liste.map((m) => (typeof m === "string" ? m : m?.name || m?.mandant)).filter(Boolean),
        );
        const byName = Object.fromEntries(rows.map((r) => [r.mandant, r]));
        rows = [...namen].sort((a, b) => a.localeCompare(b, "de")).map((name) => {
          if (byName[name]) return byName[name];
          return {
            mandant: name,
            letzte_nachricht: "",
            letzte_zeit: "",
            letzter_sender: "",
            anzahl: 0,
            hat_chat: false,
          };
        });
        rows.sort((a, b) => (b.letzte_zeit || "").localeCompare(a.letzte_zeit || ""));
      }
      setInbox(rows);
      onInboxChange?.();
    } catch (e) {
      if (e?.status !== 429) {
        showToast?.(e.message || "Chat-Liste konnte nicht geladen werden", "error");
      }
      setInbox([]);
    } finally {
      setLoading(false);
    }
  }, [showToast, onInboxChange]);

  useEffect(() => {
    laden();
    const t = setInterval(laden, 120000);
    return () => clearInterval(t);
  }, [laden]);

  useEffect(() => {
    if (!selectedMandant) setMobileShowChat(false);
  }, [selectedMandant]);

  const gefiltert = inbox.filter((row) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return String(row.mandant || "").toLowerCase().includes(needle);
  });

  const waehle = (name) => {
    onSelectMandant(name);
    if (isMobile) setMobileShowChat(true);
  };

  const zurueck = () => {
    setMobileShowChat(false);
    onSelectMandant("");
  };

  const listePanel = (
    <div
      style={{
        width: isMobile ? "100%" : 320,
        minWidth: isMobile ? undefined : 280,
        maxWidth: isMobile ? "100%" : 380,
        borderRight: isMobile ? "none" : "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        height: isMobile ? undefined : "100%",
        alignSelf: "stretch",
        flexShrink: 0,
        flex: isMobile ? 1 : undefined,
        background: "var(--bg2)",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ fontFamily: "var(--font-head)", fontSize: 18, color: "var(--text)", marginBottom: 10 }}>
          Mandanten
        </div>
        <input
          type="search"
          placeholder="Suchen…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid var(--border2)",
            background: "var(--bg3)",
            color: "var(--text)",
            fontSize: 14,
          }}
        />
      </div>
      <div style={{ flex: 1, overflowY: "auto", WebkitOverflowScrolling: "touch" }}>
        {loading && !inbox.length ? (
          <div style={{ padding: 20, color: "var(--text3)", fontSize: 13 }}>Lade Mandanten…</div>
        ) : gefiltert.length === 0 ? (
          <div style={{ padding: 20, color: "var(--text3)", fontSize: 13 }}>Keine Mandanten gefunden</div>
        ) : (
          gefiltert.map((row) => {
            const name = row.mandant;
            const active = selectedMandant === name;
            return (
              <button
                key={name}
                type="button"
                onClick={() => waehle(name)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  border: "none",
                  borderBottom: "1px solid var(--border)",
                  background: active ? "color-mix(in srgb, var(--accent) 10%, var(--bg2))" : "transparent",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: "50%",
                    background: "color-mix(in srgb, var(--accent) 22%, var(--bg3))",
                    color: "var(--accent)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 15,
                    flexShrink: 0,
                  }}
                >
                  {initialen(name)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      fontSize: 14,
                      color: active ? "var(--accent)" : "var(--text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {name}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text3)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      marginTop: 2,
                    }}
                  >
                    {previewLabel(row)}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
                  <div style={{ fontSize: 11, color: "var(--text3)" }}>
                    {fmtZeitKurz(row.letzte_zeit)}
                  </div>
                  {row.ungelesen > 0 ? (
                    <span
                      style={{
                        minWidth: 20,
                        height: 20,
                        padding: "0 6px",
                        borderRadius: 10,
                        background: "var(--accent)",
                        color: "#fff",
                        fontSize: 11,
                        fontWeight: 700,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      {row.ungelesen > 99 ? "99+" : row.ungelesen}
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );

  const chatPanel = (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        minWidth: 0,
        height: isMobile ? undefined : "100%",
        overflow: "hidden",
        background: "var(--bg)",
      }}
    >
      {isMobile ? (
        <button
          type="button"
          onClick={zurueck}
          style={{
            alignSelf: "flex-start",
            margin: "10px 12px 0",
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--bg2)",
            color: "var(--text2)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          ← Mandanten
        </button>
      ) : null}
      {selectedMandant ? (
        <PortalChat
          mandantName={selectedMandant}
          showToast={showToast}
          embedded
          fillHeight
          onRead={onInboxChange}
          onSent={() => {
            laden();
            onInboxChange?.();
          }}
        />
      ) : (
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text3)",
            fontSize: 14,
            padding: 24,
            textAlign: "center",
          }}
        >
          Wählen Sie links einen Mandanten, um den Chat zu öffnen.
        </div>
      )}
    </div>
  );

  if (isMobile) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
        {mobileShowChat && selectedMandant ? chatPanel : listePanel}
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "row",
        minHeight: 0,
        height: "100%",
        overflow: "hidden",
        border: "1px solid var(--border)",
        borderRadius: 12,
        background: "var(--bg2)",
      }}
    >
      {listePanel}
      {chatPanel}
    </div>
  );
}
