/**
 * API client — unified re-export from domain modules.
 *
 * All API endpoints are organized by domain:
 *   client.ts          — request<T>(), requestMultipart<T>(), ApiError
 *   workspace.ts       — workspaceApi, collectionApi, workspaceResourceApi
 *   conversation.ts    — conversationApi, historyApi, taskContextApi, skillApi
 *   llm.ts             — llmApi
 *   file.ts            — fileApi
 *   knowledge.ts       — knowledgeApi, knowledgeBasesApi
 *   infra.ts           — mcpApi, userMcpApi, localMcpApi, wsMcpApi, acpAgentApi, channelApi, securityApi
 *   trace.ts           — taskGraphApi, traceApi
 *   subtask.ts         — subtaskApi (§6.2 子任务委派)
 *   scheduled-tasks.ts — scheduledTasksApi
 *   external.ts        — sanctionsApi, healthApi, marketApi
 */

// ── Core client ─────────────────────────────────────────────────────
export { request, requestMultipart, ApiError } from "./client";
export type { ApiResponse } from "./client";

// ── Error translation (可用性升级 v1.1 · 红线 R1) ────────────────────
export { apiErrorMessage } from "./errors";

// ── Workspace ───────────────────────────────────────────────────────
export { workspaceApi, collectionApi, workspaceResourceApi } from "./workspace";
export type {
  WorkspaceConfig,
  AgentConfig,
  CheckpointConfig,
  CompressionConfig,
  MemoryConfig,
  KnowledgeConfig as WsKnowledgeConfig,
  SkillsConfig,
  ToolsConfig,
  WorkspaceResources,
  CollectionItem,
} from "./workspace";

// ── Conversation ────────────────────────────────────────────────────
export { conversationApi, historyApi, taskContextApi, skillApi } from "./conversation";
export type { TaskContextData, TaskGraphRef, TaskContextResponse } from "./conversation";

// ── LLM ─────────────────────────────────────────────────────────────
export { llmApi } from "./llm";
export type {
  LLMProviderConfig,
  LLMProviderItem,
  LLMSessionSettings,
  LLMProviderCreatePayload,
} from "./llm";

// ── File ─────────────────────────────────────────────────────────────
export { fileApi } from "./file";
export type { BackendFileNode } from "./file";

// ── Knowledge ───────────────────────────────────────────────────────
export { knowledgeApi, knowledgeBasesApi } from "./knowledge";
export type {
  KnowledgeBase,
  KnowledgeDomain,
  KnowledgeBaseStatus,
  KnowledgeBaseSettings,
  KnowledgeBaseStats,
  KnowledgeBaseItem,
  KnowledgeBaseListResponse,
  ScanFileInfo,
  DocumentInfo,
  GraphEntity,
  GraphRelation,
  EntitySource,
  SearchResult,
  SyncTaskStatus,
  SyncTaskResult,
  DomainInfo,
  CreateKBRequest,
} from "./knowledge";

// ── Infrastructure ──────────────────────────────────────────────────
export {
  mcpApi,
  userMcpApi,
  localMcpApi,
  wsMcpApi,
  acpAgentApi,
  channelApi,
  securityApi,
  usersSecurityApi,
} from "./infra";
export type {
  WsMcpServerConfig,
  LocalMcpServer,
  LocalMcpHostStatus,
  LocalMcpTestResult,
  AcpAgentInfo,
  ChannelInfo,
} from "./infra";

// ── Trace ───────────────────────────────────────────────────────────
export { taskGraphApi, traceApi } from "./trace";
export type { TaskGraphNode, TaskGraphData, TraceSpanItem, TraceSummary } from "./trace";

// ── Subtask (§6.2 子任务委派) ────────────────────────────────────────
export { subtaskApi } from "./subtask";
export type {
  SubtaskStatus,
  SubtaskLifecycleEventName,
  SubtaskLifecyclePayload,
  SubtaskInfo,
  SubtaskListResponse,
  SubtaskConversationResponse,
  AgentProfileInfo,
  AgentProfilesResponse,
  SubtaskActionResult,
} from "../types/subtask";

// ── Scheduled Tasks ────────────────────────────────────────────────
export { scheduledTasksApi } from "./scheduled-tasks";
export type {
  ScheduleType,
  TriggerStatus,
  ExecutionData,
  ScheduledTask,
  ScheduledTaskExecution,
  ScheduledTasksListResponse,
  ScheduledTaskExecutionsResponse,
  CreateScheduledTaskRequest,
  CreateScheduledTaskGlobalRequest,
  GlobalScheduledTasksResponse,
} from "./scheduled-tasks";

// ── External ────────────────────────────────────────────────────────
export { sanctionsApi, healthApi, marketApi } from "./external";
export type { MarketResource, MarketResourceListResponse } from "./external";

// ── Re-export env constants for backward compat ────────────────────
export { API_BASE_URL, SANCTIONS_API_URL, SUPPORT_API_URL } from "../env";
