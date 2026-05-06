// Normalize the backend origin once so fetch callers can append routes without
// worrying about trailing slash mismatches across environments.
const rawBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export const backendUrl = rawBackendUrl.replace(/\/+$/, "");