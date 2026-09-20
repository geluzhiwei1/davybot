/**
 * API type definitions — migrated from legalbot/webui/src/services/api/types.ts
 * Fetch-based HTTP client (no axios dependency).
 */

// ─── Base API Response ─────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  success: boolean;
  data: T;
  message?: string;
  code?: number;
  timestamp?: string;
}

export interface ApiError {
  code: number;
  message: string;
  details?: unknown;
  timestamp: string;
  type: string;
}

// ─── HTTP / Config ─────────────────────────────────────────────────────────

export interface HttpConfig {
  baseURL?: string;
  timeout?: number;
  headers?: Record<string, string>;
}

export type RequestMethod = "GET" | "POST" | "PUT" | "DELETE" | "PATCH";

export enum ContentType {
  JSON = "application/json",
  FORM_DATA = "multipart/form-data",
  TEXT = "text/plain",
}

export enum ErrorCode {
  UNKNOWN_ERROR = "UNKNOWN_ERROR",
  NETWORK_ERROR = "NETWORK_ERROR",
  TIMEOUT_ERROR = "TIMEOUT_ERROR",
  UNAUTHORIZED = "UNAUTHORIZED",
  FORBIDDEN = "FORBIDDEN",
  TOKEN_EXPIRED = "TOKEN_EXPIRED",
  BAD_REQUEST = "BAD_REQUEST",
  VALIDATION_ERROR = "VALIDATION_ERROR",
  NOT_FOUND = "NOT_FOUND",
  CONFLICT = "CONFLICT",
  INTERNAL_ERROR = "INTERNAL_ERROR",
  SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE",
  WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND",
  FILE_NOT_FOUND = "FILE_NOT_FOUND",
  CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND",
  TASK_FAILED = "TASK_FAILED",
  PERMISSION_DENIED = "PERMISSION_DENIED",
}

// ─── Pagination ────────────────────────────────────────────────────────────

export interface PaginationParams {
  page?: number;
  limit?: number;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
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

// ─── Workspace ─────────────────────────────────────────────────────────────

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
  theme?: "light" | "dark" | "auto";
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

export interface WorkspaceDetail extends Workspace {
  files_list?: string[];
  system_environments?: unknown;
  user_ui_environments?: unknown;
  user_ui_context?: unknown;
}

export interface WorkspaceStats {
  totalFiles: number;
  totalSize: number;
  fileTypes: Record<string, number>;
  conversationsCount: number;
  messagesCount: number;
  tasksCount: number;
  lastActivityAt: string;
}

export interface WorkspaceCollection {
  id: string;
  name: string;
  description: string;
  workspace_ids: string[];
  created_at: string;
  updated_at: string;
}

// ─── File ──────────────────────────────────────────────────────────────────

export interface FileTreeNode {
  id: string;
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  createdAt: string;
  updatedAt: string;
  children?: FileTreeNode[];
  isOpen?: boolean;
  language?: string;
  is_directory?: boolean;
}

export interface OpenFile {
  id: string;
  name: string;
  path: string;
  content?: string;
  language?: string;
  isActive?: boolean;
  isDirty?: boolean;
  cursor?: { line: number; column: number };
  scrollPosition?: { top: number; left: number };
  workspaceId?: string;
}

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

// ─── Conversation / Message ────────────────────────────────────────────────

export type TaskType = "user" | "scheduled";

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
  tokenUsage?: { input: number; output: number; total: number };
  repeat_count?: number;
  triggered_at?: string;
}

