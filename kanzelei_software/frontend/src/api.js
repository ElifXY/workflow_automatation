// ============================================================
// KANZLEI AI — API CLIENT v2.0
// Alle Endpunkte passend zur neuen api.py
// ============================================================

const BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

// ─── Generic Fetch (Auth Token + Timeout + Error Handling) ──────
const apiFetch = async (url, options = {}) => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  const token = localStorage.getItem("kanzlei_token");

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
      const msg = data?.detail || `Server Fehler (${res.status})`;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }

    return data;

  } catch (err) {
    clearTimeout(timeout);
    if (err.name === "AbortError") throw new Error("Server Timeout — Backend erreichbar?");
    throw err;
  }
};

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

// BUGFIX: Alter Endpoint war /email/{name} — neu: /email/{name}/vorschau
export const getEmailPreview = (name) =>
  apiFetch(`/email/${encodeURIComponent(name)}/vorschau`);

// BUGFIX: Unterstützt jetzt benutzerdefinierten Text + force-Bypass der 24h-Sperre
export const sendEmail = (name, options = {}) =>
  apiFetch(`/email/${encodeURIComponent(name)}/senden`, {
    method: "POST",
    body: JSON.stringify({
      // Akzeptiere beide Schreibweisen (snake_case bevorzugt)
      email_text: options.email_text || options.emailText || null,
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
export const getComplianceStatus   = () => apiFetch("/compliance/status");

// ═══════════════════════════════════════════════════════════════
// AUTH — Login, Sessions, Team
// ═══════════════════════════════════════════════════════════════

export const authLogin = (benutzername, passwort) =>
  apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ benutzername, passwort }),
  });

export const authLogout = () =>
  apiFetch("/auth/logout", { method: "POST" });

export const authMe = () => apiFetch("/auth/me");

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

// Token-Verwaltung (localStorage)
export const getToken = ()         => localStorage.getItem("kanzlei_token");
export const setToken = (token)    => localStorage.setItem("kanzlei_token", token);
export const removeToken = ()      => localStorage.removeItem("kanzlei_token");
export const isLoggedIn = ()       => !!getToken();

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
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Export Fehler ${res.status}`);
  }
  const blob     = await res.blob();
  const filename = res.headers.get("content-disposition")
    ?.split("filename=")[1]?.replace(/"/g, "") || defaultFilename;
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl; a.download = filename; a.click();
  URL.revokeObjectURL(objUrl);
};

export const exportExcel          = (name) =>
  downloadFile(`/export/${encodeURIComponent(name)}/excel`, `${name}_Report.xlsx`);

export const exportDatev          = (name, beraterNr = "1234", mandantenNr = "00000") =>
  downloadFile(`/export/${encodeURIComponent(name)}/datev?berater_nr=${beraterNr}&mandanten_nr=${mandantenNr}`,
               `DATEV_${name}_Buchungsstapel.csv`);

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

export const generierePortalToken = (mandant, adminKey) =>
  apiFetch(`/portal/admin/token/${encodeURIComponent(mandant)}?admin_key=${encodeURIComponent(adminKey)}`,
           { method: "POST" });

export const portalUnterschriftenAlle = (adminKey, mandant = null) =>
  apiFetch(`/portal/unterschriften/alle?admin_key=${encodeURIComponent(adminKey)}${mandant ? `&mandant=${encodeURIComponent(mandant)}` : ""}`);

export const portalMandantStatus = (name) =>
  apiFetch(`/portal/mandant/${encodeURIComponent(name)}/status`);

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

export const dokumentArchiv      = (mandant = null, typ = null, suche = null) => {
  const params = new URLSearchParams();
  if (mandant) params.set("mandant", mandant);
  if (typ)     params.set("typ",     typ);
  if (suche)   params.set("suche",   suche);
  const q = params.toString();
  return apiFetch(`/dokumente/archiv${q ? "?" + q : ""}`);
};

export const dokumentLoeschen    = (dokId) =>
  apiFetch(`/dokumente/${dokId}`, { method: "DELETE" });

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


// ═══════════════════════════════════════════════════════════════
// KI-ANALYSE (echte OpenAI-Analyse pro Mandant + Kanzlei)
// ═══════════════════════════════════════════════════════════════

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