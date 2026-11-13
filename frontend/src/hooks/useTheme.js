import { useEffect, useState } from "react";

const KEY = "maritimer.theme"; // "light" | "dark" | "system" (no explicit choice yet)
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function readThemePreference() {
  try {
    return localStorage.getItem(KEY) || "system";
  } catch {
    return "system";
  }
}

function resolve(preference) {
  return preference === "dark" || (preference === "system" && media().matches) ? "dark" : "light";
}

export function applyTheme(preference) {
  const theme = resolve(preference);
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0A1A26" : "#0B3C5D");
  return theme;
}

/**
 * Returns [theme, setTheme] where theme is the theme on screen ("light" | "dark").
 * Until the user picks one, it follows the device setting and reacts to changes.
 */
export function useTheme() {
  const [preference, setPreference] = useState(readThemePreference);
  const [theme, setThemeState] = useState(() => resolve(preference));

  useEffect(() => {
    setThemeState(applyTheme(preference));
    if (preference !== "system") return undefined;
    const mq = media();
    const onChange = () => setThemeState(applyTheme("system"));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference]);

  function setTheme(next) {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* private mode: the theme still applies for this session */
    }
    setPreference(next);
  }

  return [theme, setTheme];
}
