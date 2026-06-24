import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from "react";

export const THEME_STORAGE_KEY = "kanzlei_theme";

/** @typedef {"dark" | "light" | "system"} ThemePreference */

function readStoredPreference() {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "dark" || v === "light" || v === "system") return v;
  } catch {}
  return "light";
}

function prefersDark() {
  if (typeof window === "undefined" || !window.matchMedia) return true;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** @param {ThemePreference} pref */
export function resolveTheme(pref) {
  if (pref === "light") return "light";
  if (pref === "dark") return "dark";
  return prefersDark() ? "dark" : "light";
}

/** @param {"dark"|"light"} resolved */
/** Liest eine CSS-Variable vom aktiven Theme (z. B. Canvas, Chart). */
export function readCssVar(name) {
  if (typeof document === "undefined") return "";
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
  return (raw || "").trim();
}

export function applyDocumentTheme(resolved) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolved);
  try {
    document.documentElement.style.colorScheme =
      resolved === "light" ? "light" : "dark";
  } catch {}
  try {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        "content",
        resolved === "light" ? "#eef2ff" : "#0b0d11",
      );
    }
  } catch {}
}

const ThemeContext = createContext({
  /** @type {ThemePreference} */
  themePref: "light",
  /** @type {"dark"|"light"} */
  resolved: "light",
  /** @param {ThemePreference} p */
  setThemePref: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

export function ThemeQuickSwitch({ compact = false }) {
  const { themePref, setThemePref } = useTheme();
  const seg = (id, label) => (
    <button
      key={id}
      type="button"
      onClick={() => setThemePref(id)}
      style={{
        padding: compact ? "3px 8px" : "4px 10px",
        borderRadius: 8,
        border: "1px solid var(--border2)",
        background: themePref === id ? "var(--bg3)" : "transparent",
        color: themePref === id ? "var(--accent)" : "var(--text2)",
        fontSize: compact ? 10 : 11,
        fontWeight: 600,
        cursor: "pointer",
        fontFamily: "var(--font-body)",
      }}
    >
      {label}
    </button>
  );
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: compact ? 4 : 6,
        flexWrap: "wrap",
      }}
      title="Erscheinungsbild (Hell / Dunkel / System)"
    >
      {!compact ? (
        <span
          style={{
            fontSize: 10,
            color: "var(--text3)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          Ansicht
        </span>
      ) : null}
      <div
        style={{
          display: "inline-flex",
          gap: 3,
          background: "var(--bg3)",
          padding: 3,
          borderRadius: 10,
          border: "1px solid var(--border)",
        }}
      >
        {seg("system", "Auto")}
        {seg("light", "Hell")}
        {seg("dark", "Dunkel")}
      </div>
    </div>
  );
}

export function ThemeProvider({ children }) {
  const [themePref, setThemePrefState] = useState(readStoredPreference);
  const [systemDark, setSystemDark] = useState(prefersDark);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key !== THEME_STORAGE_KEY || !e.newValue) return;
      if (e.newValue === "dark" || e.newValue === "light" || e.newValue === "system") {
        setThemePrefState(e.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const resolved = useMemo(
    () =>
      themePref === "system"
        ? systemDark
          ? "dark"
          : "light"
        : themePref,
    [themePref, systemDark],
  );

  useLayoutEffect(() => {
    applyDocumentTheme(resolved);
  }, [resolved]);

  const setThemePref = useCallback((p) => {
    setThemePrefState(p);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, p);
    } catch {}
  }, []);

  const value = useMemo(
    () => ({ themePref, setThemePref, resolved }),
    [themePref, setThemePref, resolved],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
