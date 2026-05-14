import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PermissionGate, { hasRoleReal } from "../components/PermissionGate";

const API_ROOT = process.env.REACT_APP_API_URL || "/api";

const ROLE_OPTIONS = [
  { value: "assistent", label: "Assistent" },
  { value: "steuerberater", label: "Steuerberater" },
];

function authHeaders() {
  const token = localStorage.getItem("kanzlei_token");
  return token ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

function unwrapData(body) {
  if (!body || typeof body !== "object") return body;
  if (Array.isArray(body.data)) return body.data;
  if (body.data !== undefined) return body.data;
  return body;
}

function buildInviteUrl(inviteToken) {
  if (!inviteToken) return "";
  if (typeof window === "undefined") return `/register-email?invite_token=${encodeURIComponent(inviteToken)}`;
  return `${window.location.origin}/register-email?invite_token=${encodeURIComponent(inviteToken)}`;
}

function jtiShort(jti) {
  if (!jti || typeof jti !== "string") return "—";
  return jti.length <= 14 ? jti : `${jti.slice(0, 8)}…${jti.slice(-4)}`;
}

function fmtTs(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export default function TeamUsers() {
  const canManageTeam = hasRoleReal(["owner", "admin"]);
  const [users, setUsers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [invitesLoading, setInvitesLoading] = useState(true);
  const [error, setError] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("assistent");
  const [inviteHours, setInviteHours] = useState(168);
  const [sendInviteEmail, setSendInviteEmail] = useState(false);
  const [savingInvite, setSavingInvite] = useState(false);
  const [lastInvite, setLastInvite] = useState(null);

  const displayInviteUrl = useMemo(() => {
    if (!lastInvite) return "";
    return lastInvite.invite_url || buildInviteUrl(lastInvite.invite_token);
  }, [lastInvite]);

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
    setInvitesLoading(true);
    try {
      const r = await fetch(`${API_ROOT}/users/invites?limit=80`, { headers: authHeaders() });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setInvites([]);
        return;
      }
      const rows = unwrapData(body);
      setInvites(Array.isArray(rows) ? rows : []);
    } catch {
      setInvites([]);
    } finally {
      setInvitesLoading(false);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshUsers(), refreshInvites()]);
  }, [refreshUsers, refreshInvites]);

  useEffect(() => {
    if (canManageTeam) refreshAll();
  }, [canManageTeam, refreshAll]);

  const createInvite = async (e) => {
    e.preventDefault();
    const emailTrim = inviteEmail.trim().toLowerCase();
    if (sendInviteEmail && !emailTrim) {
      setError("Für den E-Mail-Versand bitte eine Empfänger-Adresse eintragen.");
      return;
    }
    setSavingInvite(true);
    setError("");
    setLastInvite(null);

    const payload = {
      role: inviteRole,
      ttl_hours: Number(inviteHours) || 168,
      email: emailTrim || null,
      send_email: sendInviteEmail,
    };

    try {
      let r = await fetch(`${API_ROOT}/users/invites`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      let body = await r.json().catch(() => ({}));

      if (r.status === 404) {
        r = await fetch(`${API_ROOT}/tenant/invites`, {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ rolle: payload.role, email_lock: payload.email, ttl_hours: payload.ttl_hours }),
        });
        body = await r.json().catch(() => ({}));
      }

      if (!r.ok) throw new Error(body.detail || body.error || body.message || `HTTP ${r.status}`);
      const data = unwrapData(body) || {};
      setLastInvite(data);
      setInviteEmail("");
      await refreshAll();
    } catch (err) {
      setError(err.message || "Einladung konnte nicht erstellt werden");
    } finally {
      setSavingInvite(false);
    }
  };

  const copyInvite = async () => {
    if (!displayInviteUrl) return;
    try {
      await navigator.clipboard.writeText(displayInviteUrl);
    } catch (_) {
      setError("Kopieren fehlgeschlagen. Link bitte manuell kopieren.");
    }
  };

  const revokeInvite = async (jti) => {
    if (!jti || !window.confirm("Einladung wirklich widerrufen?")) return;
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
    if (!window.confirm("Benutzer wirklich deaktivieren?")) return;
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
          <p>Kein Zugriff — nur Mandanten-Admins verwalten das Team.</p>
          <Link to="/" style={{ color: "var(--accent)" }}>Zurück</Link>
        </div>
      }
    >
      <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: "28px 36px" }}>
        <div style={{ maxWidth: 1080, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <div style={{ fontFamily: "var(--font-head)", fontSize: 26, color: "var(--accent)" }}>
              Team & Benutzer
            </div>
            <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>
              Einladungen (E-Mail/Outbox), Historie, Widerruf · Benutzer · Soft-Delete
            </div>
          </div>
          <Link to="/" style={{ color: "var(--accent)", fontSize: 14 }}>← Dashboard</Link>
        </div>

        {error ? (
          <div style={{ background: "color-mix(in srgb, var(--red) 14%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--red) 35%, transparent)", borderRadius: 12, padding: 12, marginBottom: 20, color: "var(--red)" }}>
            {error}
          </div>
        ) : null}

        <form onSubmit={createInvite} style={{
          marginBottom: 12,
          padding: 20,
          background: "var(--bg2)",
          borderRadius: 14,
          border: "1px solid var(--border)",
        }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1.4fr 180px 140px auto",
            gap: 12,
            alignItems: "end",
            marginBottom: 12,
          }}>
            <div>
              <label style={{ display: "block", fontSize: 11, color: "var(--text2)", marginBottom: 6 }}>E-Mail (Lock und/oder Empfänger)</label>
              <input value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} type="email"
                style={inputStyle} placeholder="name@beispiel.de (optional)" />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, color: "var(--text2)", marginBottom: 6 }}>Rolle</label>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                {ROLE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: "block", fontSize: 11, color: "var(--text2)", marginBottom: 6 }}>Gültig (Std.)</label>
              <input
                value={inviteHours}
                onChange={(e) => setInviteHours(Math.max(1, Math.min(720, Number(e.target.value) || 168)))}
                type="number"
                min={1}
                max={720}
                style={inputStyle}
              />
            </div>
            <button type="submit" disabled={savingInvite} style={btnPrimary}>
              {savingInvite ? "…" : "Einladung erstellen"}
            </button>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "var(--text2)", cursor: "pointer" }}>
            <input type="checkbox" checked={sendInviteEmail} onChange={(e) => setSendInviteEmail(e.target.checked)} />
            Einladungs-E-Mail über SMTP-Outbox senden (benötigt <code style={{ fontSize: 11 }}>EMAIL_USER</code> / <code style={{ fontSize: 11 }}>EMAIL_PASS</code>)
          </label>
        </form>

        {lastInvite && (
          <div style={{ marginBottom: 24, padding: 14, borderRadius: 12, border: "1px solid color-mix(in srgb, var(--green) 35%, transparent)", background: "color-mix(in srgb, var(--green) 12%, var(--bg3))" }}>
            <div style={{ fontSize: 12, color: "var(--green)", marginBottom: 8 }}>Zuletzt erstellt</div>
            <div style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text)", wordBreak: "break-all", marginBottom: 10 }}>
              {displayInviteUrl}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <button type="button" onClick={copyInvite} style={btnGhost}>Link kopieren</button>
              {lastInvite.email_outbox ? (
                <span style={{ fontSize: 12, color: "var(--text2)" }}>
                  Outbox #{lastInvite.email_outbox.id} ({lastInvite.email_outbox.status || "pending"})
                </span>
              ) : null}
            </div>
          </div>
        )}

        <div style={{ marginBottom: 14, fontSize: 13, color: "var(--accent)", fontWeight: 600 }}>Einladungen</div>
        <div style={{ overflowX: "auto", borderRadius: 14, border: "1px solid var(--border)", background: "var(--bg2)", marginBottom: 28 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text2)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                <th style={th}>Zeit</th>
                <th style={th}>Status</th>
                <th style={th}>Rolle</th>
                <th style={th}>Lock</th>
                <th style={th}>Empfang</th>
                <th style={th}>Outbox</th>
                <th style={th}>Gelegt</th>
                <th style={th}>SMTP</th>
                <th style={th}>JTI</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {invitesLoading ? (
                <tr><td colSpan={10} style={{ padding: 24, color: "var(--text2)" }}>Lade …</td></tr>
              ) : invites.length === 0 ? (
                <tr><td colSpan={10} style={{ padding: 24, color: "var(--text2)" }}>Noch keine Einträge</td></tr>
              ) : (
                invites.map((row) => {
                  const canRevoke = row.db_status === "pending" && row.status === "pending";
                  return (
                    <tr key={row.jti || row.id} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ ...td, fontSize: 12, color: "var(--text3)" }}>{String(row.created_at ?? "—")}</td>
                      <td style={td}>
                        <span style={{
                          padding: "2px 8px",
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          background: row.status === "pending" ? "color-mix(in srgb, var(--accent) 18%, var(--bg3))" :
                            row.status === "used" ? "color-mix(in srgb, var(--green) 22%, var(--bg3))" :
                              row.status === "revoked" ? "color-mix(in srgb, var(--red) 22%, var(--bg3))" : "color-mix(in srgb, var(--text3) 28%, var(--bg3))",
                          color: "var(--text)",
                        }}>
                          {row.status}
                        </span>
                      </td>
                      <td style={td}>{row.role || "—"}</td>
                      <td style={td}>{row.email_lock || "—"}</td>
                      <td style={td}>{row.target_email || "—"}</td>
                      <td style={{ ...td, fontSize: 12 }}>{row.email_outbox_id != null ? `#${row.email_outbox_id}` : "—"}</td>
                      <td style={{ ...td, fontSize: 11, color: "var(--text3)" }}>{fmtTs(row.email_queued_at)}</td>
                      <td style={{ ...td, fontSize: 11, color: "var(--text3)" }}>{fmtTs(row.email_sent_at)}</td>
                      <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{jtiShort(row.jti)}</td>
                      <td style={td}>
                        {canRevoke ? (
                          <button type="button" onClick={() => revokeInvite(row.jti)} style={btnDanger}>Widerrufen</button>
                        ) : (
                          <span style={{ color: "var(--text3)", fontSize: 12 }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div style={{ marginBottom: 14, fontSize: 13, color: "var(--accent)", fontWeight: 600 }}>Benutzer</div>
        <div style={{ overflowX: "auto", borderRadius: 14, border: "1px solid var(--border)", background: "var(--bg2)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text2)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                <th style={th}>ID</th>
                <th style={th}>E-Mail</th>
                <th style={th}>Login</th>
                <th style={th}>Rolle</th>
                <th style={th}>Aktiv</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 24, color: "var(--text2)" }}>Lade …</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: 24, color: "var(--text2)" }}>Keine Benutzer</td></tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={td}>{u.id}</td>
                    <td style={td}>{u.email || "—"}</td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>{u.benutzername}</td>
                    <td style={td}>
                      <select
                        value={u.role || u.rolle || "assistent"}
                        onChange={(e) => changeRole(u.id, e.target.value)}
                        style={{ ...inputStyle, padding: "6px 8px", fontSize: 13 }}
                      >
                        <option value="assistent">Assistent</option>
                        <option value="steuerberater">Steuerberater</option>
                        <option value="admin">Admin</option>
                      </select>
                    </td>
                    <td style={td}>{(u.is_active ?? u.aktiv) ? "ja" : "nein"}</td>
                    <td style={td}>
                      {(u.is_active ?? u.aktiv) ? (
                        <button type="button" onClick={() => deactivate(u.id)} style={btnDanger}>Deaktivieren</button>
                      ) : (
                        <span style={{ color: "var(--text3)", fontSize: 12 }}>inaktiv</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        </div>
      </div>
    </PermissionGate>
  );
}

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
  padding: "12px 18px",
  borderRadius: 10,
  border: "none",
  background: "var(--accent)",
  color: "var(--on-accent)",
  fontWeight: 600,
  cursor: "pointer",
  height: 42,
};

const btnGhost = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid color-mix(in srgb, var(--green) 45%, transparent)",
  background: "transparent",
  color: "var(--green)",
  fontSize: 12,
  cursor: "pointer",
};

const btnDanger = {
  padding: "8px 12px",
  borderRadius: 8,
  border: "1px solid color-mix(in srgb, var(--red) 40%, transparent)",
  background: "transparent",
  color: "var(--red)",
  fontSize: 12,
  cursor: "pointer",
};

const th = { padding: "14px 16px" };
const td = { padding: "12px 16px", verticalAlign: "middle" };
