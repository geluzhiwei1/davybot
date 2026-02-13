/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 工具执行状态枚举
export enum ToolExecutionStatus {
  STARTED = 'started',
  VALIDATING = 'validating',
  EXECUTING = 'executing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  TIMEOUT = 'timeout'
}

// WebSocket消息类型枚举
export enum MessageType {
  // 连接管理
  CONNECT = 'ws_connect',
  CONNECTED = 'ws_connected',
  DISCONNECT = 'ws_disconnect',
  HEARTBEAT = 'ws_heartbeat',

  // 基础消息通信
  USER_MESSAGE = 'user_message',
  ASSISTANT_MESSAGE = 'assistant_message',
  SYSTEM_MESSAGE = 'system_message',

  // 任务节点管理
  TASK_NODE_START = 'task_node_start',
  TASK_NODE_PROGRESS = 'task_node_progress',
  TASK_NODE_COMPLETE = 'task_node_complete',
  TASK_STATUS_UPDATE = 'task_status_update',
  TASK_GRAPH_UPDATE = 'task_graph_update',
  TODO_UPDATE = 'todo_update',

  // 流式消息
  STREAM_REASONING = 'stream_reasoning',
  STREAM_CONTENT = 'stream_content',
  STREAM_TOOL_CALL = 'stream_tool_call',
  STREAM_COMPLETE = 'stream_complete',

  // 工具调用
  TOOL_CALL_START = 'tool_call_start',
  TOOL_CALL_PROGRESS = 'tool_call_progress',
  TOOL_CALL_RESULT = 'tool_call_result',

  // 用户交互
  FOLLOWUP_QUESTION = 'followup_question',
  FOLLOWUP_RESPONSE = 'followup_response',

  // LLM API 可观测性
  LLM_API_REQUEST = 'llm_api_request',
  LLM_API_RESPONSE = 'llm_api_response',
  LLM_API_COMPLETE = 'llm_api_complete',
  LLM_API_ERROR = 'llm_api_error',

  // Agent 状态
  AGENT_START = 'agent_start',
  AGENT_MODE_SWITCH = 'agent_mode_switch',
  AGENT_THINKING = 'agent_thinking',
  AGENT_COMPLETE = 'agent_complete',
  AGENT_PAUSE = 'agent_pause',
  AGENT_RESUME = 'agent_resume',
  AGENT_STOP = 'agent_stop',

  // Agent 模式控制
  MODE_SWITCH = 'mode_switch',
  MODE_SWITCHED = 'mode_switched',

  // 上下文管理
  CONTEXT_UPDATE = 'context_update',

  // PDCA 循环管理
  PDCA_CYCLE_START = 'pdca_cycle_start',
  PDCA_STATUS_UPDATE = 'pdca_status_update',
  PDCA_CYCLE_COMPLETE = 'pdca_cycle_complete',
  PDCA_PHASE_ADVANCE = 'pdca_phase_advance',

  // 状态同步
  STATE_SYNC = 'state_sync',
  STATE_UPDATE = 'state_update',

  // 错误处理
  ERROR = 'error',
  WARNING = 'warning',

  // A2UI 消息
  A2UI_SERVER_EVENT = 'a2ui_server_event',
  A2UI_USER_ACTION = 'a2ui_user_action',
}

// 基础消息接口
export interface BaseMessage {
  id: string;
  type: MessageType;
  timestamp: string;
  session_id: string;
  task_node_id?: string;  // 任务节点ID，表示是哪个task node发送出的消息（可选）
}

// 心跳消息
export interface HeartbeatMessage extends BaseMessage {
  type: MessageType.HEARTBEAT;
}

// 用户消息
export interface UserMessage extends BaseMessage {
  type: MessageType.USER_MESSAGE;
  content: string;
  metadata?: {
    workspaceId?: string;
    conversationId?: string;
    files?: unknown[];
    mentions?: unknown[];
  };
  // 用户UI上下文信息
  user_ui_context?: {
    open_files?: string[];
    active_applications?: string[];
    user_preferences?: Record<string, unknown>;
    current_file?: string;
    current_selected_content?: string;
    current_mode?: string;
    current_llm_id?: string;
  };
}

// 助手消息
export interface AssistantMessage extends BaseMessage {
  type: MessageType.ASSISTANT_MESSAGE;
  content: string;
  task_id?: string;
  metadata?: {
    thinking?: unknown[];
    toolCalls?: unknown[];
  };
}

