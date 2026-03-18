"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { adminApi } from "@/lib/api-client";
import type { PipelineJob, PipelineJobSummary, PipelineStep, PipelineStepLog } from "@/lib/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function totalDuration(job: PipelineJob | PipelineJobSummary): string {
  if (!job.started_at || !job.finished_at) return "";
  const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime();
  return fmtDuration(ms);
}

// ── Status icons and colours ──────────────────────────────────────────────────

const STEP_ICON: Record<string, string> = {
  pending:   "○",
  running:   "⟳",
  completed: "✓",
  failed:    "✗",
  skipped:   "→",
};
const STEP_COLOR: Record<string, string> = {
  pending:   "text-gray-400",
  running:   "text-blue-500 animate-spin-slow",
  completed: "text-emerald-500",
  failed:    "text-red-500",
  skipped:   "text-gray-400",
};
const LOG_COLOR: Record<string, string> = {
  info:    "text-gray-600",
  warning: "text-amber-600",
  error:   "text-red-600",
};
const JOB_BADGE: Record<string, string> = {
  queued:    "bg-gray-100 text-gray-600",
  running:   "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed:    "bg-red-100 text-red-700",
};

// ── Step progress row ─────────────────────────────────────────────────────────

function StepRow({ step }: { step: PipelineStep }) {
  const [open, setOpen] = useState(false);
  const hasLogs = step.logs.length > 0;
  const counts = Object.entries(step.counts);

  return (
    <div className="border border-gray-100 rounded-lg overflow-hidden">
      <button
        onClick={() => hasLogs && setOpen(!open)}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
          hasLogs ? "hover:bg-gray-50 cursor-pointer" : "cursor-default"
        } ${step.status === "running" ? "bg-blue-50" : "bg-white"}`}
      >
        {/* Status icon */}
        <span className={`text-lg font-bold w-5 text-center shrink-0 ${STEP_COLOR[step.status]}`}>
          {STEP_ICON[step.status]}
        </span>

        {/* Name */}
        <span className={`flex-1 text-sm font-medium ${
          step.status === "pending" ? "text-gray-400" : "text-gray-800"
        }`}>
          {step.display_name}
        </span>

        {/* Counts (inline badges) */}
        {counts.length > 0 && (
          <div className="flex items-center gap-2 shrink-0">
            {counts.slice(0, 3).map(([k, v]) => (
              <span key={k} className="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">
                {String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",")} {k.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {/* Duration */}
        {step.duration_ms !== null && (
          <span className="text-xs text-gray-400 shrink-0 w-14 text-right">
            {fmtDuration(step.duration_ms)}
          </span>
        )}

        {/* Log toggle */}
        {hasLogs && (
          <span className="text-xs text-gray-400 shrink-0">
            {open ? "▲" : "▼"} {step.logs.length}
          </span>
        )}
      </button>

      {/* Log entries (expandable) */}
      {open && hasLogs && (
        <div className="bg-gray-950 px-4 py-3 space-y-1 max-h-64 overflow-y-auto">
          {step.logs.map((log: PipelineStepLog, i: number) => (
            <div key={i} className="flex gap-3 text-xs font-mono">
              <span className="text-gray-500 shrink-0">{fmtTime(log.timestamp)}</span>
              <span className={`shrink-0 uppercase font-bold w-8 ${LOG_COLOR[log.level] ?? "text-gray-400"}`}>
                {log.level.slice(0, 4)}
              </span>
              <span className="text-gray-200 break-all">{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Active job monitor ────────────────────────────────────────────────────────

function JobMonitor({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<PipelineJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const j = await adminApi.getJob(jobId);
      setJob(j);
      return j.status === "completed" || j.status === "failed";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Poll failed");
      return true; // stop polling
    }
  }, [jobId]);

  useEffect(() => {
    let stopped = false;
    const loop = async () => {
      while (!stopped) {
        const done = await poll();
        if (done) break;
        await new Promise((r) => setTimeout(r, 1000));
      }
    };
    loop();
    return () => { stopped = true; };
  }, [poll]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (!job) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-sm">
        Loading job status…
      </div>
    );
  }

  const completedSteps = job.steps.filter(
    (s) => s.status === "completed" || s.status === "skipped"
  ).length;
  const totalSteps = job.steps.length;
  const pct = Math.round((completedSteps / totalSteps) * 100);

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <span className="text-sm font-semibold text-gray-800">
            Job #{job.job_id.slice(0, 8)}
          </span>
          <span className="ml-2 text-xs text-gray-400">
            {job.files.join(", ")}
          </span>
        </div>
        <span className={`text-xs font-semibold px-2 py-1 rounded-full ${JOB_BADGE[job.status]}`}>
          {job.status.toUpperCase()}
        </span>
      </div>

      {/* Progress bar */}
      {(job.status === "running" || job.status === "queued") && (
        <div className="px-5 py-3 border-b border-gray-100">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{completedSteps} of {totalSteps} steps</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Steps */}
      <div className="p-4 space-y-2">
        {job.steps.map((step) => (
          <StepRow key={step.name} step={step} />
        ))}
      </div>

      {/* Totals (on completion) */}
      {job.status === "completed" && Object.keys(job.totals).length > 0 && (
        <div className="px-5 py-4 border-t border-gray-100 bg-emerald-50">
          <p className="text-xs font-semibold text-emerald-700 mb-2">Pipeline Complete</p>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(job.totals)
              .filter(([, v]) => typeof v === "number" && v > 0)
              .map(([k, v]) => (
                <div key={k} className="bg-white rounded-lg p-2 border border-emerald-100 text-center">
                  <p className="text-xs text-gray-500">{k.replace(/_/g, " ")}</p>
                  <p className="text-lg font-bold text-gray-900">
                    {String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
                  </p>
                </div>
              ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Started {fmtTime(job.started_at)} · Finished {fmtTime(job.finished_at)} · {totalDuration(job)}
          </p>
        </div>
      )}

      {/* Error */}
      {job.status === "failed" && job.error && (
        <div className="px-5 py-4 border-t border-gray-100 bg-red-50">
          <p className="text-xs font-semibold text-red-700 mb-1">Pipeline Failed</p>
          <p className="text-xs text-red-600 font-mono">{job.error}</p>
        </div>
      )}
    </div>
  );
}

// ── Job history row ───────────────────────────────────────────────────────────

function HistoryRow({
  job,
  onSelect,
}: {
  job: PipelineJobSummary;
  onSelect: (id: string) => void;
}) {
  const failed = job.steps.find((s) => s.status === "failed");
  return (
    <button
      onClick={() => onSelect(job.job_id)}
      className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
    >
      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${JOB_BADGE[job.status]}`}>
        {job.status}
      </span>
      <span className="flex-1 text-sm text-gray-700 truncate">
        {job.files.join(", ") || "—"}
      </span>
      {job.totals.entities_written !== undefined && (
        <span className="text-xs text-gray-500 shrink-0">
          {job.totals.entities_written} entities
        </span>
      )}
      {failed && (
        <span className="text-xs text-red-500 shrink-0">✗ {failed.display_name}</span>
      )}
      <span className="text-xs text-gray-400 shrink-0">{totalDuration(job) || fmtTime(job.created_at)}</span>
      <span className="text-xs text-blue-500 shrink-0">View →</span>
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function IngestPage() {
  const fileRef = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<PipelineJobSummary[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Load job history on mount
  useEffect(() => {
    adminApi.listJobs(10).then((r) => setRecentJobs(r.jobs)).catch(() => {});
  }, []);

  // Refresh history when active job finishes
  const refreshHistory = useCallback(() => {
    adminApi.listJobs(10).then((r) => setRecentJobs(r.jobs)).catch(() => {});
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
      setUploadError(null);
    }
  }

  async function handleUpload() {
    if (files.length === 0) return;
    setUploading(true);
    setUploadError(null);
    try {
      const res = await adminApi.startIngestion(files);
      setActiveJobId(res.job_id);
      setFiles([]);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  // Poll active job; when done refresh history
  const [prevJobStatus, setPrevJobStatus] = useState<string | null>(null);
  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    const poll = async () => {
      while (!stopped) {
        try {
          const j = await adminApi.getJob(activeJobId);
          if (j.status !== prevJobStatus) {
            setPrevJobStatus(j.status);
          }
          if (j.status === "completed" || j.status === "failed") {
            refreshHistory();
            break;
          }
        } catch { break; }
        await new Promise((r) => setTimeout(r, 1500));
      }
    };
    poll();
    return () => { stopped = true; };
  }, [activeJobId, prevJobStatus, refreshHistory]);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Document Ingestion</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload medical documents to build the Graph RAG knowledge base.
          Each step is tracked in real time below.
        </p>
      </div>

      {/* Upload area */}
      {!activeJobId && (
        <div className="bg-white rounded-xl border-2 border-dashed border-gray-300 p-8 text-center">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md"
            onChange={handleFileChange}
            className="hidden"
            id="file-upload"
          />
          <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center text-blue-500 text-2xl">
              ↑
            </div>
            <div>
              <p className="text-sm font-medium text-gray-700">Click to select files</p>
              <p className="text-xs text-gray-400 mt-1">PDF, DOCX, TXT, MD — multiple files supported</p>
            </div>
          </label>
        </div>
      )}

      {/* File list + start button */}
      {files.length > 0 && !activeJobId && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
          <p className="text-sm font-medium text-gray-700">
            {files.length} file{files.length !== 1 ? "s" : ""} selected:
          </p>
          {files.map((f) => (
            <div key={f.name} className="flex items-center justify-between text-sm text-gray-600">
              <span className="truncate">{f.name}</span>
              <span className="text-gray-400 ml-2">{(f.size / 1024).toFixed(1)} KB</span>
            </div>
          ))}
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="mt-3 w-full py-2.5 text-sm font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Start Ingestion Pipeline"}
          </button>
        </div>
      )}

      {uploadError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          {uploadError}
        </div>
      )}

      {/* Active job monitor */}
      {activeJobId && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">Live Pipeline Monitor</h2>
            <button
              onClick={() => { setActiveJobId(null); refreshHistory(); }}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              ✕ Dismiss
            </button>
          </div>
          <JobMonitor jobId={activeJobId} />
        </div>
      )}

      {/* Recent jobs */}
      {recentJobs.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Recent Ingestion Jobs</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {recentJobs.map((j) => (
              <HistoryRow key={j.job_id} job={j} onSelect={setActiveJobId} />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {recentJobs.length === 0 && !activeJobId && files.length === 0 && (
        <div className="text-center py-12 text-gray-400 text-sm">
          No ingestion jobs yet. Upload documents above to build the knowledge graph.
        </div>
      )}
    </div>
  );
}
