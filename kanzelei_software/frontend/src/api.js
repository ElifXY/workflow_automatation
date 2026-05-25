// ============================================================
// KANZLEI AI — API CLIENT v2.0
// Alle Endpunkte passend zur neuen api.py
// ============================================================

const BASE_URL = process.env.REACT_APP_API_URL || "/api";
let _refreshInFlight = null;
const AUTH_GRACE_KEY = "auth_login_grace_until";

export const markAuthLoginGrace = (ms = 1800000) => {
  try {
    sessionStorage.setItem(AUTH_GRACE_KEY, String(Date.now() + ms));
  } catch {}
};

export const inAuthLoginGrace = () => {
  try {
    const until = Number(sessionStorage.getItem(AUTH_GRACE_KEY) || "0");
    return until > Date.now();
  } catch {
    return false;
  }
};

const isJwtShape = (t) => t.split(".").length === 3 && t.length > 40;

/** Liest ob ein gültiges Token in localStorage liegt (kein React-State nötig). */
export const readAuthed = () => {
  try {
    const t = (localStorage.getItem("kanzlei_token") || localStorage.getItem("token") || "").trim();
    if (!t) return false;
    if (isJwtShape(t)) return true;
    return t.length >= 20;
  } catch {
    return false;
  }
};

const getAccessToken = () => {
  const t = (localStorage.getItem("kanzlei_token") || localStorage.getItem("token") || "").trim();
  if (!t) return "";
  if (isJwtShape(t)) return t;
  if (t.length >= 20) return t;
  return "";
};

const getRefreshToken = () => localStorage.getItem("kanzlei_refresh_token") || "";
const setAccessToken = (token) => {
  const v = token || "";
  localStorage.setItem("kanzlei_token", v);
  localStorage.setItem("token", v);
};
const setRefreshToken = (token) => {
  if (!token) {
    localStorage.removeItem("kanzlei_refresh_token");
    return;
  }
  localStorage.setItem("kanzlei_refresh_token", token);
};
export const clearAuthStorage = () => {
  localStorage.removeItem("kanzlei_token");
  localStorage.removeItem("token");
  localStorage.removeItem("kanzlei_refresh_token");
  localStorage.removeItem("kanzlei_user");
  localStorage.removeItem("kanzlei_rolle");
  localStorage.removeItem("role");
  try {
    localStorage.removeItem("kanzlei_view_as_role");
    sessionStorage.removeItem(AUTH_GRACE_KEY);
  } catch {}
};

/** Nur explizit aufrufen (Abmelden) — kein Auto-Logout bei API-401. */
export const logoutUser = () => {
  clearAuthStorage();
  try {
    window.dispatchEvent(new CustomEvent("auth:logout"));
  } catch {}
};

export const pickBearerFromAuthBody = (body) => {
  const access = String(body?.access_token || "").trim();
  const session = String(body?.token || body?.bearer || "").trim();
  const isSession = (t) => t.length >= 20 && !isJwtShape(t);
  if (isSession(session)) return session;
  if (isSession(access)) return access;
  if (isJwtShape(session)) return session;
  if (isJwtShape(access)) return access;
  return session || access;
};

/** Login-Antwort (ok/data, ok_compat, flach) → Nutzdaten. */
export const extractLoginPayload = (raw) => {
  if (!raw || typeof raw !== "object") return {};
  let inner = raw;
  if (raw.data && typeof raw.data === "object") {
    inner = raw.data;
    if (inner.data && typeof inner.data === "object") inner = inner.data;
  }
  const token = String(raw.token || raw.bearer || inner.token || inner.bearer || "").trim();
  const access = String(raw.access_token || inner.access_token || "").trim();
  return {
    ...inner,
    ...(token ? { token } : {}),
    ...(access ? { access_token: access } : {}),
  };
};

export const parseAuthApiError = (data, status = 0) => {
  if (!data || typeof data !== "object") {
    return status ? `Anmeldung fehlgeschlagen (Fehler ${status})` : "Anmeldung fehlgeschlagen";
  }
  if (typeof data.error === "string" && data.error.trim()) return data.error.trim();
  if (typeof data.message === "string" && data.message.trim()) return data.message.trim();
  const d = data.detail ?? data.details;
  if (typeof d === "string" && d.trim()) return d.trim();
  if (Array.isArray(d)) {
    const parts = d.map((x) => {
      if (typeof x === "string") return x;
      return x?.msg || x?.message || "";
    }).filter(Boolean);
    if (parts.length) return parts.join(" ");
  }
  return status ? `Anmeldung fehlgeschlagen (Fehler ${status})` : "Anmeldung fehlgeschlagen";
};

/** Einheitlicher Login — mehrere Endpunkte/Body-Varianten, Session bevorzugt. */
export const loginUser = async ({ identity, password, signal } = {}) => {
  const idVal = String(identity || "").trim();
  const passVal = String(password || "").trim();
  if (!idVal || !passVal) {
    throw new Error("Bitte E-Mail und Passwort eingeben.");
  }

  const isEmail = idVal.includes("@");
  const bodies = isEmail
    ? [
        { email: idVal.toLowerCase(), password: passVal, passwort: passVal },
        { email: idVal.toLowerCase(), password: passVal },
      ]
    : [{ benutzername: idVal, passwort: passVal }];

  const endpoints = [`${BASE_URL}/auth/login`, `${BASE_URL}/login`];
  let lastMsg = "Anmeldung fehlgeschlagen";

  const confirmSession = async (bearer) => {
    const meRes = await fetch(`${BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${bearer}` },
      signal,
    });
    if (meRes.ok) return;
    const meData = await meRes.json().catch(() => ({}));
    throw new Error(parseAuthApiError(meData, meRes.status));
  };

  for (const url of endpoints) {
    for (const body of bodies) {
      let res;
      try {
        res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal,
        });
      } catch (e) {
        if (e?.name === "AbortError") throw e;
        lastMsg = "Server nicht erreichbar. Bitte später erneut versuchen.";
        continue;
      }

      const rawText = await res.text().catch(() => "");
      let data = {};
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch {
        data = {};
      }

      if (res.status === 502 || res.status === 503) {
        lastMsg =
          res.status === 502
            ? "Server antwortet nicht (502). Bitte API-Container prüfen: docker compose ps api"
            : parseAuthApiError(data, res.status) ||
              "System noch nicht eingerichtet — bitte zuerst Admin anlegen.";
        continue;
      }

      if (res.ok) {
        const payload = extractLoginPayload(data);
        const bearer = pickBearerFromAuthBody(payload) || pickBearerFromAuthBody(data);
        if (!bearer) {
          lastMsg = "Server hat kein gültiges Zugangs-Token geliefert.";
          continue;
        }
        setAccessToken(bearer);
        markAuthLoginGrace();
        try {
          await confirmSession(bearer);
        } catch {
          /* /api/auth/me kann auf alter API 401 (Inaktivität) liefern — Login-Token trotzdem nutzen. */
        }
        if (payload.refresh_token) setRefreshToken(payload.refresh_token);
        const role = payload.role || payload.rolle || "";
        if (role) {
          localStorage.setItem("kanzlei_rolle", role);
          localStorage.setItem("role", role);
        }
        localStorage.setItem(
          "kanzlei_user",
          payload.anzeigename || payload.benutzer || payload.benutzername || idVal
        );
        return { ...payload, token: bearer, role };
      }

      lastMsg = parseAuthApiError(data, res.status);
      if (res.status === 401 || res.status === 403) {
        const err = new Error(lastMsg);
        err.status = res.status;
        err.verifyPending = /nicht bestätigt/i.test(lastMsg);
        throw err;
      }
    }
  }

  throw new Error(lastMsg);
};

