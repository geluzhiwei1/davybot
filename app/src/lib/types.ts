/**
 * Shared types for the legalbot backend integration.
 * WebSocket protocol types — ported from legacy Vue 3 webui to React 19.
 */

// ── WebSocket Message Types ──────────────────────────────────────────

export type WsMessageType =
  | "ws_connect"
  | "ws_connected"
  | "ws_disconnect"
  | "ws_heartbeat"
  | "user_message"
  | "assistant_message"
  | "system_message"
  | "conversation_info"
  | "stream_reasoning"
  | "stream_content"
  | "stream_tool_call"
  | "stream_complete"
  | "tool_call_start"
  | "tool_call_progress"
  | "tool_call_result"
  | "task_node_start"
  | "task_node_progress"
  | "task_node_complete"
  | "subtask_lifecycle"
  | "task_status_update"
  | "task_graph_update"
  | "todo_update"
  | "followup_question"
  | "followup_response"
  | "followup_cancel"
  | "llm_api_request"
  | "llm_api_response"
  | "llm_api_complete"
  | "llm_api_error"
  | "agent_start"
  | "agent_mode_switch"
  | "agent_thinking"
  | "agent_complete"
  | "agent_pause"
  | "agent_resume"
  | "agent_stop"
  | "agent_stopped"
  | "agent_status_update"
  | "firm_agent_status"
  | "agent_span"
  | "inter_agent_message"
  | "a2ui_server_event"
  | "a2ui_user_action"
  | "reset_conversation"
  | "error"
  | "warning"
  | "tool_approval_request"
  | "tool_approval_response";

export interface WsMessage {
  type: WsMessageType;
  session_id?: string;
  workspace_id?: string;
  conversation_id?: string;
  task_id?: string;
  message_id?: string;
  content?: string;
  data?: Record<string, unknown>;
  timestamp?: number;
  /** Agent span for execution tracing */
  span_id?: string;
  parent_span_id?: string;
  span_name?: string;
  phase?: string;
  start_time?: string;
  end_time?: string;
  duration_ms?: number;
  status?: string;
  input_summary?: string;
  output_summary?: string;
  /** Agent degraded features */
  degraded_features?: Record<string, { reason: string; impact: string; recoverable?: string }>;
  /** Tracing */
  trace_id?: string;
  /** Memory system state */
  memory_ready?: boolean;
  /** Agent mode from agent_start message (orchestrator/pdca) */
  agent_mode?: string;
  /** Per-workspace user UI context (sent with user_message, received in workspace detail) */
  user_ui_context?: Record<string, unknown>;
  /** P2.2 tool approval (human-in-the-loop) */
  request_id?: string;
  tool_name?: string;
  risk?: string;
  tool_input?: Record<string, unknown>;
  timeout_seconds?: number;
  approved?: boolean;
  /** Follow-up question (ask_followup_question, human-in-the-loop) */
  tool_call_id?: string;
  question?: string;
  suggestions?: string[];
  reason?: "user_cancelled" | "timeout" | "skipped";
  response?: string;
}

// ── Result Governance ───────────────────────────────────────────────

export interface GovernanceMeta {
  was_truncated: boolean;
  original_size: number;
  governed_size: number;
  format_type: string; // blob | list | structured | echo | compact
  snapshot_id?: string;
}

// ── Content Block System (mirrors legalbot/webui types/websocket.ts) ──

export type ContentType =
  | "text"
  | "image"
  | "audio"
  | "video"
  | "file"
  | "thinking"
  | "reasoning"
  | "tool_call"
  | "tool_result"
  | "tool_execution"
  | "error"
  | "simple_text"
  | "system_command_result"
  | "a2ui_surface";

export type ToolExecutionStatus =
  "started" | "validating" | "executing" | "completed" | "failed" | "timeout";

// ── Content Block Interfaces ────────────────────────────────────────

export interface TextContentBlock {
  type: "text";
  text: string;
}

export interface ImageContentBlock {
  type: "image";
  image: string;
  detail?: "low" | "high" | "auto";
  filename?: string;
}

export interface AudioContentBlock {
  type: "audio";
  audio: string;
  format?: string;
  filename?: string;
}

export interface VideoContentBlock {
  type: "video";
  video: string;
  format?: string;
  filename?: string;
}

export interface FileContentBlock {
  type: "file";
  file: string;
  filename?: string;
  mime_type?: string;
}

export interface ThinkingStep {
  step_id: string;
  thought: string;
  status: "in_progress" | "completed" | "failed";
  details?: unknown;
}

export interface ThinkingContentBlock {
  type: "thinking";
  steps: ThinkingStep[];
}

export interface ReasoningContentBlock {
  type: "reasoning";
  reasoning: string;
}

export interface ToolCallInfo {
  tool_call_id: string;
  tool_name: string;
  tool_input: unknown;
  status: "started" | "in_progress" | "completed" | "failed";
  output?: unknown;
  error?: string;
  progress_percentage?: number;
  current_step?: string;
  total_steps?: number;
  current_step_index?: number;
  execution_time?: number;
  estimated_remaining_time?: number;
  extra_data?: Record<string, unknown>;
}

export interface ToolCallContentBlock {
  type: "tool_call";
  toolCall: ToolCallInfo;
}

export interface ToolResultContentBlock {
  type: "tool_result";
  toolName: string;
  result: unknown;
  isError: boolean;
  executionTime?: number;
  errorCode?: string;
  errorMessage?: string;
  /** Result governance metadata (truncation, snapshot, etc.) */
  governance?: GovernanceMeta;
}

