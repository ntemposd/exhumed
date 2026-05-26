import { useCallback, useState } from "react";

const STORAGE_KEY = "exhumed-theme";
const DARK_VALUE = "dark";

export function useTheme() {
  // The inline script in layout.tsx already stamped data-theme on <html>
  // before first paint, so reading it here gives the correct initial value
  // without any effect — no flash, no correction cycle.
  const [isDark, setIsDark] = useState(
    () => typeof document !== "undefined" && document.documentElement.dataset.theme === DARK_VALUE,
  );

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
