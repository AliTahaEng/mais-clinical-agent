/**
 * Typed API client for the MAIS backend.
 * All fetch calls go through the Next.js proxy at /api/v1.
 */
import { createParser } from "eventsource-parser";
import type {
  ApprovalDecisionRequest,
  ApprovalDecisionResponse,
  ApprovalDetail,
  ApprovalListResponse,
  AuditRecord,
  DoneEvent,
  ErrorEvent,
  FeatureFlags,
  GraphNode,
  HealthResponse,
  InterruptEvent,
  PipelineJob,
  PipelineJobSummary,
  StatsResponse,
  StepEvent,
  StreamEventType,
  TokenEvent,
} from "./types";

const BASE = "/api/v1";

// ── Auth token helpers (avoid circular import with auth-api.ts) ───────────────
// We read the token from the Zustand store at call time.
function getAccessToken(): string | null {
  // Dynamic import to avoid SSR issues
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useAuthStore } = require("@/lib/stores/auth-store");
    return useAuthStore.getState().accessToken;
  } catch {
    return null;
  }
}

async function refreshAndRetry(): Promise<string | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { authApi } = require("@/lib/auth-api");
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useAuthStore } = require("@/lib/stores/auth-store");
    const data = await authApi.refresh();
    useAuthStore.getState().setAuth(data.user, data.access_token);
    return data.access_token;
  } catch {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { useAuthStore } = require("@/lib/stores/auth-store");
    useAuthStore.getState().clearAuth();
    if (typeof window !== "undefined") window.location.href = "/login";
    return null;
  }
}

// ── Generic helpers ────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = getAccessToken();
  const authHeader: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};

  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeader },
    ...options,
  });

  // On 401: try silent refresh once, then retry
  if (res.status === 401) {
    const newToken = await refreshAndRetry();
    if (newToken) {
      const retryRes = await fetch(`${BASE}${path}`, {
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${newToken}` },
        ...options,
      });
      if (!retryRes.ok) {
        const text = await retryRes.text();
        throw new Error(`API ${retryRes.status}: ${text}`);
      }
      return retryRes.json() as Promise<T>;
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── SSE streaming ─────────────────────────────────────────────────────────────

export interface SSEHandlers {
  onStep?: (event: StepEvent) => void;
  onToken?: (event: TokenEvent) => void;
  onInterrupt?: (event: InterruptEvent) => void;
  onDone?: (event: DoneEvent) => void;
  onError?: (event: ErrorEvent) => void;
}

export async function querySSE(
  query: string,
  patientId: string | undefined,
  sessionId: string | undefined,
  handlers: SSEHandlers,
  signal?: AbortSignal
): Promise<void> {
  const params = new URLSearchParams({ q: query });
  if (patientId) params.set("patient_id", patientId);
  if (sessionId) params.set("session_id", sessionId);

  const token = getAccessToken();
  const authHeader: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {};

  const res = await fetch(`${BASE}/query/stream?${params}`, {
    headers: { Accept: "text/event-stream", ...authHeader },
    signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError?.({ message: `Stream failed: ${res.status}` });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  const parser = createParser((event) => {
    if (event.type !== "event") return;
    const eventType = event.event as StreamEventType;
    try {
      const data = JSON.parse(event.data);
      switch (eventType) {
        case "step":
          handlers.onStep?.(data as StepEvent);
          break;
        case "token":
          handlers.onToken?.(data as TokenEvent);
          break;
        case "interrupt":
          handlers.onInterrupt?.(data as InterruptEvent);
          break;
        case "done":
          handlers.onDone?.(data as DoneEvent);
          break;
        case "error":
          handlers.onError?.(data as ErrorEvent);
          break;
      }
    } catch {
      // ignore parse errors
    }
  });

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.feed(decoder.decode(value, { stream: true }));
  }
}

// ── Approval API ──────────────────────────────────────────────────────────────

export const approvalApi = {
  list(): Promise<ApprovalListResponse> {
    return apiFetch("/approvals");
  },
  get(sessionId: string): Promise<ApprovalDetail> {
    return apiFetch(`/approvals/${sessionId}`);
  },
  decide(
    sessionId: string,
    body: ApprovalDecisionRequest
  ): Promise<ApprovalDecisionResponse> {
    return apiFetch(`/approvals/${sessionId}/decide`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};

// ── Admin API ─────────────────────────────────────────────────────────────────
// Token is now read from auth store automatically by apiFetch — no need to pass it manually.

export const adminApi = {
  health(): Promise<HealthResponse> {
    return apiFetch("/admin/health");
  },
  stats(): Promise<StatsResponse> {
    return apiFetch("/admin/stats");
  },
  audit(limit = 50): Promise<{ records: AuditRecord[]; total: number }> {
    return apiFetch(`/admin/audit?limit=${limit}`);
  },
  sessions(): Promise<{ sessions: ApprovalDetail[]; total: number }> {
    return apiFetch("/admin/sessions");
  },
  sessionState(
    sessionId: string
  ): Promise<{ session_id: string; state: Record<string, unknown> }> {
    return apiFetch(`/admin/sessions/${sessionId}`);
  },
  graphNodes(label?: string): Promise<{ nodes: GraphNode[] }> {
    const q = label ? `?label=${label}` : "";
    return apiFetch(`/admin/graph/nodes${q}`);
  },
  getSettings(): Promise<FeatureFlags> {
    return apiFetch("/admin/settings");
  },
  updateSettings(
    flags: Partial<FeatureFlags>
  ): Promise<{ updated: Partial<FeatureFlags> }> {
    return apiFetch("/admin/settings", {
      method: "PATCH",
      body: JSON.stringify(flags),
    });
  },
  /** Start an async ingestion job. Returns immediately with job_id. */
  startIngestion(
    files: File[]
  ): Promise<{ job_id: string; files: string[]; status: string }> {
    const token = getAccessToken();
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    // multipart/form-data — don't set Content-Type (browser sets boundary automatically)
    return apiFetch("/admin/ingest/upload", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
  },
  /** Poll a single job for full details including per-step logs. */
  getJob(jobId: string): Promise<PipelineJob> {
    return apiFetch(`/admin/ingest/jobs/${jobId}`);
  },
  /** List recent pipeline jobs (summaries, no per-step logs). */
  listJobs(limit = 20): Promise<{ jobs: PipelineJobSummary[]; total: number }> {
    return apiFetch(`/admin/ingest/jobs?limit=${limit}`);
  },
};