const refreshAccessToken = async () => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return "";
  if (_refreshInFlight) return _refreshInFlight;
  _refreshInFlight = (async () => {
    const res = await fetch(`${BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const body = await res.json().catch(() => ({}));
    const bearer = pickBearerFromAuthBody(body);
    if (!res.ok || !bearer) {
      clearAuthStorage();
      throw new Error(body?.detail || body?.error || "Session abgelaufen");
    }
    setAccessToken(bearer);
    if (body.refresh_token) setRefreshToken(body.refresh_token);
    return bearer;
  })();
  try {
    return await _refreshInFlight;
  } finally {
    _refreshInFlight = null;
  }
};

// ─── Generic Fetch (Auth Token + Timeout + Error Handling) ──────
export const apiFetch = async (url, options = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  const token = getAccessToken();

  try {
    const res = await fetch(BASE_URL + url, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        // Auth Token automatisch bei jedem Request
        ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });

    clearTimeout(timeout);

    let data = null;
    try { data = await res.json(); } catch { data = null; }

    if (!res.ok) {
      if (res.status === 402 && typeof window !== "undefined") {
        try {
          window.dispatchEvent(new CustomEvent("billing:paywall", { detail: data || {} }));
        } catch {}
      }
      if (res.status === 401 && !options._retryAfterRefresh) {
        const rt = getRefreshToken();
        const looksJwt = (tok) => tok.split(".").length === 3 && tok.length > 40;
        if (rt && looksJwt(rt)) {
          try {
            const newToken = await refreshAccessToken();
            return await apiFetch(url, {
              ...options,
              _retryAfterRefresh: true,
              headers: {
                ...(options.headers || {}),
                Authorization: `Bearer ${newToken}`,
              },
            });
          } catch {
            /* Kein Auto-Logout — einzelne Requests dürfen 401 liefern ohne Redirect zur Login-Seite. */
          }
        }
      }
      const msg =
        data?.error ||
        data?.detail ||
        data?.message ||
        `Server Fehler (${res.status})`;
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = res.status;
      err.apiPayload = data;
      throw err;
    }

    if (typeof window !== "undefined") {
      try {
        const quotaStatus = (res.headers.get("X-Quota-Status") || "").toLowerCase();
        if (quotaStatus === "warning" || quotaStatus === "critical") {
          window.dispatchEvent(
            new CustomEvent("billing:quota-warning", {
              detail: {
                metric: res.headers.get("X-Quota-Metric") || "",
                used: Number(res.headers.get("X-Quota-Used") || "0"),
                limit: Number(res.headers.get("X-Quota-Limit") || "0"),
                percent: Number(res.headers.get("X-Quota-Percent") || "0"),
                status: quotaStatus,
                plan: res.headers.get("X-Quota-Plan") || "",
                recommended_plan: res.headers.get("X-Quota-Recommend-Plan") || "",
                upgrade_url: res.headers.get("X-Quota-Upgrade-Url") || "",
              },
            })
          );
        }
      } catch {}
    }

    return data;

  } catch (err) {
    clearTimeout(timeout);
    if (err.name === "AbortError") throw new Error("Zeitüberschreitung. Bitte erneut versuchen.");
    throw err;
  }
};

/** Alias: einheitliche ``api(url, opts)``-Schicht für neue Komponenten */
export const api = apiFetch;

/** GET mit gleichem Auth-Handling wie ``apiFetch`` */
export const apiGet = (path) => apiFetch(path);

/** Antwort von GET /mandanten/…/aufgaben (ok_compat: top-level oder data.aufgaben) */
export function extrahiereAufgabenArray(resp) {
  if (resp == null || typeof resp !== "object") return [];
  const candidates = [
    resp.aufgaben,
    resp.data?.aufgaben,
    resp.data?.data?.aufgaben,
    resp.result?.aufgaben,
    resp.payload?.aufgaben,
  ];
  for (const c of candidates) {
    if (Array.isArray(c)) return c;
  }
  return [];
}

/** Wie ``core.aufgabe_erledigt.aufgabe_ist_erledigt`` (SQLite 0/1, bool, Strings) */
export function istAufgabeErledigt(a) {
  const e = a?.erledigt;
  if (e == null || e === false) return false;
  if (e === true) return true;
  if (typeof e === "number" && Number.isFinite(e)) return e !== 0;
  if (typeof e === "string") {
    const s = e.trim().toLowerCase();
    if (["", "0", "false", "nein", "no", "none", "null"].includes(s)) return false;
    if (["1", "true", "yes", "ja"].includes(s)) return true;
    return false;
  }
  return Boolean(e);
}

/** Tage bis Frist (negativ = überfällig), analog zu core.frist_utils.tage_bis_frist */
export function tageBisFristClient(fristStr) {
  if (fristStr == null || fristStr === "") return null;
  const s = String(fristStr).trim();
  let d = null;
  const iso = s.slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    d = new Date(`${iso}T12:00:00`);
  } else {
    const m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
    if (m) d = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]), 12, 0, 0);
    else d = new Date(s);
  }
  if (!d || Number.isNaN(d.getTime())) return null;
  const heute = new Date();
  heute.setHours(12, 0, 0, 0);
  return Math.round((d - heute) / 86400000);
}

export function aufgabeIstUeberfaellig(a) {
  if (!a || istAufgabeErledigt(a)) return false;
  const t = tageBisFristClient(a.frist);
  return t !== null && t < 0;
}

export function zaehleUeberfaelligeAufgaben(aufgaben) {
  if (!Array.isArray(aufgaben)) return 0;
  return aufgaben.filter((a) => aufgabeIstUeberfaellig(a)).length;
}

/** GET /heute → ``ok_compat({ eintraege }``) */
export function extrahiereHeuteEintraege(resp) {
  if (resp == null || typeof resp !== "object") return [];
  const arr = resp.eintraege ?? resp.data?.eintraege;
  return Array.isArray(arr) ? arr : [];
}

// ═══════════════════════════════════════════════════════════════
// MANDANTEN
// ═══════════════════════════════════════════════════════════════

export const getMandanten = (params = {}) => {
  const q = new URLSearchParams(params).toString();
  return apiFetch(`/mandanten${q ? "?" + q : ""}`);
};

export const getMandant = (name) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}`);

export const addMandantAPI = (data) =>
  apiFetch("/mandanten", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateMandantAPI = (name, data) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteMandantAPI = (name) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });

export const mandantAntwortEmpfangen = (name) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/antwort`, {
    method: "POST",
  });

// ═══════════════════════════════════════════════════════════════
// AUFGABEN
// ═══════════════════════════════════════════════════════════════

export const getAufgabenMandant = (name, params = {}) => {
  const q = new URLSearchParams(params).toString();
  return apiFetch(`/mandanten/${encodeURIComponent(name)}/aufgaben${q ? "?" + q : ""}`);
};

export const addAufgabeAPI = (name, data) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/aufgaben`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const addAufgabenBulkAPI = (name, aufgaben) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/aufgaben/bulk`, {
    method: "POST",
    body: JSON.stringify({ aufgaben }),
  });

export const toggleAufgabeAPI = (id) =>
  apiFetch(`/aufgaben/${id}/erledigen`, { method: "POST" });

export const updateAufgabeAPI = (id, data) =>
  apiFetch(`/aufgaben/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteAufgabeAPI = (id) =>
  apiFetch(`/aufgaben/${id}`, { method: "DELETE" });

// ═══════════════════════════════════════════════════════════════
// DOKUMENTE
// ═══════════════════════════════════════════════════════════════

export const getDokumente = (name) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/dokumente`);

export const dokumentAnfordern = (name, dokument_name, beschreibung = "") =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/dokumente/anfordern`, {
    method: "POST",
    body: JSON.stringify({ dokument_name, beschreibung }),
  });

