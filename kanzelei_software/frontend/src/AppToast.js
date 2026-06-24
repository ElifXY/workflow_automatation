/**
 * Globale Toast-Benachrichtigungen inkl. Undo-Aktion
 */
import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(null);

const ToastContainer = ({ toasts }) => (
  <div style={{
    position: "fixed", top: 20, right: 12, zIndex: 9999,
    display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-end",
    maxWidth: "calc(100vw - 24px)", pointerEvents: "none",
  }}>
    {toasts.map((t) => {
      const colors = { success: "var(--green)", error: "var(--red)", info: "var(--blue)", warn: "var(--orange)" };
      const c = colors[t.type] || "var(--accent)";
      return (
        <div key={t.id} style={{
          background: "var(--bg3)", border: `1px solid color-mix(in srgb, ${c} 32%, transparent)`,
          borderLeft: `3px solid ${c}`, color: "var(--text)",
          borderRadius: "var(--radius)", padding: "12px 16px",
          width: "min(340px, calc(100vw - 24px))", minWidth: 0, maxWidth: "100%",
          fontSize: 13, fontWeight: 500, pointerEvents: "auto",
          animation: "slideIn 0.25s ease both",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
        }}>
          <span>{t.text}</span>
          {t.action ? (
            <button type="button" onClick={t.action.onClick} style={{
              flexShrink: 0, padding: "4px 10px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "var(--bg2)", color: "var(--accent)", fontSize: 12, fontWeight: 600, cursor: "pointer",
            }}>
              {t.action.label}
            </button>
          ) : null}
        </div>
      );
    })}
  </div>
);

export function AppToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((p) => p.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((text, type = "success", action = null) => {
    const id = Date.now() + Math.random();
    setToasts((p) => [...p, { id, text, type, action }]);
    const ms = action ? 8000 : 4000;
    setTimeout(() => dismiss(id), ms);
    return id;
  }, [dismiss]);

  const toastUndo = useCallback((text, undoFn, type = "warn") => {
    const id = Date.now() + Math.random();
    setToasts((p) => [...p, {
      id,
      text,
      type,
      action: {
        label: "Rückgängig",
        onClick: async () => {
          dismiss(id);
          try {
            await undoFn();
          } catch (e) {
            toast(e?.message || "Rückgängig fehlgeschlagen", "error");
          }
        },
      },
    }]);
    setTimeout(() => dismiss(id), 8000);
  }, [dismiss, toast]);

  return (
    <ToastContext.Provider value={{ toast, toastUndo }}>
      {children}
      <ToastContainer toasts={toasts} />
    </ToastContext.Provider>
  );
}

export function useAppToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useAppToast muss innerhalb von AppToastProvider verwendet werden");
  }
  return ctx;
}
