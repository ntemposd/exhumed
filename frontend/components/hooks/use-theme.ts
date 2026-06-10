import { useCallback, useEffect, useState } from "react";

import {
  THEME_DARK,
  THEME_LIGHT,
  THEME_STORAGE_KEY,
  applyThemeToDocument,
  shouldUseDarkTheme,
} from "@/lib/theme";

function readDarkFromDocument(): boolean {
  return typeof document !== "undefined" && document.documentElement.dataset.theme === THEME_DARK;
}

export function useTheme() {
  // The beforeInteractive theme script stamps data-theme before first paint.
  const [isDark, setIsDark] = useState(readDarkFromDocument);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const syncFromPreference = () => {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === THEME_DARK || stored === THEME_LIGHT) {
        return;
      }

      const nextIsDark = shouldUseDarkTheme(stored, mediaQuery.matches);
      applyThemeToDocument(nextIsDark);
      setIsDark(nextIsDark);
    };

    mediaQuery.addEventListener("change", syncFromPreference);
    return () => mediaQuery.removeEventListener("change", syncFromPreference);
  }, []);

  const toggleTheme = useCallback(() => {
    setIsDark((current) => {
      const next = !current;
      applyThemeToDocument(next);
      window.localStorage.setItem(THEME_STORAGE_KEY, next ? THEME_DARK : THEME_LIGHT);
      return next;
    });
  }, []);

  return { isDark, toggleTheme };
}
