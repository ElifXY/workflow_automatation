import { useState, useEffect } from "react";

/** Sichtbare Breite (Notch, Safari-URL-Leiste, „Desktop-Website“). */
export function readContentLayoutWidth() {
  if (typeof window === "undefined") return 1200;
  const doc = document.documentElement;
  const client = doc?.clientWidth;
  const inner = window.innerWidth;
  const vv = window.visualViewport;
  const vw = vv && vv.width > 32 ? vv.width : inner;
  const w = Math.min(client || inner, inner, vw);
  return Math.max(280, Math.round(w));
}

export function useContentLayoutWidth() {
  const [w, setW] = useState(() => readContentLayoutWidth());
  useEffect(() => {
    const tick = () => setW(readContentLayoutWidth());
    tick();
    window.addEventListener("resize", tick);
    window.addEventListener("orientationchange", tick);
    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener("resize", tick);
      vv.addEventListener("scroll", tick);
    }
    return () => {
      window.removeEventListener("resize", tick);
      window.removeEventListener("orientationchange", tick);
      if (vv) {
        vv.removeEventListener("resize", tick);
        vv.removeEventListener("scroll", tick);
      }
    };
  }, []);
  return w;
}
