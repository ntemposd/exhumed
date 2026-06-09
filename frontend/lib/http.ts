// Thin alias kept so call-sites don't need updating.
// Auth is handled server-side by the /api/backend proxy route.
export function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    credentials: "same-origin",
    ...init,
  });
}

type ReadableErrorPayload = {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
  message?: string;
  error?: string;
};


export async function getResponseErrorMessage(response: Response, fallbackMessage: string) {
  try {
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as ReadableErrorPayload;
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        const detail = payload.detail.trim();
        if (response.status === 401 && detail.toLowerCase() === "unauthorized") {
          return "BACKEND_API_KEY on Vercel does not match BACKEND_API_KEY on Railway. Set the same value for Preview and Production, then redeploy.";
        }
        return detail;
      }

      if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        const firstError = payload.detail[0];
        const location = Array.isArray(firstError?.loc) ? firstError.loc.join(".") : "request";
        const message = typeof firstError?.msg === "string" ? firstError.msg : fallbackMessage;
        return `${location}: ${message}`;
      }

      if (typeof payload.message === "string" && payload.message.trim()) {
        return payload.message.trim();
      }

      if (typeof payload.error === "string" && payload.error.trim()) {
        return payload.error.trim();
      }
    }

    const text = (await response.text()).trim();
    if (response.status === 401 && (contentType.includes("text/html") || text.includes("Authentication Required"))) {
      return "Vercel deployment protection blocked the backend proxy. Open the deployment while signed into Vercel, or allow preview access in project settings.";
    }
    if (text.startsWith("<!") || text.startsWith("<html")) {
      return `${fallbackMessage} (${response.status})`;
    }
    if (text) {
      return text;
    }
  } catch {
    // Fall through to the generic message when the response body cannot be parsed.
  }

  return `${fallbackMessage} (${response.status})`;
}


export function getRequestFailureMessage(error: unknown, fallbackMessage: string) {
  if (error instanceof TypeError) {
    return "Could not reach the backend. Check BACKEND_URL, BACKEND_API_KEY, and that the backend is running.";
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
}