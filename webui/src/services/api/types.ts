/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 基础API响应类型
export interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  message?: string;
  code?: number;
  timestamp?: string;
}

// API错误类型
export interface ApiError {
  code: number;
  message: string;
  details?: unknown;
  timestamp: string;
  type: string;
}

// HTTP配置类型
export interface HttpConfig {
  baseURL: string;
  timeout?: number;
  headers?: Record<string, string>;
  logRequests?: boolean;
  logResponses?: boolean;
}

// WebSocket配置类型
export interface WebSocketConfig {
  url: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  heartbeatInterval?: number;
  messageTimeout?: number;
  connectionTimeout?: number;
}

// 工作区相关类型
export interface Workspace {
  id: string;
  name: string;
  description?: string;
  path: string;
  createdAt: string;
  updatedAt: string;
  isActive?: boolean;
  settings?: WorkspaceSettings;
}

export interface WorkspaceSettings {
  theme?: 'light' | 'dark' | 'auto';
  language?: string;
  autoSave?: boolean;
  fontSize?: number;
  tabSize?: number;
  wordWrap?: boolean;
}

export interface WorkspaceInfo extends Workspace {
  fileCount?: number;
  conversationCount?: number;
  lastAccessedAt?: string;
  size?: number;
}

export interface FileTreeNode {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  createdAt: string;
  updatedAt: string;
  children?: FileTreeNode[];
  isOpen?: boolean;
  language?: string;
}

export interface OpenFile {
  id: string;
  name: string;
  path: string;
  content?: string;
  language?: string;
  isActive?: boolean;
  isDirty?: boolean;
  cursor?: {
    line: number;
    column: number;
  };
  scrollPosition?: {
    top: number;
    left: number;
  };
}

// 文件相关类型
export interface FileContent {
  path: string;
  content: string;
  language?: string;
  encoding?: string;
  size?: number;
  lastModified?: string;
}

export interface FileSaveRequest {
  path: string;
  content: string;
  encoding?: string;
  createBackup?: boolean;
}

export interface FileSaveResponse {
  success: boolean;
  path: string;
  size: number;
  savedAt: string;
  backupPath?: string;
}

// 对话相关类型
export interface Conversation {
  id: string;
  workspaceId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  lastMessageAt?: string;
  isArchived?: boolean;
  tags?: string[];
  metadata?: ConversationMetadata;
  task_type?: TaskType;
  source_task_id?: string;
}

export interface ConversationMetadata {
  taskType?: string;
  mode?: string;
  toolsUsed?: string[];
  duration?: number;
  tokenUsage?: {
    input: number;
    output: number;
    total: number;
  };
  repeat_count?: number;
  triggered_at?: string;
}

// Task type for conversations
export type TaskType = 'user' | 'scheduled';

export interface Message {
  id: string;
  conversationId: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: MessageMetadata;
}

export interface MessageMetadata {
  thinking?: unknown[];
  toolCalls?: unknown[];
  files?: unknown[];
  mentions?: unknown[];
  taskId?: string;
  mode?: string;
}

// 分页相关类型
export interface PaginationParams {
  page?: number;
  limit?: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

// 搜索相关类型
export interface SearchParams {
  query: string;
  type?: 'file' | 'content' | 'all';
  fileExtensions?: string[];
  excludePatterns?: string[];
  maxResults?: number;
}

export interface SearchResult {
  path: string;
  name: string;
  type: 'file' | 'directory';
  matches: SearchMatch[];
  score?: number;
}

export interface SearchMatch {
  line: number;
  column: number;
  text: string;
  context?: string;
}

// 任务相关类型
export interface Task {
  id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  message?: string;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  result?: unknown;
  error?: string;
  metadata?: TaskMetadata;
}

export interface TaskMetadata {
  workspaceId?: string;
  conversationId?: string;
  userId?: string;
  mode?: string;
  tools?: string[];
  input?: unknown;
  output?: unknown;
  duration?: number;
}

// 事件相关类型
export interface ApiEvent {
  type: string;
  payload: unknown;
  timestamp: string;
  source?: string;
}

export interface EventListener {
  (event: ApiEvent): void;
}

// 统计相关类型
export interface WorkspaceStats {
  totalFiles: number;
  totalSize: number;
  fileTypes: Record<string, number>;
  conversationsCount: number;
  messagesCount: number;
  tasksCount: number;
  lastActivityAt: string;
}

export interface UserStats {
  totalWorkspaces: number;
  totalConversations: number;
  totalMessages: number;
  totalTasks: number;
  activeWorkspace?: string;
  joinDate: string;
  lastLoginAt: string;
}

// 配置相关类型
export interface AppConfig {
  api: {
    baseURL: string;
    timeout: number;
    retryAttempts: number;
  };
  websocket: {
    url: string;
    reconnectAttempts: number;
    reconnectDelay: number;
    heartbeatInterval: number;
  };
  features: {
    fileUpload: boolean;
    realTimeSync: boolean;
    autoSave: boolean;
    notifications: boolean;
  };
  ui: {
    theme: 'light' | 'dark' | 'auto';
    language: string;
    pageSize: number;
  };
}

// 错误代码枚举
export enum ErrorCode {
  // 通用错误
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
  NETWORK_ERROR = 'NETWORK_ERROR',
  TIMEOUT_ERROR = 'TIMEOUT_ERROR',
  
