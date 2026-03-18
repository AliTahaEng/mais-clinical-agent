"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";

export default function SessionsPage() {

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: () => adminApi.sessions(),
    refetchInterval: 15_000,
  });

  const sessions = data?.sessions ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Active Sessions</h1>
        <p className="text-sm text-gray-500 mt-1">
          Sessions with pending human approval requests
        </p>
      </div>

      {isLoading && <div className="text-gray-400 text-sm">Loading...</div>}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          Failed to load sessions.
        </div>
      )}

      {sessions.length === 0 && !isLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
          No active sessions awaiting approval.
        </div>
      )}

      <div className="space-y-3">
        {sessions.map((session) => (
          <div
            key={session.session_id}
            className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-sm text-gray-800">
                  {session.session_id}
                </p>
                <p className="text-sm text-gray-500 mt-1 line-clamp-1">
                  {session.message || "Awaiting approval"}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {session.proposed_actions.length} proposed action(s)
                </p>
              </div>
              <div className="flex gap-2">
                <Link
                  href={`/admin/sessions/${session.session_id}`}
                  className="text-sm text-blue-600 hover:underline"
                >
                  View State
                </Link>
                <Link
                  href={`/approvals/${session.session_id}`}
                  className="text-sm text-amber-600 hover:underline"
                >
                  Review →
                </Link>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