export interface ToolProgressEntry {
  timestamp: string;
  message?: string;
  progress_percentage?: number;
  step?: string;
}

export interface ToolExecutionContentBlock {
  type: "tool_execution";
  toolCallId: string;
  toolName: string;
  toolInput?: unknown;
  status: ToolExecutionStatus;
  startTime: string;
  endTime?: string;
  executionTime?: number;
  progressPercentage?: number;
  currentStep?: string;
  totalSteps?: number;
  currentStepIndex?: number;
  streamOutput?: string[];
  result?: unknown;
  isError?: boolean;
  errorCode?: string;
  errorMessage?: string;
  /** Result governance metadata (truncation, snapshot, etc.) */
  governance?: GovernanceMeta;
}

/** UI-B 子任务卡片块（new_task/run_task 工具结果派生，§6.3） */
export interface SubtaskCardContentBlock {
  type: "subtask_card";
  subtaskId: string;
  toolName: "new_task" | "run_task";
  agent: string | null;
  conversationId: string | null;
  mode: string | null;
  /** 任务描述（结果 message 或 tool_input.message） */
  message: string | null;
  /** 结果携带的初始状态；实时状态由渲染端经 subtask-store 联动 */
  initialStatus: string | null;
  isError: boolean;
  executionTime?: number;
}

export type ErrorCategory = "auth" | "credits" | "rate_limit" | "server" | "network" | "unknown";

export interface ErrorContentBlock {
  type: "error";
  message: string;
  category?: ErrorCategory;
  details?: unknown;
}

export interface SimpleTextContentBlock {
  type: "simple_text";
  text: string;
  /**
   * Optional semantic kind — used by display-mode filters to decide visibility
   * without depending on text content. Known values:
   *   - "history-tool-marker": synthesised in loadHistory() to surface intermediate
   *     tool-call rounds in default/detailed modes; hidden in minimal mode.
   *   - "interrupted": fallback text appended when the stream is interrupted
   *     or times out (see chat-store.ts stream_complete / interruptAllStreams).
   *   - "attempt_completion": the visible body of an attempt_completion tool
   *     result, emitted from tool_call_result handler.
   * Undefined = legacy / unspecified; treated as a regular simple_text line.
   */
  kind?: "history-tool-marker" | "interrupted" | "attempt_completion";
}

export interface SystemCommandResultContentBlock {
  type: "system_command_result";
  command: string;
  stdout?: string;
  stderr?: string;
  exitCode: number;
  executionTime?: number;
  cwd?: string;
}

export type ContentBlock =
  | TextContentBlock
  | ImageContentBlock
  | AudioContentBlock
  | VideoContentBlock
  | FileContentBlock
  | ThinkingContentBlock
  | ReasoningContentBlock
  | ToolCallContentBlock
  | ToolResultContentBlock
  | ToolExecutionContentBlock
  | SubtaskCardContentBlock
  | ErrorContentBlock
  | SimpleTextContentBlock
  | SystemCommandResultContentBlock;

// ── Chat Message ────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  /** Plain text content (legacy, used by user messages & mock) */
  content: string;
  /** Structured content blocks (used by assistant messages from backend) */
  blocks?: ContentBlock[];
  /** Reasoning text (streamed separately from main content) */
  reasoning?: string;
  agentId?: string;
  agentName?: string;
  toolCallId?: string;
  toolName?: string;
  toolResult?: string;
  status: "pending" | "streaming" | "complete" | "error";
  ts: number;
  /** LLM message_id for stream correlation */
  messageId?: string;
  /** Task node ID this message belongs to */
  taskNodeId?: string;
}

// ── Conversation ────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  workspaceId: string;
  title: string;
  messages: ChatMessage[];
  model?: string;
  expertId?: string;
  mode: "single" | "team";
  createdAt: number;
  updatedAt: number;
}

// ── Workspace (backend) ─────────────────────────────────────────────

export interface BackendWorkspace {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

// ── Connection State ────────────────────────────────────────────────

export type ConnectionState =
  "disconnected" | "connecting" | "connected" | "reconnecting" | "error";

// ── Stream Buffer ───────────────────────────────────────────────────

export interface StreamBuffer {
  messageId: string;
  content: string;
  reasoning: string;
  toolCalls: ToolCallBuffer[];
  lastUpdate: number;
}

export interface ToolCallBuffer {
  id: string;
  name: string;
  arguments: string;
  result?: string;
  status: "pending" | "running" | "complete" | "error";
}

// ── LLM Provider ────────────────────────────────────────────────────

export interface LLMProvider {
  id: string;
  name: string;
  type: string;
  models: LLMModel[];
  enabled: boolean;
  apiKeyConfigured: boolean;
}

export interface LLMModel {
  id: string;
  name: string;
  provider: string;
  enabled: boolean;
}

// ── MCP Server ──────────────────────────────────────────────────────

export interface MCPServer {
  id: string;
  name: string;
  transport: "stdio" | "sse" | "streamable-http";
  command?: string;
  url?: string;
  enabled: boolean;
  status: "connected" | "disconnected" | "error";
  tools?: MCPTool[];
}

export interface MCPTool {
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
}

// ── Skill ───────────────────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  installed: boolean;
  version?: string;
}

// ── Agent ───────────────────────────────────────────────────────────

export interface AgentStatus {
  mode: "idle" | "thinking" | "executing" | "waiting_input" | "error";
  thinking?: string;
  currentTask?: string;
}

// ── API Response ────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}
