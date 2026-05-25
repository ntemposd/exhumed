import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "exhumed-theme";
const DARK_VALUE = "dark";

export function useTheme() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const prefersDark = stored === DARK_VALUE;
    setIsDark(prefersDark);
    document.documentElement.dataset.theme = prefersDark ? DARK_VALUE : "";
  }, []);

  const toggleTheme = useCallback(() => {
    setIsDark((current) => {
      const next = !current;
      document.documentElement.dataset.theme = next ? DARK_VALUE : "";
      window.localStorage.setItem(STORAGE_KEY, next ? DARK_VALUE : "light");
      return next;
    });
  }, []);

  return { isDark, toggleTheme };
}
