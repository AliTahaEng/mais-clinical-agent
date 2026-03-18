"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api-client";
import type { FeatureFlags } from "@/lib/types";

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between py-4 border-b border-gray-100 last:border-0">
      <div className="flex-1 pr-8">
        <p className="text-sm font-medium text-gray-900">{label}</p>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative flex-shrink-0 h-6 w-11 rounded-full transition-colors focus:outline-none ${
          checked ? "bg-blue-600" : "bg-gray-300"
        }`}
        role="switch"
        aria-checked={checked}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<FeatureFlags>({
    queryKey: ["admin", "settings"],
    queryFn: () => adminApi.getSettings(),
  });

  const [local, setLocal] = useState<Partial<FeatureFlags>>({});

  useEffect(() => {
    if (data) setLocal(data);
  }, [data]);

  const mutation = useMutation({
    mutationFn: (flags: Partial<FeatureFlags>) =>
      adminApi.updateSettings(flags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "settings"] });
    },
  });

  function updateFlag(key: keyof FeatureFlags, value: boolean) {
    const updated = { ...local, [key]: value };
    setLocal(updated);
    mutation.mutate({ [key]: value });
  }

  if (isLoading) return <div className="text-gray-400 text-sm">Loading settings...</div>;
  if (error) return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
      Failed to load settings.
    </div>
  );

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">System Settings</h1>
        <p className="text-sm text-gray-500 mt-1">
          Live feature flag controls (in-memory; restart to revert)
        </p>
      </div>

      {/* Info banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-700">
        <strong>Note:</strong> Changes are applied immediately but are not persisted to the .env file.
        Restart the server to revert to default values.
      </div>

      {/* Config readonly */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Configuration</h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ["LLM Provider", local.llm_provider],
            ["Embedding Provider", local.embedding_provider],
            ["EHR Provider", local.ehr_provider],
            ["Confidence Threshold", `${((local.confidence_threshold ?? 0) * 100).toFixed(0)}%`],
            ["Max Iterations", local.max_iterations],
          ].map(([label, value]) => (
            <div key={String(label)} className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-xs text-gray-400">{label}</p>
              <p className="font-medium text-gray-800 mt-0.5">{String(value ?? "—")}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Feature flags */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-700 mb-2">Feature Flags</h2>
        <Toggle
          label="Action Execution"
          description="Allow agents to autonomously execute Tier 1 actions"
          checked={Boolean(local.enable_action_execution)}
          onChange={(v) => updateFlag("enable_action_execution", v)}
        />
        <Toggle
          label="Force Human Approval"
          description="Require human approval for ALL actions, overriding tier settings"
          checked={Boolean(local.force_human_approval)}
          onChange={(v) => updateFlag("force_human_approval", v)}
        />
        <Toggle
          label="Web Search Fallback"
          description="Enable Tavily web search when retrieval quality is low"
          checked={Boolean(local.enable_web_search)}
          onChange={(v) => updateFlag("enable_web_search", v)}
        />
        <Toggle
          label="LangSmith Tracing"
          description="Send traces to LangSmith for observability"
          checked={Boolean(local.enable_tracing)}
          onChange={(v) => updateFlag("enable_tracing", v)}
        />
      </div>

      {mutation.isSuccess && (
        <div className="text-sm text-green-600 font-medium">✓ Settings updated</div>
      )}
      {mutation.isError && (
        <div className="text-sm text-red-600">Failed to update settings</div>
      )}
    </div>
  );
}
