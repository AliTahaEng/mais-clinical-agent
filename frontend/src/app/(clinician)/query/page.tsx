"use client";

import { useRef, useState } from "react";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { querySSE } from "@/lib/api-client";
import { useSessionStore } from "@/lib/stores/session-store";
import { SSEStatusIndicator } from "@/components/SSEStatusIndicator";
import { ActionCard } from "@/components/ActionCard";
import { approvalApi } from "@/lib/api-client";
import type { SourceItem } from "@/lib/types";

// ── Source type metadata ──────────────────────────────────────────────────────

const SOURCE_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  vector:       { label: "Document (semantic)",  color: "text-blue-700",   bg: "bg-blue-50",   border: "border-blue-200" },
  bm25:         { label: "Document (keyword)",   color: "text-blue-700",   bg: "bg-blue-50",   border: "border-blue-200" },
  graph_local:  { label: "Knowledge Graph",      color: "text-purple-700", bg: "bg-purple-50", border: "border-purple-200" },
  graph_global: { label: "Knowledge Graph",      color: "text-purple-700", bg: "bg-purple-50", border: "border-purple-200" },
  web:          { label: "Web Search",           color: "text-emerald-700",bg: "bg-emerald-50",border: "border-emerald-200" },
  unknown:      { label: "Retrieved",            color: "text-gray-600",   bg: "bg-gray-50",   border: "border-gray-200" },
};

const SOURCE_ICON: Record<string, string> = {
  vector: "📄", bm25: "📄",
  graph_local: "🧠", graph_global: "🧠",
  web: "🌐", unknown: "📎",
};

// ── Source card ───────────────────────────────────────────────────────────────

