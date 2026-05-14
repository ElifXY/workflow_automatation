import { useEffect, useState } from "react";
import PermissionGate from "../components/PermissionGate";

const API_ROOT = process.env.REACT_APP_API_URL || "/api";

export default function AdminUsers() {
  const role = (localStorage.getItem("role") || localStorage.getItem("kanzlei_rolle") || "").toLowerCase();
  const isAdminish = role === "admin" || role === "owner";
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAdminish) return;
    const token = localStorage.getItem("kanzlei_token");
    fetch(`${API_ROOT}/admin/users`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(async (r) => {
        const body = await r.json().catch(() => []);
        if (!r.ok) throw new Error(body?.error || body?.detail || `HTTP ${r.status}`);
        setUsers(Array.isArray(body) ? body : []);
      })
      .catch((e) => setError(e.message || "Fehler"));
  }, [isAdminish]);

  return (
    <PermissionGate roles={["owner", "admin"]} fallback={<div style={{ padding: 16 }}>Kein Zugriff</div>}>
      <div style={{ padding: 16 }}>
        <h2>Admin Users</h2>
        {error ? <div style={{ color: "var(--red)", marginBottom: 12 }}>{error}</div> : null}
        <ul>
          {users.map((u) => (
            <li key={`${u.benutzername}:${u.email || ""}`}>
              {(u.email || u.benutzername)} - {u.rolle}
            </li>
          ))}
        </ul>
      </div>
    </PermissionGate>
  );
}
