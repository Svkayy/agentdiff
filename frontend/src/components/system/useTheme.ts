import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "agentdiff-theme";
export type Theme = "light" | "dark";

/** Reads the persisted theme, defaulting to "light" (no system-preference
 * detection — DESIGN.md: default light, class-based dark mode only). */
function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "dark" ? "dark" : "light";
}

function applyThemeClass(theme: Theme) {
  const root = window.document.documentElement;
  root.classList.toggle("dark", theme === "dark");
}

/**
 * Brutalist design system's theme hook — adapts the reference template's
 * `next-themes` usage to plain React state + localStorage, since this app
 * is Vite (not Next). Applies/removes the `dark` class on `<html>`;
 * Tailwind's `darkMode: "class"` (see tailwind.config.js) does the rest.
 *
 * No system-preference (`prefers-color-scheme`) detection — default is
 * always light until the user explicitly toggles, per the locked
 * architecture decision.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme());

  useEffect(() => {
    applyThemeClass(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage may be unavailable (private mode, disabled storage) —
      // theme still applies for the current session via React state.
    }
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark");
  }, [theme, setTheme]);

  return { theme, setTheme, toggleTheme };
}