  // 认证错误
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  TOKEN_EXPIRED = 'TOKEN_EXPIRED',
  
  // 请求错误
  BAD_REQUEST = 'BAD_REQUEST',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  NOT_FOUND = 'NOT_FOUND',
  CONFLICT = 'CONFLICT',
  
  // 服务器错误
  INTERNAL_ERROR = 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE = 'SERVICE_UNAVAILABLE',
  
  // 业务错误
  WORKSPACE_NOT_FOUND = 'WORKSPACE_NOT_FOUND',
  FILE_NOT_FOUND = 'FILE_NOT_FOUND',
  CONVERSATION_NOT_FOUND = 'CONVERSATION_NOT_FOUND',
  TASK_FAILED = 'TASK_FAILED',
  PERMISSION_DENIED = 'PERMISSION_DENIED'
}

// HTTP状态码映射
export const HTTP_STATUS_CODES = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  UNPROCESSABLE_ENTITY: 422,
  INTERNAL_SERVER_ERROR: 500,
  SERVICE_UNAVAILABLE: 503
} as const;

// 请求方法类型
export type RequestMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

// 内容类型枚举
export enum ContentType {
  JSON = 'application/json',
  FORM_DATA = 'multipart/form-data',
  TEXT = 'text/plain',
  HTML = 'text/html',
  XML = 'application/xml'
}

// 系统环境信息
export interface SystemEnvironments {
  os_name: string;
  os_version: string;
  python_version: string;
  cpu_count: number;
  memory_total: number;  // MB
  memory_available: number;  // MB
  disk_total: number;  // MB
  disk_available: number;  // MB
}

// 用户UI环境信息
export interface UserUIEnvironments {
  browser_name: string;
  browser_version: string;
  user_os: string;
  user_language: string;
  timezone: string;
  screen_resolution: string;
}

// 用户UI上下文信息
export interface UserUIContext {
  open_files: string[];
  active_applications: string[];
  user_preferences: Record<string, unknown>;
  current_file: string | null;
  current_selected_content: string | null;
  current_mode: string | null;
  current_llm_id: string | null;
  conversation_id: string | null;
}

// 代理配置
export interface ProxyConfig {
  http_proxy: string;
  https_proxy: string;
  no_proxy: string;
}

// 插件配置相关类型（两层配置系统）
export interface PluginInstanceConfig {
  enabled: boolean;
  activated: boolean;
  settings: Record<string, unknown>;
  version?: string;
  install_path?: string;
}

export interface PluginsConfig {
  plugins: Record<string, PluginInstanceConfig>;
}

export interface PluginsConfigResponse {
  success: boolean;
  config: PluginsConfig;
  message?: string;
}

export interface PluginConfigResponse {
  plugin_id: string;
  exists: boolean;
  enabled: boolean;
  activated: boolean;
  settings: Record<string, unknown>;
  version: string | null;
  install_path: string | null;
}

export interface PluginConfigUpdateRequest {
  enabled?: boolean;
  settings?: Record<string, unknown>;
}

export interface PluginListResponse {
  success: boolean;
  plugins: Array<{
    plugin_id: string;
    exists: boolean;
    enabled: boolean;
    activated: boolean;
    version: string | null;
    install_path: string | null;
  }>;
  message?: string;
}

export interface UpdatePluginConfigRequest {
  plugin_id: string;
  config: Record<string, unknown>;
}

export interface ResetPluginConfigRequest {
  plugin_id: string;
}

// Scheduled Task types
export interface ScheduledTask {
  task_id: string;
  workspace_id: string;
  description: string;
  schedule_type: 'delay' | 'at_time' | 'recurring' | 'cron';
  trigger_time: string;
  repeat_interval?: number;
  max_repeats?: number;
  cron_expression?: string;
  execution_type: 'message';
  execution_data: {
    message?: string;
    llm?: string;
    mode?: string;
  };
  status: 'pending' | 'paused' | 'triggered' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  updated_at?: string;
  paused_at?: string;
  resumed_at?: string;
  triggered_at?: string;
  repeat_count: number;
  last_error?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface ScheduledTaskExecution {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  repeat_count: number;
  triggered_at: string;
}

export interface ScheduledTasksListResponse {
  success: boolean;
  tasks: ScheduledTask[];
  total: number;
  scheduler_active: boolean;
}

export interface ScheduledTaskExecutionsResponse {
  success: boolean;
  task_id: string;
  executions: ScheduledTaskExecution[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
