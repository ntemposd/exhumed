import styles from "./app-navbar.module.css";

import { logoUrl } from "../utils";

export function AppNavbar() {
  return (
    <header className={styles.navbar}>
      <div className={styles.brandMark}>
        <img className={styles.logo} src={logoUrl()} alt="Exhumed logo" />
        <div className={styles.brandCopy}>
          <span className={styles.brandTitle}>EXHUMED</span>
          <span className={styles.brandSubtitle}>Historical Logic Engine</span>
        </div>
      </div>
    </header>
  );
}