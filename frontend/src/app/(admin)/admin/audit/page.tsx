"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";

// ── Types ──────────────────────────────────────────────────────────────────────

interface TraceStep {
  node: string;
  label: string;
  icon: string;
  status: "done" | "empty" | "passed" | "failed";
  detail: string;
  sub_queries?: string[];
  iterations?: number;
  chunks?: number;
  score?: number;
  web_triggered?: boolean;
  passed?: boolean;
  issues?: string[];
  total_chunks?: number;
  actions_proposed?: number;
  actions_executed?: number;
  escalated?: boolean;
  requires_approval?: boolean;
}

interface SourcePreview {
  index: number;
  source_type: string;
  score: number;
  text_preview: string;
  filename?: string;
  url?: string;
}

interface AuditPayload {
  query: string;
  patient_id?: string;
  user_id?: string;
  final_answer?: string;
  confidence_score?: number;
  current_plan?: string;
  sub_queries?: string[];
  iterations?: number;
  retrieval_quality?: number;
  chunks_retrieved?: number;
  retrieval_breakdown?: Record<string, number>;
  sources_preview?: SourcePreview[];
  graph_context_used?: boolean;
  community_context_used?: boolean;
  web_search_used?: boolean;
  fact_check_passed?: boolean;
  fact_check_issues?: string[];
  actions_proposed?: number;
  actions_executed?: number;
  escalated?: boolean;
  execution_trace?: TraceStep[];
}

interface AuditRecord {
  event_type: string;
  session_id: string;
  timestamp?: string;
  agent_id?: string;
  payload?: AuditPayload;
}

// ── Source type metadata ───────────────────────────────────────────────────────

const SOURCE_META: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  graph_local:  { label: "Knowledge Graph",      color: "text-purple-700", bg: "bg-purple-100", icon: "🧠" },
  graph_global: { label: "Knowledge Graph",      color: "text-purple-700", bg: "bg-purple-100", icon: "🕸️" },
  hybrid:       { label: "Document",             color: "text-blue-700",   bg: "bg-blue-100",   icon: "📄" },
  vector:       { label: "Document (semantic)",  color: "text-blue-700",   bg: "bg-blue-100",   icon: "📄" },
  bm25:         { label: "Document (keyword)",   color: "text-blue-700",   bg: "bg-blue-100",   icon: "📄" },
  web:          { label: "Web Search",           color: "text-emerald-700",bg: "bg-emerald-100",icon: "🌐" },
  unknown:      { label: "Retrieved",            color: "text-gray-600",   bg: "bg-gray-100",   icon: "📎" },
};

// ── Retrieval breakdown bar ────────────────────────────────────────────────────

