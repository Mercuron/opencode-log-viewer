const BASE = "/api/v1"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    throw new ApiError(res.status, body || res.statusText)
  }
  const contentType = res.headers.get("content-type") || ""
  if (contentType.includes("application/json")) return res.json() as Promise<T>
  return res.text() as unknown as Promise<T>
}

export interface Source {
  id: string
  name: string
  display_name: string | null
  hostname: string | null
  first_seen_at: string
  last_seen_at: string
  opencode_version: string | null
  plugin_version: string | null
  session_count: number
  last_session_at: string | null
  active_count: number
}

export interface Session {
  id: string
  source_id: string
  parent_id: string | null
  title: string | null
  project: string | null
  directory: string | null
  status: string | null
  created_at: string | null
  updated_at: string | null
  completed_at: string | null
  duration_ms: number | null
  model: string | null
  provider: string | null
  agent: string | null
  tokens_input: number
  tokens_output: number
  tokens_reasoning: number
  tokens_cache_read: number
  tokens_cache_write: number
  tool_calls: number
  tool_errors: number
  compactions: number
  error_count: number
  unaccounted_ms: number
  imported: number
  notes: string | null
}

export interface Message {
  id: string
  seq: number
  role: string | null
  started_at: string | null
  completed_at: string | null
  elapsed_ms: number | null
  tool_time_ms: number | null
  model_time_ms: number | null
  model: string | null
  tokens_input: number
  tokens_output: number
  tokens_reasoning: number
  tokens_cache_read: number
  finish_reason: string | null
  error: string | null
}

export interface Part {
  id: string
  message_id: string | null
  seq: number
  type: string
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  tool_name: string | null
  call_id: string | null
  status: string | null
  title: string | null
  error: string | null
  text: string | null
  input_json: string | null
  output_text: string | null
  output_bytes: number | null
  output_tokens_est: number | null
  metadata_json: string | null
  linked_session_id?: string
  linked_session_match?: string
}

export interface Detection {
  id: number
  kind: string
  level: "info" | "warn" | "bad"
  message: string
  evidence_json: string | null
}

export interface TodoSnapshot {
  id: number
  captured_at: string | null
  items_json: string
}

export interface SessionDetail {
  session: Session
  messages: Message[]
  parts: Part[]
  detections: Detection[]
  todo_snapshots: TodoSnapshot[]
  children: { id: string; title: string | null; status: string | null; agent: string | null; created_at: string | null }[]
  inference_spans: Record<string, unknown>[]
  tool_stats: Record<string, { calls: number; errors: number; total_ms: number; tokens_est: number }>
  context_attribution: { part_id: string; seq: number; tool_name: string | null; output_tokens_est: number }[]
  context_growth: { seq: number; tokens_input: number; message_id: string }[]
}

export const api = {
  login: (password: string) => request<{ status: string }>("/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  sources: () => request<Source[]>("/sources"),
  renameSource: (id: string, displayName: string | null) =>
    request<{ status: string }>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify({ display_name: displayName }) }),
  updateSessionNotes: (id: string, notes: string | null) =>
    request<{ status: string }>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify({ notes }) }),
  sessions: (params: Record<string, string | undefined> = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][])
    const suffix = qs.toString() ? `?${qs.toString()}` : ""
    return request<Session[]>(`/sessions${suffix}`)
  },
  session: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  exportUrl: (id: string, limit = 1500) => `${BASE}/sessions/${id}/export?format=md&limit=${limit}`,
  exportMarkdown: (id: string, limit = 1500) => request<string>(`/sessions/${id}/export?format=md&limit=${limit}`),
  streamUrl: (id: string) => `${BASE}/sessions/${id}/stream`,
  importStorage: (path: string, sourceName: string) =>
    request<{ accepted: number; duplicates: number; rejected: number; sessions_touched: number }>("/import/storage", {
      method: "POST",
      body: JSON.stringify({ path, source_name: sourceName }),
    }),
  importInference: (sourceName: string, log: string, sessionId?: string) =>
    request<{ parsed_spans: number; stored: number }>("/import/inference", {
      method: "POST",
      body: JSON.stringify({ source_name: sourceName, format: "llama-server", log, session_id: sessionId }),
    }),
  stats: () => request<{ sources: number; sessions: number; events: number; db_size_bytes: number }>("/stats"),
}
