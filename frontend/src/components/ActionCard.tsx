"use client";

import { cn } from "@/lib/utils";
import type { ProposedAction } from "@/lib/types";

interface ActionCardProps {
  action: ProposedAction;
  index: number;
  selected: boolean;
  onToggle: (index: number) => void;
}

const TIER_COLORS: Record<number, string> = {
  1: "bg-green-50 border-green-200 text-green-800",
  2: "bg-amber-50 border-amber-200 text-amber-800",
  3: "bg-red-50 border-red-200 text-red-800",
};

const TIER_LABELS: Record<number, string> = {
  1: "Auto-Execute",
  2: "Approval Required",
  3: "Mandatory Escalation",
};

export function ActionCard({ action, index, selected, onToggle }: ActionCardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border p-4 cursor-pointer transition-all",
        TIER_COLORS[action.tier] ?? "bg-gray-50 border-gray-200",
        selected ? "ring-2 ring-blue-500" : "hover:opacity-80"
      )}
      onClick={() => onToggle(index)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{action.tool_name}</span>
            <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-white bg-opacity-60">
              TIER {action.tier} — {TIER_LABELS[action.tier]}
            </span>
          </div>
          <p className="mt-1 text-sm">{action.rationale}</p>
          {Object.keys(action.parameters).length > 0 && (
            <pre className="mt-2 text-xs bg-white bg-opacity-40 rounded p-2 overflow-auto">
              {JSON.stringify(action.parameters, null, 2)}
            </pre>
          )}
        </div>
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(index)}
          className="h-4 w-4 mt-1"
          onClick={(e) => e.stopPropagation()}
        />
      </div>
    </div>
  );
}
