import styles from "./app-navbar.module.css";

import { useTheme } from "../hooks";
import { logoUrl } from "../utils";

export function AppNavbar() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className={styles.navbar}>
      <div className={styles.brandMark}>
        <img className={styles.logo} src={logoUrl()} alt="Exhumed logo" />
        <div className={styles.brandCopy}>
          <span className={styles.brandTitle}>EXHUMED</span>
          <span className={styles.brandSubtitle}>Historical Convo Engine</span>
        </div>
      </div>
      <div className={styles.navbarActions}>
        <span className={styles.betaBadge}>v0</span>
        <button
          type="button"
          className={styles.themeToggle}
          onClick={toggleTheme}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {isDark ? "☀" : "🌙"}
        </button>
      </div>
    </header>
  );
}