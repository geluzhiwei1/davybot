/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 类型安全的WebSocket消息系统
 *
 * 设计原则：
 * 1. 完整的TypeScript类型覆盖
 * 2. 编译时类型推导
 * 3. 运行时类型验证（仅在开发时）
 * 4. 零运行时开销（生产环境移除验证）
 */

import { z } from 'zod'



// ==================== 消息类型枚举 ====================

export enum MessageType {
  // 连接管理
  CONNECT = 'ws_connect',
  CONNECTED = 'ws_connected',
  DISCONNECT = 'ws_disconnect',
  HEARTBEAT = 'ws_heartbeat',

  // 基础消息
  USER_MESSAGE = 'user_message',
  ASSISTANT_MESSAGE = 'assistant_message',
  SYSTEM_MESSAGE = 'system_message',
  TOOL_MESSAGE = 'tool_message',

  // 任务管理
  TASK_START = 'task_start',
  TASK_PROGRESS = 'task_progress',
  TASK_COMPLETE = 'task_complete',
  TASK_ERROR = 'task_error',
  TASK_STATUS_UPDATE = 'task_status_update',
  TASK_GRAPH_UPDATE = 'task_graph_update',

  // 状态同步
  STATE_SYNC = 'state_sync',
  STATE_UPDATE = 'state_update',

  // 流式消息
  STREAM_REASONING = 'stream_reasoning',
  STREAM_CONTENT = 'stream_content',
  STREAM_TOOL_CALL = 'stream_tool_call',
  STREAM_USAGE = 'stream_usage',
  STREAM_COMPLETE = 'stream_complete',
  STREAM_ERROR = 'stream_error',

  // 工具调用
  TOOL_CALL_START = 'tool_call_start',
  TOOL_CALL_PROGRESS = 'tool_call_progress',
  TOOL_CALL_RESULT = 'tool_call_result',

  // 用户交互
  FOLLOWUP_QUESTION = 'followup_question',
  FOLLOWUP_RESPONSE = 'followup_response',

  // LLM API
  LLM_API_REQUEST = 'llm_api_request',
  LLM_API_RESPONSE = 'llm_api_response',
  LLM_API_COMPLETE = 'llm_api_complete',
  LLM_API_ERROR = 'llm_api_error',

  // Agent状态
  AGENT_START = 'agent_start',
  AGENT_MODE_SWITCH = 'agent_mode_switch',
  AGENT_THINKING = 'agent_thinking',
  AGENT_COMPLETE = 'agent_complete',
  AGENT_STOP = 'agent_stop',
  AGENT_STOPPED = 'agent_stopped',

  // 任务节点
  TASK_NODE_START = 'task_node_start',
  TASK_NODE_PROGRESS = 'task_node_progress',
  TASK_NODE_COMPLETE = 'task_node_complete',
  TASK_NODE_STOP = 'task_node_stop',
  TASK_NODE_STOPPED = 'task_node_stopped',

  // Todo system
  TODO_UPDATE = 'todo_update',
  TODO_CREATED = 'todo_created',
  TODO_UPDATED = 'todo_updated',
  TODO_DELETED = 'todo_deleted',
  TODO_BATCH_UPDATED = 'todo_batch_updated',

  // 错误处理
  ERROR = 'error',
  WARNING = 'warning',
}

// ==================== 基础消息结构 ====================

export interface BaseMessageStruct {
  id: string
  type: MessageType
  timestamp: string
  session_id: string
  user_message_id?: string
}

// ==================== 消息Payload类型 ====================

// 用户消息
export interface UserMessagePayload {
  content: string
  metadata?: Record<string, unknown>
  user_ui_context?: UserUIContext
}

// UI上下文
export interface UserUIContext {
  open_files?: string[]
  active_applications?: string[]
  user_preferences?: Record<string, unknown>
  current_file?: string | null
  current_selected_content?: string | null
  current_mode?: string | null
  current_llm_id?: string | null
  conversation_id?: string | null
}

// 助手消息
export interface AssistantMessagePayload {
  content: string
  task_id?: string
  metadata?: Record<string, unknown>
  tool_calls?: ToolCall[]
}

// 工具调用
export interface ToolCall {
  tool_call_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  status?: 'started' | 'in_progress' | 'completed' | 'failed'
  output?: unknown
  error?: string
}

// 流式内容消息
export interface StreamContentPayload {
  task_id: string
  message_id?: string
  content: string
  user_message_id?: string
}

// 流式推理消息
export interface StreamReasoningPayload {
  task_id: string
  message_id?: string
  content: string
  user_message_id?: string
}

// 流式完成消息
export interface StreamCompletePayload {
  task_id: string
  message_id?: string
  reasoning_content?: string
  content?: string
  tool_calls: ToolCall[]
  finish_reason?: string
  usage?: TokenUsage
  user_message_id?: string
  conversation_id?: string
}

// Token使用统计
export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

// 工具调用开始
export interface ToolCallStartPayload {
  task_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  tool_call_id?: string
}

// 工具调用进度
export interface ToolCallProgressPayload {
  task_id: string
  tool_name: string
  message: string
  progress_percentage?: number
  tool_call_id?: string
}

