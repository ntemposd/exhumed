import Image from "next/image";

import styles from "./app-navbar.module.css";

import { useTheme } from "../hooks";

function SunIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <line x1="12" y1="2" x2="12" y2="4" />
      <line x1="12" y1="20" x2="12" y2="22" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="2" y1="12" x2="4" y2="12" />
      <line x1="20" y1="12" x2="22" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export function AppNavbar() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className={styles.navbar}>
      <div className={styles.brandMark}>
        <Image className={styles.logo} src="/logo.png" alt="Exhumed logo" width={48} height={48} priority />
        <div className={styles.brandCopy}>
          <div className={styles.brandTitleRow}>
            <span className={styles.brandTitle}>EXHUMED</span>
            <span className={styles.betaBadge}>v1.0.0-beta.1</span>
          </div>
          <span className={styles.brandSubtitle}>Historical Convo Engine</span>
        </div>
      </div>
      <button
        type="button"
        className={styles.themeToggle}
        onClick={toggleTheme}
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      >
        {isDark ? <SunIcon /> : <MoonIcon />}
      </button>
    </header>
  );
}