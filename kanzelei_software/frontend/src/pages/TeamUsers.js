/**
 * Team — Benutzer einladen und Rolle zuweisen (Pass 5, schlank)
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PermissionGate, { hasRoleReal } from "../components/PermissionGate";

const API_ROOT = process.env.REACT_APP_API_URL || "/api";

const ROLE_OPTIONS = [
  { value: "assistent", label: "Mitarbeiter", hint: "Mandanten, Dokumente, Aufgaben" },
  { value: "steuerberater", label: "Steuerberater", hint: "+ Automationen (je nach Einstellung)" },
];

function authHeaders() {
  const token = localStorage.getItem("kanzlei_token");
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}

function unwrapData(body) {
  if (!body || typeof body !== "object") return body;
  if (Array.isArray(body.data)) return body.data;
  if (body.data !== undefined) return body.data;
  return body;
}

function buildInviteUrl(inviteToken) {
  if (!inviteToken) return "";
  return `${window.location.origin}/register-email?invite_token=${encodeURIComponent(inviteToken)}`;
}

function roleLabel(role) {
  const hit = ROLE_OPTIONS.find((o) => o.value === role);
  if (hit) return hit.label;
  if (role === "admin") return "Admin";
  if (role === "owner") return "Inhaber";
  return role || "—";
}

export default function TeamUsers() {
  const navigate = useNavigate();
  const canManageTeam = hasRoleReal(["owner", "admin"]);
  const [users, setUsers] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("assistent");
  const [savingInvite, setSavingInvite] = useState(false);
  const [lastInviteUrl, setLastInviteUrl] = useState("");

  const refreshUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API_ROOT}/users`, { headers: authHeaders() });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`);
      const rows = unwrapData(body);
      setUsers(Array.isArray(rows) ? rows : []);
    } catch (e) {
      setError(e.message || "Fehler beim Laden");
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshInvites = useCallback(async () => {
    try {
      const r = await fetch(`${API_ROOT}/users/invites?limit=20`, { headers: authHeaders() });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setPendingInvites([]);
        return;
      }
      const rows = unwrapData(body);
      const list = Array.isArray(rows) ? rows : [];
      setPendingInvites(list.filter((row) => row.status === "pending" && row.db_status === "pending"));
    } catch {
      setPendingInvites([]);
    }
  }, []);

  useEffect(() => {
    if (canManageTeam) {
      refreshUsers();
      refreshInvites();
    }
  }, [canManageTeam, refreshUsers, refreshInvites]);

  const activeCount = useMemo(
    () => users.filter((u) => u.is_active ?? u.aktiv).length,
    [users],
  );

  const createInvite = async (e) => {
    e.preventDefault();
    const emailTrim = inviteEmail.trim().toLowerCase();
    if (!emailTrim) {
      setError("Bitte E-Mail-Adresse eintragen.");
      return;
    }
    setSavingInvite(true);
    setError("");
    setLastInviteUrl("");

    try {
      let r = await fetch(`${API_ROOT}/users/invites`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          role: inviteRole,
          ttl_hours: 168,
          email: emailTrim,
          send_email: true,
        }),
      });
      let body = await r.json().catch(() => ({}));

      if (r.status === 404) {
        r = await fetch(`${API_ROOT}/tenant/invites`, {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ rolle: inviteRole, email_lock: emailTrim, ttl_hours: 168 }),
        });
        body = await r.json().catch(() => ({}));
      }

      if (!r.ok) throw new Error(body.detail || body.error || body.message || `HTTP ${r.status}`);
      const data = unwrapData(body) || {};
      const url = data.invite_url || buildInviteUrl(data.invite_token);
      setLastInviteUrl(url);
      setInviteEmail("");
      await Promise.all([refreshUsers(), refreshInvites()]);
    } catch (err) {
      setError(err.message || "Einladung konnte nicht erstellt werden");
    } finally {
      setSavingInvite(false);
    }
  };

  const copyInvite = async () => {
    if (!lastInviteUrl) return;
    try {
      await navigator.clipboard.writeText(lastInviteUrl);
    } catch {
      setError("Link konnte nicht kopiert werden.");
    }
  };

  const revokeInvite = async (jti) => {
    if (!jti || !window.confirm("Einladung widerrufen?")) return;
    setError("");
    try {
      const r = await fetch(`${API_ROOT}/users/invites/${encodeURIComponent(jti)}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`);
      await refreshInvites();
    } catch (err) {
      setError(err.message || "Widerruf fehlgeschlagen");
    }
  };

  const deactivate = async (id) => {
    if (!window.confirm("Benutzer deaktivieren?")) return;
    setError("");
    try {
      const r = await fetch(`${API_ROOT}/users/${id}`, { method: "DELETE", headers: authHeaders() });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`);
      await refreshUsers();
    } catch (err) {
      setError(err.message || "Deaktivieren fehlgeschlagen");
    }
  };

  const changeRole = async (id, value) => {
    setError("");
    try {
      const r = await fetch(`${API_ROOT}/users/${id}/role`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ role: value }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || body.error || `HTTP ${r.status}`);
      await refreshUsers();
    } catch (err) {
      setError(err.message || "Rolle ändern fehlgeschlagen");
    }
  };

  return (
    <PermissionGate
      roles={["owner", "admin"]}
      fallback={
        <div style={{ padding: 28, maxWidth: 560, margin: "0 auto", color: "var(--text)" }}>
          <p>Kein Zugriff — nur Kanzlei-Admins verwalten das Team.</p>
          <Link to="/" style={{ color: "var(--accent)" }}>Zurück</Link>
        </div>
      }
    >
      <div style={{ minHeight: "100%", background: "var(--bg)", padding: "24px 32px 40px" }}>
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <header style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 11, letterSpacing: "0.1em", color: "var(--text3)", textTransform: "uppercase" }}>
              Administration
            </div>
            <h1 style={{ fontFamily: "var(--font-head)", fontSize: 26, color: "var(--text)", margin: "8px 0 10px" }}>
              Team
            </h1>
            <p style={{ fontSize: 14, color: "var(--text3)", lineHeight: 1.55 }}>
              Person einladen, Rolle zuweisen — fertig. Welche Bereiche sichtbar sind, steuern Sie unter{" "}
              <button
                type="button"
                onClick={() => {
                  try {
                    sessionStorage.setItem("kanzlei_settings_open_tab", "team");
                  } catch {}
                  navigate("/", { state: { tab: "settings" } });
                }}
                style={{
                  background: "none", border: "none", padding: 0, color: "var(--accent)",
                  cursor: "pointer", fontSize: "inherit", textDecoration: "underline",
                }}
              >
                Einstellungen → Team & Berechtigungen
              </button>.
            </p>
          </header>

          {error ? (
            <div style={{
              background: "color-mix(in srgb, var(--red) 14%, var(--bg3))",
              border: "1px solid color-mix(in srgb, var(--red) 35%, transparent)",
              borderRadius: 12, padding: 12, marginBottom: 16, color: "var(--red)", fontSize: 13,
            }}>
              {error}
            </div>
          ) : null}

          <form onSubmit={createInvite} style={{
            padding: 18, background: "var(--bg2)", borderRadius: 14, border: "1px solid var(--border)", marginBottom: 20,
          }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)", marginBottom: 12 }}>
              Person einladen
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 180px auto", gap: 10, alignItems: "end" }}>
              <div>
                <label style={labelStyle}>E-Mail</label>
                <input
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  type="email"
                  required
                  placeholder="name@beispiel.de"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Rolle</label>
                <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                  {ROLE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <button type="submit" disabled={savingInvite} style={btnPrimary}>
                {savingInvite ? "…" : "Einladen"}
              </button>
            </div>
            <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 8 }}>
              Einladungslink per E-Mail (SMTP muss in Einstellungen konfiguriert sein).
            </div>
          </form>

          {lastInviteUrl ? (
            <div style={{
              marginBottom: 20, padding: 14, borderRadius: 12,
              border: "1px solid color-mix(in srgb, var(--green) 35%, transparent)",
              background: "color-mix(in srgb, var(--green) 10%, var(--bg3))",
            }}>
              <div style={{ fontSize: 12, color: "var(--green)", marginBottom: 6 }}>Einladungslink</div>
              <div style={{ fontSize: 12, wordBreak: "break-all", color: "var(--text)", marginBottom: 8 }}>{lastInviteUrl}</div>
              <button type="button" onClick={copyInvite} style={btnGhost}>Link kopieren</button>
            </div>
          ) : null}

          {pendingInvites.length > 0 ? (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text2)", marginBottom: 8 }}>
                Offene Einladungen ({pendingInvites.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {pendingInvites.slice(0, 5).map((row) => (
                  <div key={row.jti || row.id} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10,
                    padding: "10px 12px", borderRadius: 10, background: "var(--bg2)", border: "1px solid var(--border)",
                    fontSize: 13,
                  }}>
                    <span style={{ color: "var(--text)" }}>
                      {row.email_lock || row.target_email || "—"} · {roleLabel(row.role)}
                    </span>
                    <button type="button" onClick={() => revokeInvite(row.jti)} style={btnDanger}>Widerrufen</button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text2)", marginBottom: 10 }}>
            Team ({activeCount} aktiv)
          </div>

          <div style={{ borderRadius: 14, border: "1px solid var(--border)", background: "var(--bg2)", overflow: "hidden" }}>
            {loading ? (
              <div style={{ padding: 24, color: "var(--text3)" }}>Lade…</div>
            ) : users.length === 0 ? (
              <div style={{ padding: 24, color: "var(--text3)" }}>Noch keine Benutzer.</div>
            ) : (
              users.map((u) => {
                const aktiv = u.is_active ?? u.aktiv;
                const role = u.role || u.rolle || "assistent";
                const isProtected = role === "owner" || role === "admin";
                return (
                  <div
                    key={u.id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 160px auto",
                      gap: 12,
                      alignItems: "center",
                      padding: "12px 16px",
                      borderTop: "1px solid var(--border)",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500, color: aktiv ? "var(--text)" : "var(--text3)" }}>
                        {u.email || u.benutzername || "—"}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text3)", marginTop: 2 }}>
                        {aktiv ? "Aktiv" : "Deaktiviert"}
                      </div>
                    </div>
                    <div>
                      {isProtected ? (
                        <span style={{ fontSize: 13, color: "var(--text2)" }}>{roleLabel(role)}</span>
                      ) : (
                        <select
                          value={role === "assistent" || role === "steuerberater" ? role : "assistent"}
                          onChange={(e) => changeRole(u.id, e.target.value)}
                          style={{ ...inputStyle, padding: "6px 8px", fontSize: 13 }}
                        >
                          {ROLE_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                      )}
                    </div>
                    <div>
                      {aktiv && !isProtected ? (
                        <button type="button" onClick={() => deactivate(u.id)} style={btnDanger}>Deaktivieren</button>
                      ) : (
                        <span style={{ fontSize: 12, color: "var(--text3)" }}>—</span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div style={{ marginTop: 20 }}>
            <Link to="/" style={{ color: "var(--accent)", fontSize: 14 }}>← Zurück zur App</Link>
          </div>
        </div>
      </div>
    </PermissionGate>
  );
}

const labelStyle = { display: "block", fontSize: 11, color: "var(--text2)", marginBottom: 6 };
const inputStyle = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--border2)",
  background: "var(--bg)",
  color: "var(--text)",
  outline: "none",
};
const btnPrimary = {
  padding: "10px 16px",
  borderRadius: 10,
  border: "none",
  background: "var(--accent)",
  color: "var(--on-accent)",
  fontWeight: 600,
  cursor: "pointer",
  height: 42,
};
const btnGhost = {
  padding: "6px 12px",
  borderRadius: 8,
  border: "1px solid var(--border2)",
  background: "transparent",
  color: "var(--text2)",
  fontSize: 12,
  cursor: "pointer",
};
const btnDanger = {
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid color-mix(in srgb, var(--red) 40%, transparent)",
  background: "transparent",
  color: "var(--red)",
  fontSize: 12,
  cursor: "pointer",
};
