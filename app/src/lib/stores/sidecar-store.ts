/**
 * Sidecar status store — lifecycle of the bundled dawei sidecar (Tauri desktop).
 *
 * Rust emits `sidecar-status` events
 * ({ status: "starting" | "progress" | "ready" | "failed", port, message,
 *    attempt?, max_attempts?, elapsed_ms?, logs? }) plus high-frequency
 * `sidecar-log` events ({ line, ts_ms }); useSidecarStatus() listens and updates
 * this store. SidecarOverlay renders a connecting (with live progress + a
 * collapsible log) / failed screen until `stage === "ready"`. No-op in web build.
 */
import { create } from "zustand";

export type SidecarStage = "starting" | "ready" | "failed";

export interface SidecarLogLine {
  id: string;
  ts: number;
  text: string;
}

/** Cap the in-memory log buffer so a long/stuck startup can't grow it forever. */
const MAX_LOG_LINES = 300;

interface SidecarState {
  stage: SidecarStage;
  port: number | null;
  message: string | null;
  /** Health-check progress (null until the first `progress` event arrives). */
  attempt: number | null;
  maxAttempts: number | null;
  elapsedMs: number | null;
  /** Tailed sidecar log lines (newest last). */
  logs: SidecarLogLine[];
  setStarting: (port: number) => void;
  setProgress: (attempt: number, maxAttempts: number, elapsedMs: number) => void;
  appendLog: (text: string, ts?: number) => void;
  setReady: (port: number) => void;
  setFailed: (port: number | null, message?: string | null, logs?: string[] | null) => void;
}

export const useSidecarStore = create<SidecarState>((set) => ({
  stage: "starting",
  port: null,
  message: null,
  attempt: null,
  maxAttempts: null,
  elapsedMs: null,
  logs: [],
  setStarting: (port) =>
    set({
      stage: "starting",
      port,
      message: null,
      attempt: null,
      maxAttempts: null,
      elapsedMs: null,
      logs: [],
    }),
  setProgress: (attempt, maxAttempts, elapsedMs) => set({ attempt, maxAttempts, elapsedMs }),
  appendLog: (text, ts = Date.now()) =>
    set((state) => {
      const line: SidecarLogLine = { id: makeId(), ts, text };
      const logs = [...state.logs, line];
      return { logs: logs.length > MAX_LOG_LINES ? logs.slice(logs.length - MAX_LOG_LINES) : logs };
    }),
  setReady: (port) =>
    set({ stage: "ready", port, message: null, attempt: null, maxAttempts: null, elapsedMs: null }),
  setFailed: (port, message = null, logs = null) =>
    set((state) => {
      // Rust may hand back a tail of the log file with the failure; merge it into
      // the buffer (deduped by text against what we already have) so the failure
      // screen shows the smoking gun even if the live tailer hadn't run yet.
      const existing = new Set(state.logs.map((l) => l.text));
      const merged =
        logs && logs.length > 0
          ? [
              ...state.logs,
              ...logs
                .filter((t) => t.trim() !== "" && !existing.has(t))
                .map((t) => ({ id: makeId(), ts: Date.now(), text: t })),
            ]
          : state.logs;
      const trimmed =
        merged.length > MAX_LOG_LINES ? merged.slice(merged.length - MAX_LOG_LINES) : merged;
      return { stage: "failed", port, message, logs: trimmed };
    }),
}));

/** crypto.randomUUID may be absent in older webviews; fall back to a counter. */
let idCounter = 0;
function makeId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  idCounter += 1;
  return `log-${Date.now()}-${idCounter}`;
}
