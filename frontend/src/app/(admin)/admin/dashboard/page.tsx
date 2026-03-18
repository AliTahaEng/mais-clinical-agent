"use client";

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { HealthResponse, StatsResponse } from "@/lib/types";

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

function ServiceBadge({ name, ok }: { name: string; ok: boolean }) {
  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
        ok
          ? "bg-green-50 text-green-700 border border-green-200"
          : "bg-red-50 text-red-700 border border-red-200"
      }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${ok ? "bg-green-500" : "bg-red-500"}`}
      />
      {name}
    </div>
  );
}

export default function DashboardPage() {

  const health = useQuery<HealthResponse>({
    queryKey: ["admin", "health"],
    queryFn: () => adminApi.health(),
    refetchInterval: 30_000,
  });

  const stats = useQuery<StatsResponse>({
    queryKey: ["admin", "stats"],
    queryFn: () => adminApi.stats(),
    refetchInterval: 60_000,
  });

  const chartData = stats.data
    ? Object.entries(stats.data.event_breakdown).map(([name, count]) => ({
        name: name.replace(".", "\n"),
        count,
      }))
    : [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">System overview and health status</p>
      </div>

      {/* Health */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          Service Health
        </h2>
        {health.isLoading ? (
          <div className="text-sm text-gray-400">Checking services...</div>
        ) : health.error ? (
          <div className="text-sm text-red-500">Failed to load health status</div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <ServiceBadge
              name="Overall"
              ok={health.data?.status === "healthy"}
            />
            {Object.entries(health.data?.services ?? {}).map(([name, ok]) => (
              <ServiceBadge key={name} name={name} ok={ok} />
            ))}
          </div>
        )}
      </section>

      {/* Stats cards */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          Usage Statistics
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total Queries"
            value={stats.data?.total_queries ?? "—"}
          />
          <StatCard
            label="Actions Executed"
            value={stats.data?.total_actions_executed ?? "—"}
          />
          <StatCard
            label="Pending Approvals"
            value={stats.data?.pending_approvals ?? "—"}
            sub="Awaiting clinician review"
          />
          <StatCard
            label="Event Types"
            value={
              stats.data ? Object.keys(stats.data.event_breakdown).length : "—"
            }
          />
        </div>
      </section>

      {/* Chart */}
      {chartData.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
            Event Breakdown
          </h2>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  );
}
