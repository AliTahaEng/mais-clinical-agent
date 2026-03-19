// TypeScript interfaces mirroring all Pydantic schemas

export type QueryStatus =
  | "complete"
  | "awaiting_approval"
  | "escalated"
  | "error";

export type StreamEventType =
  | "step"
  | "token"
  | "interrupt"
  | "done"
  | "error";

export type StreamStatus = "idle" | "streaming" | "interrupted" | "complete" | "error";

// ── Query ──────────────────────────────────────────────────────────────────────

export interface QueryRequest {
  query: string;
  patient_id?: string;
  session_id?: string;
}

export interface QueryResponse {
  session_id: string;
  answer: string;
  confidence_score: number;
  fact_check_passed: boolean;
  retrieval_quality: number;
  chunks_used: number;
  actions_proposed: number;
  actions_executed: number;
  requires_human_approval: boolean;
  status: QueryStatus;
}

// ── SSE Events ────────────────────────────────────────────────────────────────

export interface StepEvent {
  node: string;
  label: string;
  status: "running" | "done";
}

export interface TokenEvent {
  token: string;
}

export interface InterruptEvent {
  session_id: string;
  message: string;
  proposed_actions: ProposedAction[];
}

export interface SourceItem {
  index: number;
  source_type: "vector" | "bm25" | "graph_local" | "graph_global" | "web" | "unknown";
  score: number;
  text_preview: string;
  url?: string | null;
  filename?: string | null;
}

export interface DoneEvent {
  session_id: string;
  answer: string;
  confidence_score: number;
  fact_check_passed: boolean;
  retrieval_quality: number;
  chunks_used: number;
  actions_proposed: number;
  actions_executed: number;
  requires_human_approval: boolean;
  escalated: boolean;
  sources: SourceItem[];
  web_search_used: boolean;
}

export interface ErrorEvent {
  message: string;
}

// ── Actions ───────────────────────────────────────────────────────────────────

export interface ProposedAction {
  tool_name: string;
  tier: number;
  rationale: string;
  parameters: Record<string, unknown>;
}

// ── Approvals ─────────────────────────────────────────────────────────────────

export interface ApprovalDetail {
  session_id: string;
  message: string;
  proposed_actions: ProposedAction[];
  status: "pending" | "decided";
  approved_indices: number[];
  feedback: string;
}

export interface ApprovalListResponse {
  items: ApprovalDetail[];
  total: number;
}

export interface ApprovalDecisionRequest {
  approved_indices: number[];
  feedback: string;
}

export interface ApprovalDecisionResponse {
  session_id: string;
  approved_count: number;
  executed_count: number;
  status: string;
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  timestamp: string;
  services: Record<string, boolean>;
}

export interface AuditRecord {
  session_id: string;
  event_type: string;
  timestamp: string;
  [key: string]: unknown;
}

export interface StatsResponse {
  total_queries: number;
  total_actions_executed: number;
  event_breakdown: Record<string, number>;
  pending_approvals: number;
}

export interface FeatureFlags {
  llm_provider: string;
  embedding_provider: string;
  ehr_provider: string;
  enable_action_execution: boolean;
  force_human_approval: boolean;
  enable_web_search: boolean;
  enable_tracing: boolean;
  confidence_threshold: number;
  max_iterations: number;
}

export interface GraphNode {
  label?: string;
  count?: number;
  name?: string;
  type?: string;
  description?: string;
}

// ── Pipeline Job Monitoring ───────────────────────────────────────────────────

export type PipelineStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export type PipelineJobStatus = "queued" | "running" | "completed" | "failed";

export interface PipelineStepLog {
  timestamp: string;
  level: "info" | "warning" | "error";
  message: string;
  data: Record<string, unknown>;
}

export interface PipelineStep {
  name: string;
  display_name: string;
  status: PipelineStepStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  counts: Record<string, number>;
  logs: PipelineStepLog[];
}

export interface PipelineJob {
  job_id: string;
  files: string[];
  status: PipelineJobStatus;
  steps: PipelineStep[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  totals: Record<string, number>;
}

export interface PipelineJobSummary extends Omit<PipelineJob, "steps"> {
  steps: Omit<PipelineStep, "logs">[];
}