export const dokumentErhalten = (name, dokument_name) =>
  apiFetch(
    `/mandanten/${encodeURIComponent(name)}/dokumente/erhalten?dokument_name=${encodeURIComponent(dokument_name)}`,
    { method: "POST" }
  );

// ═══════════════════════════════════════════════════════════════
// EMAIL
// ═══════════════════════════════════════════════════════════════

/** API-Antwort: Top-Level oder ok/data-Wrapper */
export const unwrapApiData = (body) => {
  if (!body || typeof body !== "object") return body;
  if (body.email_html || body.email_text || body.mandant || body.nachrichten) return body;
  if (body.data != null && typeof body.data === "object") return body.data;
  return body;
};

export const getEmailAbsender = async () =>
  unwrapApiData(await apiFetch("/email/absender"));

// BUGFIX: Alter Endpoint war /email/{name} — neu: /email/{name}/vorschau
export const getEmailPreview = async (name) =>
  unwrapApiData(await apiFetch(`/email/${encodeURIComponent(name)}/vorschau`));

// BUGFIX: Unterstützt jetzt benutzerdefinierten Text + force-Bypass der 24h-Sperre
export const sendEmail = (name, options = {}) =>
  apiFetch(`/email/${encodeURIComponent(name)}/senden`, {
    method: "POST",
    body: JSON.stringify({
      email_text: options.email_text || options.emailText || null,
      email_html: options.email_html || options.emailHtml || null,
      empfaenger: options.empfaenger || options.to || null,
      betreff:    options.betreff   || null,
      force:      options.force !== undefined ? options.force : true,
    }),
  });

export const sendEmailBulk = (namen) =>
  apiFetch("/email/bulk", {
    method: "POST",
    body: JSON.stringify(namen),
  });

// ═══════════════════════════════════════════════════════════════
// DASHBOARD & ANALYTICS
// ═══════════════════════════════════════════════════════════════

export const getDashboard   = async () => {
  const r = await apiFetch("/dashboard");
  return r?.data || r;
};
export const getHeute       = async () => {
  const r = await apiFetch("/heute");
  if (Array.isArray(r)) return r;
  return r?.eintraege || r?.data?.eintraege || [];
};

export const getHeuteOps = async () => {
  const r = await apiFetch("/dashboard/heute-ops");
  return r?.data ?? r;
};

export const getPilotScorecard = async () => {
  const r = await apiFetch("/dashboard/pilot-scorecard");
  return r?.data ?? r;
};

export const setPilotBaseline = () =>
  apiFetch("/dashboard/pilot-baseline", { method: "POST" });
// BUGFIX: Alter Endpoint war /kpi — neu: /kpis
export const getKpis        = async () => {
  const r = await apiFetch("/kpis");
  if (Array.isArray(r)) return r;
  return r?.eintraege || r?.data?.eintraege || [];
};
export const getDecisions   = () => apiFetch("/decisions");
export const getEmpfehlungen= async () => {
  const r = await apiFetch("/empfehlungen");
  if (Array.isArray(r)) return r;
  return r?.eintraege || r?.data?.eintraege || [];
};

// ═══════════════════════════════════════════════════════════════
// ANALYSE
// ═══════════════════════════════════════════════════════════════