export interface Message {
  id: string;
  conversationId: string;
  type: "user" | "assistant" | "system";
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

// ─── Task ──────────────────────────────────────────────────────────────────

export interface Task {
  id: string;
  type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
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

// ─── Search ────────────────────────────────────────────────────────────────

export interface SearchParams {
  query: string;
  type?: "file" | "content" | "all";
  fileExtensions?: string[];
  excludePatterns?: string[];
  maxResults?: number;
}

export interface SearchResult {
  path: string;
  name: string;
  type: "file" | "directory";
  matches: SearchMatch[];
  score?: number;
}

export interface SearchMatch {
  line: number;
  column: number;
  text: string;
  context?: string;
}

// ─── Scheduled Task ────────────────────────────────────────────────────────

export interface ScheduledTask {
  task_id: string;
  workspace_id: string;
  description: string;
  schedule_type: "delay" | "at_time" | "recurring" | "cron";
  trigger_time: string;
  repeat_interval?: number;
  max_repeats?: number;
  cron_expression?: string;
  execution_type: "message";
  execution_data: { message?: string; llm?: string; mode?: string };
  status: "pending" | "paused" | "triggered" | "completed" | "failed" | "cancelled";
  enabled?: boolean;
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

// ─── Plugin ────────────────────────────────────────────────────────────────

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

// ─── Security ──────────────────────────────────────────────────────────────

export interface UserSecuritySettings {
  enableCommandWhitelist: boolean;
  allowedSources: ("system" | "custom")[];
  customAllowedCommands: string[];
  customDeniedCommands: string[];
  allowShellCommands: boolean;
  allowBackgroundCommands: boolean;
  allowPipeCommands: boolean;
  commandExecutionTimeout: number;
  enableSandbox: boolean;
  containerRuntime: "docker" | "podman" | "auto" | "e2b";
  dropAllCapabilities: boolean;
  noNewPrivileges: boolean;
  sandboxDisableNetwork: boolean;
  allowWorkspaceOverrideCommandSecurity: boolean;
  allowWorkspaceOverrideSandbox: boolean;
  // approval (human-in-the-loop)
  approvalEnabled: boolean;
  approvalRequiredForRisk: "low" | "medium" | "high" | "critical" | "never";
  approvalTimeoutSeconds: number;
  approvalNoChannelBehavior: "allow" | "deny";
}

export interface WorkspaceSecuritySettings {
  enableCommandWhitelist: boolean;
  allowedSources: ("system" | "custom")[];
  customAllowedCommands: string[];
  customDeniedCommands: string[];
  allowShellCommands: boolean;
  allowBackgroundCommands: boolean;
  allowPipeCommands: boolean;
  commandExecutionTimeout: number;
  enableSandbox: boolean;
  containerRuntime?: "docker" | "podman" | "auto" | "e2b";
  dropAllCapabilities?: boolean;
  noNewPrivileges?: boolean;
  sandboxDisableNetwork?: boolean;
  // approval (human-in-the-loop)
  approvalEnabled?: boolean;
  approvalRequiredForRisk?: "low" | "medium" | "high" | "critical" | "never";
  approvalTimeoutSeconds?: number;
  approvalNoChannelBehavior?: "allow" | "deny";
}

// ─── System Command Whitelist ─────────────────────────────────────────────

export interface SystemCommandConfig {
  maxArgs: number;
  allowedFlags: string[];
  allowedSubcommands: string[] | null;
  description: string;
}

export interface SystemCommandWhitelist {
  version: number;
  allowedCommands: Record<string, SystemCommandConfig>;
  dangerousCommands: string[];
  dangerousPatterns: string[];
}

export interface SecuritySettingsResponse {
  success: boolean;
  settings: UserSecuritySettings | WorkspaceSecuritySettings;
  message?: string;
}

// ─── System / UI ───────────────────────────────────────────────────────────

export interface SystemEnvironments {
  os_name: string;
  os_version: string;
  python_version: string;
  cpu_count: number;
  memory_total: number;
  memory_available: number;
  disk_total: number;
  disk_available: number;
}

export interface UserUIEnvironments {
  browser_name: string;
  browser_version: string;
  user_os: string;
  user_language: string;
  timezone: string;
  screen_resolution: string;
}

export interface UserUIContext {
  open_files: string[];
  active_applications: string[];
  user_preferences: Record<string, unknown>;
  current_file: string | null;
  current_selected_content: string | null;
  current_mode: string | null;
  current_llm_id: string | null;
  conversation_id: string | null;
  current_experts: string[];
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

export interface AppConfig {
  api: { baseURL: string; timeout: number; retryAttempts: number };
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
  ui: { theme: "light" | "dark" | "auto"; language: string; pageSize: number };
}

export interface ValidatePathResponse {
  success: boolean;
  valid: boolean;
  message: string;
  exists: boolean;
  writable?: boolean;
  is_empty?: boolean;
  is_workspace?: boolean;
}
