/**
 * 4-Schritte-Onboarding-Wizard
 */
import { useState } from "react";
import { updateSetting } from "../api";

const WIZARD_HIDE_KEY = "kanzlei_onboarding_wizard_hidden";

export function readWizardHidden() {
  try {
    return localStorage.getItem(WIZARD_HIDE_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeWizardHidden(v = true) {
  try {
    localStorage.setItem(WIZARD_HIDE_KEY, v ? "1" : "0");
  } catch {}
}

export default function OnboardingWizard({ status, onTab, onRefresh }) {
  const [step, setStep] = useState(() => {
    const next = status?.naechster_schritt?.nr;
    return next ? Math.max(0, next - 1) : 0;
  });
  const [kanzleiName, setKanzleiName] = useState("");
  const [kanzleiEmail, setKanzleiEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [hidden, setHidden] = useState(readWizardHidden);

  const schritte = status?.wizard_schritte || [];
  if (!schritte.length || status?.bereit || hidden) return null;

  const current = schritte[step] || schritte[0];
  const erledigt = schritte.filter((s) => s.erledigt).length;

  const geheZu = (s) => {
    if (s.tab && onTab) onTab(s.tab);
    if (s.settings_tab) {
      try {
        sessionStorage.setItem("kanzlei_settings_open_tab", s.settings_tab);
      } catch {}
    }
  };

  const speichereKanzlei = async () => {
    setSaving(true);
    try {
      if (kanzleiName.trim()) await updateSetting("kanzlei_name", kanzleiName.trim());
      if (kanzleiEmail.trim()) await updateSetting("kanzlei_email", kanzleiEmail.trim());
      await onRefresh?.();
    } finally {
      setSaving(false);
    }
  };

  const weiter = () => {
    if (step < schritte.length - 1) setStep(step + 1);
    else onRefresh?.();
  };

  return (
    <div style={{
      marginBottom: 24,
      borderRadius: 14,
      border: "1px solid color-mix(in srgb, var(--accent) 28%, var(--border))",
      background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--bg2)), var(--bg2))",
      overflow: "hidden",
    }}>
      <div style={{
        display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 12,
        padding: "16px 18px", borderBottom: "1px solid var(--border)",
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16, color: "var(--text)" }}>
            Einrichtung — Schritt {current?.nr || step + 1} von {schritte.length}
          </div>
          <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 4 }}>
            {erledigt}/{schritte.length} erledigt · ca. 5 Minuten
          </div>
        </div>
        <button
          type="button"
          onClick={() => { writeWizardHidden(true); setHidden(true); }}
          style={{
            border: "1px solid var(--border2)", background: "transparent",
            borderRadius: 8, padding: "6px 12px", fontSize: 12, cursor: "pointer", color: "var(--text3)",
          }}
        >
          Später
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, padding: "12px 18px 0", flexWrap: "wrap" }}>
        {schritte.map((s, i) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStep(i)}
            style={{
              padding: "6px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
              border: i === step ? "1px solid var(--accent)" : "1px solid var(--border2)",
              background: s.erledigt
                ? "color-mix(in srgb, var(--green) 12%, var(--bg3))"
                : i === step
                  ? "color-mix(in srgb, var(--accent) 12%, var(--bg3))"
                  : "var(--bg3)",
              color: s.erledigt ? "var(--green)" : i === step ? "var(--accent)" : "var(--text3)",
              fontWeight: i === step ? 600 : 400,
            }}
          >
            {s.erledigt ? "✓" : s.nr} {s.label.split(" ")[0]}
          </button>
        ))}
      </div>

      <div style={{ padding: "18px 18px 20px" }}>
        <div style={{ fontWeight: 600, fontSize: 15, color: "var(--text)", marginBottom: 6 }}>
          {current?.label}
        </div>
        <div style={{ fontSize: 13, color: "var(--text2)", lineHeight: 1.55, marginBottom: 16 }}>
          {current?.hinweis}
        </div>

        {current?.id === "kanzlei" && !current.erledigt ? (
          <div style={{ display: "grid", gap: 10, maxWidth: 420, marginBottom: 14 }}>
            <input
              placeholder="Kanzleiname"
              value={kanzleiName}
              onChange={(e) => setKanzleiName(e.target.value)}
              style={{
                padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border2)",
                background: "var(--bg)", color: "var(--text)", fontSize: 13,
              }}
            />
            <input
              type="email"
              placeholder="Kanzlei-E-Mail"
              value={kanzleiEmail}
              onChange={(e) => setKanzleiEmail(e.target.value)}
              style={{
                padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border2)",
                background: "var(--bg)", color: "var(--text)", fontSize: 13,
              }}
            />
            <button
              type="button"
              disabled={saving}
              onClick={speichereKanzlei}
              style={{
                padding: "10px 14px", borderRadius: 8, border: "none",
                background: "var(--accent)", color: "var(--on-accent)",
                fontWeight: 600, fontSize: 13, cursor: "pointer", width: "fit-content",
              }}
            >
              {saving ? "Speichern…" : "Speichern"}
            </button>
          </div>
        ) : null}

        {current?.erledigt ? (
          <div style={{
            fontSize: 13, color: "var(--green)", marginBottom: 14,
            padding: "10px 12px", background: "color-mix(in srgb, var(--green) 10%, var(--bg3))",
            borderRadius: 8,
          }}>
            ✓ Erledigt
          </div>
        ) : null}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {!current?.erledigt && current?.id !== "kanzlei" ? (
            <button
              type="button"
              onClick={() => geheZu(current)}
              style={{
                padding: "10px 16px", borderRadius: 8, border: "none",
                background: "var(--accent)", color: "var(--on-accent)",
                fontWeight: 600, fontSize: 13, cursor: "pointer",
              }}
            >
              {current?.id === "email" ? "E-Mail einrichten" : current?.id === "vorlage" ? "Vorlagen öffnen" : "Jetzt erledigen"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={weiter}
            style={{
              padding: "10px 16px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "var(--bg3)", fontSize: 13, cursor: "pointer", color: "var(--text2)",
            }}
          >
            {step < schritte.length - 1 ? "Nächster Schritt" : "Aktualisieren"}
          </button>
        </div>
      </div>
    </div>
  );
}
