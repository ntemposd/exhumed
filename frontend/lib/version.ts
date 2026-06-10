/** Application release version — keep in sync with backend/version.py */
export const APP_VERSION = "1.0.0";

/** Navbar display label derived from semver (1.0.0 → v1.0). */
export function appVersionLabel(version: string = APP_VERSION): string {
  const [major, minor] = version.split(".");
  return `v${major}.${minor ?? "0"}`;
}