export const getSimulation = (name, data) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/simulation`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const getBenchmarking = (branche = null) =>
  apiFetch(`/benchmarking${branche ? "?branche=" + encodeURIComponent(branche) : ""}`);

export const getMandantReport = (name) =>
  apiFetch(`/mandanten/${encodeURIComponent(name)}/report`);

// ═══════════════════════════════════════════════════════════════
// AUDIT
// ═══════════════════════════════════════════════════════════════

export const getAuditLog = (limit = 50, suche = null) =>
  apiFetch(`/audit?limit=${limit}${suche ? "&suche=" + encodeURIComponent(suche) : ""}`);

// ═══════════════════════════════════════════════════════════════
// WORKFLOWS — One-Click Automatisierung
// ═══════════════════════════════════════════════════════════════

export const workflowMonatsabschluss = (name, monat, jahr) => {
  const jetzt = new Date();
  const m = monat || jetzt.getMonth() + 1;
  const j = jahr  || jetzt.getFullYear();
  return apiFetch(
    `/workflow/monatsabschluss/${encodeURIComponent(name)}?monat=${m}&jahr=${j}`,
    { method: "POST" }
  );
};

export const workflowJahresabschluss = (name, jahr) =>
  apiFetch(
    `/workflow/jahresabschluss/${encodeURIComponent(name)}?jahr=${jahr || new Date().getFullYear()}`,
    { method: "POST" }
  );

export const workflowOnboarding = (name) =>
  apiFetch(`/workflow/onboarding/${encodeURIComponent(name)}`, { method: "POST" });

// ═══════════════════════════════════════════════════════════════
// ENGINE — Manuelle Steuerung
// ═══════════════════════════════════════════════════════════════

export const engineRun      = () => apiFetch("/engine/run",     { method: "POST" });
export const engineAnalyse  = () => apiFetch("/engine/analyse");
export const engineBericht  = () => apiFetch("/engine/bericht");

// ═══════════════════════════════════════════════════════════════
// PREDICTIVE ANALYTICS
// ═══════════════════════════════════════════════════════════════

export const getPrognoseFristen    = (tage = 30)   => apiFetch(`/prognose/fristen?tage=${tage}`);
export const getPrognoseUmsatz     = ()             => apiFetch("/prognose/umsatz");
export const getPrsteuerfristen    = (jahr = null)  =>
  apiFetch(`/prognose/steuerfristen${jahr ? `?jahr=${jahr}` : ""}`);

// ═══════════════════════════════════════════════════════════════
// TIMELINE & KOMMUNIKATION
// ═══════════════════════════════════════════════════════════════

export const getTimeline = (name, limit = 50) =>
  apiFetch(`/timeline/${encodeURIComponent(name)}?limit=${limit}`);

export const getKommunikation = (name, limit = 50) =>
  apiFetch(`/kommunikation/${encodeURIComponent(name)}?limit=${limit}`);

export const addKommunikation = (name, typ, text) =>
  apiFetch(`/kommunikation/${encodeURIComponent(name)}`, {
    method: "POST",
    body: JSON.stringify({ typ, text }),
  });

// ═══════════════════════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════════════════════

export const getSettings   = ()           => apiFetch("/settings");
export const updateSetting = (key, wert)  =>
  apiFetch("/settings", {
    method: "PUT",
    body: JSON.stringify({ key, wert }),
  });

export const batchUpdateSettings = (updates) =>
  apiFetch("/settings/batch", {
    method: "PUT",
    body: JSON.stringify(updates),
  });

export const getSettingsKategorien = () =>
  apiFetch("/settings/kategorien");

export const getFestgeschrieben = () =>
  apiFetch("/settings/festgeschrieben");
export const getSettingsSuggestions = () =>
  apiFetch("/settings/suggestions");
export const applySettingsSuggestion = (suggestionId) =>
  apiFetch(`/settings/suggestions/${encodeURIComponent(suggestionId)}/apply`, {
    method: "POST",
  });
export const resetSettings = (key = null) =>
  apiFetch(`/settings/reset${key ? `?key=${encodeURIComponent(key)}` : ""}`,
    { method: "POST" });

// ═══════════════════════════════════════════════════════════════
// SYSTEM & PLAUSIBILITÄT
// ═══════════════════════════════════════════════════════════════

export const getSystemInfo         = () => apiFetch("/system/info");
export const getSystemExport       = () => apiFetch("/system/export");
export const getPlausibilitaet     = () => apiFetch("/plausibilitaet");
export const getSaasReadiness      = () => apiFetch("/saas/readiness");
export const getBillingUsage       = () => apiFetch("/billing/usage");
export const getBillingMetrics     = () => apiFetch("/billing/metrics");
export const getBillingFunnel      = (lookback_hours = 24) => apiFetch(`/billing/funnel?lookback_hours=${encodeURIComponent(lookback_hours)}`);
export const getBillingWeeklyReport = () => apiFetch("/billing/report/weekly");
export const sendBillingWeeklyReport = () =>
  apiFetch("/billing/report/weekly/send", { method: "POST" });
export const trackBillingFunnelEvent = (stage, meta = {}) =>
  apiFetch("/billing/funnel/event", {
    method: "POST",
    body: JSON.stringify({ stage, meta }),
  });
export const getStripePublicConfig = () => apiFetch("/billing/stripe/config");
export const createStripeCheckoutSession = (body) =>
  apiFetch("/billing/stripe/checkout-session", {
    method: "POST",
    body: JSON.stringify(body),
  });
export const createStripePortalSession = (return_url) =>
  apiFetch("/billing/stripe/portal-session", {
    method: "POST",
    body: JSON.stringify({ return_url }),
  });
export const getComplianceStatus   = () => apiFetch("/compliance/status");

// ═══════════════════════════════════════════════════════════════
// AUTH — Login, Sessions, Team
// ═══════════════════════════════════════════════════════════════

export const authLogin = (benutzername, passwort) => {
  const id = String(benutzername || "").trim();
  const isEmail = id.includes("@");
  const path = isEmail ? "/login" : "/auth/login";
  const body = isEmail
    ? { email: id, password: passwort }
    : { benutzername: id, passwort };
  return apiFetch(path, { method: "POST", body: JSON.stringify(body) });
};

export const authLogout = () =>
  apiFetch("/auth/logout", { method: "POST" });

export const authMe = () => apiFetch("/auth/me");
export const meGet = () => apiFetch("/me");
export const meUpdate = (payload) =>
  apiFetch("/me", { method: "PUT", body: JSON.stringify(payload) });
export const mePasswordUpdate = (payload) =>
  apiFetch("/me/password", { method: "PUT", body: JSON.stringify(payload) });
export const meLogoutAll = () =>
  apiFetch("/me/logout-all", { method: "POST" });

export const authRegistrieren = (data) =>
  apiFetch("/auth/registrieren", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const authBenutzer = () => apiFetch("/auth/benutzer");

export const authPasswortAendern = (altes, neues) =>
  apiFetch("/auth/passwort", {
    method: "PUT",
    body: JSON.stringify({ altes_passwort: altes, neues_passwort: neues }),
  });

export const authSetupStatus = () => apiFetch("/auth/setup-status");
export const authPasswortForgot = (email) =>
  apiFetch("/auth/password/forgot", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
export const authPasswortReset = (payload) =>
  apiFetch("/auth/password/reset", {
    method: "POST",
    body: JSON.stringify(payload),
  });
export const authEmailVerify = (token) =>
  apiFetch("/auth/email/verify", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
export const authEmailResend = (email) =>
  apiFetch("/auth/email/resend", {
    method: "POST",
    body: JSON.stringify({ email }),
  });

// Token-Verwaltung (localStorage)
export const getToken = ()         => localStorage.getItem("kanzlei_token");
export const setToken = (token)    => setAccessToken(token);
export const removeToken = ()      => clearAuthStorage();
export const isLoggedIn = ()       => !!getToken();

/** JWT ist stateless — Client-Session leeren und zur Login-Seite (Pfad anpassen). */
export const clearClientAuth = () => {
  clearAuthStorage();
};

// ═══════════════════════════════════════════════════════════════
// BANK IMPORT
// ═══════════════════════════════════════════════════════════════

export const bankImport = async (datei) => {
  const token = getToken();
  const arrayBuffer = await datei.arrayBuffer();
  const res = await fetch(`${BASE_URL}/bank/import?dateiname=${encodeURIComponent(datei.name)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
      ...(token ? { "Authorization": `Bearer ${token}` } : {}),
    },
    body: arrayBuffer,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Bank-Import Fehler ${res.status}`);
  return data;
};

export const getBankBuchungen = (mandant = null, limit = 50) =>
  apiFetch(`/bank/buchungen?limit=${limit}${mandant ? `&mandant=${encodeURIComponent(mandant)}` : ""}`);

// ═══════════════════════════════════════════════════════════════
// EXPORT — DATEV / ELSTER / EXCEL / CSV
// ═══════════════════════════════════════════════════════════════

const downloadFile = async (url, defaultFilename) => {
  const token = getToken();
  const res = await fetch(BASE_URL + url, {
    headers: token ? { "Authorization": `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    let detail = `Export Fehler ${res.status}`;
    if (ct.includes("application/json")) {
      const err = await res.json().catch(() => ({}));
      detail = err.detail || detail;
    } else {
      const txt = await res.text().catch(() => "");
      if (txt) detail = txt.slice(0, 400);
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const meta = {
    datevWarnings: res.headers.get("x-datev-warnings") || "",
    datevBuchungen: res.headers.get("x-datev-buchungen") || "",
    datevNutzen: res.headers.get("x-datev-nutzen") || "",
    datevDebitor: res.headers.get("x-datev-debitor") || "",
    exportDateien: res.headers.get("x-export-dateien") || "",
  };
  const blob     = await res.blob();
  const filename = res.headers.get("content-disposition")
    ?.split("filename=")[1]?.replace(/"/g, "") || defaultFilename;
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl; a.download = filename; a.click();
  URL.revokeObjectURL(objUrl);
  return meta;
};

export const exportDatevInfo = (name, beraterNr = "") =>
  apiFetch(`/export/${encodeURIComponent(name)}/datev/info${beraterNr ? `?berater_nr=${encodeURIComponent(beraterNr)}` : ""}`);

export const exportExcel          = (name) =>
  downloadFile(`/export/${encodeURIComponent(name)}/excel`, `${name}_Report.xlsx`);

export const exportDatev          = (name, beraterNr = "", mandantenNr = "") => {
  const q = new URLSearchParams();
  if (beraterNr) q.set("berater_nr", beraterNr);
  if (mandantenNr) q.set("mandanten_nr", mandantenNr);
  const qs = q.toString();
  return downloadFile(
    `/export/${encodeURIComponent(name)}/datev${qs ? `?${qs}` : ""}`,
    `DATEV_${name}_Buchungsstapel.csv`,
  );
};

export const exportDatevStammdaten = (beraterNr = "1234") =>
  downloadFile(`/export/datev/stammdaten?berater_nr=${beraterNr}`, "DATEV_Stammdaten.csv");

export const exportElster         = (name, steuerart = "UStVA") =>
  downloadFile(`/export/${encodeURIComponent(name)}/elster?steuerart=${steuerart}`,
               `${name}_${steuerart}.xml`);

export const exportCsvMandanten   = () =>
  downloadFile("/export/csv/mandanten", "Mandanten.csv");

export const exportCsvAufgaben    = () =>
  downloadFile("/export/csv/aufgaben", "Aufgaben.csv");

export const exportKomplett       = (name) =>
  downloadFile(`/export/${encodeURIComponent(name)}/komplett`,
               `${name}_KanzleiAI_Export.zip`);

// ═══════════════════════════════════════════════════════════════
// PORTAL ADMIN
// ═══════════════════════════════════════════════════════════════

export const generierePortalToken = (mandant) =>
  apiFetch(`/portal/admin/token/${encodeURIComponent(mandant)}`, { method: "POST" });

export const portalUnterschriftenAlle = (mandant = null) =>
  apiFetch(`/portal/unterschriften/alle${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);

export const portalMandantStatus = (name) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/status`);

export const getPortalUploads = (name) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/uploads`);

export const portalUnterschriftAnfragen = (name, body) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/unterschrift-anfragen`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getPortalDokumentQuellen = (name) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/dokument-quellen`);

export const getPortalDokumentQuelleInhalt = (name, quelle, itemId) =>
  apiFetch(
    `/portal/mandant/${encodeURIComponent(name)}/dokument-quellen/${encodeURIComponent(quelle)}/${encodeURIComponent(itemId)}/inhalt`
  );

export const getPortalUnterschriftDetail = (name, uid) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/unterschrift/${encodeURIComponent(uid)}`);

