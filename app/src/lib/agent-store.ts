/**
 * Agent store — migrated from legalbot/webui/src/stores/agent.ts
 * Zustand store for Agent execution state, mode management, and thinking state.
 * Extended with degraded features tracking and trace span observation.
 */
import { create } from "zustand";
import type { AgentState, DegradedFeature, TraceSpan } from "./types/agents";
import { traceApi } from "./api-client";
import { on } from "./event-bus";

interface AgentStoreState {
  // Per-workspace state (keyed by workspaceId)
  workspaceIsThinking: Record<string, boolean>;
  workspaceCurrentTaskId: Record<string, string | null>;
  workspaceAgentStatus: Record<string, AgentState>;

  // Per-workspace degraded features (for user notification)
  workspaceDegradedFeatures: Record<string, Record<string, DegradedFeature>>;
  // Per-workspace trace span list
  workspaceTraceSpans: Record<string, TraceSpan[]>;

  // Cross-reference: maps backend task_id → workspace_id for store sync
  // Populated by connection-store on agent_start, used by chat-store on agent_complete/error
  _taskToWorkspace: Record<string, string>;

  // Actions
  startAgent: (workspaceId: string, mode: string, taskId?: string) => void;
  stopAgent: (workspaceId: string) => void;
  /** Stop agent by backend task_id — resolves workspace via _taskToWorkspace map. */
  stopAgentByTaskId: (taskId: string) => void;
  setAgentMode: (workspaceId: string, mode: string) => void;
  updateAgentStatus: (workspaceId: string, updates: Partial<AgentState>) => void;
  setThinking: (workspaceId: string, thinking: boolean) => void;
  setCurrentTask: (workspaceId: string, task: string) => void;
  updateThinking: (workspaceId: string, thinking: string) => void;
  /** Sync thinking state from chat-store (used when agent_thinking WS message arrives). */
  syncThinking: (taskId: string, thinking: string) => void;
  setCurrentTaskId: (workspaceId: string, taskId: string | null) => void;

  // Degraded features actions
  setDegradedFeatures: (workspaceId: string, features: Record<string, DegradedFeature>) => void;
  clearDegradedFeatures: (workspaceId: string) => void;

  // Trace span actions
  addTraceSpan: (workspaceId: string, span: TraceSpan) => void;
  updateTraceSpan: (workspaceId: string, spanId: string, updates: Partial<TraceSpan>) => void;
  clearTraceSpans: (workspaceId: string) => void;
  /** Fetch persisted trace spans from backend on WS reconnect */
  fetchTraceSpans: (workspaceId: string) => Promise<void>;

  // Convenience getters (for current workspace)
  getIsThinking: (workspaceId: string) => boolean;
  getCurrentTaskId: (workspaceId: string) => string | null;
  getAgentStatus: (workspaceId: string) => AgentState;
  getDegradedFeatures: (workspaceId: string) => Record<string, DegradedFeature>;
}

const defaultAgentStatus: AgentState = {
  isActive: false,
  isPaused: false,
  agentMode: "orchestrator",
  startTime: null,
  thinking: "",
  currentTask: "",
};