function SourceCard({ source }: { source: SourceItem }) {
  const [expanded, setExpanded] = useState(false);
  const meta = SOURCE_META[source.source_type] ?? SOURCE_META.unknown;
  const icon = SOURCE_ICON[source.source_type] ?? "📎";
  const confidencePct = Math.round(source.score * 100);

  return (
    <div className={`rounded-lg border ${meta.border} ${meta.bg} p-3 text-sm`}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base shrink-0">{icon}</span>
          <div className="min-w-0">
            <span className={`font-semibold ${meta.color}`}>Source {source.index}</span>
            <span className={`ml-2 text-xs ${meta.color} opacity-75`}>{meta.label}</span>
            {source.filename && (
              <p className="text-xs text-gray-500 truncate mt-0.5">{source.filename}</p>
            )}
            {source.url && source.source_type === "web" && (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-emerald-600 hover:underline truncate block mt-0.5"
              >
                {source.url}
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {source.score > 0 && (
            <span className="text-xs text-gray-400">
              {confidencePct}% match
            </span>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className={`text-xs px-2 py-0.5 rounded-full border ${meta.border} ${meta.color} hover:opacity-75 transition-opacity`}
          >
            {expanded ? "Less" : "Preview"}
          </button>
        </div>
      </div>

      {/* Expandable preview */}
      {expanded && source.text_preview && (
        <p className="mt-2 pt-2 border-t border-current/10 text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
          {source.text_preview}
          {source.text_preview.length >= 300 && "…"}
        </p>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function QueryPage() {
  const [query, setQuery] = useState("");
  const [patientId, setPatientId] = useState("");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const {
    streamStatus,
    streamingTokens,
    steps,
    doneEvent,
    interruptPayload,
    streamError,
    startStream,
    addToken,
    updateStep,
    setInterrupt,
    setDone,
    setError,
    reset,
  } = useSessionStore();

  const isStreaming = streamStatus === "streaming";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || isStreaming) return;

    reset();
    setSourcesOpen(false);
    const controller = new AbortController();
    abortRef.current = controller;
    startStream("pending");

    try {
      await querySSE(
        query.trim(),
        patientId.trim() || undefined,
        undefined,
        {
          onStep: updateStep,
          onToken: (ev) => addToken(ev.token),
          onInterrupt: setInterrupt,
          onDone: setDone,
          onError: (ev) => setError(ev.message),
        },
        controller.signal
      );
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        setError(err.message);
      }
    }
  }

  function handleStop() {
    abortRef.current?.abort();
    reset();
  }

  // ── Approval handling ───────────────────────────────────────────────────────
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [approvingAll, setApprovingAll] = useState(false);

  function toggleIndex(i: number) {
    setSelectedIndices((prev) =>
      prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i]
    );
  }

  async function submitApproval() {
    if (!interruptPayload) return;
    setApprovingAll(true);
    try {
      await approvalApi.decide(interruptPayload.session_id, {
        approved_indices: selectedIndices,
        feedback: "Clinician reviewed and approved",
      });
      reset();
    } catch {
      setError("Failed to submit approval");
    } finally {
      setApprovingAll(false);
    }
  }

  const answerText = streamingTokens || doneEvent?.answer || "";
  const confidencePct = doneEvent ? Math.round(doneEvent.confidence_score * 100) : null;
  const sources = doneEvent?.sources ?? [];
  const webUsed = doneEvent?.web_search_used ?? false;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Medical Query</h1>
        <p className="text-gray-500 text-sm mt-1">
          Ask a clinical question and get evidence-based answers from the knowledge graph.
        </p>
      </div>

      {/* Query form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Patient ID (optional)
          </label>
          <input
            type="text"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            placeholder="e.g. P001"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Clinical Query <span className="text-red-500">*</span>
          </label>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What are the drug interactions for metformin in a patient with renal impairment?"
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>

        <div className="flex items-center justify-between">
          <SSEStatusIndicator />
          <div className="flex gap-2">
            {isStreaming && (
              <button
                type="button"
                onClick={handleStop}
                className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
              >
                Stop
              </button>
            )}
            <button
              type="submit"
              disabled={isStreaming || !query.trim()}
              className="px-5 py-2 text-sm font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isStreaming ? "Processing..." : "Submit Query"}
            </button>
          </div>
        </div>
      </form>

      {/* Step progress */}
      {steps.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Progress</h2>
          <div className="space-y-2">
            {steps.map((step) => (
              <div key={step.node} className="flex items-center gap-3 text-sm">
                <div
                  className={
                    step.status === "running"
                      ? "w-2 h-2 rounded-full bg-blue-500 animate-pulse"
                      : "w-2 h-2 rounded-full bg-green-500"
                  }
                />
                <span className={step.status === "done" ? "text-gray-400 line-through" : "text-gray-700"}>
                  {step.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Answer card */}
      {(answerText || streamStatus === "complete") && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">

          {/* Answer header */}
          <div className="flex items-center justify-between px-6 pt-5 pb-3">
            <h2 className="text-sm font-semibold text-gray-700">Answer</h2>
            <div className="flex items-center gap-2">
              {webUsed && (
                <span className="flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                  🌐 Web search included
                </span>
              )}
              {doneEvent?.fact_check_passed && (
                <span className="flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                  ✓ Fact-checked
                </span>
              )}
              {confidencePct !== null && (
                <span
                  className={
                    confidencePct >= 80
                      ? "text-xs font-semibold text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full"
                      : confidencePct >= 60
                      ? "text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full"
                      : "text-xs font-semibold text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full"
                  }
                >
                  {confidencePct}% confidence
                </span>
              )}
            </div>
          </div>

          {/* Rendered markdown answer */}
          <div className="px-6 pb-5">
            <div>
              {isStreaming ? (
                <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {answerText}
                  <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse ml-0.5 align-middle" />
                </p>
              ) : (
                <MarkdownRenderer content={answerText} />
              )}
            </div>
          </div>

          {/* Sources section */}
          {sources.length > 0 && (
            <div className="border-t border-gray-100">
              <button
                onClick={() => setSourcesOpen((v) => !v)}
                className="w-full flex items-center justify-between px-6 py-3 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <span className="font-medium">
                  {sources.length} Sources used
                  {webUsed && <span className="ml-2 text-emerald-600">· includes web</span>}
                </span>
                <span className="text-gray-400">{sourcesOpen ? "▲ Hide" : "▼ Show"}</span>
              </button>

              {sourcesOpen && (
                <div className="px-6 pb-5 space-y-2">
                  {/* Source type legend */}
                  <div className="flex flex-wrap gap-3 mb-3 text-xs text-gray-500">
                    <span className="flex items-center gap-1">📄 Document knowledge</span>
                    <span className="flex items-center gap-1">🧠 Knowledge graph</span>
                    <span className="flex items-center gap-1">🌐 Web search</span>
                  </div>
                  {sources.map((src) => (
                    <SourceCard key={src.index} source={src} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Footer stats */}
          {doneEvent && (
            <div className="border-t border-gray-100 px-6 py-3 flex flex-wrap gap-4 text-xs text-gray-400">
              <span>{doneEvent.chunks_used} chunks retrieved</span>
              {doneEvent.actions_proposed > 0 && (
                <span>{doneEvent.actions_proposed} actions proposed</span>
              )}
              {doneEvent.actions_executed > 0 && (
                <span>{doneEvent.actions_executed} actions executed</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Interrupt / approval banner */}
      {streamStatus === "interrupted" && interruptPayload && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-amber-800 mb-2">
            Clinician Approval Required
          </h2>
          <p className="text-sm text-amber-700 mb-4">{interruptPayload.message}</p>

          <div className="space-y-3 mb-5">
            {interruptPayload.proposed_actions.map((action, i) => (
              <ActionCard
                key={i}
                action={action}
                index={i}
                selected={selectedIndices.includes(i)}
                onToggle={toggleIndex}
              />
            ))}
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setSelectedIndices(interruptPayload.proposed_actions.map((_, i) => i))}
              className="text-sm text-blue-600 hover:underline"
            >
              Select All
            </button>
            <button
              onClick={() => setSelectedIndices([])}
              className="text-sm text-gray-500 hover:underline"
            >
              Deselect All
            </button>
            <div className="flex-1" />
            <button
              onClick={() => reset()}
              className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Reject All
            </button>
            <button
              onClick={submitApproval}
              disabled={approvingAll || selectedIndices.length === 0}
              className="px-5 py-2 text-sm font-semibold text-white bg-amber-600 rounded-lg hover:bg-amber-700 disabled:opacity-50"
            >
              {approvingAll ? "Submitting..." : `Approve ${selectedIndices.length} Action(s)`}
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {streamError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
          <span className="font-medium">Error:</span> {streamError}
        </div>
      )}
    </div>
  );
}
