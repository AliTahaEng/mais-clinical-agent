"use client";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";

export default function AuditPage() {

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => adminApi.audit(100),
  });

  const records = data?.records ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Audit Log</h1>
          <p className="text-sm text-gray-500 mt-1">
            Immutable record of all system actions
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="text-sm text-blue-600 hover:underline"
        >
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

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        {records.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left px-4 py-3 font-medium text-gray-600">Time</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Event</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Session</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Details</th>
              </tr>
            </thead>
            <tbody>
              {records.map((record, i) => (
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-500 whitespace-nowrap">
                    {record.timestamp
                      ? new Date(record.timestamp).toLocaleString()
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {record.event_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500 max-w-[180px] truncate">
                    {record.session_id}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 max-w-[300px] truncate">
                    {JSON.stringify(
                      Object.fromEntries(
                        Object.entries(record).filter(
                          ([k]) =>
                            !["session_id", "event_type", "timestamp"].includes(k)
                        )
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
