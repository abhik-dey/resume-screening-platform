// Fetch wrapper handling auth, error normalization, and the backend's
// two distinct failure modes.
//
// The backend returns HTTP errors for routing/permission problems, but
// returns 200 with {success: false, reasoning: "..."} for *handled*
// failures — a resume that couldn't be parsed, an LLM that returned
// unusable output. A client that only inspects catch blocks would
// display a failed parse as a success, so both are surfaced here.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// sessionStorage rather than localStorage: it clears when the tab closes,
// which narrows the window an XSS payload has to exfiltrate the token.
// It does NOT solve XSS — any script running on the page can still read it.
// httpOnly cookies would be materially better and would require changing
// the backend from bearer tokens to cookie auth. Documented as a known
// limitation rather than presented as secure.
const TOKEN_KEY = "rsp_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, signal } = options;
  const headers: Record<string, string> = {};

  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload: BodyInit | undefined;
  if (formData) {
    payload = formData; // browser sets the multipart boundary itself
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: payload, signal });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new ApiError(
      "Can't reach the server. Check that the backend is running on " + API_BASE_URL,
      0,
    );
  }

  if (response.status === 429) {
    const retryAfter = Number(response.headers.get("Retry-After") ?? 60);
    throw new ApiError(
      `Too many requests. Try again in ${retryAfter} seconds.`,
      429,
      retryAfter,
    );
  }

  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) throw new ApiError(await response.text(), response.status);
    return (await response.blob()) as T;
  }

  const data = await response.json();

  if (!response.ok) {
    throw new ApiError(extractDetail(data, response.status), response.status);
  }
  return data as T;
}

/** FastAPI returns `detail` as a string OR as a validation-error array. */
function extractDetail(data: unknown, status: number): string {
  if (typeof data === "object" && data !== null && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          const field = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : "";
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join("; ");
    }
  }
  return `Request failed with status ${status}`;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  postForm: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", formData }),
  blob: (path: string) => request<Blob>(path),
};

export { API_BASE_URL };