// 工具调用
export interface ToolCall {
  tool_call_id: string;
  tool_name: string;
  tool_input: unknown;
  status: 'started' | 'in_progress' | 'completed' | 'failed';
  output?: unknown;
  error?: string;
  // 工具执行进度信息
  progress_percentage?: number;
  current_step?: string;
  total_steps?: number;
  current_step_index?: number;
  execution_time?: number;
  estimated_remaining_time?: number;
  extra_data?: Record<string, unknown>;
  progress_history?: ToolCallProgressHistory[];
  performance_metrics?: Record<string, unknown>;
}

// 工具调用进度历史记录
export interface ToolCallProgressHistory {
  timestamp: string;
  message: string;
  progress_percentage?: number;
  step?: string;
}

// 工具调用开始消息
export interface ToolCallStartMessage extends BaseMessage {
  type: MessageType.TOOL_CALL_START;
  task_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_call_id?: string;
  workspace_id?: string;  // 工作区ID
  tool_call?: Omit<ToolCall, 'status' | 'output' | 'error'> & { status: 'started' };
}

// 工具调用进度消息
export interface ToolCallProgressMessage extends BaseMessage {
  type: MessageType.TOOL_CALL_PROGRESS;
  task_id: string;
  tool_name: string;
  message: string;
  progress_percentage?: number;
  tool_call_id?: string;
  status?: ToolExecutionStatus;
  current_step?: string;
  total_steps?: number;
  current_step_index?: number;
  estimated_remaining_time?: number;
  stream_output?: string;  // 流式输出内容（实时显示）
  workspace_id?: string;  // 工作区ID
}

// 工具调用结果消息
export interface ToolCallResultMessage extends BaseMessage {
  type: MessageType.TOOL_CALL_RESULT;
  task_id: string;
  tool_name: string;
  result: unknown;
  is_error: boolean;
  tool_call_id?: string;
  error_message?: string;
  error_code?: string;
  execution_time?: number;
  performance_metrics?: Record<string, unknown>;  // 性能指标
  workspace_id?: string;  // 工作区ID
}

// 流式推理消息
export interface StreamReasoningMessage extends BaseMessage {
  type: MessageType.STREAM_REASONING;
  task_id: string;
  task_node_id?: string;  // 任务节点ID
  message_id?: string;  // 消息ID，用于标识单个消息气泡
  content: string;
  user_message_id?: string;
}

// 流式内容消息
export interface StreamContentMessage extends BaseMessage {
  type: MessageType.STREAM_CONTENT;
  task_id: string;
  task_node_id?: string;  // 任务节点ID
  message_id?: string;  // 消息ID，用于标识单个消息气泡
  content: string;
  user_message_id?: string;
  workspace_id?: string;  // 工作区ID
}

// 流式工具调用消息
export interface StreamToolCallMessage extends BaseMessage {
  type: MessageType.STREAM_TOOL_CALL;
  task_id: string;
  task_node_id?: string;  // 任务节点ID
  tool_call: ToolCall;
  all_tool_calls: ToolCall[];
  user_message_id?: string;
}

// 流式完成消息
export interface StreamCompleteMessage extends BaseMessage {
  type: MessageType.STREAM_COMPLETE;
  task_id: string;
  task_node_id?: string;  // 任务节点ID
  message_id?: string;  // 消息ID，用于标识单个消息气泡
  reasoning_content?: string;
  content?: string;
  tool_calls: ToolCall[];
  finish_reason?: string;
  usage?: unknown;
  user_message_id?: string;
  conversation_id?: string; // 后端创建的新会话ID
}

// 错误消息
export interface ErrorMessage extends BaseMessage {
  type: MessageType.ERROR;
  code: string;
  message: string;
  details?: Record<string, unknown>;
  recoverable?: boolean;
  workspace_id?: string;  // 工作区ID
  task_id?: string;  // 任务ID
  user_message_id?: string;  // 用户消息ID
}

