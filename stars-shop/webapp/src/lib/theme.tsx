import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { onTelegramEvent, paintChrome, telegramColorScheme } from "./telegram";

export type ThemePref = "dark" | "light" | "telegram";
const STORAGE_KEY = "pulsar.theme";

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "dark" || v === "light" || v === "telegram") return v;
  } catch {
    /* storage unavailable (private mode) */
  }
  return "dark"; // premium dark theme by default
}

function resolve(pref: ThemePref): "dark" | "light" {
  if (pref === "telegram") return telegramColorScheme() ?? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  return pref;
}

const ThemeContext = createContext<{ pref: ThemePref; theme: "dark" | "light"; setPref: (p: ThemePref) => void }>({
  pref: "dark",
  theme: "dark",
  setPref: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(readPref);
  // Re-render when Telegram switches its theme; `theme` is derived each render.
  const [, setTick] = useState(0);
  const theme = resolve(pref);

  useEffect(() => onTelegramEvent("themeChanged", () => setTick((t) => t + 1)), []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--c-bg").trim() || (theme === "dark" ? "#07080c" : "#f4f5f9");
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
    paintChrome(bg);
  }, [theme]);

  const setPref = useCallback((p: ThemePref) => {
    setPrefState(p);
    try {
      localStorage.setItem(STORAGE_KEY, p);
    } catch {
      /* ignore */
    }
  }, []);

  return <ThemeContext.Provider value={{ pref, theme, setPref }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);

/** Apply admin-defined brand accents. */
export function applyAccents(accents: { accent_primary: string; accent_secondary: string; accent_tertiary: string }): void {
  const root = document.documentElement.style;
  root.setProperty("--c-accent", accents.accent_primary);
  root.setProperty("--c-accent-2", accents.accent_secondary);
  root.setProperty("--c-accent-3", accents.accent_tertiary);
}
