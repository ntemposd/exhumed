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
          <span className={styles.brandSubtitle}>Historical Logic Engine</span>
        </div>
      </div>
      <div className={styles.navbarActions}>
        <span className={styles.betaBadge}>Beta</span>
        <button
          type="button"
          className="button"
          onClick={toggleTheme}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          style={{ minHeight: "32px", padding: "0 12px", fontSize: "0.72rem", letterSpacing: "0.08em" }}
        >
          {isDark ? "◑ LIGHT" : "◐ DARK"}
        </button>
      </div>
    </header>
  );
}