// 工具调用结果
export interface ToolCallResultPayload {
  task_id: string
  tool_name: string
  result: unknown
  is_error: boolean
  tool_call_id?: string
}

// 任务开始
export interface TaskStartPayload {
  task_id: string
  message: string
  metadata?: Record<string, unknown>
}

// 任务进度
export interface TaskProgressPayload {
  task_id: string
  progress: number
  status: 'planning' | 'executing' | 'completed' | 'error'
  message: string
  data?: unknown
}

// 追问问题
export interface FollowupQuestionPayload {
  task_id: string
  question: string
  suggestions: string[]
  tool_call_id: string
  user_message_id?: string
}

// Agent开始
export interface AgentStartPayload {
  task_id: string
  agent_mode: string
  user_message: string
  workspace_id: string
  metadata?: Record<string, unknown>
}

// Agent完成
export interface AgentCompletePayload {
  task_id: string
  result_summary: string
  total_duration_ms: number
  tasks_completed: number
  tools_used: string[]
  metadata?: Record<string, unknown>
}

// ==================== 任务节点相关 ====================

// 任务节点开始
export interface TaskNodeStartPayload {
  task_node_id: string
  parent_node_id?: string
  mode: string
  description: string
  todos?: unknown[]
  metadata?: Record<string, unknown>
}

// 任务节点进度
export interface TaskNodeProgressPayload {
  task_node_id: string
  progress: number
  total?: number
  message?: string
  data?: unknown
}

// 任务节点完成
export interface TaskNodeCompletePayload {
  task_node_id: string
  result?: unknown
  duration_ms?: number
  metadata?: Record<string, unknown>
}

// Todo update
export interface TodoUpdatePayload {
  task_node_id: string
  todos: Array<{
    id: string
    content: string
    status: string
    result?: string
    error?: string
  }>
}

// Todo created
export interface TodoCreatedPayload {
  todo_id: string
  task_node_id: string
  content: string
  priority?: string
  task_description?: string
}

// Todo updated details
export interface TodoUpdatedPayload {
  todo_id: string
  task_node_id: string
  status?: string
  content?: string
  priority?: string
}

// Todo deleted
export interface TodoDeletedPayload {
  todo_id: string
  task_node_id: string
}

// Batch todo update
export interface TodoBatchUpdatedPayload {
  task_node_id: string
  todo_ids: string[]
  operation: string
  status?: string
}

// 任务节点控制（前端→后端）
export interface TaskNodeControlPayload {
  task_node_id: string
  reason?: string
}

// 任务节点状态通知（后端→前端）
export interface TaskNodeStateChangePayload {
  task_node_id: string
  from_status: string
  to_status: string
  timestamp: string
  reason?: string
}

// ==================== 消息类型映射 ====================

export type MessagePayloadMap = {
  [MessageType.USER_MESSAGE]: UserMessagePayload
  [MessageType.ASSISTANT_MESSAGE]: AssistantMessagePayload
  [MessageType.STREAM_CONTENT]: StreamContentPayload
  [MessageType.STREAM_REASONING]: StreamReasoningPayload
  [MessageType.STREAM_COMPLETE]: StreamCompletePayload
  [MessageType.TOOL_CALL_START]: ToolCallStartPayload
  [MessageType.TOOL_CALL_PROGRESS]: ToolCallProgressPayload
  [MessageType.TOOL_CALL_RESULT]: ToolCallResultPayload
  [MessageType.TASK_START]: TaskStartPayload
  [MessageType.TASK_PROGRESS]: TaskProgressPayload
  [MessageType.TASK_COMPLETE]: { task_id: string; result?: unknown }
  [MessageType.TASK_ERROR]: { task_id: string; code: string; message: string; details?: unknown; recoverable: boolean }
  [MessageType.FOLLOWUP_QUESTION]: FollowupQuestionPayload
  [MessageType.FOLLOWUP_RESPONSE]: { task_id: string; tool_call_id: string; response: string }
  [MessageType.AGENT_START]: AgentStartPayload
  [MessageType.AGENT_COMPLETE]: AgentCompletePayload
  [MessageType.HEARTBEAT]: { message?: string }
  [MessageType.ERROR]: { error: string; details?: unknown }
  [MessageType.WARNING]: { code: string; message: string; details?: unknown }
  [MessageType.STATE_SYNC]: { data: Record<string, unknown> }
  [MessageType.STATE_UPDATE]: { data: Record<string, unknown>; path?: string }

  // PDCA 循环管理相关
  [MessageType.PDCA_CYCLE_START]: {
    cycle_id: string;
    domain: string;
    task_description: string;
    task_goals: string[];
    success_criteria: string[];
    start_time: string;
  }
  [MessageType.PDCA_STATUS_UPDATE]: {
    cycle_id: string;
    current_phase: 'plan' | 'do' | 'check' | 'act';
    phases: {
      plan: 'pending' | 'in_progress' | 'completed';
      do: 'pending' | 'in_progress' | 'completed';
      check: 'pending' | 'in_progress' | 'completed';
      act: 'pending' | 'in_progress' | 'completed';
    };
    completion: number;
    cycle_count: number;
    current_phase_description?: string;
    estimated_remaining_time?: number;
    timestamp?: string;
  }
  [MessageType.PDCA_PHASE_ADVANCE]: {
    cycle_id: string;
    from_phase: 'plan' | 'do' | 'check' | 'act';
    to_phase: 'plan' | 'do' | 'check' | 'act';
    reason: string;
    phase_data?: Record<string, unknown>;
    timestamp?: string;
  }
  [MessageType.PDCA_CYCLE_COMPLETE]: {
    cycle_id: string;
    domain: string;
    total_cycles: number;
    completion: number;
    result_summary: string;
    lessons_learned?: string;
    next_steps?: string[];
    start_time: string;
    end_time: string;
    duration_seconds?: number;
  }
  [MessageType.MODE_SWITCH]: {
    mode: 'orchestrator' | 'plan' | 'do' | 'check' | 'act' | 'build';
  }
  [MessageType.MODE_SWITCHED]: {
    previous_mode: string;
    current_mode: string;
    message: string;
  }

  // 任务节点相关
  [MessageType.TASK_NODE_START]: TaskNodeStartPayload
  [MessageType.TASK_NODE_PROGRESS]: TaskNodeProgressPayload
  [MessageType.TASK_NODE_COMPLETE]: TaskNodeCompletePayload
  [MessageType.TASK_NODE_PAUSE]: TaskNodeControlPayload
  [MessageType.TASK_NODE_RESUME]: TaskNodeControlPayload
  [MessageType.TASK_NODE_STOP]: TaskNodeControlPayload
  [MessageType.TASK_NODE_PAUSED]: TaskNodeStateChangePayload
  [MessageType.TASK_NODE_RESUMED]: TaskNodeStateChangePayload
  [MessageType.TASK_NODE_STOPPED]: TaskNodeStateChangePayload

  // Todo system related
  [MessageType.TODO_UPDATE]: TodoUpdatePayload
  [MessageType.TODO_CREATED]: TodoCreatedPayload
  [MessageType.TODO_UPDATED]: TodoUpdatedPayload
  [MessageType.TODO_DELETED]: TodoDeletedPayload
  [MessageType.TODO_BATCH_UPDATED]: TodoBatchUpdatedPayload
}