// WebSocket消息联合类型（优化后）
export type WebSocketMessage =
  // 基础消息通信
  | BaseMessage
  | HeartbeatMessage
  | UserMessage
  | AssistantMessage
  // 任务节点管理
  | TaskNodeStartMessage
  | TaskNodeProgressMessage
  | TaskNodeCompleteMessage
  | TaskStatusUpdateMessage
  | TaskGraphUpdateMessage
  | TodoUpdateMessage
  // 流式消息
  | StreamReasoningMessage
  | StreamContentMessage
  | StreamToolCallMessage
  | StreamCompleteMessage
  // 工具调用生命周期
  | ToolCallStartMessage
  | ToolCallProgressMessage
  | ToolCallResultMessage
  // 用户交互
  | FollowupQuestionMessage
  | FollowupResponseMessage
  // LLM API 可观测性
  | LLMApiRequestMessage
  | LLMApiResponseMessage
  | LLMApiCompleteMessage
  | LLMApiErrorMessage
  // Agent 状态可观测性
  | AgentStartMessage
  | AgentModeSwitchMessage
  | AgentThinkingMessage
  | AgentCompleteMessage
  // Agent 控制消息
  | AgentStopMessage
  // A2UI 消息
  | A2UIServerEventMessage
  | A2UIUserActionMessage
  | AgentStoppedMessage
  // Agent 模式控制
  | ModeSwitchMessage
  | ModeSwitchedMessage
  // 上下文管理
  | ContextUpdateMessage
  // PDCA 循环管理
  | PDACycleStartMessage
  | PDCAStatusUpdateMessage
  | PDCAPhaseAdvanceMessage
  | PDACycleCompleteMessage
  // 错误处理
  | ErrorMessage;

// WebSocket连接状态
export enum ConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error'
}

// 错误类型
export enum ErrorType {
  CONNECTION_ERROR = 'connection_error',
  MESSAGE_ERROR = 'message_error',
  VALIDATION_ERROR = 'validation_error',
  TIMEOUT_ERROR = 'timeout_error',
  NETWORK_ERROR = 'network_error'
}

// 错误严重程度
export enum ErrorSeverity {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical'
}

// 错误信息
export interface ErrorInfo {
  type: ErrorType;
  severity: ErrorSeverity;
  message: string;
  details?: unknown;
  timestamp: string;
  recoverable: boolean;
  retryCount?: number;
}

// WebSocket配置
export interface WebSocketConfig {
  url: string;
  reconnectAttempts: number;
  reconnectDelay: number;
  heartbeatInterval: number;
  messageTimeout: number;
  connectionTimeout?: number;
}

// 兼容性类型定义（保持向后兼容）
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error' | 'initial';

// ==================== 任务状态更新消息 ====================

// 任务状态更新消息
export interface TaskStatusUpdateMessage extends BaseMessage {
  type: MessageType.TASK_STATUS_UPDATE;
  task_id: string;
  graph_id: string;
  old_status: string;
  new_status: string;
  timestamp: string;
}

// 任务图更新消息
export interface TaskGraphUpdateMessage extends BaseMessage {
  type: MessageType.TASK_GRAPH_UPDATE;
  graph_id: string;
  update_type: 'task_added' | 'task_removed' | 'status_changed' | 'hierarchy_changed';
  data: {
    task_id?: string;
    task_info?: unknown;
    hierarchy?: unknown;
    statistics?: {
      total_tasks: number;
      status_counts: {
        pending: number;
        running: number;
        completed: number;
        failed: number;
        paused: number;
        aborted: number;
      };
    };
  };
  timestamp: string;
}

// ==================== 追问问题消息 ====================

// 追问问题消息（后端→前端）
export interface FollowupQuestionMessage extends BaseMessage {
  type: MessageType.FOLLOWUP_QUESTION;
  task_id: string;
  question: string;
  suggestions: string[];
  tool_call_id: string;
  user_message_id?: string;
}

// 追问回复消息（前端→后端）
export interface FollowupResponseMessage extends BaseMessage {
  type: MessageType.FOLLOWUP_RESPONSE;
  task_id: string;
  tool_call_id: string;
  response: string;
  user_message_id?: string;
}

// ==================== LLM API 交互状态消息 ====================

// LLM API 请求开始消息
export interface LLMApiRequestMessage extends BaseMessage {
  type: MessageType.LLM_API_REQUEST;
  task_id: string;
  provider: string;
  model: string;
  request_type?: string;
  input_tokens?: number;
  metadata?: Record<string, unknown>;
}

// LLM API 响应消息（流式）
export interface LLMApiResponseMessage extends BaseMessage {
  type: MessageType.LLM_API_RESPONSE;
  task_id: string;
  response_type: 'reasoning' | 'content' | 'tool_call' | 'usage';
  content?: string;
  data?: unknown;
  is_streaming: boolean;
}

// LLM API 调用完成消息
export interface LLMApiCompleteMessage extends BaseMessage {
  type: MessageType.LLM_API_COMPLETE;
  task_id: string;
  provider: string;
  model: string;
  finish_reason?: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  duration_ms?: number;
}

