/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// HTTP客户端
export { HttpClient, createHttpClient, httpClient } from './http';

// WebSocket客户端
export {
  WebSocketClient,
  createWebSocketClient,
  getWebSocketClient,
  initWebSocketClient
} from '@/services/websocket';

// 类型定义
export type {
  ApiResponse,
  ApiError,
  HttpConfig,
  WebSocketConfig,
  Workspace,
  WorkspaceSettings,
  WorkspaceInfo,
  FileTreeNode,
  OpenFile,
  FileContent,
  FileSaveRequest,
  FileSaveResponse,
  Conversation,
  ConversationMetadata,
  Message,
  MessageMetadata,
  PaginationParams,
  PaginatedResponse,
  SearchParams,
  SearchResult,
  SearchMatch,
  Task,
  TaskMetadata,
  ApiEvent,
  EventListener,
  WorkspaceStats,
  UserStats,
  AppConfig,
  RequestMethod
} from './types';

export type {
  Skill,
  SkillsListResponse,
  SkillSearchResponse
} from './services/skills';

export type {
  MemoryEntry,
  MemoryFilters,
  MemoryListResponse,
  MemoryApiResponse,
  MemoryStats,
  TemporalQueryParams,
  AssociativeRetrievalParams,
  MemoryExportFormat,
  ContextPage,
  MemorySearchResult,
  CreateMemoryParams,
  UpdateMemoryParams,
  ViewMode,
  GraphData,
  TimelineEntry,
  MemoryType
} from './types/memory';

export {
  ErrorCode,
  HTTP_STATUS_CODES,
  ContentType as ApiContentType
} from './types';

// API服务
export { WorkspacesApiService, workspacesApi } from './services/workspaces';
export { FilesApiService, filesApi } from './services/files';
export { ConversationsApiService, conversationsApi } from './services/conversations';
export { SkillsApiService, skillsApi } from './services/skills';
export {
  SlashCommandsApiService,
  slashCommandsApi,
  listSlashCommands,
  getSlashCommand,
  reloadSlashCommands,
  executeSlashCommand
} from './services/slashCommands';

export { MemoryApiService, createMemoryApiService } from './services/memory';

// Plugin Configuration API Service
export { pluginConfigClient } from './pluginConfig';
export type {
  PluginConfigField,
  PluginConfigManifest,
  GetPluginSchemaRequest,
  GetPluginConfigRequest,
  UpdatePluginConfigRequest,
  ResetPluginConfigRequest,
  PluginConfigResponse,
  PluginListResponse,
} from './pluginConfigTypes';

// Market API Service
export {
  MarketApiService,
  marketApi,
  searchMarketResources,
  getMarketResourceInfo,
  installMarketResource,
  listInstalledMarketResources,
  uninstallMarketPlugin,
  getFeaturedMarketResources
} from './services/market';

// Slash Commands类型
export type {
  SlashCommand,
  ListCommandsResponse,
  GetCommandResponse,
  ReloadCommandsResponse,
  ExecuteCommandResponse
} from './services/slashCommands';

// Market API types
export type {
  ResourceType,
  SearchResult,
  ResourceInfo,
  InstallResult,
  InstalledResource,
  SearchRequest,
  SearchResponse,
  InstallRequest,
  InstallResponse,
  InfoResponse,
  ListInstalledResponse,
  UninstallResponse,
  FeaturedResponse,
  CategoryResponse
} from './services/market';

// 工作区便捷函数
export {
  getWorkspaces,
  getWorkspaceInfo,
  createWorkspace,
  updateWorkspace,
  deleteWorkspace,
  getConversations,
  getFileTree,
  getOpenFiles,
  setActiveWorkspace,
  getWorkspaceStats,
  searchWorkspace,
  exportWorkspace,
  importWorkspace,
  cloneWorkspace,
  getWorkspaceMembers,
  inviteMember,
  removeMember,
  updateMemberRole
} from './services/workspaces';

// 文件便捷函数
export {
  getFileContent,
  saveFileContent,
  createFile,
  deleteFile,
  copyFile,
  moveFile,
  renameFile,
  createDirectory,
  deleteDirectory,
  getFileInfo,
  getFileHistory,
  restoreFileVersion,
  searchFiles,
  uploadFile,
  downloadFile,
  getFilePreview,
  getFileDiff,
  batchOperation,
  getFileStats
} from './services/files';

// 对话便捷函数
export {
  getConversations as getConversationsList,
  getConversation,
  createConversation,
  updateConversation,
  deleteConversation,
  archiveConversation,
  unarchiveConversation,
  duplicateConversation,
  getMessages,
  sendMessage,
  updateMessage,
  deleteMessage,
  getTasks,
  createTask,
  getTask,
  cancelTask,
  retryTask,
  searchConversations,
  exportConversation,
  importConversation,
  getConversationStats,
  getConversationSummary,
  markMessageImportant,
  unmarkMessageImportant,
  getImportantMessages
} from './services/conversations';

// API管理器
import { httpClient, HttpClient } from './http';
import { getWebSocketClient, WebSocketClient } from '@/services/websocket';
import { WorkspacesApiService, workspacesApi } from './services/workspaces';
import { FilesApiService, filesApi } from './services/files';
import { ConversationsApiService, conversationsApi } from './services/conversations';
import { SkillsApiService, skillsApi } from './services/skills';
import { MemoryApiService, createMemoryApiService } from './services/memory';
import { MarketApiService, marketApi } from './services/market';
import type { HttpConfig, WebSocketConfig } from './types';

export class ApiManager {
  private static instance: ApiManager | null = null;

  private constructor() {}

  static getInstance(): ApiManager {
    if (!ApiManager.instance) {
      ApiManager.instance = new ApiManager();
    }
    return ApiManager.instance;
  }

  initialize(config?: {
    http?: Partial<HttpConfig>;
    websocket?: Partial<WebSocketConfig>;
  }): void {
    if (config?.http) {
      httpClient.updateConfig(config.http);
    }

    if (config?.websocket) {
      getWebSocketClient(config.websocket as unknown);
    }
  }

  getHttpClient(): HttpClient {
    return httpClient;
  }

  getWebSocketClient(): WebSocketClient {
    return getWebSocketClient();
  }

  getWorkspacesApi(): WorkspacesApiService {
    return workspacesApi;
  }

  getFilesApi(): FilesApiService {
    return filesApi;
  }

  getConversationsApi(): ConversationsApiService {
    return conversationsApi;
  }

  getSkillsApi(): SkillsApiService {
    return skillsApi;
  }

  getMemoryApi(): MemoryApiService {
    return createMemoryApiService(this);
  }

  getMarketApi(): MarketApiService {
    return marketApi;
  }

  setAuthToken(token: string): void {
    httpClient.setAuthToken(token);
  }

  clearAuthToken(): void {
    httpClient.clearAuthToken();
  }

  async connectWebSocket(): Promise<void> {
    const wsClient = getWebSocketClient();
    await wsClient.connect();
  }

  disconnectWebSocket(): void {
    const wsClient = getWebSocketClient();
    wsClient.disconnect();
  }

  isWebSocketConnected(): boolean {
    const wsClient = getWebSocketClient();
    return wsClient.isConnected.value;
  }
}

// 创建默认API管理器实例
export const apiManager = ApiManager.getInstance();

// 默认导出
export default apiManager;

// 向后兼容性导出
export type { WebSocketConfig as BaseWebSocketConfig } from './types';