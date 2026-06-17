"use client";
import React from "react";

export type Theme = "light" | "dark";

// Reads the theme set on <html> by the pre-paint inline script (app/layout.tsx),
// and persists changes to localStorage. The attribute is the source of truth so the
// hook stays in sync with the no-flash boot script.
export function useTheme(): [Theme, (t: Theme) => void, () => void] {
  const [theme, setThemeState] = React.useState<Theme>("light");

  React.useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "light";
    setThemeState(current);
  }, []);

  const setTheme = React.useCallback((t: Theme) => {
    setThemeState(t);
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("aba.theme", t); } catch { /* ignore */ }
  }, []);

  const toggle = React.useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("aba.theme", next); } catch { /* ignore */ }
      return next;
    });
  }, []);

  return [theme, setTheme, toggle];
}