// 提取所有可能的Payload类型
export type AnyMessagePayload = MessagePayloadMap[keyof MessagePayloadMap]

// ==================== 完整消息类型 ====================

export type WebSocketMessage<T extends MessageType = MessageType> = BaseMessageStruct &
  (T extends keyof MessagePayloadMap
    ? { type: T } & MessagePayloadMap[T]
    : { type: T;[key: string]: unknown })

// ==================== 连接状态 ====================

export enum ConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
}

// ==================== 配置类型 ====================

export interface WebSocketConfig {
  url: string
  reconnectAttempts?: number
  reconnectDelay?: number
  heartbeatInterval?: number
  messageTimeout?: number
  connectionTimeout?: number
}

// ==================== 事件类型 ====================

export type WebSocketEventMap = {
  connect: void
  disconnect: { code: number; reason: string }
  message: WebSocketMessage
  error: Error
  stateChange: ConnectionState
}

export type WebSocketEvent = keyof WebSocketEventMap

// ==================== Zod验证Schema（仅在开发时使用）====================

const BaseMessageSchema = z.object({
  id: z.string(),
  type: z.nativeEnum(MessageType),
  timestamp: z.string(),
  session_id: z.string(),
  user_message_id: z.string().optional(),
})

export const UserMessageSchema = BaseMessageSchema.extend({
  type: z.literal(MessageType.USER_MESSAGE),
  content: z.string(),
  metadata: z.record(z.any()).optional(),
  user_ui_context: z.object({
    open_files: z.array(z.string()).optional(),
    active_applications: z.array(z.string()).optional(),
    user_preferences: z.record(z.any()).optional(),
    current_file: z.string().nullable().optional(),
    current_selected_content: z.string().nullable().optional(),
    current_mode: z.string().nullable().optional(),
    current_llm_id: z.string().nullable().optional(),
    conversation_id: z.string().nullable().optional(),
  }).optional(),
})

// ==================== 类型守卫 ====================

export function isWebSocketMessage(obj: unknown): obj is WebSocketMessage {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'type' in obj &&
    'timestamp' in obj &&
    'session_id' in obj &&
    Object.values(MessageType).includes((obj as unknown).type)
  )
}

export function isMessageType<T extends MessageType>(
  msg: WebSocketMessage,
  type: T
): msg is WebSocketMessage<T> {
  return msg.type === type
}

// ==================== 消息构建器类型 ====================

export type MessageBuilder<T extends MessageType> = (
  payload: MessagePayloadMap[T],
  sessionId?: string
) => WebSocketMessage<T>

// ==================== 消息处理器类型 ====================

export type MessageHandler<T extends MessageType> = (
  message: WebSocketMessage<T>
) => void | Promise<void>

// ==================== 订阅器类型 ====================

export type Unsubscribe = () => void

export type MessageSubscription<T extends MessageType> = {
  handler: MessageHandler<T>
  once?: boolean
}
