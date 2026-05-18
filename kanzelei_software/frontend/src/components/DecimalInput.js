import { useState, useEffect } from "react";

const DECIMAL_RE = /^-?\d*[.,]?\d*$/;
const INTEGER_RE = /^-?\d*$/;

export function parseDecimalInput(raw, fallback = 0) {
  const s = String(raw ?? "").trim().replace(",", ".");
  if (s === "" || s === "-") return fallback;
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : fallback;
}

export function isValidDecimalTyping(raw, integer = false) {
  return raw === "" || (integer ? INTEGER_RE : DECIMAL_RE).test(String(raw));
}

/** Entfernt führende Nullen (0785 → 785), behält 0,5 / 0.5. */
export function normalizeDecimalTyping(raw, integer = false) {
  if (raw === "" || raw === "-" || raw === "," || raw === ".") return raw;
  if (!integer) {
    if (/^0[.,]\d*$/.test(raw)) return raw;
    if (/^0+[1-9]/.test(raw)) return raw.replace(/^0+/, "");
    return raw;
  }
  if (/^0+\d/.test(raw)) return raw.replace(/^0+/, "") || "0";
  return raw;
}

/**
 * Dezimal-/Zahleneingabe ohne führende 0 beim Tippen.
 * Leeres Feld während der Eingabe: Parent-Wert erst beim Verlassen des Feldes (blur).
 */
export default function DecimalInput({
  value,
  onChange,
  integer = false,
  min,
  max,
  step,
  placeholder,
  style = {},
  className,
  emptyValue = 0,
  showEmptyWhenZero = true,
  disabled = false,
  onBlur: onBlurProp,
  onFocus: onFocusProp,
  ...rest
}) {
  const [local, setLocal] = useState("");
  const [focused, setFocused] = useState(false);

  const toDisplay = (v) => {
    if (v === "" || v === null || v === undefined) return "";
    if (showEmptyWhenZero && Number(v) === 0) return "";
    return String(v);
  };

  useEffect(() => {
    if (!focused) setLocal(toDisplay(value));
  }, [value, focused, showEmptyWhenZero]);

  const clamp = (n) => {
    let x = n;
    if (min != null) x = Math.max(min, x);
    if (max != null) x = Math.min(max, x);
    return x;
  };

  const commit = (raw) => {
    let n = integer
      ? parseInt(String(raw).replace(",", "."), 10)
      : parseDecimalInput(raw, emptyValue);
    if (!Number.isFinite(n)) n = emptyValue;
    n = clamp(n);
    onChange(n);
    return n;
  };

  const handleChange = (raw) => {
    if (!isValidDecimalTyping(raw, integer)) return;
    const normalized = normalizeDecimalTyping(raw, integer);
    setLocal(normalized);
    /* Parent erst bei blur aktualisieren, wenn Feld leer — verhindert sofortige „0“ / „1“. */
    if (normalized === "" || normalized === "-") return;
    const partial = integer
      ? parseInt(normalized, 10)
      : parseFloat(normalized.replace(",", "."));
    if (Number.isFinite(partial)) onChange(clamp(partial));
  };

  return (
    <input
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      className={className}
      disabled={disabled}
      placeholder={placeholder}
      step={step}
      value={focused ? local : toDisplay(value)}
      onFocus={(e) => {
        setFocused(true);
        setLocal(toDisplay(value));
        onFocusProp?.(e);
        requestAnimationFrame(() => {
          try { e.target.select(); } catch { /* ignore */ }
        });
      }}
      onBlur={(e) => {
        setFocused(false);
        const n = commit(local);
        setLocal(toDisplay(n));
        onBlurProp?.(e);
      }}
      onChange={(e) => handleChange(e.target.value)}
      style={style}
      {...rest}
    />
  );
}
