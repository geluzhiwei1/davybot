/**
 * Agent type definitions — migrated from legalbot/webui/src/types/agents.ts
 */

export type AgentSource = "system" | "user" | "workspace";

export interface Agent {
  slug: string;
  name: string;
  description: string;
  is_default: boolean;
  source: AgentSource;
  role_definition?: string;
  when_to_use?: string;
  groups?: string[];
  custom_instructions?: string;
}

export interface AgentConfig {
  slug: string;
  mode: string;
  workspaceId?: string;
}

export interface AgentState {
  isActive: boolean;
  isPaused: boolean;
  agentMode: string;
  startTime: number | null;
  thinking: string;
  currentTask: string;
}

/** Degraded feature record (from agent_status/agent_start messages) */
export interface DegradedFeature {
  reason: string;
  impact: string;
  recoverable?: string;
}

/** Agent execution trace span */
export interface TraceSpan {
  span_id: string;
  parent_span_id?: string;
  span_name: string;
  phase?: string;
  start_time: string;
  end_time?: string;
  duration_ms?: number;
  status: "running" | "success" | "error";
  input_summary?: string;
  output_summary?: string;
}
