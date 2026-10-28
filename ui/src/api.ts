import type {
  EvalReport,
  EvalReportSummary,
  Health,
  Job,
  ReviewAction,
  ReviewPayload,
  StructuredJudgment,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";
const KEY_STORAGE = "legal-ai.api-key";

export function getApiKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    if (key) localStorage.setItem(KEY_STORAGE, key);
    else localStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable (private window) — the key just won't persist */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const key = getApiKey();
  return { ...(key ? { "X-API-Key": key } : {}), ...extra };
}

function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? `${(d as { loc?: unknown[] }).loc?.join(".") ?? ""}: ${(d as { msg: string }).msg}` : String(d)))
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: headers(init.headers as Record<string, string> | undefined),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, detailOf(body, `${response.status} ${response.statusText}`));
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  listDocuments: () => request<Job[]>("/api/documents"),
  getDocument: (id: string) => request<Job>(`/api/documents/${id}`),
  getResult: (id: string) => request<StructuredJudgment>(`/api/documents/${id}/result`),
  getReview: (id: string) => request<ReviewPayload>(`/api/documents/${id}/review`),
  submitReview: (id: string, decision: ReviewAction) =>
    request<Job>(`/api/documents/${id}/review`, {
      method: "POST",
      body: JSON.stringify(decision),
      headers: { "Content-Type": "application/json" },
    }),
  listReports: () => request<EvalReportSummary[]>("/api/eval/reports"),
  getReport: (name: string) => request<EvalReport>(`/api/eval/reports/${encodeURIComponent(name)}`),

  /** Fetches the PDF with the auth header and returns an object URL for an <iframe>. */
  async pdfUrl(id: string): Promise<string> {
    const response = await fetch(`${BASE}/api/documents/${id}/pdf`, { headers: headers() });
    if (!response.ok) throw new ApiError(response.status, "Could not load the PDF.");
    return URL.createObjectURL(await response.blob());
  },

  /** Upload with progress events (fetch() can't report upload progress). */
  upload(file: File, onProgress: (fraction: number) => void): Promise<Job> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/api/documents`);
      Object.entries(headers()).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
      xhr.onload = () => {
        let body: unknown = null;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* non-JSON error page */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as Job);
        else reject(new ApiError(xhr.status, detailOf(body, `Upload failed (${xhr.status})`)));
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error — is the API running?"));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    });
  },
};
