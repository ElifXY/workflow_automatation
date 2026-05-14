import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { meGet, meUpdate, mePasswordUpdate, meLogoutAll, authLogout } from "../api";
import { getViewAsRole, hasRoleReal } from "../components/PermissionGate";

const box = {
  background: "var(--bg2)",
  border: "1px solid var(--border)",
  borderRadius: 12,
  padding: 16,
  marginBottom: 14,
};

const input = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid var(--border2)",
  background: "var(--bg)",
  color: "var(--text)",
  outline: "none",
};

const label = { fontSize: 12, color: "var(--text2)", marginBottom: 6, display: "block" };

function BoolRow({ checked, onChange, title }) {
  return (
    <label style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8, color: "var(--text)" }}>
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{title}</span>
    </label>
  );
}

export default function Profile() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [okMsg, setOkMsg] = useState("");
  const [me, setMe] = useState(null);
  const [form, setForm] = useState({
    vorname: "",
    nachname: "",
    telefon: "",
    sprache: "de",
    dark_mode: true,
    notify_email: true,
    notify_updates: true,
    notify_deadlines: true,
  });
  const [pw, setPw] = useState({ aktuelles_passwort: "", neues_passwort: "", bestaetigen: "" });

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await meGet();
      setMe(data);
      setForm((p) => ({
        ...p,
        vorname: data?.vorname || "",
        nachname: data?.nachname || "",
        telefon: data?.telefon || "",
        sprache: data?.sprache || "de",
        dark_mode: data?.dark_mode !== false,
        notify_email: data?.notify_email !== false,
        notify_updates: data?.notify_updates !== false,
        notify_deadlines: data?.notify_deadlines !== false,
      }));
    } catch (e) {
      setError(e.message || "Profil konnte nicht geladen werden");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveProfile = async () => {
    setSaving(true);
    setError("");
    setOkMsg("");
    try {
      await meUpdate(form);
      setOkMsg("Profil gespeichert");
      await load();
    } catch (e) {
      setError(e.message || "Speichern fehlgeschlagen");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async () => {
    setSaving(true);
    setError("");
    setOkMsg("");
    try {
      await mePasswordUpdate(pw);
      setPw({ aktuelles_passwort: "", neues_passwort: "", bestaetigen: "" });
      setOkMsg("Passwort geändert");
      await load();
    } catch (e) {
      setError(e.message || "Passwortänderung fehlgeschlagen");
    } finally {
      setSaving(false);
    }
  };

  const logoutAll = async () => {
    setSaving(true);
    setError("");
    setOkMsg("");
    try {
      await meLogoutAll();
      localStorage.removeItem("kanzlei_token");
      localStorage.removeItem("token");
      localStorage.removeItem("kanzlei_refresh_token");
      window.location.href = "/login";
    } catch (e) {
      setError(e.message || "Session-Logout fehlgeschlagen");
      setSaving(false);
    }
  };

  const doLogout = async () => {
    try {
      await authLogout();
    } catch {}
    localStorage.removeItem("kanzlei_token");
    localStorage.removeItem("token");
    localStorage.removeItem("kanzlei_refresh_token");
    window.location.href = "/login";
  };

  if (loading) return <div style={{ padding: 24, color: "var(--text)" }}>Profil lädt ...</div>;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)", padding: 24 }}>
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <h2 style={{ margin: 0, color: "var(--accent)", fontFamily: "var(--font-head)" }}>Profil & Sicherheit</h2>
          <Link to="/" style={{ color: "var(--accent)" }}>Zurück</Link>
        </div>
        {error ? (
          <div style={{ ...box, background: "color-mix(in srgb, var(--red) 12%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--red) 35%, transparent)", color: "var(--red)" }}>{error}</div>
        ) : null}
        {okMsg ? (
          <div style={{ ...box, background: "color-mix(in srgb, var(--green) 10%, var(--bg3))", border: "1px solid color-mix(in srgb, var(--green) 35%, transparent)", color: "var(--green)" }}>{okMsg}</div>
        ) : null}

        <div style={box}>
          <h3 style={{ marginTop: 0 }}>Basis Profil</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={label}>Vorname</label>
              <input style={input} value={form.vorname} onChange={(e) => setForm({ ...form, vorname: e.target.value })} />
            </div>
            <div>
              <label style={label}>Nachname</label>
              <input style={input} value={form.nachname} onChange={(e) => setForm({ ...form, nachname: e.target.value })} />
            </div>
            <div>
              <label style={label}>E-Mail (read-only)</label>
              <input style={{ ...input, opacity: 0.7 }} readOnly value={me?.email || ""} />
            </div>
            <div>
              <label style={label}>Telefon</label>
              <input style={input} value={form.telefon} onChange={(e) => setForm({ ...form, telefon: e.target.value })} />
            </div>
            <div>
              <label style={label}>Sprache</label>
              <select style={input} value={form.sprache} onChange={(e) => setForm({ ...form, sprache: e.target.value })}>
                <option value="de">Deutsch</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <BoolRow checked={form.dark_mode} onChange={(v) => setForm({ ...form, dark_mode: v })} title="Dark Mode" />
            <BoolRow checked={form.notify_email} onChange={(v) => setForm({ ...form, notify_email: v })} title="E-Mail Benachrichtigungen" />
            <BoolRow checked={form.notify_updates} onChange={(v) => setForm({ ...form, notify_updates: v })} title="System Updates" />
            <BoolRow checked={form.notify_deadlines} onChange={(v) => setForm({ ...form, notify_deadlines: v })} title="Aufgaben / Fristen" />
          </div>
          <button onClick={saveProfile} disabled={saving} style={{ marginTop: 12, padding: "10px 14px", borderRadius: 8, border: "none", background: "var(--accent)", color: "var(--on-accent)", fontWeight: 600 }}>
            {saving ? "Speichern ..." : "Profil speichern"}
          </button>
        </div>

        <div style={box}>
          <h3 style={{ marginTop: 0 }}>Sicherheit</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            <div>
              <label style={label}>Aktuelles Passwort</label>
              <input type="password" style={input} value={pw.aktuelles_passwort} onChange={(e) => setPw({ ...pw, aktuelles_passwort: e.target.value })} />
            </div>
            <div>
              <label style={label}>Neues Passwort</label>
              <input type="password" style={input} value={pw.neues_passwort} onChange={(e) => setPw({ ...pw, neues_passwort: e.target.value })} />
            </div>
            <div>
              <label style={label}>Bestätigen</label>
              <input type="password" style={input} value={pw.bestaetigen} onChange={(e) => setPw({ ...pw, bestaetigen: e.target.value })} />
            </div>
          </div>
          <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button onClick={changePassword} disabled={saving} style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid color-mix(in srgb, var(--green) 40%, transparent)", background: "color-mix(in srgb, var(--green) 14%, var(--bg3))", color: "var(--green)" }}>
              Passwort ändern
            </button>
            <button onClick={logoutAll} disabled={saving} style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid color-mix(in srgb, var(--orange) 40%, transparent)", background: "color-mix(in srgb, var(--orange) 14%, var(--bg3))", color: "var(--orange)" }}>
              Alle Sessions abmelden
            </button>
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color: "var(--text2)" }}>
            Rolle: <b>{me?.rolle || me?.role || "—"}</b>
            {getViewAsRole() && hasRoleReal(["owner", "admin"]) ? (
              <span>
                {" "}
                · <span style={{ color: "var(--orange)", fontWeight: 600 }}>Menü-Vorschau: {getViewAsRole()}</span>
              </span>
            ) : null}
            {" "}· letzter Login: <b>{String(me?.last_login || "n/a")}</b> · Passwort zuletzt geändert: <b>{String(me?.password_last_changed_at || "n/a")}</b>
          </div>
        </div>

        <div style={box}>
          <h3 style={{ marginTop: 0 }}>Kanzlei-Infos (read-only MVP)</h3>
          <div style={{ fontSize: 13, lineHeight: 1.8 }}>
            <div><b>Name:</b> {me?.kanzlei_profil?.name || "-"}</div>
            <div><b>Adresse:</b> {me?.kanzlei_profil?.adresse || "-"}</div>
            <div><b>Telefon:</b> {me?.kanzlei_profil?.telefon || "-"}</div>
            <div><b>Logo:</b> {me?.kanzlei_profil?.logo_url || "-"}</div>
          </div>
        </div>

        <div style={box}>
          <h3 style={{ marginTop: 0 }}>Account Aktionen</h3>
          <button onClick={doLogout} style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid var(--border2)", background: "transparent", color: "var(--text)", marginRight: 8 }}>
            Logout
          </button>
          <button disabled style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid color-mix(in srgb, var(--red) 35%, transparent)", background: "color-mix(in srgb, var(--red) 12%, var(--bg3))", color: "var(--red)", opacity: 0.7 }}>
            Account löschen (gesperrt im MVP)
          </button>
        </div>
      </div>
    </div>
  );
}

