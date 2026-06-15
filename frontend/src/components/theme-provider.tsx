import { useCallback, useEffect, useState } from "react";

import { ThemeContext, type Theme } from "@/components/theme";

const STORAGE_KEY = "signaldeck-theme";

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getThemeStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function getStoredTheme(): Theme {
  const stored = getThemeStorage()?.getItem(STORAGE_KEY);
  return (stored === "light" || stored === "dark" || stored === "system") ? stored : "system";
}

function storeTheme(theme: Theme) {
  getThemeStorage()?.setItem(STORAGE_KEY, theme);
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") {
    return;
  }

  const resolved = theme === "system" ? getSystemTheme() : theme;
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    storeTheme(next);
    applyTheme(next);
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
