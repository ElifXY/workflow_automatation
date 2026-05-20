// ============================================================
// PORTAL-CHAT
// ============================================================
let _chatPoll = null;

function formatChatZeit(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    return "";
  }
}

function renderChatNachricht(n) {
  const sender = n.sender || "system";
  const side =
    sender === "mandant"
      ? "mandant"
      : sender === "kanzlei"
        ? "kanzlei"
        : "system";
  const zeit = formatChatZeit(n.zeit || n.timestamp);
  const meta = n.meta || {};
  const refs = n.refs || {};
  let inner = `<div>${esc(n.text || "")}</div>`;

  if (n.typ === "aufgabe") {
    const erledigt = !!meta.aufgabe_erledigt;
    const aid = refs.aufgabe_id;
    inner = `<div class="chat-card"><strong>📋 Aufgabe</strong><br>${esc(
      meta.aufgabe_beschreibung || n.text
    )}<br>
      <span style="color:var(--text3);font-size:12px">Frist: ${esc(
        meta.aufgabe_frist || "—"
      )}</span>
      ${
        aid
          ? `<button class="btn btn-sm ${
              erledigt ? "btn-ghost" : "btn-success"
            } btn-full" onclick="chatAufgabeToggle('${aid}')">${
              erledigt ? "✓ Erledigt" : "Als erledigt markieren"
            }</button>`
          : ""
      }
    </div>`;
  } else if (n.typ === "unterschrift_anfrage") {
    const st = meta.unterschrift_status || "ausstehend";
    const uid = refs.unterschrift_id;
    inner = `<div class="chat-card"><strong>✍ Unterschrift</strong><br>${esc(
      meta.dokumentname || n.text
    )}<br>
      <span class="badge" style="background:var(--bg3);color:var(--text2)">${esc(st)}</span>
      ${
        uid && st === "ausstehend"
          ? `<button class="btn btn-primary btn-sm btn-full" style="margin-top:8px" onclick="oeffneUnterschrift('${uid}')">Jetzt unterzeichnen</button>`
          : ""
      }
    </div>`;
  } else if (n.typ === "dokument_anfrage") {
    const offen = meta.dokument_offen !== false;
    inner = `<div class="chat-card"><strong>📄 Dokument anfordern</strong><br>${esc(
      meta.dokument_name || refs.dokument_name || n.text
    )}
      ${
        offen
          ? `<button class="btn btn-ghost btn-sm btn-full" style="margin-top:8px" onclick="wechsleTab('dokumente')">Zum Upload</button>`
          : `<span style="color:var(--green);font-size:12px"> ✓ eingereicht</span>`
      }
    </div>`;
  } else if (n.typ === "upload") {
    inner = `<div class="chat-card">📎 ${esc(meta.dateiname || n.text)}</div>`;
  } else if (n.typ === "unterschrift_status" || n.typ === "aufgabe_status") {
    inner = `<div style="font-size:13px">${esc(n.text || "")}</div>`;
  } else {
    inner = `<div>${esc(n.text || "")}</div>`;
  }

  if (side === "system") {
    return `<div class="chat-bubble system">${inner}<div class="chat-meta">${zeit}</div></div>`;
  }
  return `<div class="chat-bubble ${side}">${inner}<div class="chat-meta">${
    sender === "kanzlei" ? "Kanzlei" : "Sie"
  } · ${zeit}</div></div>`;
}

async function ladeChat() {
  const el = document.getElementById("chat-msgs");
  if (!el) return;
  try {
    const d = await api("/portal/chat");
    const lst = (d.nachrichten || [])
      .slice()
      .sort((a, b) => (a.zeit || "").localeCompare(b.zeit || ""));
    if (!lst.length) {
      el.innerHTML =
        '<div style="color:var(--text3);text-align:center;padding:24px">Noch keine Nachrichten — schreiben Sie Ihrer Kanzlei.</div>';
      return;
    }
    el.innerHTML = lst.map(renderChatNachricht).join("");
    el.scrollTop = el.scrollHeight;
  } catch (e) {
    el.innerHTML = `<div style="color:var(--red)">${esc(e.message)}</div>`;
  }
}

async function chatSenden() {
  const ta = document.getElementById("chat-text");
  const text = (ta?.value || "").trim();
  if (!text) {
    toast("Bitte Text eingeben", "error");
    return;
  }
  try {
    await api("/portal/chat", { method: "POST", body: JSON.stringify({ text }) });
    ta.value = "";
    await ladeChat();
  } catch (e) {
    toast(e.message, "error");
  }
}

function chatDateiWaehlen() {
  document.getElementById("chat-file")?.click();
}

async function chatDateiSenden(ev) {
  const file = ev.target.files?.[0];
  if (!file) return;
  try {
    const b64 = await fileToB64(file);
    await api("/portal/dokumente/hochladen", {
      method: "POST",
      body: JSON.stringify({
        dateiname: file.name,
        dateityp: file.type || "application/octet-stream",
        inhalt_b64: b64,
        beschreibung: "Im Chat hochgeladen",
      }),
    });
    ev.target.value = "";
    await ladeChat();
    toast("Datei gesendet", "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function chatAufgabeToggle(aid) {
  try {
    await api(`/portal/aufgaben/${aid}/erledigen`, { method: "POST" });
    await ladeChat();
    toast("Aufgabe aktualisiert", "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

function startChatPoll() {
  if (_chatPoll) clearInterval(_chatPoll);
  _chatPoll = setInterval(() => {
    if (document.getElementById("tab-chat")?.classList.contains("active")) ladeChat();
  }, 45000);
}
