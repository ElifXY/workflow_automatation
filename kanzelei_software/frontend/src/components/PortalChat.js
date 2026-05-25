import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  getPortalChat,
  sendPortalChat,
  sendPortalChatAufgabe,
  sendPortalChatDokument,
  sendPortalChatUnterschrift,
  sendPortalChatUpload,
  patchPortalChat,
  deletePortalChat,
  getPortalDokumentQuellen,
  getPortalDokumentQuelleInhalt,
  getPortalUnterschriftBild,
  getPortalUnterschriftDokument,
} from "../api";

const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = reader.result || "";
      resolve(String(raw).includes(",") ? String(raw).split(",")[1] : raw);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

const flattenBaumDateien = (knoten, zielPfad = "") => {
  const out = [];
  (knoten || []).forEach((k) => {
    const pfad = k.pfad || zielPfad || k.name;
    (k.dateien || []).forEach((d) => out.push({ ...d, ordner_pfad: d.ordner_pfad || pfad }));
    if (k.kinder?.length) out.push(...flattenBaumDateien(k.kinder, pfad));
  });
  return out;
};

const DokumentExplorer = ({ mandantName, selected, onSelect, showToast }) => {
  const [baum, setBaum] = useState([]);
  const [alle, setAlle] = useState([]);
  const [aktOrdner, setAktOrdner] = useState("");
  const [laden, setLaden] = useState(false);

  useEffect(() => {
    if (!mandantName) return;
    let cancelled = false;
    (async () => {
      setLaden(true);
      try {
        const d = await getPortalDokumentQuellen(mandantName);
        const payload = d?.data || d;
        const b = payload?.baum || [];
        const flat = Array.isArray(payload?.dateien) && payload.dateien.length
          ? payload.dateien
          : flattenBaumDateien(b);
        if (!cancelled) {
          setBaum(b);
          setAlle(flat);
          if (!aktOrdner && flat.length) setAktOrdner(flat[0].ordner_pfad || "");
        }
      } catch (e) {
        if (!cancelled) {
          setBaum([]);
          setAlle([]);
          showToast?.(e.message || "Dokumente konnten nicht geladen werden", "error");
        }
      } finally {
        if (!cancelled) setLaden(false);
      }
    })();
    return () => { cancelled = true; };
  }, [mandantName, showToast]);

  const ordnerListe = [...new Set(alle.map((x) => x.ordner_pfad || "Sonstiges"))].sort();
  const dateienImOrdner = alle.filter(
    (x) => (x.ordner_pfad || "Sonstiges") === (aktOrdner || ordnerListe[0] || "Sonstiges")
  );

  return (
    <div style={{ display: "flex", gap: 8, minHeight: 140, marginBottom: 10 }}>
      <div style={{
        flex: "0 0 38%",
        maxHeight: 200,
        overflowY: "auto",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 6,
        background: "var(--bg)",
      }}>
        <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 6, textTransform: "uppercase" }}>
          Ordner {laden ? "…" : `(${alle.length} Dateien)`}
        </div>
        {ordnerListe.length === 0 && !laden ? (
          <div style={{ fontSize: 11, color: "var(--text3)", padding: 8 }}>Keine Dokumente im Archiv/Uploads</div>
        ) : (
          ordnerListe.map((o) => (
            <button
              key={o}
              type="button"
              onClick={() => setAktOrdner(o)}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                padding: "6px 8px",
                marginBottom: 4,
                borderRadius: 6,
                border: "none",
                cursor: "pointer",
                fontSize: 11,
                background: aktOrdner === o ? "rgba(200,169,110,0.15)" : "transparent",
                color: aktOrdner === o ? "var(--accent)" : "var(--text2)",
              }}
            >
              📁 {o}
            </button>
          ))
        )}
      </div>
      <div style={{
        flex: 1,
        maxHeight: 200,
        overflowY: "auto",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 6,
        background: "var(--bg)",
      }}>
        <div style={{ fontSize: 10, color: "var(--text3)", marginBottom: 6, textTransform: "uppercase" }}>
          Dateien
        </div>
        {dateienImOrdner.length === 0 ? (
          <div style={{ fontSize: 11, color: "var(--text3)", padding: 8 }}>
            {laden ? "Lade…" : "In diesem Ordner keine Dateien"}
          </div>
        ) : (
          dateienImOrdner.map((d) => {
            const key = `${d.quelle}:${d.id}`;
            const active = selected?.quelle === d.quelle && selected?.id === d.id;
            return (
              <button
                key={key}
                type="button"
                disabled={d.datei_vorhanden === false}
                onClick={() => onSelect(d)}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "7px 8px",
                  marginBottom: 4,
                  borderRadius: 6,
                  border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                  cursor: d.datei_vorhanden === false ? "not-allowed" : "pointer",
                  fontSize: 11,
                  opacity: d.datei_vorhanden === false ? 0.45 : 1,
                  background: active ? "rgba(200,169,110,0.12)" : "var(--bg2)",
                  color: "var(--text)",
                }}
              >
                📄 {d.dateiname}
                {d.datei_vorhanden === false ? " (Datei fehlt auf Server)" : ""}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};

const fmtZeit = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
};

const ChatBubble = ({ msg, mandantName, showToast, onRefresh }) => {
  const sender = msg.sender || "system";
  const isKanzlei = sender === "kanzlei";
  const isMandant = sender === "mandant";
  const meta = msg.meta || {};
  const refs = msg.refs || {};
  const align = isMandant ? "flex-end" : isKanzlei ? "flex-start" : "center";
  const bg = isMandant
    ? "rgba(200,169,110,0.12)"
    : isKanzlei
      ? "var(--bg)"
      : "transparent";
  const border = isMandant
    ? "1px solid rgba(200,169,110,0.3)"
    : isKanzlei
      ? "1px solid var(--border)"
      : "none";

  let body = <div style={{ whiteSpace: "pre-wrap" }}>{msg.text}</div>;

  if (msg.typ === "aufgabe") {
    const erledigt = !!meta.aufgabe_erledigt;
    body = (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>📋 Aufgabe</div>
        <div>{meta.aufgabe_beschreibung || msg.text}</div>
        <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 4 }}>
          Frist: {meta.aufgabe_frist || "—"} · {erledigt ? "✓ erledigt" : "offen"}
        </div>
      </div>
    );
  } else if (msg.typ === "unterschrift_anfrage") {
    const uid = refs.unterschrift_id;
    const st = meta.unterschrift_status || "ausstehend";
    body = (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>✍ Unterschrift</div>
        <div>{meta.dokumentname || msg.text}</div>
        <div style={{ fontSize: 11, color: st === "unterschrieben" ? "var(--green)" : "var(--text3)", marginTop: 4 }}>
          Status: {st}
        </div>
        {isKanzlei && uid && st === "unterschrieben" ? (
          <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={{ fontSize: 10, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", color: "var(--text2)" }}
              onClick={async () => {
                try {
                  const d = await getPortalUnterschriftDokument(mandantName, uid);
                  const p = d?.data || d;
                  const b64 = p?.dokument_b64;
                  const typ = (p?.dokumenttyp || "application/pdf").includes("pdf") ? "application/pdf" : p?.dokumenttyp;
                  if (!b64) { showToast?.("Kein Dokument", "error"); return; }
                  const w = window.open("", "_blank");
                  if (w) {
                    w.document.title = p?.dokumentname || "Dokument";
                    if (typ.includes("pdf")) {
                      w.document.write(`<embed width="100%" height="100%" src="data:application/pdf;base64,${b64}" type="application/pdf"/>`);
                    } else {
                      w.document.write(`<img style="max-width:100%" src="data:${typ};base64,${b64}"/>`);
                    }
                  }
                } catch (e) { showToast?.(e.message, "error"); }
              }}
            >
              📄 Dokument
            </button>
            <button
              type="button"
              style={{ fontSize: 10, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", color: "var(--text2)" }}
              onClick={async () => {
                try {
                  const d = await getPortalUnterschriftBild(mandantName, uid);
                  const p = d?.data || d;
                  const b64 = p?.unterschrift_b64;
                  if (!b64) { showToast?.("Keine Unterschrift gespeichert", "error"); return; }
                  const w = window.open("", "_blank");
                  if (w) {
                    w.document.title = "Unterschrift";
                    w.document.write(`<img style="max-width:100%;background:#fff;padding:20px" src="data:image/png;base64,${b64}"/>`);
                  }
                } catch (e) { showToast?.(e.message, "error"); }
              }}
            >
              ✍ Unterschrift ansehen
            </button>
          </div>
        ) : null}
      </div>
    );
  } else if (msg.typ === "dokument_anfrage") {
    const offen = meta.dokument_erledigt_am || refs.upload_id
      ? false
      : meta.dokument_offen !== false;
    body = (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>📄 Dokument anfordern</div>
        <div>{meta.dokument_name || refs.dokument_name || msg.text}</div>
        <div style={{ fontSize: 11, color: offen ? "var(--text3)" : "var(--green)", marginTop: 4 }}>
          {offen ? "Wartet auf Upload vom Mandanten" : "✓ eingereicht"}
        </div>
      </div>
    );
  } else if (msg.typ === "upload") {
    body = <div>📎 {meta.dateiname || msg.text}</div>;
  } else if (msg.typ === "aufgabe_status") {
    body = (
      <div style={{ fontSize: 12, color: meta.aufgabe_erledigt ? "var(--green)" : "var(--text2)" }}>
        {msg.text}
      </div>
    );
  } else {
    const bearbeitet = meta.bearbeitet_am ? (
      <span style={{ fontSize: 10, color: "var(--text3)" }}> (bearbeitet)</span>
    ) : null;
    body = (
      <div style={{ whiteSpace: "pre-wrap" }}>
        {msg.text}
        {bearbeitet}
      </div>
    );
  }

  if (sender === "system") {
    return (
      <div style={{ textAlign: "center", fontSize: 11, color: "var(--text3)", margin: "6px 0" }}>
        {msg.text} · {fmtZeit(msg.zeit)}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", justifyContent: align, marginBottom: 8 }}>
      <div
        style={{
          maxWidth: "85%",
          padding: "10px 12px",
          borderRadius: 12,
          background: bg,
          border,
          fontSize: 13,
          lineHeight: 1.5,
        }}
      >
        {body}
        {isKanzlei && !meta.geloescht && msg.id ? (
          <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={{ fontSize: 10, padding: "3px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", color: "var(--text2)" }}
              onClick={async () => {
                const neu = window.prompt("Nachricht bearbeiten:", msg.text || "");
                if (neu === null) return;
                const t = neu.trim();
                if (!t) { showToast?.("Text leer", "error"); return; }
                try {
                  await patchPortalChat(mandantName, msg.id, t);
                  showToast?.("Bearbeitet", "success");
                  onRefresh?.();
                } catch (e) { showToast?.(e.message, "error"); }
              }}
            >
              Bearbeiten
            </button>
            <button
              type="button"
              style={{ fontSize: 10, padding: "3px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", color: "var(--red)" }}
              onClick={async () => {
                if (!window.confirm("Nachricht löschen?")) return;
                try {
                  await deletePortalChat(mandantName, msg.id);
                  showToast?.("Gelöscht", "success");
                  onRefresh?.();
                } catch (e) { showToast?.(e.message, "error"); }
              }}
            >
              Löschen
            </button>
          </div>
        ) : null}
        <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 6 }}>
          {isKanzlei ? "Kanzlei" : "Mandant"} · {fmtZeit(msg.zeit)}
          {isMandant && meta.gelesen_von_kanzlei_am ? (
            <span style={{ marginLeft: 6, color: "var(--green)" }}>
              · Gelesen {fmtZeit(meta.gelesen_von_kanzlei_am)}
            </span>
          ) : null}
          {isKanzlei && meta.gelesen_von_mandant_am ? (
            <span style={{ marginLeft: 6, color: "var(--green)" }}>
              · Gelesen {fmtZeit(meta.gelesen_von_mandant_am)}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
};

export default function PortalChat({
  mandantName,
  showToast,
  embedded = false,
  fillHeight = false,
  onSent,
  onRead,
}) {
  const [msgs, setMsgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState(null);
  const [aufgabeForm, setAufgabeForm] = useState({ beschreibung: "", frist: "", hinweis: "" });
  const [dokForm, setDokForm] = useState({ name: "", beschreibung: "", frist: "" });
  const [sigFile, setSigFile] = useState(null);
  const [sigAusArchiv, setSigAusArchiv] = useState(null);
  const [sigBetreff, setSigBetreff] = useState("Bitte unterzeichnen");
  const [sigQuelle, setSigQuelle] = useState("explorer");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadKategorie, setUploadKategorie] = useState("Sonstiges");
  const [uploadBeschreibung, setUploadBeschreibung] = useState("");
  const endRef = useRef(null);

  const laden = useCallback(async () => {
    if (!mandantName) {
      setMsgs([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const d = await getPortalChat(mandantName);
      const list = d?.nachrichten || d?.data?.nachrichten || [];
      setMsgs(Array.isArray(list) ? list : []);
    } catch (e) {
      showToast?.(e.message || "Chat konnte nicht geladen werden", "error");
      setMsgs([]);
    } finally {
      setLoading(false);
      onRead?.();
    }
  }, [mandantName, showToast, onRead]);

  useEffect(() => {
    laden();
    const t = setInterval(laden, 20000);
    return () => clearInterval(t);
  }, [laden]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const sendText = async () => {
    const t = text.trim();
    if (!t) return;
    setSending(true);
    try {
      await sendPortalChat(mandantName, t);
      setText("");
      await laden();
      onSent?.();
    } catch (e) {
      showToast?.(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  const sendAufgabe = async () => {
    if (!aufgabeForm.beschreibung.trim() || !aufgabeForm.frist.trim()) {
      showToast?.("Beschreibung und Frist erforderlich", "error");
      return;
    }
    setSending(true);
    try {
      await sendPortalChatAufgabe(mandantName, {
        beschreibung: aufgabeForm.beschreibung.trim(),
        frist: aufgabeForm.frist,
        hinweis: aufgabeForm.hinweis.trim(),
        prioritaet: "normal",
        portal_sichtbar: true,
      });
      showToast?.("Aufgabe im Chat erstellt — sichtbar im Mandantenportal", "success");
      setMode(null);
      setAufgabeForm({ beschreibung: "", frist: "", hinweis: "" });
      await laden();
      onSent?.();
    } catch (e) {
      showToast?.(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  const sendDokument = async () => {
    if (!dokForm.name.trim()) {
      showToast?.("Dokumentname erforderlich", "error");
      return;
    }
    setSending(true);
    try {
      await sendPortalChatDokument(mandantName, {
        dokument_name: dokForm.name.trim(),
        beschreibung: dokForm.beschreibung.trim(),
        frist: dokForm.frist || null,
        portal_sichtbar: true,
      });
      showToast?.("Dokument angefordert", "success");
      setMode(null);
      setDokForm({ name: "", beschreibung: "", frist: "" });
      await laden();
      onSent?.();
    } catch (e) {
      showToast?.(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  const sendUpload = async () => {
    if (!uploadFile) {
      showToast?.("Datei wählen", "error");
      return;
    }
    setSending(true);
    try {
      const b64 = await fileToBase64(uploadFile);
      await sendPortalChatUpload(mandantName, {
        dateiname: uploadFile.name,
        inhalt_b64: b64,
        dateityp: uploadFile.type || "application/octet-stream",
        kategorie: uploadKategorie.trim() || "Sonstiges",
        beschreibung: uploadBeschreibung.trim(),
        portal_sichtbar: true,
      });
      showToast?.("Dokument im Portal bereitgestellt", "success");
      setMode(null);
      setUploadFile(null);
      setUploadBeschreibung("");
      await laden();
      onSent?.();
    } catch (e) {
      showToast?.(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  const sendUnterschrift = async () => {
    setSending(true);
    try {
      let dokumentname = "";
      let dokument_b64 = "";
      let dokumenttyp = "application/pdf";
      if (sigQuelle === "datei") {
        if (!sigFile) {
          showToast?.("PDF wählen", "error");
          return;
        }
        dokumentname = sigFile.name;
        dokument_b64 = await fileToBase64(sigFile);
        dokumenttyp = sigFile.type || "application/pdf";
      } else {
        if (!sigAusArchiv?.id || !sigAusArchiv?.quelle) {
          showToast?.("Dokument im Explorer wählen", "error");
          return;
        }
        const inh = await getPortalDokumentQuelleInhalt(mandantName, sigAusArchiv.quelle, sigAusArchiv.id);
        const p = inh?.data || inh;
        dokumentname = p?.dateiname || sigAusArchiv.dateiname;
        dokument_b64 = p?.inhalt_b64 || "";
        dokumenttyp = p?.dateityp || "application/pdf";
        if (!dokument_b64 || dokument_b64.length < 20) {
          showToast?.("Dateiinhalt leer — Datei fehlt evtl. auf dem Server", "error");
          return;
        }
      }
      await sendPortalChatUnterschrift(mandantName, {
        dokumentname,
        dokument_b64,
        dokumenttyp,
        betreff: sigBetreff.trim() || "Bitte unterzeichnen",
        hinweis: "",
        gueltig_tage: 30,
        portal_sichtbar: true,
      });
      showToast?.("Unterschrift im Chat angefordert", "success");
      setMode(null);
      setSigFile(null);
      setSigAusArchiv(null);
      await laden();
      onSent?.();
    } catch (e) {
      showToast?.(e.message, "error");
    } finally {
      setSending(false);
    }
  };

  const inputStyle = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    color: "var(--text)",
    fontSize: 13,
    marginBottom: 8,
  };

  if (!mandantName) {
    return (
      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--text3)", fontSize: 14, padding: 24, textAlign: "center",
      }}>
        Bitte links einen Mandanten für den Chat auswählen.
      </div>
    );
  }

  const msgAreaStyle = {
    flex: 1,
    overflowY: "auto",
    padding: "4px 2px",
    marginBottom: 12,
    border: "1px solid var(--border)",
    borderRadius: 10,
    background: "var(--bg)",
    minHeight: fillHeight ? 0 : 200,
    maxHeight: fillHeight ? "none" : 360,
  };

  return (
    <div
      style={{
        background: embedded ? "transparent" : "var(--bg2)",
        border: embedded ? "none" : "1px solid var(--border)",
        borderRadius: embedded ? 0 : 14,
        padding: embedded ? "12px 16px" : 16,
        display: "flex",
        flexDirection: "column",
        minHeight: fillHeight ? 0 : 420,
        flex: fillHeight ? 1 : undefined,
        height: fillHeight ? "100%" : undefined,
        overflow: fillHeight ? "hidden" : undefined,
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexShrink: 0, flex: "0 0 auto" }}>
        <div style={{ fontFamily: "'DM Serif Display', serif", fontSize: embedded ? 20 : 17 }}>
          {embedded ? mandantName : `Portal-Chat — ${mandantName}`}
        </div>
        <button
          type="button"
          onClick={laden}
          disabled={loading}
          style={{
            fontSize: 11,
            padding: "4px 10px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--text2)",
            cursor: "pointer",
          }}
        >
          {loading ? "…" : "Aktualisieren"}
        </button>
      </div>

      <div style={msgAreaStyle}>
        {loading && !msgs.length ? (
          <div style={{ padding: 20, color: "var(--text3)", fontSize: 12 }}>Lade Chat…</div>
        ) : !msgs.length ? (
          <div style={{ padding: 20, color: "var(--text3)", fontSize: 12, textAlign: "center" }}>
            Noch kein Verlauf — erste Nachricht senden.
          </div>
        ) : (
          msgs.map((m) => (
            <ChatBubble
              key={m.id}
              msg={m}
              mandantName={mandantName}
              showToast={showToast}
              onRefresh={laden}
            />
          ))
        )}
        <div ref={endRef} />
      </div>

      <div style={{ flexShrink: 0 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {[
          ["text", "Nachricht"],
          ["aufgabe", "Aufgabe"],
          ["dokument", "anfordern"],
          ["upload", "hochladen"],
          ["unterschrift", "Unterschrift"],
        ].map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setMode(mode === k ? null : k)}
            style={{
              fontSize: 11,
              padding: "5px 10px",
              borderRadius: 8,
              border: `1px solid ${mode === k ? "var(--accent)" : "var(--border)"}`,
              background: mode === k ? "rgba(200,169,110,0.15)" : "transparent",
              color: mode === k ? "var(--accent)" : "var(--text2)",
              cursor: "pointer",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "aufgabe" && (
        <div style={{ marginBottom: 10, padding: 10, border: "1px dashed var(--border)", borderRadius: 8 }}>
          <input
            placeholder="Aufgabe (z. B. Belege Q1 hochladen)"
            value={aufgabeForm.beschreibung}
            onChange={(e) => setAufgabeForm((p) => ({ ...p, beschreibung: e.target.value }))}
            style={inputStyle}
          />
          <input
            type="date"
            value={aufgabeForm.frist}
            onChange={(e) => setAufgabeForm((p) => ({ ...p, frist: e.target.value }))}
            style={inputStyle}
          />
          <input
            placeholder="Hinweis (optional)"
            value={aufgabeForm.hinweis}
            onChange={(e) => setAufgabeForm((p) => ({ ...p, hinweis: e.target.value }))}
            style={inputStyle}
          />
          <button type="button" onClick={sendAufgabe} disabled={sending} style={{ fontSize: 12, padding: "6px 12px" }}>
            Aufgabe senden
          </button>
        </div>
      )}

      {mode === "dokument" && (
        <div style={{ marginBottom: 10, padding: 10, border: "1px dashed var(--border)", borderRadius: 8 }}>
          <input
            placeholder="Dokumentname"
            value={dokForm.name}
            onChange={(e) => setDokForm((p) => ({ ...p, name: e.target.value }))}
            style={inputStyle}
          />
          <input
            placeholder="Beschreibung"
            value={dokForm.beschreibung}
            onChange={(e) => setDokForm((p) => ({ ...p, beschreibung: e.target.value }))}
            style={inputStyle}
          />
          <button type="button" onClick={sendDokument} disabled={sending} style={{ fontSize: 12, padding: "6px 12px" }}>
            Dokument anfordern
          </button>
        </div>
      )}

      {mode === "upload" && (
        <div style={{ marginBottom: 10, padding: 10, border: "1px dashed var(--border)", borderRadius: 8 }}>
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/*"
            onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            style={{ fontSize: 12, marginBottom: 8, width: "100%" }}
          />
          <input
            placeholder="Kategorie (z. B. Belege)"
            value={uploadKategorie}
            onChange={(e) => setUploadKategorie(e.target.value)}
            style={inputStyle}
          />
          <input
            placeholder="Beschreibung (optional)"
            value={uploadBeschreibung}
            onChange={(e) => setUploadBeschreibung(e.target.value)}
            style={inputStyle}
          />
          <button type="button" onClick={sendUpload} disabled={sending} style={{ fontSize: 12, padding: "6px 12px" }}>
            Für Mandant bereitstellen
          </button>
        </div>
      )}

      {mode === "unterschrift" && (
        <div style={{ marginBottom: 10, padding: 10, border: "1px dashed var(--border)", borderRadius: 8 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            {[
              ["explorer", "Aus Archiv"],
              ["datei", "Datei hochladen"],
            ].map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setSigQuelle(k)}
                style={{
                  fontSize: 11,
                  padding: "5px 10px",
                  borderRadius: 8,
                  border: `1px solid ${sigQuelle === k ? "var(--accent)" : "var(--border)"}`,
                  background: sigQuelle === k ? "rgba(200,169,110,0.12)" : "transparent",
                  color: sigQuelle === k ? "var(--accent)" : "var(--text2)",
                  cursor: "pointer",
                }}
              >
                {label}
              </button>
            ))}
          </div>
          {sigQuelle === "explorer" ? (
            <>
              <DokumentExplorer
                mandantName={mandantName}
                selected={sigAusArchiv}
                onSelect={(d) => setSigAusArchiv(d)}
                showToast={showToast}
              />
              {sigAusArchiv ? (
                <div style={{ fontSize: 11, color: "var(--green)", marginBottom: 8 }}>
                  ✓ {sigAusArchiv.dateiname}
                </div>
              ) : null}
            </>
          ) : (
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => setSigFile(e.target.files?.[0] || null)}
              style={{ fontSize: 12, marginBottom: 8, width: "100%" }}
            />
          )}
          <input
            placeholder="Betreff"
            value={sigBetreff}
            onChange={(e) => setSigBetreff(e.target.value)}
            style={inputStyle}
          />
          <button type="button" onClick={sendUnterschrift} disabled={sending} style={{ fontSize: 12, padding: "6px 12px" }}>
            Unterschrift anfordern
          </button>
        </div>
      )}

      {(!mode || mode === "text") && (
        <div style={{ display: "flex", gap: 8 }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Nachricht an Mandant…"
            rows={2}
            style={{ ...inputStyle, flex: 1, marginBottom: 0, resize: "vertical" }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendText();
              }
            }}
          />
          <button
            type="button"
            onClick={sendText}
            disabled={sending}
            style={{
              alignSelf: "flex-end",
              padding: "10px 16px",
              borderRadius: 10,
              border: "none",
              background: "var(--accent)",
              color: "var(--on-accent)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Senden
          </button>
        </div>
      )}
      </div>
    </div>
  );
}
