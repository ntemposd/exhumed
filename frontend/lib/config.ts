// All backend calls are proxied through the Next.js API route so that
// BACKEND_URL and BACKEND_API_KEY never reach the browser bundle.
// The proxy lives at /api/backend and forwards to the real Railway backend
// server-side, injecting the API key there.
export const backendUrl = "/api/backend";
