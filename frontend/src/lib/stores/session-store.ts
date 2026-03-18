/**
 * Zustand store for the active streaming session state.
 */
import { create } from "zustand";
import type { DoneEvent, InterruptEvent, StepEvent, StreamStatus } from "../types";

interface StepProgress {
  node: string;
  label: string;
  status: "running" | "done";
}

interface SessionState {
  // Current session
  activeSessionId: string | null;
  streamStatus: StreamStatus;

  // Streaming content
  streamingTokens: string;
  steps: StepProgress[];

  // Final result
  doneEvent: DoneEvent | null;

  // Interrupt payload (needs human approval)
  interruptPayload: InterruptEvent | null;

  // Error
  streamError: string | null;

  // Actions
  startStream: (sessionId: string) => void;
  addToken: (token: string) => void;
  updateStep: (step: StepEvent) => void;
  setInterrupt: (payload: InterruptEvent) => void;
  setDone: (event: DoneEvent) => void;
  setError: (message: string) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  activeSessionId: null,
  streamStatus: "idle",
  streamingTokens: "",
  steps: [],
  doneEvent: null,
  interruptPayload: null,
  streamError: null,

  startStream: (sessionId) =>
    set({
      activeSessionId: sessionId,
      streamStatus: "streaming",
      streamingTokens: "",
      steps: [],
      doneEvent: null,
      interruptPayload: null,
      streamError: null,
    }),

  addToken: (token) =>
    set((state) => ({ streamingTokens: state.streamingTokens + token })),

  updateStep: (step) =>
    set((state) => {
      const existing = state.steps.findIndex((s) => s.node === step.node);
      const updated =
        existing >= 0
          ? state.steps.map((s, i) => (i === existing ? step : s))
          : [...state.steps, step];
      return { steps: updated };
    }),

  setInterrupt: (payload) =>
    set({ interruptPayload: payload, streamStatus: "interrupted" }),

  setDone: (event) =>
    set({ doneEvent: event, streamStatus: "complete" }),

  setError: (message) =>
    set({ streamError: message, streamStatus: "error" }),

  reset: () =>
    set({
      activeSessionId: null,
      streamStatus: "idle",
      streamingTokens: "",
      steps: [],
      doneEvent: null,
      interruptPayload: null,
      streamError: null,
    }),
}));
