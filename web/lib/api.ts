export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type DocumentSummary = {
  id: string;
  filename: string;
  status: string;
  created_at?: string | null;
  uploaded_at?: string | null;
  completed_at?: string | null;
  page_count?: number | null;
  confidence?: number | null;
  decision?: string | null;
  run_id?: string | null;
  error?: string | null;
  source?: string;
  has_pdf?: boolean;
  review_payload?: ReviewPayload | null;
};

export type JobEvent = {
  type: "status" | "node";
  status?: string;
  node?: string;
  ts: string;
  payload?: ReviewPayload;
  confidence?: number;
  decision?: string;
  reasons?: string[];
  error?: string;
  note?: string;
};

export type ReviewPayload = {
  document_id: string;
  decision: string;
  confidence_score: number;
  flagged_fields: { agent: string; field_path: string; status: string; reason: string | null }[];
  result_preview: Record<string, unknown>;
};

export type SourceRef = {
  page: number;
  quote: string;
  chunk_id?: string | null;
  section_path?: string | null;
};

export type Sourced<T = unknown> = {
  value: T | null;
  sources: SourceRef[];
};

export type SourcedItem<T = unknown> = {
  value: T;
  sources: SourceRef[];
};

export type KbStats = {
  acts: { act_version: string; sections: number }[];
  total_sections: number;
  crosswalk_mappings: number;
  total_runs: number;
};

export type KbSection = {
  act_version: string;
  section_number: string;
  section_title: string | null;
  chapter_path: string | null;
  snippet: string;
  status: string;
  effective_from: string | null;
  effective_to: string | null;
  exact: boolean;
};

export type SettingsView = {
  llm_model: string;
  validator_llm_model: string;
  llm_base_url: string;
  is_openrouter: boolean;
  has_api_key: boolean;
  api_key_hint: string | null;
  pipeline_max_concurrency: number;
  llm_max_retries: number;
  confidence_autosave_threshold: number;
  confidence_review_threshold: number;
  max_retries: number;
};

export type ModelInfo = {
  id: string;
  name: string;
  tools: boolean | null;
  free: boolean;
  context_length: number | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDocuments: () => request<DocumentSummary[]>("/api/documents"),
  getDocument: (id: string) => request<DocumentSummary>(`/api/documents/${id}`),
  getResult: (id: string) => request<Record<string, any>>(`/api/documents/${id}/result`),
  getValidation: (id: string) =>
    request<{ agent: string; attempt: number; field_path: string; status: string; reason: string | null }[]>(
      `/api/documents/${id}/validation`,
    ),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentSummary>("/api/documents", { method: "POST", body: form });
  },
  review: (id: string, action: "approve" | "reject" | "edit", patches?: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/documents/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, patches }),
    }),
  kbStats: () => request<KbStats>("/api/kb/stats"),
  kbSearch: (q: string, act?: string) =>
    request<KbSection[]>(`/api/kb/search?q=${encodeURIComponent(q)}${act ? `&act=${encodeURIComponent(act)}` : ""}`),
  getSettings: () => request<SettingsView>("/api/settings"),
  updateSettings: (patch: Record<string, unknown>) =>
    request<SettingsView>("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  testConnection: () =>
    request<{ ok: boolean; detail: string; model_found?: boolean | null }>("/api/settings/test", {
      method: "POST",
    }),
  listModels: () => request<ModelInfo[]>("/api/models"),
  pdfUrl: (id: string) => `${API_URL}/api/documents/${id}/pdf`,
  eventsUrl: (id: string) => `${API_URL}/api/documents/${id}/events`,
};
