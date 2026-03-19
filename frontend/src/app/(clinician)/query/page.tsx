"use client";

import { useRef, useState } from "react";
import { querySSE } from "@/lib/api-client";
import { useSessionStore } from "@/lib/stores/session-store";
import { SSEStatusIndicator } from "@/components/SSEStatusIndicator";
import { ActionCard } from "@/components/ActionCard";
import { approvalApi } from "@/lib/api-client";

export default function QueryPage() {
  const [query, setQuery] = useState("");
  const [patientId, setPatientId] = useState("");
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
    activeSessionId,
  } = useSessionStore();

  const isStreaming = streamStatus === "streaming";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || isStreaming) return;

    reset();
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

  // ── Approval handling ──────────────────────────────────────────────────────
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
      // Reset to show completion
      reset();
    } catch {
      setError("Failed to submit approval");
    } finally {
      setApprovingAll(false);
    }
  }

  const confidencePercent = doneEvent
    ? Math.round(doneEvent.confidence_score * 100)
    : null;

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

      {/* Streaming answer */}
      {(streamingTokens || streamStatus === "complete") && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700">Answer</h2>
            {confidencePercent !== null && (
              <span
                className={
                  confidencePercent >= 80
                    ? "text-xs font-medium text-green-600 bg-green-50 px-2 py-0.5 rounded-full"
                    : confidencePercent >= 60
                    ? "text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full"
                    : "text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full"
                }
              >
                {confidencePercent}% confidence
              </span>
            )}
          </div>
          <div className="prose prose-sm max-w-none text-gray-800 whitespace-pre-wrap">
            {streamingTokens || doneEvent?.answer}
            {isStreaming && (
              <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse ml-0.5" />
            )}
          </div>
          {doneEvent && (
            <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap gap-4 text-xs text-gray-500">
              <span>Chunks used: {doneEvent.chunks_used}</span>
              <span>Actions proposed: {doneEvent.actions_proposed}</span>
              {doneEvent.fact_check_passed && (
                <span className="text-green-600">✓ Fact-checked</span>
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
              onClick={() =>
                setSelectedIndices(
                  interruptPayload.proposed_actions.map((_, i) => i)
                )
              }
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