function RetrievalBar({ breakdown, total }: { breakdown: Record<string, number>; total: number }) {
  if (!total) return <span className="text-xs text-gray-400">No chunks retrieved</span>;
  const colors: Record<string, string> = {
    graph_local: "bg-purple-500", graph_global: "bg-violet-400",
    hybrid: "bg-blue-500", vector: "bg-blue-400", bm25: "bg-sky-400",
    web: "bg-emerald-500", unknown: "bg-gray-400",
  };
  return (
    <div className="space-y-1.5">
      {Object.entries(breakdown).map(([src, count]) => {
        const meta = SOURCE_META[src] ?? SOURCE_META.unknown;
        const pct = Math.round((count / total) * 100);
        return (
          <div key={src} className="flex items-center gap-2 text-xs">
            <span className="w-36 text-gray-500 shrink-0">{meta.icon} {meta.label}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
              <div
                className={`${colors[src] ?? "bg-gray-400"} h-2 rounded-full transition-all`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-16 text-right text-gray-600 shrink-0">{count} chunk{count !== 1 ? "s" : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Execution timeline step ────────────────────────────────────────────────────

function TraceStepRow({ step }: { step: TraceStep }) {
  const [open, setOpen] = useState(false);
  const statusColor =
    step.status === "done" || step.status === "passed"
      ? "bg-green-500"
      : step.status === "empty"
      ? "bg-gray-300"
      : "bg-red-500"; // failed

  return (
    <div className="flex gap-3">
      {/* Timeline dot + line */}
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full mt-0.5 shrink-0 ${statusColor}`} />
        <div className="w-px flex-1 bg-gray-200 mt-1" />
      </div>

      {/* Content */}
      <div className="pb-4 flex-1 min-w-0">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 text-left w-full group"
        >
          <span className="text-base">{step.icon}</span>
          <span className="text-sm font-medium text-gray-800 group-hover:text-blue-600 transition-colors">
            {step.label}
          </span>
          <span className={`ml-auto text-xs px-2 py-0.5 rounded-full shrink-0 font-medium
            ${step.status === "done" || step.status === "passed"
              ? "bg-green-100 text-green-700"
              : step.status === "empty"
              ? "bg-gray-100 text-gray-500"
              : "bg-red-100 text-red-700"}`}>
            {step.status === "passed" ? "✓ passed"
             : step.status === "failed" ? "✗ failed"
             : step.status === "empty" ? "no results"
             : "✓ done"}
          </span>
          <span className="text-gray-400 text-xs ml-1">{open ? "▲" : "▼"}</span>
        </button>

        <p className="text-xs text-gray-500 mt-0.5 ml-7">{step.detail}</p>

        {open && (
          <div className="ml-7 mt-2 space-y-1.5 bg-gray-50 rounded-lg p-3 text-xs text-gray-600">
            {step.sub_queries && step.sub_queries.length > 0 && (
              <div>
                <p className="font-medium text-gray-700 mb-1">Sub-queries generated:</p>
                <ol className="list-decimal list-inside space-y-0.5">
                  {step.sub_queries.map((q, i) => <li key={i}>{q}</li>)}
                </ol>
              </div>
            )}
            {step.iterations !== undefined && step.iterations > 0 && (
              <p>Retrieval iterations: <span className="font-medium">{step.iterations}</span></p>
            )}
            {step.score !== undefined && (
              <p>Quality score: <span className="font-medium">{(step.score * 100).toFixed(0)}%</span></p>
            )}
            {step.issues && step.issues.length > 0 && (
              <div>
                <p className="font-medium text-red-600 mb-1">Issues found:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {step.issues.map((issue, i) => <li key={i} className="text-red-600">{issue}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Source card ────────────────────────────────────────────────────────────────

function SourceCard({ src }: { src: SourcePreview }) {
  const [open, setOpen] = useState(false);
  const meta = SOURCE_META[src.source_type] ?? SOURCE_META.unknown;
  return (
    <div className={`rounded-lg border border-gray-200 ${meta.bg} p-3`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span>{meta.icon}</span>
          <div className="min-w-0">
            <span className={`text-xs font-semibold ${meta.color}`}>Source {src.index} · {meta.label}</span>
            {src.filename && <p className="text-xs text-gray-500 truncate">{src.filename}</p>}
            {src.url && (
              <a href={src.url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-emerald-600 hover:underline truncate block">
                {src.url}
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {src.score > 0 && <span className="text-xs text-gray-400">{(src.score * 100).toFixed(0)}% match</span>}
          <button
            onClick={() => setOpen((v) => !v)}
            className={`text-xs px-2 py-0.5 rounded-full border border-gray-300 ${meta.color} hover:opacity-75`}>
            {open ? "Hide" : "Preview"}
          </button>
        </div>
      </div>
      {open && src.text_preview && (
        <p className="mt-2 pt-2 border-t border-gray-200 text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
          {src.text_preview}{src.text_preview.length >= 400 && "…"}
        </p>
      )}
    </div>
  );
}

// ── Detail drawer ──────────────────────────────────────────────────────────────

function AuditDetailDrawer({ record, onClose }: { record: AuditRecord; onClose: () => void }) {
  const p = record.payload ?? {} as AuditPayload;
  const confidencePct = p.confidence_score != null ? Math.round(p.confidence_score * 100) : null;
  const qualityPct    = p.retrieval_quality  != null ? Math.round(p.retrieval_quality  * 100) : null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/30 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="w-full max-w-2xl bg-white shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-start justify-between gap-4 shrink-0">
          <div className="min-w-0">
            <p className="text-xs text-gray-400 font-mono mb-1">{record.session_id}</p>
            <h2 className="text-base font-semibold text-gray-900 leading-snug line-clamp-2">
              {p.query || "—"}
            </h2>
            <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-500">
              {record.timestamp && (
                <span>🕐 {new Date(record.timestamp).toLocaleString()}</span>
              )}
              {p.patient_id && <span>👤 Patient: {p.patient_id}</span>}
              {p.user_id && <span>🔑 User: {p.user_id}</span>}
            </div>
          </div>
          <button onClick={onClose}
            className="shrink-0 text-gray-400 hover:text-gray-700 text-xl leading-none mt-0.5">
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-7">

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-gray-200 p-3 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {confidencePct != null ? `${confidencePct}%` : "—"}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Confidence</p>
            </div>
            <div className="rounded-xl border border-gray-200 p-3 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {qualityPct != null ? `${qualityPct}%` : "—"}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Retrieval quality</p>
            </div>
            <div className="rounded-xl border border-gray-200 p-3 text-center">
              <p className="text-2xl font-bold text-gray-900">{p.chunks_retrieved ?? 0}</p>
              <p className="text-xs text-gray-500 mt-0.5">Chunks used</p>
            </div>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-2">
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
              p.fact_check_passed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}>
              {p.fact_check_passed ? "✓ Fact-checked" : "✗ Fact-check failed"}
            </span>
            {p.web_search_used && (
              <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-emerald-100 text-emerald-700">
                🌐 Web search used
              </span>
            )}
            {p.graph_context_used && (
              <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-purple-100 text-purple-700">
                🧠 Knowledge graph used
              </span>
            )}
            {p.escalated && (
              <span className="text-xs px-2.5 py-1 rounded-full font-medium bg-red-100 text-red-700">
                ⚠️ Escalated
              </span>
            )}
          </div>

          {/* Execution timeline */}
          {p.execution_trace && p.execution_trace.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-gray-800 mb-3">Execution Flow</h3>
              <div>
                {p.execution_trace.map((step) => (
                  <TraceStepRow key={step.node} step={step} />
                ))}
              </div>
            </section>
          )}

          {/* Retrieval breakdown */}
          {p.retrieval_breakdown && Object.keys(p.retrieval_breakdown).length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-gray-800 mb-3">
                Retrieval Breakdown
                <span className="ml-2 text-xs font-normal text-gray-400">({p.chunks_retrieved} total)</span>
              </h3>
              <RetrievalBar breakdown={p.retrieval_breakdown} total={p.chunks_retrieved ?? 0} />
            </section>
          )}

          {/* Answer */}
          {p.final_answer && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gray-800">Answer</h3>
                {confidencePct != null && (
                  <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                    confidencePct >= 80 ? "bg-green-100 text-green-700"
                    : confidencePct >= 60 ? "bg-amber-100 text-amber-700"
                    : "bg-red-100 text-red-700"
                  }`}>
                    {confidencePct}% confidence
                  </span>
                )}
              </div>
              <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
                <MarkdownRenderer content={p.final_answer} />
              </div>
              {p.fact_check_issues && p.fact_check_issues.length > 0 && (
                <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-red-700 mb-1">Fact-check issues:</p>
                  <ul className="text-xs text-red-600 list-disc list-inside space-y-0.5">
                    {p.fact_check_issues.map((issue, i) => <li key={i}>{issue}</li>)}
                  </ul>
                </div>
              )}
            </section>
          )}

          {/* Sources */}
          {p.sources_preview && p.sources_preview.length > 0 && (
            <section>
              <h3 className="text-sm font-semibold text-gray-800 mb-3">
                Sources Used
                <span className="ml-2 text-xs font-normal text-gray-400">
                  ({p.sources_preview.length} shown)
                </span>
              </h3>
              <div className="space-y-2">
                {p.sources_preview.map((src) => (
                  <SourceCard key={src.index} src={src} />
                ))}
              </div>
            </section>
          )}

        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const [selected, setSelected] = useState<AuditRecord | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => adminApi.audit(100),
  });

  const records: AuditRecord[] = data?.records ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
          <p className="text-sm text-gray-500 mt-1">
            Immutable record of all system actions — click any row to see full execution details
          </p>
        </div>
        <button onClick={() => refetch()} className="text-sm text-blue-600 hover:underline">
          Refresh
        </button>
      </div>

      {isLoading && <div className="text-gray-400 text-sm">Loading audit log...</div>}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          Failed to load audit log.
        </div>
      )}
      {records.length === 0 && !isLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
          No audit records yet.
        </div>
      )}

      {records.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-44">Time</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-36">Event</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Query</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-24">Conf.</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-20">Chunks</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-24">Fact-check</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record, i) => {
                const p = record.payload ?? {} as AuditPayload;
                const confPct = p.confidence_score != null ? Math.round(p.confidence_score * 100) : null;
                return (
                  <tr
                    key={i}
                    onClick={() => setSelected(record)}
                    className="border-b border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">
                      {record.timestamp ? new Date(record.timestamp).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {record.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700 max-w-xs truncate">
                      {p.query || <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      {confPct != null ? (
                        <span className={`text-xs font-semibold ${
                          confPct >= 80 ? "text-green-700"
                          : confPct >= 60 ? "text-amber-700"
                          : "text-red-700"
                        }`}>
                          {confPct}%
                        </span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600">
                      {p.chunks_retrieved ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {p.fact_check_passed != null ? (
                        <span className={`text-xs font-medium ${
                          p.fact_check_passed ? "text-green-600" : "text-red-600"
                        }`}>
                          {p.fact_check_passed ? "✓ Pass" : "✗ Fail"}
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail drawer */}
      {selected && (
        <AuditDetailDrawer record={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