export const getPortalUnterschriftBild = (name, uid) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/unterschrift/${encodeURIComponent(uid)}/unterschrift-bild`);

export const getPortalUnterschriftDokument = (name, uid) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/unterschrift/${encodeURIComponent(uid)}/dokument`);

export const sendPortalAntwort = (name, betreff, text) =>
  apiFetch(`/kommunikation/${encodeURIComponent(name)}/portal-antwort`, {
    method: "POST",
    body: JSON.stringify({ betreff, text }),
  });

export const getPortalChatInbox = () => apiFetch("/portal/mandant/chat/inbox");

export const getPortalChatUnread = () => apiFetch("/portal/mandant/chat/unread-summary");

export const markPortalChatRead = (name) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/read`, { method: "POST" });

export const uploadPortalDokumentAnfrage = (name, msgId, body) =>
  apiFetch(
    `/portal/mandant/${encodeURIComponent(name)}/chat/dokument-anfrage/${encodeURIComponent(msgId)}/hochladen`,
    { method: "POST", body: JSON.stringify(body) }
  );

export const getPortalChat = (name, seit = null) =>
  apiFetch(
    `/portal/mandant/${encodeURIComponent(name)}/chat${seit ? `?seit=${encodeURIComponent(seit)}` : ""}`
  );

export const sendPortalChat = (name, text) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });

export const sendPortalChatAufgabe = (name, body) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/aufgabe`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const sendPortalChatDokument = (name, body) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/dokument-anfrage`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const sendPortalChatUnterschrift = (name, body) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/unterschrift`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const sendPortalChatUpload = (name, body) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/upload`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const patchPortalChat = (name, msgId, text) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/${encodeURIComponent(msgId)}`, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });

