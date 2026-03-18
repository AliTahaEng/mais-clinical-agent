"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";

const KNOWN_LABELS = ["Drug", "Condition", "Gene", "Enzyme", "Symptom", "Treatment"];

export default function GraphPage() {
  const [selectedLabel, setSelectedLabel] = useState<string>("");

  const counts = useQuery({
    queryKey: ["admin", "graph", "counts"],
    queryFn: () => adminApi.graphNodes(undefined),
  });

  const nodes = useQuery({
    queryKey: ["admin", "graph", "nodes", selectedLabel],
    queryFn: () => adminApi.graphNodes(selectedLabel || undefined),
    enabled: !!selectedLabel,
  });

  const countData = counts.data?.nodes ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Graph Explorer</h1>
        <p className="text-sm text-gray-500 mt-1">
          Browse the medical knowledge graph
        </p>
      </div>

      {/* Node counts by label */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          Node Counts by Type
        </h2>
        {counts.isLoading ? (
          <div className="text-gray-400 text-sm">Loading graph stats...</div>
        ) : counts.error ? (
          <div className="text-sm text-red-500">Failed to connect to knowledge graph.</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {countData.map((item, i) => (
              <button
                key={i}
                onClick={() => setSelectedLabel(item.label ?? "")}
                className={`text-left bg-white rounded-xl border p-4 shadow-sm hover:border-blue-300 transition-colors ${
                  selectedLabel === item.label
                    ? "border-blue-400 ring-1 ring-blue-400"
                    : "border-gray-200"
                }`}
              >
                <p className="text-2xl font-bold text-gray-900">{item.count}</p>
                <p className="text-sm text-gray-500 mt-0.5">{item.label}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Label filter */}
      <section>
        <h2 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
          Browse Nodes
        </h2>
        <div className="flex gap-2 flex-wrap mb-4">
          {KNOWN_LABELS.map((label) => (
            <button
              key={label}
              onClick={() => setSelectedLabel(label)}
              className={`px-3 py-1.5 text-sm rounded-lg border font-medium transition-colors ${
                selectedLabel === label
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-600 border-gray-300 hover:border-blue-300"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            onClick={() => setSelectedLabel("")}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-200 text-gray-400 hover:text-gray-600"
          >
            Clear
          </button>
        </div>

        {selectedLabel && (
          <>
            {nodes.isLoading && (
              <div className="text-gray-400 text-sm">Loading {selectedLabel} nodes...</div>
            )}
            {nodes.data && (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Type</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(nodes.data.nodes ?? []).map((node, i) => (
                      <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium">{node.name ?? "—"}</td>
                        <td className="px-4 py-3 text-gray-500">{node.type ?? "—"}</td>
                        <td className="px-4 py-3 text-gray-500 text-xs max-w-[300px] truncate">
                          {node.description ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