// LLM API 调用错误消息
export interface LLMApiErrorMessage extends BaseMessage {
  type: MessageType.LLM_API_ERROR;
  task_id: string;
  provider: string;
  model: string;
  error_code: string;
  error_message: string;
  is_retryable: boolean;
  details?: unknown;
}

// Agent 状态消息接口
export interface AgentStartMessage extends BaseMessage {
  type: MessageType.AGENT_START;
  task_id: string;
  agent_mode: string;  // architect, code, ask, debug, plan
  user_message: string;
  workspace_id: string;
  metadata?: {
    model?: string;
    temperature?: number;
    [key: string]: unknown;
  };
}

export interface AgentModeSwitchMessage extends BaseMessage {
  type: MessageType.AGENT_MODE_SWITCH;
  task_id: string;
  old_mode: string;
  new_mode: string;
  reason: string;
  metadata?: unknown;
}

export interface AgentThinkingMessage extends BaseMessage {
  type: MessageType.AGENT_THINKING;
  task_id: string;
  thinking_content: string;
  step_id?: string;
  is_complete: boolean;
  metadata?: unknown;
}

export interface AgentCompleteMessage extends BaseMessage {
  type: MessageType.AGENT_COMPLETE;
  task_id: string;
  result_summary: string;
  total_duration_ms: number;
  tasks_completed: number;
  tools_used: string[];
  metadata?: unknown;
}

// Agent 控制消息（前端 -> 后端）
export interface AgentStopMessage extends BaseMessage {
  type: MessageType.AGENT_STOP;
  task_id: string;
  reason?: string;
  force?: boolean;
  timestamp: string;
}

// Agent 状态通知（后端 -> 前端）
export interface AgentStoppedMessage extends BaseMessage {
  type: MessageType.AGENT_STOP;
  task_id: string;
  stopped_at: string;
  result_summary: string;
  partial?: boolean;
  metadata?: unknown;
}

// A2UI Server Event Message (Server → Client)
export interface A2UIServerEventMessage extends BaseMessage {
  type: MessageType.A2UI_SERVER_EVENT;
  messages: Array<{
    beginRendering?: {
      surfaceId: string;
      root: string;
      styles?: Record<string, string>;
    };
    surfaceUpdate?: {
      surfaceId: string;
      components: Array<{
        id: string;
        weight?: number;
        component?: unknown;
      }>;
    };
    dataModelUpdate?: {
      surfaceId: string;
      path?: string;
      contents: Array<unknown>;
    };
    deleteSurface?: {
      surfaceId: string;
    };
  }>;
}

// A2UI User Action Message (Client → Server)
export interface A2UIUserActionMessage extends BaseMessage {
  type: MessageType.A2UI_USER_ACTION;
  surfaceId: string;
  componentId: string;
  actionName: string;
  context?: Record<string, unknown>;
}

export interface TaskNodeStartMessage extends BaseMessage {
  type: MessageType.TASK_NODE_START;
  task_id: string;
  task_node_id: string;
  node_type: string;
  description: string;
  metadata?: unknown;
}

export interface TaskNodeProgressMessage extends BaseMessage {
  type: MessageType.TASK_NODE_PROGRESS;
  task_id: string;
  task_node_id: string;
  progress: number;  // 0-100
  status: string;
  message: string;
  data?: unknown;
}

export interface TaskNodeCompleteMessage extends BaseMessage {
  type: MessageType.TASK_NODE_COMPLETE;
  task_id: string;
  task_node_id: string;
  result?: unknown;
  duration_ms: number;
  metadata?: unknown;
}

export interface TodoUpdateMessage extends BaseMessage {
  type: MessageType.TODO_UPDATE;
  task_node_id: string;
  todos: Array<{
    id: string;
    content: string;
    status: string;
    result?: string;
    error?: string;
    created_at: string;
    updated_at: string;
    completed_at?: string;
  }>;
  metadata?: unknown;
}

// ==================== 聊天相关类型 ====================

/**
 * 消息角色枚举
 */
export enum MessageRole {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system',
  TOOL = 'tool'
}

/**
 * 内容类型枚举
 */