export const deletePortalChat = (name, msgId) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/chat/${encodeURIComponent(msgId)}`, {
    method: "DELETE",
  });

// ═══════════════════════════════════════════════════════════════
// PROAKTIVER BOT
// ═══════════════════════════════════════════════════════════════

export const botFrageStellen = (data) =>
  apiFetch("/bot/frage", { method: "POST", body: JSON.stringify(data) });

export const botAntwort = (frageId, antwort, notiz = "") =>
  apiFetch(`/bot/frage/${frageId}/antwort`, {
    method: "POST", body: JSON.stringify({ antwort, notiz }),
  });

export const botFragen = (mandant = null, status = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (status)  params.set("status",  status);
  const q = params.toString();
  return apiFetch(`/bot/fragen${q ? "?" + q : ""}`);
};

export const botFragenMandant   = (mandant, nurOffen = true) =>
  apiFetch(`/bot/fragen/${encodeURIComponent(mandant)}?nur_offen=${nurOffen}`);

export const botAnalyse         = () =>
  apiFetch("/bot/analyse", { method: "POST" });

export const botStatistiken     = () => apiFetch("/bot/statistiken");

// ═══════════════════════════════════════════════════════════════
// PROFIT MONITOR
// ═══════════════════════════════════════════════════════════════

export const getProfitMandant   = (mandant, tage = 30) =>
  apiFetch(`/profit/${encodeURIComponent(mandant)}?tage=${tage}`);

export const getProfitRanking   = (tage = 30) =>
  apiFetch(`/profit/ranking/alle?tage=${tage}`);

export const getProfitKanzlei   = (tage = 30) =>
  apiFetch(`/profit/kanzlei/uebersicht?tage=${tage}`);

export const getProfitBenchmark = (mandant) =>
  apiFetch(`/profit/${encodeURIComponent(mandant)}/benchmarking`);

// ═══════════════════════════════════════════════════════════════
// ML-BUCHUNGSASSISTENT
// ═══════════════════════════════════════════════════════════════

export const mlKategorisieren   = (data) =>
  apiFetch("/ml/kategorisieren", { method: "POST", body: JSON.stringify(data) });

export const mlFeedback         = (data) =>
  apiFetch("/ml/feedback", { method: "POST", body: JSON.stringify(data) });

export const mlStatistiken      = () => apiFetch("/ml/statistiken");

export const mlLieferanten      = () => apiFetch("/ml/lieferanten");

// ═══════════════════════════════════════════════════════════════
// STEUER-AUTOPILOT
// ═══════════════════════════════════════════════════════════════

export const steuerVerarbeiten  = (mandant, jahr, steuerart = "ESt") =>
  apiFetch("/steuer/verarbeiten", {
    method: "POST",
    body: JSON.stringify({ mandant, jahr, steuerart }),
  });

export const steuerDaten        = (mandant, jahr) =>
  apiFetch(`/steuer/daten/${encodeURIComponent(mandant)}/${jahr}`);

export const steuerFreigeben    = (fallId, von = "Steuerberater") =>
  apiFetch(`/steuer/${fallId}/freigeben?freigegeben_von=${encodeURIComponent(von)}`,
           { method: "POST" });

export const steuerFaelle       = (mandant = null, status = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (status)  params.set("status",  status);
  const q = params.toString();
  return apiFetch(`/steuer/faelle${q ? "?" + q : ""}`);
};

export const steuerStatistiken  = () => apiFetch("/steuer/statistiken");

// ═══════════════════════════════════════════════════════════════
// FINANZIERUNG
// ═══════════════════════════════════════════════════════════════

export const finanzierungAngebot = (data) =>
  apiFetch("/finanzierung/angebot", { method: "POST", body: JSON.stringify(data) });

export const finanzierungAngebote = (mandant = null) =>
  apiFetch(`/finanzierung/angebote${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);

export const finanzierungPartner  = () => apiFetch("/finanzierung/partner");

export const finanzierungStats    = () => apiFetch("/finanzierung/statistiken");

// ═══════════════════════════════════════════════════════════════
// WORKFLOW-BAUKASTEN (No-Code Regeln)
// ═══════════════════════════════════════════════════════════════

export const regelnListe         = (nurAktive = false) =>
  apiFetch(`/regeln?nur_aktive=${nurAktive}`);

export const regelErstellen      = (data) =>
  apiFetch("/regeln", { method: "POST", body: JSON.stringify(data) });

export const regelToggle         = (id, aktiv) =>
  apiFetch(`/regeln/${id}/aktiv?aktiv=${aktiv}`, { method: "PUT" });

export const regelLoeschen       = (id) =>
  apiFetch(`/regeln/${id}`, { method: "DELETE" });

export const regelnAusfuehren    = () =>
  apiFetch("/regeln/ausfuehren", { method: "POST" });

export const regelnStandard      = () =>
  apiFetch("/regeln/standard-erstellen", { method: "POST" });

export const regelnStatistiken   = () => apiFetch("/regeln/statistiken");

