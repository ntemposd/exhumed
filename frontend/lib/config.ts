// Normalize the backend origin once so fetch callers can append routes without
// worrying about trailing slash mismatches across environments.
const rawBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim();

function resolveBackendUrl() {
	if (rawBackendUrl) {
		return rawBackendUrl.replace(/\/+$/, "");
	}

	if (process.env.NODE_ENV === "production") {
		throw new Error("NEXT_PUBLIC_BACKEND_URL must be set for production builds.");
	}

	return "http://localhost:8000";
}

export const backendUrl = resolveBackendUrl();