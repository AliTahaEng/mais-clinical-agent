"use client";

import { useSessionStore } from "@/lib/stores/session-store";
import { cn } from "@/lib/utils";

export function SSEStatusIndicator() {
  const { streamStatus, steps } = useSessionStore();

  const statusConfig = {
    idle: { color: "bg-gray-300", label: "Idle" },
    streaming: { color: "bg-blue-500 animate-pulse", label: "Processing..." },
    interrupted: { color: "bg-amber-500", label: "Awaiting Approval" },
    complete: { color: "bg-green-500", label: "Complete" },
    error: { color: "bg-red-500", label: "Error" },
  };

  const config = statusConfig[streamStatus];
  const activeStep = steps.findLast((s) => s.status === "running");

  return (
    <div className="flex items-center gap-2 text-sm text-gray-600">
      <div className={cn("h-2 w-2 rounded-full", config.color)} />
      <span>{activeStep?.label ?? config.label}</span>
    </div>
  );
}
