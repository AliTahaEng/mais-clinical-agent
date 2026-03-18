"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { approvalApi } from "@/lib/api-client";
import { ActionCard } from "@/components/ActionCard";

export default function ApprovalDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [feedback, setFeedback] = useState("Clinician reviewed and approved");

  const { data, isLoading, error } = useQuery({
    queryKey: ["approval", sessionId],
    queryFn: () => approvalApi.get(sessionId),
  });

  const mutation = useMutation({
    mutationFn: () =>
      approvalApi.decide(sessionId, {
        approved_indices: selectedIndices,
        feedback,
      }),
    onSuccess: () => {
      router.push("/approvals");
    },
  });

  function toggleIndex(i: number) {
    setSelectedIndices((prev) =>
      prev.includes(i) ? prev.filter((x) => x !== i) : [...prev, i]
    );
  }

  if (isLoading) {
    return (
      <div className="text-center py-20 text-gray-400">
        Loading approval request...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700">
          Approval request not found or expired.
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Review Proposed Actions</h1>
        <p className="text-sm text-gray-500 mt-1">
          Session: <span className="font-mono">{sessionId}</span>
        </p>
      </div>

      {/* Message */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
        <p className="text-sm text-amber-800 whitespace-pre-wrap">{data.message}</p>
      </div>

      {/* Actions */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">
            Proposed Actions ({data.proposed_actions.length})
          </h2>
          <div className="flex gap-3 text-sm">
            <button
              onClick={() =>
                setSelectedIndices(data.proposed_actions.map((_, i) => i))
              }
              className="text-blue-600 hover:underline"
            >
              Select All
            </button>
            <button
              onClick={() => setSelectedIndices([])}
              className="text-gray-500 hover:underline"
            >
              Deselect All
            </button>
          </div>
        </div>

        {data.proposed_actions.map((action, i) => (
          <ActionCard
            key={i}
            action={action}
            index={i}
            selected={selectedIndices.includes(i)}
            onToggle={toggleIndex}
          />
        ))}
      </div>

      {/* Feedback */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Feedback / Notes
        </label>
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={2}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
      </div>

      {/* Buttons */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={() => router.back()}
          className="text-sm text-gray-500 hover:underline"
        >
          ← Back to inbox
        </button>
        <div className="flex gap-3">
          <button
            onClick={() =>
              mutation.mutate()
            }
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
            disabled={mutation.isPending}
          >
            Reject All
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || selectedIndices.length === 0}
            className="px-5 py-2 text-sm font-semibold text-white bg-amber-600 rounded-lg hover:bg-amber-700 disabled:opacity-50"
          >
            {mutation.isPending
              ? "Submitting..."
              : `Approve ${selectedIndices.length} of ${data.proposed_actions.length}`}
          </button>
        </div>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          Failed to submit decision. Please try again.
        </div>
      )}
    </div>
  );
}
