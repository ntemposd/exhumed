// Thin alias kept so call-sites don't need updating.
// Auth is handled server-side by the /api/backend proxy route.
export function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, init);
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
        return payload.detail.trim();
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
    return "Could not reach the backend. Check NEXT_PUBLIC_BACKEND_URL, CORS, and backend availability.";
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallbackMessage;
}