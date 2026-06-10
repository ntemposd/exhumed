export const THEME_STORAGE_KEY = "exhumed-theme";
export const THEME_DARK = "dark";
export const THEME_LIGHT = "light";

/** True when no explicit user choice is stored and OS prefers dark. */
export function shouldUseDarkTheme(stored: string | null, prefersDark: boolean): boolean {
  if (stored === THEME_DARK) {
    return true;
  }

  if (stored === THEME_LIGHT) {
    return false;
  }

  return prefersDark;
}

export function applyThemeToDocument(isDark: boolean): void {
  if (isDark) {
    document.documentElement.dataset.theme = THEME_DARK;
    return;
  }

  delete document.documentElement.dataset.theme;
}

// Runs before first paint — explicit choice wins, otherwise follows OS scheme.
export const THEME_INIT_SCRIPT = `try{var s=localStorage.getItem('${THEME_STORAGE_KEY}');var d=s==='${THEME_DARK}'||(s!=='${THEME_LIGHT}'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.dataset.theme='${THEME_DARK}';}catch(e){}`;