export enum ContentType {
  TEXT = 'text',
  IMAGE = 'image',
  AUDIO = 'audio',
  VIDEO = 'video',
  FILE = 'file',
  THINKING = 'thinking',
  REASONING = 'reasoning',
  TOOL_CALL = 'tool_call',
  TOOL_RESULT = 'tool_result',
  TOOL_EXECUTION = 'tool_execution',  // 聚合工具执行生命周期（start + progress + result）
  ERROR = 'error',
  SIMPLE_TEXT = 'simple_text',  // 简单纯文本，无气泡装饰
  SYSTEM_COMMAND_RESULT = 'system_command_result',  // 系统命令执行结果 (!ls, !pwd等)
  A2UI_SURFACE = 'a2ui_surface'  // A2UI 声明式 UI 组件
}

/**
 * 任务状态枚举
 */
export enum TaskStatus {
  PLANNING = 'planning',
  EXECUTING = 'executing',
  COMPLETED = 'completed',
  ERROR = 'error'
}

/**
 * 基础内容块接口
 */
export interface BaseContentBlock {
  type: ContentType;
}

/**
 * 文本内容块
 */
export interface TextContentBlock extends BaseContentBlock {
  type: ContentType.TEXT;
  text: string;
}

/**
 * 图片内容块
 */
export interface ImageContentBlock extends BaseContentBlock {
  type: ContentType.IMAGE;
  image: string;
  detail?: 'low' | 'high' | 'auto';
  filename?: string;
}

/**
 * 音频内容块
 */
export interface AudioContentBlock extends BaseContentBlock {
  type: ContentType.AUDIO;
  audio: string;
  format?: string;
  filename?: string;
}

/**
 * 视频内容块
 */
export interface VideoContentBlock extends BaseContentBlock {
  type: ContentType.VIDEO;
  video: string;
  format?: string;
  filename?: string;
}

/**
 * 文件内容块
 */
export interface FileContentBlock extends BaseContentBlock {
  type: ContentType.FILE;
  file: string;
  filename?: string;
  mime_type?: string;
}

/**
 * 思考过程内容块
 */
export interface ThinkingContentBlock extends BaseContentBlock {
  type: ContentType.THINKING;
  steps: ThinkingStep[];
}

/**
 * 推理内容块
 */
export interface ReasoningContentBlock extends BaseContentBlock {
  type: ContentType.REASONING;
  reasoning: string;
}

/**
 * 工具调用内容块
 */
export interface ToolCallContentBlock extends BaseContentBlock {
  type: ContentType.TOOL_CALL;
  toolCall: ToolCall;
}

/**
 * 工具结果内容块
 */
export interface ToolResultContentBlock extends BaseContentBlock {
  type: ContentType.TOOL_RESULT;
  toolName: string;
  result: unknown;
  isError: boolean;
  executionTime?: number;
  errorCode?: string;
  errorMessage?: string;
}

/**
 * 工具执行内容块 - 聚合整个工具执行生命周期
 */
export interface ToolExecutionContentBlock extends BaseContentBlock {
  type: ContentType.TOOL_EXECUTION;
  toolCallId: string;
  toolName: string;
  toolInput?: unknown;
  status: ToolExecutionStatus;
  startTime: string;
  endTime?: string;
  executionTime?: number;

  // 进度信息
  progressPercentage?: number;
  currentStep?: string;
  totalSteps?: number;
  currentStepIndex?: number;
  estimatedRemainingTime?: number;
  progressHistory?: ToolProgressEntry[];

  // 流式输出内容（实时显示）
  streamOutput?: string[];

  // 结果信息
  result?: unknown;
  isError?: boolean;
  errorCode?: string;
  errorMessage?: string;
  performanceMetrics?: Record<string, unknown>;
}

/**
 * 工具进度条目
 */
export interface ToolProgressEntry {
  timestamp: string;
  message?: string;
  progress_percentage?: number;
  step?: string;
}

/**
 * 错误内容块
 */
export interface ErrorContentBlock extends BaseContentBlock {
  type: ContentType.ERROR;
  message: string;
  details?: unknown;
}

/**
 * 简单文本内容块（无markdown渲染，无气泡装饰）
 */
export interface SimpleTextContentBlock extends BaseContentBlock {
  type: ContentType.SIMPLE_TEXT;
  text: string;
}

/**
 * 系统命令结果内容块（!ls, !pwd等）
 */
export interface SystemCommandResultContentBlock extends BaseContentBlock {
  type: ContentType.SYSTEM_COMMAND_RESULT;
  command: string;  // 执行的命令，如 "ls -la"
  stdout?: string;  // 标准输出
  stderr?: string;  // 错误输出
  exitCode: number;  // 退出码
  executionTime?: number;  // 执行时间（毫秒）
  cwd?: string;  // 当前工作目录
}

/**
 * A2UI 声明式 UI 组件内容块
 */
