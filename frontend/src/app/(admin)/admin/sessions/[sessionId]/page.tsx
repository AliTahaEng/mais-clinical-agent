"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";

export default function SessionStatePage() {
  const params = useParams();
  const sessionId = params.sessionId as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "session", sessionId],
    queryFn: () => adminApi.sessionState(sessionId),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Session State</h1>
        <p className="font-mono text-sm text-gray-500 mt-1">{sessionId}</p>
      </div>

      {isLoading && <div className="text-gray-400 text-sm">Loading state...</div>}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          Session not found or expired.
        </div>
      )}

      {data && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <pre className="text-xs text-gray-700 overflow-auto max-h-[600px] whitespace-pre-wrap">
            {JSON.stringify(data.state, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