export const useAgentStore = create<AgentStoreState>((set, get) => ({
  workspaceIsThinking: {},
  workspaceCurrentTaskId: {},
  workspaceAgentStatus: {},
  workspaceDegradedFeatures: {},
  workspaceTraceSpans: {},
  _taskToWorkspace: {},

  startAgent: (workspaceId, mode, taskId) => {
    set((s) => {
      const updates: Partial<AgentStoreState> = {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [workspaceId]: {
            isActive: true,
            isPaused: false,
            agentMode: mode,
            startTime: Date.now(),
            thinking: "",
            currentTask: "",
          },
        },
        workspaceIsThinking: { ...s.workspaceIsThinking, [workspaceId]: false },
      };
      // Save task → workspace mapping for cross-store sync
      if (taskId) {
        updates._taskToWorkspace = { ...s._taskToWorkspace, [taskId]: workspaceId };
        updates.workspaceCurrentTaskId = { ...s.workspaceCurrentTaskId, [workspaceId]: taskId };
      }
      return updates;
    });
  },

  stopAgent: (workspaceId) => {
    set((s) => ({
      workspaceAgentStatus: {
        ...s.workspaceAgentStatus,
        [workspaceId]: { ...defaultAgentStatus },
      },
      workspaceIsThinking: { ...s.workspaceIsThinking, [workspaceId]: false },
      workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [workspaceId]: null },
    }));
  },

  stopAgentByTaskId: (taskId) => {
    const wsId = get()._taskToWorkspace[taskId];
    if (!wsId) return;
    set((s) => {
      const nextTaskMap = { ...s._taskToWorkspace };
      delete nextTaskMap[taskId];
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [wsId]: { ...defaultAgentStatus },
        },
        workspaceIsThinking: { ...s.workspaceIsThinking, [wsId]: false },
        workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [wsId]: null },
        _taskToWorkspace: nextTaskMap,
      };
    });
  },

  setAgentMode: (workspaceId, mode) => {
    set((s) => {
      const current = s.workspaceAgentStatus[workspaceId] || defaultAgentStatus;
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [workspaceId]: { ...current, agentMode: mode },
        },
      };
    });
  },

  updateAgentStatus: (workspaceId, updates) => {
    set((s) => {
      const current = s.workspaceAgentStatus[workspaceId] || defaultAgentStatus;
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [workspaceId]: { ...current, ...updates },
        },
      };
    });
  },

  setThinking: (workspaceId, thinking) => {
    set((s) => ({
      workspaceIsThinking: { ...s.workspaceIsThinking, [workspaceId]: thinking },
    }));
  },

  setCurrentTask: (workspaceId, task) => {
    set((s) => {
      const current = s.workspaceAgentStatus[workspaceId] || defaultAgentStatus;
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [workspaceId]: { ...current, currentTask: task },
        },
      };
    });
  },

  updateThinking: (workspaceId, thinking) => {
    set((s) => {
      const current = s.workspaceAgentStatus[workspaceId] || defaultAgentStatus;
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [workspaceId]: { ...current, thinking },
        },
      };
    });
  },

  /** Sync thinking state from chat-store when agent_thinking WS message arrives. */
  syncThinking: (taskId, thinking) => {
    const wsId = get()._taskToWorkspace[taskId];
    if (!wsId) return;
    set((s) => {
      const current = s.workspaceAgentStatus[wsId] || defaultAgentStatus;
      return {
        workspaceAgentStatus: {
          ...s.workspaceAgentStatus,
          [wsId]: { ...current, thinking },
        },
      };
    });
  },

  setCurrentTaskId: (workspaceId, taskId) => {
    set((s) => ({
      workspaceCurrentTaskId: { ...s.workspaceCurrentTaskId, [workspaceId]: taskId },
    }));
  },

  // ── Degraded features ───────────────────────────────────────
  setDegradedFeatures: (workspaceId, features) => {
    set((s) => ({
      workspaceDegradedFeatures: {
        ...s.workspaceDegradedFeatures,
        [workspaceId]: features,
      },
    }));
  },

  clearDegradedFeatures: (workspaceId) => {
    set((s) => {
      const next = { ...s.workspaceDegradedFeatures };
      delete next[workspaceId];
      return { workspaceDegradedFeatures: next };
    });
  },

  // ── Trace spans ─────────────────────────────────────────────
  addTraceSpan: (workspaceId, span) => {
    set((s) => ({
      workspaceTraceSpans: {
        ...s.workspaceTraceSpans,
        [workspaceId]: [...(s.workspaceTraceSpans[workspaceId] || []), span],
      },
    }));
  },

  updateTraceSpan: (workspaceId, spanId, updates) => {
    set((s) => {
      const spans = s.workspaceTraceSpans[workspaceId] || [];
      return {
        workspaceTraceSpans: {
          ...s.workspaceTraceSpans,
          [workspaceId]: spans.map((sp) => (sp.span_id === spanId ? { ...sp, ...updates } : sp)),
        },
      };
    });
  },

  clearTraceSpans: (workspaceId) => {
    set((s) => {
      const next = { ...s.workspaceTraceSpans };
      delete next[workspaceId];
      return { workspaceTraceSpans: next };
    });
  },

  fetchTraceSpans: async (workspaceId) => {
    try {
      const res = await traceApi.getTraces(workspaceId, { limit: 50 });
      if (!res.success || !res.data?.traces.length) return;

      // Flatten all spans from all traces into a single TraceSpan array
      const spans: TraceSpan[] = [];
      for (const trace of res.data.traces) {
        for (const s of trace.spans) {
          spans.push({
            span_id: s.span_id,
            parent_span_id: s.parent_span_id ?? undefined,
            span_name: s.span_name,
            phase: (s.phase as TraceSpan["phase"]) ?? undefined,
            start_time: s.start_time,
            end_time: s.end_time ?? undefined,
            duration_ms: s.duration_ms ?? undefined,
            status: (s.status as TraceSpan["status"]) || "running",
            input_summary: s.input_summary ?? undefined,
            output_summary: s.output_summary ?? undefined,
          });
        }
      }

      console.log(
        `[Trace] Reconnected — restored ${spans.length} trace span(s) for workspace ${workspaceId}`,
      );
      set((s) => ({
        workspaceTraceSpans: { ...s.workspaceTraceSpans, [workspaceId]: spans },
      }));
    } catch (err) {
      console.warn("[Trace] Reconnect restore failed (non-fatal):", err);
    }
  },

  getIsThinking: (workspaceId) => get().workspaceIsThinking[workspaceId] ?? false,
  getCurrentTaskId: (workspaceId) => get().workspaceCurrentTaskId[workspaceId] ?? null,
  getAgentStatus: (workspaceId) => get().workspaceAgentStatus[workspaceId] ?? defaultAgentStatus,
  getDegradedFeatures: (workspaceId) => get().workspaceDegradedFeatures[workspaceId] ?? {},
}));

// ── Event bus subscriptions (decoupled from connection-store) ───────

on("ws:agent_start", (detail) => {
  const { wsId, mode, taskId } = detail as { wsId: string; mode: string; taskId?: string };
  useAgentStore.getState().startAgent(wsId, mode, taskId);
});

on("ws:degraded_features", (detail) => {
  const { wsId, features } = detail as {
    wsId: string;
    features: Record<string, DegradedFeature>;
  };
  useAgentStore.getState().setDegradedFeatures(wsId, features);
});

on("ws:memory_ready", (detail) => {
  const { wsId } = detail as { wsId: string };
  useAgentStore.getState().clearDegradedFeatures(wsId);
});

on("ws:agent_span", (detail) => {
  const { wsId, span } = detail as { wsId: string; span: TraceSpan };
  useAgentStore.getState().addTraceSpan(wsId, span);
});

on("ws:restore_traces", (detail) => {
  const { wsId } = detail as { wsId: string };
  useAgentStore.getState().fetchTraceSpans(wsId);
});
