import { useState, useEffect, useRef } from "react";

function MandantForm({ onSubmit, initialData = null, onCancel, loading }) {

  // ==============================
  // 🧠 STATE
  // ==============================

  const [form, setForm] = useState({
    name: "",
    email: "",
    umsatz: ""
  });

  const [error, setError] = useState("");

  // ==============================
  // 🔄 INITIAL DATA SYNC (ROBUST)
  // ==============================
  
  const initialized = useRef(false);

useEffect(() => {
  if (initialData && !initialized.current) {
    setForm({
      name: initialData.name || "",
      email: initialData.email || "",
      umsatz: initialData.umsatz || ""
    });

    initialized.current = true;
  }
}, [initialData]);

  // ==============================
  // ✏️ CHANGE HANDLER
  // ==============================

  const handleChange = (field, value) => {
    setForm(prev => ({
      ...prev,
      [field]: value
    }));

    if (error) setError("");
  };

  // ==============================
  // ✅ VALIDATION
  // ==============================

  const validate = () => {

    if (!form.name.trim()) return "Name fehlt";

    if (form.email && !form.email.includes("@")) {
      return "Ungültige Email";
    }

    if (!form.umsatz || isNaN(form.umsatz)) {
      return "Umsatz muss Zahl sein";
    }

    if (Number(form.umsatz) < 0) {
      return "Umsatz ungültig";
    }

    return null;
  };

  // ==============================
  // 🚀 SUBMIT
  // ==============================

  const handleSubmit = async () => {

    const validationError = validate();

    if (validationError) {
      setError(validationError);
      return;
    }

    setError("");

    try {
      await onSubmit({
        name: form.name.trim(),
        email: form.email.trim(),
        umsatz: parseFloat(form.umsatz)
      });
    } catch (e) {
      setError(e.message || "Fehler beim Speichern");
    }
  };

  // ==============================
  // ⌨️ ENTER SUPPORT
  // ==============================

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  // ==============================
  // 🎨 UI
  // ==============================

  return (
    <div style={{
      background: "var(--bg2)",
      color: "var(--text)",
      padding: "20px",
      borderRadius: "14px",
      border: "1px solid var(--border)",
      boxShadow: "var(--shadow-elev)",
      maxWidth: "420px"
    }}>

      <h3 style={{ marginBottom: "15px", color: "var(--accent)", fontFamily: "var(--font-head)" }}>
        {initialData ? "✏️ Mandant bearbeiten" : "➕ Neuer Mandant"}
      </h3>

      {/* ERROR */}
      {error && (
        <div style={{
          background: "color-mix(in srgb, var(--red) 12%, var(--bg3))",
          color: "var(--red)",
          border: "1px solid color-mix(in srgb, var(--red) 30%, transparent)",
          padding: "10px",
          borderRadius: "8px",
          marginBottom: "10px"
        }}>
          {error}
        </div>
      )}

      {/* NAME */}
      <input
        placeholder="Name"
        value={form.name}
        disabled={!!initialData} // 🔥 verhindert Key-Bugs
        onChange={e => handleChange("name", e.target.value)}
        onKeyDown={handleKeyDown}
        style={inputStyle}
      />

      {/* EMAIL */}
      <input
        placeholder="Email"
        value={form.email}
        onChange={e => handleChange("email", e.target.value)}
        onKeyDown={handleKeyDown}
        style={inputStyle}
      />

      {/* UMSATZ */}
      <input
        placeholder="Umsatz (€)"
        value={form.umsatz}
        onChange={e => handleChange("umsatz", e.target.value)}
        onKeyDown={handleKeyDown}
        style={inputStyle}
      />

      {/* BUTTONS */}
      <div style={{ marginTop: "10px" }}>

        <button
          onClick={handleSubmit}
          disabled={loading}
          style={{
            ...buttonStyle,
            background: "var(--green)",
            color: "color-mix(in srgb, white 96%, var(--green))",
          }}
        >
          {loading ? "Speichert..." : "💾 Speichern"}
        </button>

        {onCancel && (
          <button
            onClick={onCancel}
            style={{
              ...buttonStyle,
              background: "var(--bg3)",
              color: "var(--text2)",
              border: "1px solid var(--border2)",
              marginLeft: "10px"
            }}
          >
            Abbrechen
          </button>
        )}
      </div>

    </div>
  );
}

// ==============================
// 🎨 STYLES
// ==============================

const inputStyle = {
  width: "100%",
  padding: "10px",
  marginBottom: "10px",
  borderRadius: "8px",
  border: "1px solid var(--border2)",
  background: "var(--bg)",
  color: "var(--text)",
  fontSize: "14px",
  outline: "none"
};

const buttonStyle = {
  padding: "10px 15px",
  border: "none",
  borderRadius: "8px",
  cursor: "pointer",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
};

export default MandantForm;