export interface A2UISurfaceContentBlock extends BaseContentBlock {
  type: ContentType.A2UI_SURFACE;
  surfaceId: string;  // UI 表面唯一ID
  surfaceType: 'form' | 'dashboard' | 'visualization' | 'custom';
  components: unknown[];  // A2UI 组件列表（扁平邻接表模型）
  dataModel: Record<string, unknown>;  // 应用状态数据
  metadata?: {
    title?: string;
    description?: string;
    interactive?: boolean;
    layout?: 'vertical' | 'horizontal' | 'grid';
  };
}

/**
 * 思考步骤
 */
export interface ThinkingStep {
  step_id: string;
  thought: string;
  status: 'in_progress' | 'completed' | 'failed';
  details?: unknown;
}

/**
 * 内容块的联合类型
 */
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
  | SimpleTextContentBlock
  | ErrorContentBlock
  | SystemCommandResultContentBlock
  | A2UISurfaceContentBlock;

/**
 * 聊天消息的统一接口
 * 一条消息可以由多个不同类型的内容块组成
 */
export interface ChatMessage {
  id: string;
  role: MessageRole | 'user' | 'assistant' | 'system' | 'tool';
  timestamp: string;
  content: ContentBlock[];
  taskId?: string;
  sessionId?: string;  // Session ID for workspace routing
  messageId?: string;  // ✅ 新增：LLM message_id，用于标识单个消息气泡
  metadata?: Record<string, unknown>;
}

/**
 * Agent 模式切换消息（前端→后端）
 */
export interface ModeSwitchMessage extends BaseMessage {
  type: MessageType.MODE_SWITCH;
  mode: 'plan' | 'build';  // 目标模式
}

/**
 * Agent 模式切换完成消息（后端→前端）
 */
export interface ModeSwitchedMessage extends BaseMessage {
  type: MessageType.MODE_SWITCHED;
  previous_mode: 'plan' | 'build';
  current_mode: 'plan' | 'build';
  message: string;
}

/**
 * 上下文使用更新消息（后端→前端）
 */
export interface ContextUpdateMessage extends BaseMessage {
  type: MessageType.CONTEXT_UPDATE;
  stats: {
    total: number;
    used: number;
    percentage: number;
    breakdown: {
      system_prompt: number;
      conversation: number;
      workspace_files: number;
      tool_definitions: number;
      files: Array<{
        path: string;
        tokens: number;
        percentage: number;
        last_updated: number;
        char_count: number;
      }>;
    };
    remaining: number;
  };
  warnings: string[];
}

/**
 * PDCA 循环开始消息（后端→前端）
 */
export interface PDACycleStartMessage extends BaseMessage {
  type: MessageType.PDCA_CYCLE_START;
  cycle_id: string;
  domain: string;
  task_description: string;
  task_goals: string[];
  success_criteria: string[];
  start_time: string;
}

/**
 * PDCA 状态更新消息（后端→前端）
 */
export interface PDCAStatusUpdateMessage extends BaseMessage {
  type: MessageType.PDCA_STATUS_UPDATE;
  cycle_id: string;
  current_phase: 'plan' | 'do' | 'check' | 'act';
  phases: {
    plan: 'pending' | 'in_progress' | 'completed';
    do: 'pending' | 'in_progress' | 'completed';
    check: 'pending' | 'in_progress' | 'completed';
    act: 'pending' | 'in_progress' | 'completed';
  };
  completion: number; // 0-100
  cycle_count: number;
  current_phase_description?: string;
  estimated_remaining_time?: number;
  timestamp?: string;
}

/**
 * PDCA 阶段推进消息（后端→前端）
 */
export interface PDCAPhaseAdvanceMessage extends BaseMessage {
  type: MessageType.PDCA_PHASE_ADVANCE;
  cycle_id: string;
  from_phase: 'plan' | 'do' | 'check' | 'act';
  to_phase: 'plan' | 'do' | 'check' | 'act';
  reason: string;
  phase_data?: Record<string, unknown>;
  timestamp?: string;
}

/**
 * PDCA 循环完成消息（后端→前端）
 */
export interface PDACycleCompleteMessage extends BaseMessage {
  type: MessageType.PDCA_CYCLE_COMPLETE;
  cycle_id: string;
  domain: string;
  total_cycles: number;
  completion: number; // 0-100
  result_summary: string;
  lessons_learned?: string;
  next_steps?: string[];
  start_time: string;
  end_time: string;
  duration_seconds?: number;
}
