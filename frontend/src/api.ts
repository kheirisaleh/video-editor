export type WorkflowStatus = "draft" | "queued" | "running" | "done" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped";

export interface Probe {
  duration: number;
  width: number;
  height: number;
  fps: number;
  orientation: "vertical" | "horizontal" | "square";
  has_audio: boolean;
}

export interface Clip {
  id: string;
  position: number;
  original_name: string;
  size_bytes: number;
  probe: Probe | null;
  thumbnail_url: string | null;
  proxy_url: string | null;
  original_url: string;
}

export interface Step {
  name: string;
  status: StepStatus;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface WorkflowSummary {
  id: string;
  title: string;
  status: WorkflowStatus;
  current_step: string | null;
  progress: number;
  error: string | null;
  clip_count: number;
  thumbnail_url: string | null;
  queue_position: number | null;
  cover_url: string | null;
  output_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Output {
  index: number;
  label: string;
  duration: number;
  video_url: string;
  silent_url: string | null;
  cover_url: string;
  caption: string;
  music: string | null;
  size_bytes: number;
}

export interface RenderOptions {
  variants: number;
  min_duration: number;
  max_duration: number;
  music: boolean;
  music_track: string | null;
  beat_sync: boolean;
  texts: boolean;
  emoji: boolean;
  call_to_action: boolean;
  text_style: "auto" | "sans" | "serif";
  silent_copy: boolean;
  quality: "standard" | "high";
  hashtags: string[];
  disclosure: string;
}

export interface AppSettings {
  defaults: RenderOptions;
  emoji: string;
  fonts: Record<string, string>;
  storage: { uploads: number; work: number; exports: number; music: number; free: number; total: number };
}

export type AiProvider = "none" | "anthropic" | "openai";

export interface AiSettings {
  provider: AiProvider;
  base_url: string;
  api_key_set: boolean;
  text_model: string;
  vision_model: string;
  effort: "low" | "medium" | "high" | "xhigh";
  shots_per_request: number;
  timeout: number;
  required: boolean;
  monthly_budget_usd: number;
  workflow_budget_usd: number;
}

export interface AiUsage {
  month_spent: number;
  month_budget: number;
  month_calls: number;
  workflow_budget: number;
}

export interface AiSettingsInput extends Omit<AiSettings, "api_key_set"> {
  api_key?: string | null;
}

export interface AiTestResult {
  ok: boolean;
  provider: string;
  text_ok: boolean;
  vision_ok: boolean;
  seconds: number;
  detail: string;
}

export interface Track {
  name: string;
  title: string;
  duration: number;
  size_bytes: number;
  tempo: number | null;
  url: string;
}

export interface Workflow extends WorkflowSummary {
  product_text: string;
  product_url: string;
  prompt: string;
  clips: Clip[];
  steps: Step[];
  outputs: Output[];
  options: RenderOptions;
  ai_cost: number;
}

export interface WorkflowInput {
  title?: string;
  product_text?: string;
  product_url?: string | null;
  prompt?: string;
  options?: Partial<RenderOptions>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    // body was not JSON
  }
  return `${res.status} ${res.statusText}`;
}

export const api = {
  list: () => request<WorkflowSummary[]>("GET", "/api/workflows"),
  get: (id: string) => request<Workflow>("GET", `/api/workflows/${id}`),
  create: (input: WorkflowInput) => request<Workflow>("POST", "/api/workflows", input),
  update: (id: string, input: WorkflowInput) =>
    request<Workflow>("PATCH", `/api/workflows/${id}`, input),
  remove: (id: string) => request<void>("DELETE", `/api/workflows/${id}`),
  submit: (id: string) => request<Workflow>("POST", `/api/workflows/${id}/submit`),
  cancel: (id: string) => request<Workflow>("POST", `/api/workflows/${id}/cancel`),
  retry: (id: string) => request<Workflow>("POST", `/api/workflows/${id}/retry`),
  removeClip: (id: string, clipId: string) =>
    request<void>("DELETE", `/api/workflows/${id}/clips/${clipId}`),
  settings: () => request<AppSettings>("GET", "/api/settings"),
  saveDefaults: (options: RenderOptions) =>
    request<RenderOptions>("PUT", "/api/settings/defaults", options),
  music: () => request<Track[]>("GET", "/api/music"),
  ai: () => request<AiSettings>("GET", "/api/settings/ai"),
  saveAi: (input: AiSettingsInput) => request<AiSettings>("PUT", "/api/settings/ai", input),
  aiUsage: () => request<AiUsage>("GET", "/api/settings/ai/usage"),
  testAi: () => request<AiTestResult>("POST", "/api/settings/ai/test"),
  rerun: (id: string, from: string) =>
    request<Workflow>("POST", `/api/workflows/${id}/rerun?from=${encodeURIComponent(from)}`),
  removeMusic: (name: string) => request<void>("DELETE", `/api/music/${encodeURIComponent(name)}`),
};

export function uploadClip(
  workflowId: string,
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<Clip> {
  const url = `/api/workflows/${workflowId}/clips?filename=${encodeURIComponent(file.name)}`;
  return uploadFile<Clip>(url, file, onProgress, signal);
}

export function uploadMusic(file: File, onProgress: (fraction: number) => void): Promise<Track> {
  return uploadFile<Track>(`/api/music?filename=${encodeURIComponent(file.name)}`, file, onProgress);
}

/** Upload with XHR because fetch cannot report upload progress. */
function uploadFile<T>(
  url: string,
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as T);
      } else {
        let detail = `${xhr.status}`;
        try {
          detail = JSON.parse(xhr.responseText).detail ?? detail;
        } catch {
          // keep status code
        }
        reject(new ApiError(xhr.status, detail));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network"));
    xhr.onabort = () => reject(new ApiError(0, "aborted"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}
