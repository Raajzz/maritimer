import { useEffect, useState } from "react";

const KEY = "maritimer.theme"; // "light" | "dark" | "system"
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function readThemePreference() {
  try {
    return localStorage.getItem(KEY) || "system";
  } catch {
    return "system";
  }
}

export function applyTheme(preference) {
  const dark = preference === "dark" || (preference === "system" && media().matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0A1A26" : "#0B3C5D");
}

/** Theme preference persisted per browser; "system" follows the OS and reacts to changes. */
export function useTheme() {
  const [preference, setPreference] = useState(readThemePreference);

  useEffect(() => {
    applyTheme(preference);
    try {
      localStorage.setItem(KEY, preference);
    } catch {
      /* private mode: theme still applies for this session */
    }
    if (preference !== "system") return undefined;
    const mq = media();
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference]);

  return [preference, setPreference];
}