export const regelnVerfuegbar    = () => apiFetch("/regeln/verfuegbare-trigger");

// ═══════════════════════════════════════════════════════════════
// LOHNABRECHNUNG
// ═══════════════════════════════════════════════════════════════

export const lohnMitarbeiterNeu  = (data) =>
  apiFetch("/lohn/mitarbeiter", { method: "POST", body: JSON.stringify(data) });

export const lohnMitarbeiterUpdate = (maId, data) =>
  apiFetch(`/lohn/mitarbeiter/${encodeURIComponent(maId)}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const lohnMitarbeiterLoeschen = (maId, endgueltig = false) =>
  apiFetch(
    `/lohn/mitarbeiter/${encodeURIComponent(maId)}${endgueltig ? "?endgueltig=true" : ""}`,
    { method: "DELETE" }
  );

export const lohnMitarbeiter     = (mandant = null) =>
  apiFetch(`/lohn/mitarbeiter${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);

export const lohnZeitdaten       = (maId, monat, data) =>
  apiFetch(`/lohn/zeitdaten/${maId}/${monat}`, {
    method: "POST", body: JSON.stringify(data),
  });

export const lohnAbrechnung      = (maId, monat) =>
  apiFetch(`/lohn/abrechnung/${maId}/${monat}`, { method: "POST" });

export const lohnBatch           = (mandant, monat) =>
  apiFetch(`/lohn/batch/${encodeURIComponent(mandant)}/${monat}`, { method: "POST" });

export const lohnZettelUrl       = (abrechnungId) =>
  `${BASE_URL}/lohn/abrechnung/${abrechnungId}/html`;

export const lohnAbrechnungen    = (mandant = null, monat = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (monat)   params.set("monat",   monat);
  const q = params.toString();
  return apiFetch(`/lohn/abrechnungen${q ? "?" + q : ""}`);
};

// ═══════════════════════════════════════════════════════════════
// ZEITERFASSUNG
// ═══════════════════════════════════════════════════════════════

export const zeitStarten         = (data) =>
  apiFetch("/zeit/starten", { method: "POST", body: JSON.stringify(data) });

export const zeitStoppen         = (mitarbeiter, notiz = "") =>
  apiFetch(`/zeit/stoppen/${encodeURIComponent(mitarbeiter)}?notiz=${encodeURIComponent(notiz)}`,
           { method: "POST" });

export const zeitLaufend         = () => apiFetch("/zeit/laufend");

export const zeitEintraege       = (params = {}) => {
  const q = new URLSearchParams(params).toString();
  return apiFetch(`/zeit/eintraege${q ? "?" + q : ""}`);
};

export const zeitStatistiken     = (mandant = null) =>
  apiFetch(`/zeit/statistiken${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);

// ═══════════════════════════════════════════════════════════════
// BELEGE (Belegscanner)
// ═══════════════════════════════════════════════════════════════

export const belegAnalysieren    = (dateiname, inhaltB64, mandant = "") =>
  apiFetch("/belege/analysieren", {
    method: "POST",
    body: JSON.stringify({ dateiname, inhalt_b64: inhaltB64, mandant }),
  });

export const belegeLaden         = (mandant = null, status = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (status)  params.set("status",  status);
  const q = params.toString();
  return apiFetch(`/belege${q ? "?" + q : ""}`);
};

export const belegBestaetigen    = (belegId, korrekturen = {}) =>
  apiFetch(`/belege/${belegId}/bestaetigen`, {
    method: "POST", body: JSON.stringify(korrekturen),
  });

export const belegAblehnen       = (belegId) =>
  apiFetch(`/belege/${belegId}/ablehnen`, { method: "POST" });

export const belegStatistiken    = (mandant = null) =>
  apiFetch(`/belege/statistiken${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);

// ═══════════════════════════════════════════════════════════════
// DOKUMENT-SCANNER
// ═══════════════════════════════════════════════════════════════

export const dokumentAnalysieren = (dateiname, inhaltB64, dateityp = "application/pdf") =>
  apiFetch("/dokumente/analysieren", {
    method: "POST",
    body: JSON.stringify({ dateiname, inhalt_b64: inhaltB64, dateityp }),
  });

export const dokumentSpeichern   = (data) =>
  apiFetch("/dokumente/speichern", { method: "POST", body: JSON.stringify(data) });

/** API-Antwort → Dokumenten-Array (Archiv / Liste). */
export const extractDokumenteListe = (resp) => {
  if (!resp) return [];
  if (Array.isArray(resp.dokumente)) return resp.dokumente;
  if (Array.isArray(resp.data?.dokumente)) return resp.data.dokumente;
  if (Array.isArray(resp.data)) return resp.data;
  return [];
};

export const dokumentArchiv = async (mandant = null, typ = null, suche = null, status = "gespeichert") => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (typ) params.set("typ", typ);
  if (suche) params.set("suche", suche);
  if (status) params.set("status", status);
  const q = params.toString();
  try {
    return await apiFetch(`/dokumente/archiv${q ? "?" + q : ""}`);
  } catch (e) {
    if (e?.status !== 404) throw e;
    const legacy = await apiFetch(`/dokumente/liste${mandant ? `?mandant=${encodeURIComponent(mandant)}` : ""}`);
    const liste = extractDokumenteListe(legacy).map((d, i) => ({
      dok_id: d.dok_id || `legacy-${i}-${d.dateiname || "dok"}`,
      dateiname: d.dateiname,
      dokumenttyp: d.dokumenttyp || d.doktyp || "sonstiges",
      mandant: d.mandant,
      ordner_pfad: d.ordner_pfad || d.ordner,
      ordner_kategorie: d.ordner_kategorie || d.ordner,
      lieferant: d.lieferant || d.absender,
      datum: d.datum,
      betrag: d.betrag,
      notiz: d.notiz,
      ki_zusammenfassung: d.ki_zusammenfassung || "",
      gespeichert_am: d.gespeichert_am,
      status: d.status || "gespeichert",
      pfad: d.pfad,
    }));
    const st = (status || "gespeichert").toLowerCase();
    const gefiltert =
      st === "alle" || st === "all"
        ? liste
        : liste.filter((d) => (d.status || "gespeichert") === st);
    return { dokumente: gefiltert, anzahl: gefiltert.length, legacy_fallback: true };
  }
};

export const dokumentArchivEinzel = (dokId) =>
  apiFetch(`/dokumente/${encodeURIComponent(dokId)}`);

export const dokumentAktualisieren = (dokId, data) =>
  apiFetch(`/dokumente/${encodeURIComponent(dokId)}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const dokumentLoeschen = (dokId, endgueltig = false) =>
  apiFetch(`/dokumente/${encodeURIComponent(dokId)}?endgueltig=${endgueltig ? "true" : "false"}`, {
    method: "DELETE",
  });

export const dokumentWiederherstellen = (dokId) =>
  apiFetch(`/dokumente/${encodeURIComponent(dokId)}/wiederherstellen`, { method: "POST" });

/** Datei im Browser öffnen (neuer Tab), nicht als Download. */
export const dokumentDateiBlobUrl = async (dokId) => {
  const base = process.env.REACT_APP_API_URL || "/api";
  const token = (localStorage.getItem("kanzlei_token") || localStorage.getItem("token") || "").trim();
  const res = await fetch(`${base}/dokumente/${encodeURIComponent(dokId)}/datei`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let msg = `Öffnen fehlgeschlagen (${res.status})`;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {}
    throw new Error(msg);
  }
  const raw = await res.blob();
  const ct = res.headers.get("Content-Type") || raw.type || "application/pdf";
  const blob = raw.type ? raw : new Blob([raw], { type: ct });
  const url = URL.createObjectURL(blob);
  return { url, contentType: ct, blob };
};

/** Öffnet in neuem Tab (Fallback, wenn Vorschau nicht genutzt wird). */
export const dokumentDateiOeffnen = async (dokId, dateiname = "dokument") => {
  const { url } = await dokumentDateiBlobUrl(dokId);
  const tab = window.open(url, "_blank", "noopener,noreferrer");
  if (!tab) {
    URL.revokeObjectURL(url);
    throw new Error("Pop-up blockiert — bitte Pop-ups für diese Seite erlauben.");
  }
  setTimeout(() => URL.revokeObjectURL(url), 120000);
};

/** Alias: expliziter Download (falls später benötigt). */
export const dokumentDateiDownload = async (dokId, dateiname = "dokument") => {
  const base = process.env.REACT_APP_API_URL || "/api";
  const token = (localStorage.getItem("kanzlei_token") || localStorage.getItem("token") || "").trim();
  const res = await fetch(`${base}/dokumente/${encodeURIComponent(dokId)}/datei`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Download fehlgeschlagen (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = dateiname || "dokument";
  a.click();
  URL.revokeObjectURL(url);
};

export const dokumentPapierkorbLeeren = () =>
  apiFetch("/dokumente/papierkorb/leeren", { method: "POST" });

export const dokumentPapierkorbWiederherstellenAlle = () =>
  apiFetch("/dokumente/papierkorb/wiederherstellen-alle", { method: "POST" });

/** Alle gespeicherten Archiv-Dokumente in den Papierkorb (optional Mandant). */
export const dokumentArchivAlleInPapierkorb = (mandant = null) => {
  const q = mandant ? `?mandant=${encodeURIComponent(mandant)}` : "";
  return apiFetch(`/dokumente/archiv/in-papierkorb-alle${q}`, { method: "POST" });
};

// ═══════════════════════════════════════════════════════════════
// RECHNUNGEN
// ═══════════════════════════════════════════════════════════════

export const rechnungErstellen   = (data) =>
  apiFetch("/rechnungen", { method: "POST", body: JSON.stringify(data) });

export const rechnungenLaden     = (mandant = null, status = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (status)  params.set("status",  status);
  const q = params.toString();
  return apiFetch(`/rechnungen${q ? "?" + q : ""}`);
};

export const rechnungBezahlt     = (id, betrag = null) =>
  apiFetch(`/rechnungen/${id}/bezahlt`, {
    method: "POST", body: JSON.stringify({ betrag }),
  });

export const rechnungMahnung     = (id) =>
  apiFetch(`/rechnungen/${id}/mahnung`, { method: "POST" });

export const rechnungEmail       = (id) =>
  apiFetch(`/rechnungen/${id}/email`, { method: "POST" });

export const rechnungHtmlUrl     = (id) => `${BASE_URL}/rechnungen/${id}/html`;

export const rechnungsStats      = () => apiFetch("/rechnungen/statistiken");

export const rechnungsMahnungen  = () => apiFetch("/rechnungen/mahnungen");

// ═══════════════════════════════════════════════════════════════
// TEAM & AUFGABEN
// ═══════════════════════════════════════════════════════════════

export const aufgabeZuweisen     = (aufgabeId, mitarbeiter) =>
  apiFetch(`/aufgaben/${aufgabeId}/zuweisen?mitarbeiter=${encodeURIComponent(mitarbeiter)}`,
           { method: "POST" });

export const teamAufgaben        = (mitarbeiter) =>
  apiFetch(`/team/aufgaben/${encodeURIComponent(mitarbeiter)}`);

export const teamAuslastung      = () => apiFetch("/team/auslastung");

// ═══════════════════════════════════════════════════════════════
// HEALTH & SYSTEM
// ═══════════════════════════════════════════════════════════════

export const getHealth           = () => apiFetch("/health");

export const getAuditFull        = (limit = 100, suche = null) => {
  const params = new URLSearchParams({ limit });
  if (suche) params.set("suche", suche);
  return apiFetch(`/audit?${params.toString()}`);
};


export const kiMandantAnalyse = (name) =>
  apiFetch(`/ki/mandant-analyse/${encodeURIComponent(name)}`);

export const kiKanzleiZusammenfassung = () =>
  apiFetch("/ki/kanzlei-zusammenfassung");

export const kiStatus = () =>
  apiFetch("/ki/status");

// ═══════════════════════════════════════════════════════════════
// KANZLEI & USER MANAGEMENT (Multi-Kanzlei)
// ═══════════════════════════════════════════════════════════════

export const erstelleKanzlei = (data) =>
  apiFetch("/auth/kanzlei", { method: "POST", body: JSON.stringify(data) });

export const listeKanzleien = () =>
  apiFetch("/auth/kanzleien");

export const erstelleBenutzer = (data) =>
  apiFetch("/auth/benutzer", { method: "POST", body: JSON.stringify(data) });

export const listeBenutzer = () =>
  apiFetch("/auth/benutzer");

export const setupStatus = () =>
  apiFetch("/auth/setup-status");