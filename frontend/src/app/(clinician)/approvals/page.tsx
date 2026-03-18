"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { approvalApi } from "@/lib/api-client";

export default function ApprovalsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => approvalApi.list(),
    refetchInterval: 30_000,
  });

  const items = data?.items ?? [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Approval Inbox</h1>
          <p className="text-sm text-gray-500 mt-1">
            Pending actions waiting for your review
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="text-sm text-blue-600 hover:underline"
        >
          Refresh
        </button>
      </div>

      {isLoading && (
        <div className="text-center py-12 text-gray-400">Loading...</div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          Failed to load approvals
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <div className="text-4xl mb-3">✓</div>
          <h2 className="text-gray-600 font-medium">No pending approvals</h2>
          <p className="text-sm text-gray-400 mt-1">
            All clinical actions have been reviewed.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {items.map((item) => (
          <Link
            key={item.session_id}
            href={`/approvals/${item.session_id}`}
            className="block bg-white rounded-xl border border-amber-200 p-5 shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  Session: {item.session_id}
                </p>
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                  {item.message || "Pending approval"}
                </p>
              </div>
              <div className="ml-3 flex flex-col items-end gap-1">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                  {item.proposed_actions.length} action
                  {item.proposed_actions.length !== 1 ? "s" : ""}
                </span>
                <span className="text-xs text-amber-600">→ Review</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
