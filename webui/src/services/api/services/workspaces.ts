/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';
import type {
  Workspace,
  WorkspaceInfo,
  OpenFile,
  Conversation,
  PaginatedResponse,
  UserUIEnvironments,
  UserUIContext,
  ProxyConfig,
  ValidatePathRequest,
  ValidatePathResponse,
  FileTreeNode,
  SystemEnvironments
} from '../types';

// 重新导出类型以供外部使用
export type { ValidatePathRequest, ValidatePathResponse };

// 工作区API服务类
export class WorkspacesApiService {
  private baseUrl = '/workspaces';
  private crudUrl = this.baseUrl;

  // 获取工作区列表
  async getWorkspaces(params?: {
    include_inactive?: boolean;
  }): Promise<Workspace[]> {
    // 使用新的 /list 端点
    const response = await httpClient.get<{ workspaces: Workspace[] }>(`${this.crudUrl}/list`, params);
    return response.workspaces;
  }

  // 获取工作区信息
  async getWorkspaceInfo(workspaceId: string): Promise<WorkspaceInfo> {
    const response = await httpClient.get<{ workspace: WorkspaceInfo }>(`${this.crudUrl}/${workspaceId}/info`);
    return response.workspace;
  }

  // 创建工作区
  async createWorkspace(data: {
    name: string;
    description?: string;
    path: string;
    settings?: {
      theme?: 'light' | 'dark' | 'auto';
      language?: string;
      autoSave?: boolean;
      fontSize?: number;
      tabSize?: number;
      wordWrap?: boolean;
    };
  }): Promise<Workspace> {
    const response = await httpClient.post<{ workspace: Workspace }>(`${this.crudUrl}/create`, data);
    return response.workspace;
  }

  // 更新工作区
  async updateWorkspace(workspaceId: string, data: {
    name?: string;
    description?: string;
    settings?: {
      theme?: 'light' | 'dark' | 'auto';
      language?: string;
      autoSave?: boolean;
      fontSize?: number;
      tabSize?: number;
      wordWrap?: boolean;
    };
  }): Promise<Workspace> {
    const response = await httpClient.put<{ workspace: Workspace }>(`${this.crudUrl}/${workspaceId}`, data);
    return response.workspace;
  }

  // 删除工作区
  async deleteWorkspace(
    workspaceId: string,
    deleteConfig?: boolean,
    deleteFiles?: boolean
  ): Promise<{ success: boolean; message: string; workspace?: Workspace }> {
    const params: Record<string, string> = {};
    if (deleteConfig !== undefined) params.delete_config = String(deleteConfig);
    if (deleteFiles !== undefined) params.delete_files = String(deleteFiles);

    return await httpClient.delete<{ success: boolean; message: string; workspace?: Workspace }>(
      `${this.crudUrl}/${workspaceId}`,
      { params }
    );
  }

  // 验证工作区路径
  async validatePath(data: ValidatePathRequest): Promise<ValidatePathResponse> {
    return await httpClient.post<ValidatePathResponse>(`${this.baseUrl}/validate-path`, data);
  }

  // 获取历史对话
  async getConversations(workspaceId: string, params?: {
    page?: number;
    limit?: number;
    sortBy?: 'createdAt' | 'updatedAt' | 'lastMessageAt';
    sortOrder?: 'asc' | 'desc';
    search?: string;
    isArchived?: boolean;
  }): Promise<PaginatedResponse<Conversation>> {
    const response = await httpClient.get<{
      conversations: Conversation[],
      page: number,
      limit: number,
      total: number,
      totalPages: number
    }>(
      `${this.baseUrl}/${workspaceId}/conversations`,
      params
    );

    return {
      items: response.conversations,
      pagination: {
        page: response.page,
        limit: response.limit,
        total: response.total,
        totalPages: response.totalPages,
        hasNext: response.page < response.totalPages,
        hasPrev: response.page > 1,
      }
    };
  }

  // 创建新对话（后端期望接收会话数组）
  async createConversation(
    workspaceId: string,
    conversations: Array<{
      id: string;
      title: string;
      created_at: string;
      updated_at: string;
      messages: unknown[];
      message_count: number;
      task_type?: string;
      metadata?: Record<string, unknown>;
    }>
  ): Promise<{
    success: boolean;
    message: string;
    workspace_name: string;
    saved_count: number;
  }> {
    return await httpClient.post<{
      success: boolean;
      message: string;
      workspace_name: string;
      saved_count: number;
    }>(
      `${this.baseUrl}/${workspaceId}/conversations`,
      conversations
    );
  }

  // 更新对话（支持更新标题等）
  async updateConversation(
    workspaceId: string,
    conversationId: string,
    data: {
      title?: string;
      messages?: unknown[];
      message_count?: number;
      updated_at?: string;
    }
  ): Promise<{
    success: boolean;
    message: string;
    workspace_name: string;
    conversation_id: string;
  }> {
    return await httpClient.post<{
      success: boolean;
      message: string;
      workspace_name: string;
      conversation_id: string;
    }>(
      `${this.baseUrl}/${workspaceId}/conversations/${conversationId}`,
      data
    )
  }

  // 获取单个对话详情（包含消息）支持分页
  async getConversationById(
    workspaceId: string,
    conversationId: string,
    params?: {
      skip?: number;
      limit?: number;
      include_metadata?: boolean;
      order?: 'asc' | 'desc';  // 'asc' = oldest first, 'desc' = newest first
    }
  ): Promise<{
    success: boolean;
    conversation: unknown;
    message: string;
  }> {
    const queryParams = new URLSearchParams()
    if (params?.skip !== undefined) queryParams.append('skip', params.skip.toString())
    if (params?.limit !== undefined) queryParams.append('limit', params.limit.toString())
    if (params?.include_metadata !== undefined) queryParams.append('include_metadata', params.include_metadata.toString())
    if (params?.order !== undefined) queryParams.append('order', params.order)

    const queryString = queryParams.toString()
    const url = `/workspaces/${workspaceId}/conversations/${conversationId}${queryString ? `?${queryString}` : ''}`

    const response = await httpClient.get<{
      success: boolean;
      conversation: unknown;
      message: string;
    }>(url)

    return response
  }

  // 删除对话
  async deleteConversation(workspaceId: string, conversationId: string): Promise<{
    success: boolean;
    message: string;
  }> {
    const response = await httpClient.delete<{
      success: boolean;
      message: string;
    }>(
      `/workspaces/${workspaceId}/conversations/${conversationId}`
    );
    return response;
  }

  // 删除所有对话
  async deleteAllConversations(workspaceId: string): Promise<{
    success: boolean;
    message: string;
    deletedCount: number;
  }> {
    const response = await httpClient.delete<{
      success: boolean;
      message: string;
      deletedCount: number;
    }>(
      `/workspaces/${workspaceId}/conversations`
    );
    return response;
  }

  // 转换扁平文件列表为树形结构
  private buildFileTree(nodes: FileTreeNode[]): FileTreeNode[] {
    if (!nodes || !Array.isArray(nodes)) {
      return [];
    }

    const tree: FileTreeNode[] = [];
    const map: { [key: string]: FileTreeNode } = {};

    // 1. 创建映射表并初始化children（只添加不存在的节点）
    nodes.forEach(node => {
      // 确保 type 字段正确设置
      if (node.is_directory && node.type !== 'directory') {
        node.type = 'directory';
      }
      if (!node.is_directory && node.type !== 'file') {
        node.type = 'file';
      }

      // 只在节点不存在时创建，避免覆盖已添加的children
      if (!map[node.path]) {
        // 只有目录节点才需要 children 数组
        if (node.is_directory || node.type === 'directory') {
          map[node.path] = { ...node, children: [] };
        } else {
          // 文件节点不需要 children 字段
          map[node.path] = { ...node };
        }
      }
    });

    // 2. 构建树形结构
    nodes.forEach(node => {
      const treeNode = map[node.path];
      if (!treeNode) return;

      const lastSlashIndex = node.path.lastIndexOf('/');
      const parentPath = lastSlashIndex !== -1 ? node.path.substring(0, lastSlashIndex) : '';

      if (parentPath && map[parentPath]) {
        // 添加到父节点的 children（避免重复添加）
        if (Array.isArray(map[parentPath].children)) {
          const exists = map[parentPath].children!.some(child => child.path === node.path);
          if (!exists) {
            map[parentPath].children!.push(treeNode);
          }
        }
      } else {
        // 顶层节点（避免重复添加）
        const exists = tree.some(t => t.path === node.path);
        if (!exists) {
          tree.push(treeNode);
        }
      }
    });

    // 3. 按名称排序（目录在前，文件在后）
    tree.sort((a, b) => {
      const aIsDir = a.is_directory || a.type === 'directory';
      const bIsDir = b.is_directory || b.type === 'directory';
      if (aIsDir && !bIsDir) return -1;
      if (!aIsDir && bIsDir) return 1;
      return a.name.localeCompare(b.name);
    });

    // 递归排序所有子节点
    const sortChildren = (nodes: FileTreeNode[]) => {
      nodes.forEach(node => {
        if (node.children && node.children.length > 0) {
          node.children.sort((a, b) => {
            const aIsDir = a.is_directory || a.type === 'directory';
            const bIsDir = b.is_directory || b.type === 'directory';
            if (aIsDir && !bIsDir) return -1;
            if (!aIsDir && bIsDir) return 1;
            return a.name.localeCompare(b.name);
          });
          sortChildren(node.children);
        }
      });
    };

    sortChildren(tree);

    return tree;
  }

  // 获取文件树
  async getFileTree(workspaceId: string, params?: {
    path?: string;
    includeHidden?: boolean;
    maxDepth?: number;
    recursive?: boolean; // Add missing recursive parameter
  }): Promise<FileTreeNode[]> {
    try {
      // 默认启用递归获取，以便显示完整的文件树
      const requestParams = {
        path: params?.path,
        include_hidden: params?.includeHidden ?? true,
        max_depth: params?.maxDepth ?? 3,
        recursive: params?.recursive ?? true  // 默认启用递归
      };

      const response = await httpClient.get<{ success: boolean; type: string; files: FileTreeNode[] }>(
        `${this.baseUrl}/${workspaceId}/files`,
        requestParams
      );
      // 后端返回格式: { success: true, type: "directory", files: [...] }
      const fileTreeData = response?.files || [];
      return this.buildFileTree(fileTreeData);
    } catch (error) {
      console.error('获取文件树失败:', error);
      return [];
    }
  }

  // 获取打开的文件
  async getOpenFiles(workspaceId: string): Promise<OpenFile[]> {
    const response = await httpClient.get<{ openFiles: OpenFile[] }>(`${this.baseUrl}/${workspaceId}/open-files`);
    return response.openFiles;
  }

  // 设置活动工作区
  async setActiveWorkspace(workspaceId: string): Promise<Workspace> {
    const response = await httpClient.post<{ workspace: Workspace }>(`${this.baseUrl}/${workspaceId}/activate`);
    return response.workspace;
  }

  // 获取工作区统计信息
  async getWorkspaceStats(workspaceId: string): Promise<{
    totalFiles: number;
    totalSize: number;
    fileTypes: Record<string, number>;
    conversationsCount: number;
    messagesCount: number;
    tasksCount: number;
    skillsCount: number;
    agentsCount: number;
    lastActivityAt: string;
  }> {
    try {
      return await httpClient.get(`${this.baseUrl}/${workspaceId}/stats`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取全局统计信息（用户级）
  async getGlobalStats(): Promise<{
    workspacesCount: number;
    skillsCount: number;
    agentsCount: number;
  }> {
    try {
      return await httpClient.get(`${this.baseUrl}/global-stats`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 搜索工作区内容
  async searchWorkspace(workspaceId: string, params: {
    query: string;
    type?: 'file' | 'content' | 'all';
    fileExtensions?: string[];
    excludePatterns?: string[];
    maxResults?: number;
    path?: string;
  }): Promise<{
    files: Array<{
      path: string;
      name: string;
      type: 'file' | 'directory';
      matches: Array<{
        line: number;
        column: number;
        text: string;
        context?: string;
      }>;
      score?: number;
    }>;
    total: number;
    searchTime: number;
  }> {
    try {
      return await httpClient.get(`${this.baseUrl}/${workspaceId}/search`, params);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 导出工作区
  async exportWorkspace(workspaceId: string, params?: {
    format?: 'zip' | 'tar' | 'json';
    includeHistory?: boolean;
    includeSettings?: boolean;
  }): Promise<{
    downloadUrl: string;
    filename: string;
    size: number;
    expiresAt: string;
  }> {
    try {
      return await httpClient.post(`${this.baseUrl}/${workspaceId}/export`, params);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 导入工作区
  async importWorkspace(data: {
    name: string;
    description?: string;
    file: File;
    format?: 'zip' | 'tar' | 'json';
  }): Promise<Workspace> {
    try {
      const formData = new FormData();
      formData.append('name', data.name);
      if (data.description) {
        formData.append('description', data.description);
      }
      formData.append('file', data.file);
      if (data.format) {
        formData.append('format', data.format);
      }

      return await httpClient.upload<Workspace>(`${this.baseUrl}/import`, formData);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 克隆工作区
  async cloneWorkspace(workspaceId: string, data: {
    name: string;
    description?: string;
    includeHistory?: boolean;
    includeSettings?: boolean;
  }): Promise<Workspace> {
    try {
      return await httpClient.post<Workspace>(`${this.baseUrl}/${workspaceId}/clone`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取工作区成员
  async getWorkspaceMembers(workspaceId: string): Promise<Array<{
    id: string;
    username: string;
    email: string;
    role: 'owner' | 'admin' | 'member' | 'viewer';
    joinedAt: string;
    lastActiveAt: string;
  }>> {
    try {
      return await httpClient.get(`${this.baseUrl}/${workspaceId}/members`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 邀请成员到工作区
  async inviteMember(workspaceId: string, data: {
    email: string;
    role: 'admin' | 'member' | 'viewer';
    message?: string;
  }): Promise<{
    invitationId: string;
    email: string;
    role: string;
    expiresAt: string;
  }> {
    try {
      return await httpClient.post(`${this.baseUrl}/${workspaceId}/members/invite`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 移除工作区成员
  async removeMember(workspaceId: string, memberId: string): Promise<void> {
    try {
      return await httpClient.delete(`${this.baseUrl}/${workspaceId}/members/${memberId}`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新成员角色
  async updateMemberRole(workspaceId: string, memberId: string, role: 'admin' | 'member' | 'viewer'): Promise<void> {
    try {
      return await httpClient.put(`${this.baseUrl}/${workspaceId}/members/${memberId}`, { role });
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // ==================== MCP Server Management API ====================

  // 获取所有MCP服务器
  async getMCPServers(workspaceId: string): Promise<{
    success: boolean;
    servers: Array<{
      name: string;
      command: string;
      args: string[];
      cwd: string | null;
      always_allow: string[];
      timeout: number;
      disabled: boolean;
    }>;
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        servers: Array<{
          name: string;
          command: string;
          args: string[];
          cwd: string | null;
          always_allow: string[];
          timeout: number;
          disabled: boolean;
        }>;
      }>(`${this.baseUrl}/${workspaceId}/mcp-servers`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 创建MCP服务器
  async createMCPServer(
    workspaceId: string,
    data: {
      name: string;
      command: string;
      args?: string[];
      cwd?: string;
      always_allow?: string[];
      timeout?: number;
      disabled?: boolean;
    }
  ): Promise<{
    success: boolean;
    message: string;
    server: {
      name: string;
      command: string;
      args: string[];
      cwd: string | null;
      always_allow: string[];
      timeout: number;
      disabled: boolean;
    } | null;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        server: {
          name: string;
          command: string;
          args: string[];
          cwd: string | null;
          always_allow: string[];
          timeout: number;
          disabled: boolean;
        } | null;
      }>(`${this.baseUrl}/${workspaceId}/mcp-servers`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新MCP服务器
  async updateMCPServer(
    workspaceId: string,
    serverName: string,
    data: {
      command?: string;
      args?: string[];
      cwd?: string;
      always_allow?: string[];
      timeout?: number;
      disabled?: boolean;
    }
  ): Promise<{
    success: boolean;
    message: string;
    server: {
      name: string;
      command: string;
      args: string[];
      cwd: string | null;
      always_allow: string[];
      timeout: number;
      disabled: boolean;
    } | null;
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        message: string;
        server: {
          name: string;
          command: string;
          args: string[];
          cwd: string | null;
          always_allow: string[];
          timeout: number;
          disabled: boolean;
        } | null;
      }>(`${this.baseUrl}/${workspaceId}/mcp-servers/${serverName}`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 删除MCP服务器
  async deleteMCPServer(workspaceId: string, serverName: string): Promise<{
    success: boolean;
    message: string;
    server: null;
  }> {
    try {
      return await httpClient.delete<{
        success: boolean;
        message: string;
        server: null;
      }>(`${this.baseUrl}/${workspaceId}/mcp-servers/${serverName}`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 测试MCP服务器连接
  async testMCPServer(workspaceId: string, serverName: string): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/mcp-servers/${serverName}/test`, {});
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取用户UI环境信息
  async getUIEnvironments(workspaceId: string): Promise<UserUIEnvironments> {
    try {
      const response = await httpClient.get<{ ui_environments: UserUIEnvironments }>(
        `${this.baseUrl}/${workspaceId}/ui-environments`
      );
      return response.ui_environments;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新用户UI环境信息
  async updateUIEnvironments(workspaceId: string, data: Partial<UserUIEnvironments>): Promise<UserUIEnvironments> {
    try {
      const response = await httpClient.put<{ ui_environments: UserUIEnvironments }>(
        `${this.baseUrl}/${workspaceId}/ui-environments`,
        data
      );
      return response.ui_environments;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取代理配置
  async getProxyConfig(workspaceId: string): Promise<ProxyConfig> {
    try {
      const response = await httpClient.get<ProxyConfig>(
        `${this.baseUrl}/${workspaceId}/proxy`
      );
      return response;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新代理配置
  async updateProxyConfig(workspaceId: string, data: Partial<ProxyConfig>): Promise<ProxyConfig> {
    try {
      const response = await httpClient.put<ProxyConfig>(
        `${this.baseUrl}/${workspaceId}/proxy`,
        data
      );
      return response;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取用户UI上下文信息
  async getUIContext(workspaceId: string): Promise<UserUIContext> {
    try {
      const response = await httpClient.get<{ ui_context: UserUIContext }>(
        `${this.baseUrl}/${workspaceId}/ui-context`
      );
      return response.ui_context;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新用户UI上下文信息
  async updateUIContext(workspaceId: string, data: Partial<UserUIContext>): Promise<UserUIContext> {
    try {
      const response = await httpClient.put<{ ui_context: UserUIContext }>(
        `${this.baseUrl}/${workspaceId}/ui-context`,
        data
      );
      return response.ui_context;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取系统环境信息
  async getSystemEnvironments(workspaceId: string): Promise<SystemEnvironments> {
    try {
      const response = await httpClient.get<{ system_environments: SystemEnvironments }>(
        `${this.baseUrl}/${workspaceId}/system-environments`
      );
      return response.system_environments;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新系统环境信息
  async updateSystemEnvironments(workspaceId: string, data: Partial<SystemEnvironments>): Promise<SystemEnvironments> {
    try {
      const response = await httpClient.put<{ system_environments: SystemEnvironments }>(
        `${this.baseUrl}/${workspaceId}/system-environments`,
        data
      );
      return response.system_environments;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 创建文件或目录
  async createFileOrDirectory(
    workspaceId: string,
    data: {
      path: string;
      content?: string;
      is_directory?: boolean;
    }
  ): Promise<{ success: boolean; message: string; path: string }> {
    try {
      return await httpClient.post<{ success: boolean; message: string; path: string }>(
        `${this.baseUrl}/${workspaceId}/files/create`,
        data
      );
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 删除文件或目录
  async deleteFileOrDirectory(
    workspaceId: string,
    path: string
  ): Promise<{ success: boolean; message: string; path: string }> {
    try {
      return await httpClient.delete<{ success: boolean; message: string; path: string }>(
        `${this.baseUrl}/${workspaceId}/files/delete`,
        { params: { path } }
      );
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 复制文件或目录
  async copyFileOrDirectory(
    workspaceId: string,
    data: {
      source_path: string;
      destination_path: string;
    }
  ): Promise<{ success: boolean; message: string; source: string; destination: string }> {
    try {
      return await httpClient.post<{ success: boolean; message: string; source: string; destination: string }>(
        `${this.baseUrl}/${workspaceId}/files/copy`,
        data
      );
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 重命名文件或目录
  async renameFileOrDirectory(
    workspaceId: string,
    data: {
      old_path: string;
      new_path: string;
    }
  ): Promise<{ success: boolean; message: string; old_path: string; new_path: string }> {
    try {
      return await httpClient.put<{ success: boolean; message: string; old_path: string; new_path: string }>(
        `${this.baseUrl}/${workspaceId}/files/rename`,
        data
      );
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 下载文件或目录
  async downloadFileOrDirectory(
    workspaceId: string,
    path: string
  ): Promise<Blob> {
    try {
      return await httpClient.download(`${this.baseUrl}/${workspaceId}/files/download`, {
        params: { path }
      });
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取 LLM 配置设置
  async getLLMSettings(workspaceId: string): Promise<{
    success: boolean;
    settings: {
      currentApiConfigName: string | null;
      currentConfig?: unknown;
      allConfigs: Record<string, unknown>;
      modeApiConfigs: Record<string, string>;
    };
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        settings: {
          currentApiConfigName: string | null;
          currentConfig?: unknown;
          allConfigs: Record<string, unknown>;
          modeApiConfigs: Record<string, string>;
        };
      }>(`${this.baseUrl}/${workspaceId}/llm-settings`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 LLM 配置设置
  async updateLLMSettings(
    workspaceId: string,
    data: {
      currentApiConfigName?: string;
      modeApiConfigs?: Record<string, string>;
    }
  ): Promise<{
    success: boolean;
    message: string;
    settings: {
      currentApiConfigName: string;
      modeApiConfigs: Record<string, string>;
    };
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        settings: {
          currentApiConfigName: string;
          modeApiConfigs: Record<string, string>;
        };
      }>(`${this.baseUrl}/${workspaceId}/llm-settings`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取所有级别的 LLM 配置设置（用户级、工作区级）
  async getLLMSettingsAllLevels(workspaceId: string): Promise<{
    success: boolean;
    settings: {
      user: Array<{
        name: string;
        source: string;
        is_default: boolean;
        config: unknown;
      }>;
      workspace: Array<{
        name: string;
        source: string;
        is_default: boolean;
        config: unknown;
      }>;
      current_config: string | null;
      mode_configs: Record<string, string>;
    };
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        settings: {
          user: Array<{
            name: string;
            source: string;
            is_default: boolean;
            config: unknown;
          }>;
          workspace: Array<{
            name: string;
            source: string;
            is_default: boolean;
            config: unknown;
          }>;
          current_config: string | null;
          mode_configs: Record<string, string>;
        };
      }>(`${this.baseUrl}/${workspaceId}/llm-settings-all`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 创建 LLM Provider
  async createLLMProvider(
    workspaceId: string,
    data: {
      name: string;
      apiProvider: string;
      openAiBaseUrl?: string;
      openAiApiKey?: string;
      openAiModelId?: string;
      openAiLegacyFormat?: boolean;
      ollamaBaseUrl?: string;
      ollamaModelId?: string;
      ollamaApiKey?: string;
      openAiCustomModelInfo?: Record<string, unknown>;
      diffEnabled?: boolean;
      todoListEnabled?: boolean;
      fuzzyMatchThreshold?: number;
      rateLimitSeconds?: number;
      consecutiveMistakeLimit?: number;
      enableReasoningEffort?: boolean;
      saveLocation?: 'user' | 'workspace';  // 新增：保存位置
    }
  ): Promise<{
    success: boolean;
    message: string;
    provider: {
      name: string;
      id: string;
      config: unknown;
      location?: string;  // 新增：返回保存位置
    };
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        provider: {
          name: string;
          id: string;
          config: unknown;
        };
      }>(`${this.baseUrl}/${workspaceId}/llm-providers`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 LLM Provider
  async updateLLMProvider(
    workspaceId: string,
    providerName: string,
    data: {
      name: string;
      apiProvider: string;
      openAiBaseUrl?: string;
      openAiApiKey?: string;
      openAiModelId?: string;
      openAiLegacyFormat?: boolean;
      ollamaBaseUrl?: string;
      ollamaModelId?: string;
      ollamaApiKey?: string;
      openAiCustomModelInfo?: Record<string, unknown>;
      diffEnabled?: boolean;
      todoListEnabled?: boolean;
      fuzzyMatchThreshold?: number;
      rateLimitSeconds?: number;
      consecutiveMistakeLimit?: number;
      enableReasoningEffort?: boolean;
    }
  ): Promise<{
    success: boolean;
    message: string;
    provider: {
      name: string;
      id: string;
      config: unknown;
    };
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        message: string;
        provider: {
          name: string;
          id: string;
          config: unknown;
        };
      }>(`${this.baseUrl}/${workspaceId}/llm-providers/${providerName}`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Test LLM Provider Tool Call support
  async testLLMProvider(
    workspaceId: string,
    data: {
      name: string;
      apiProvider: string;
      openAiBaseUrl?: string;
      openAiApiKey?: string;
      openAiModelId?: string;
      openAiLegacyFormat?: boolean;
      openAiHeaders?: Record<string, string>;
      ollamaBaseUrl?: string;
      ollamaModelId?: string;
      ollamaApiKey?: string;
    }
  ): Promise<{
    success: boolean;
    supported: boolean;
    message: string;
    model?: string;
  }> {
    try {
      // LLM provider test needs longer timeout (60s) for API calls
      return await httpClient.post<{
        success: boolean;
        supported: boolean;
        message: string;
        model?: string;
      }>(`${this.baseUrl}/${workspaceId}/llm-providers/test`, data, { timeout: 60000 });
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 删除 LLM Provider
  async deleteLLMProvider(
    workspaceId: string,
    providerName: string
  ): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      return await httpClient.delete<{
        success: boolean;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/llm-providers/${providerName}`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // ==================== Configuration Reload API ====================

  // 重新加载工作区配置
  async reloadWorkspaceConfig(
    workspaceId: string,
    configType: 'all' | 'skills' | 'modes' | 'tools' = 'all',
    force: boolean = true
  ): Promise<{
    success: boolean;
    message: string;
    details: {
      skills?: string | number;
      skills_count?: number;
      modes?: string | number;
      modes_count?: number;
      tools?: string | number;
      tools_count?: number;
    };
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        details: {
          skills?: string | number;
          skills_count?: number;
          modes?: string | number;
          modes_count?: number;
          tools?: string | number;
          tools_count?: number;
        };
      }>(
        `${this.baseUrl}/${workspaceId}/reload-config`,
        {
          config_type: configType,
          force
        }
      );
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // ==================== Mode Settings API ====================

  // 获取 Mode 设置
  async getModeSettings(workspaceId: string): Promise<{
    success: boolean;
    settings: {
      customModes: unknown[];
      mcpServers: Record<string, unknown>;
    };
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        settings: {
          customModes: unknown[];
          mcpServers: Record<string, unknown>;
        };
      }>(`${this.baseUrl}/${workspaceId}/mode-settings`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 Mode 设置
  async updateModeSettings(
    workspaceId: string,
    data: {
      customModes: unknown[];
    }
  ): Promise<{
    success: boolean;
    message: string;
    customModes: unknown[];
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        customModes: unknown[];
      }>(`${this.baseUrl}/${workspaceId}/mode-settings`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 MCP 设置
  async updateMcpSettings(
    workspaceId: string,
    data: {
      mcpServers: Record<string, unknown>;
    }
  ): Promise<{
    success: boolean;
    message: string;
    mcpServers: Record<string, unknown>;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        mcpServers: Record<string, unknown>;
      }>(`${this.baseUrl}/${workspaceId}/mcp-settings`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 创建 Mode
  async createMode(
    workspaceId: string,
    data: {
      slug: string;
      name: string;
      description: string;
      roleDefinition: string;
      whenToUse: string;
      groups?: unknown[];
      customInstructions?: string;
    }
  ): Promise<{
    success: boolean;
    message: string;
    mode: unknown;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        message: string;
        mode: unknown;
      }>(`${this.baseUrl}/${workspaceId}/modes`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 Mode
  async updateMode(
    workspaceId: string,
    modeSlug: string,
    data: {
      slug: string;
      name: string;
      description: string;
      roleDefinition: string;
      whenToUse: string;
      groups?: unknown[];
      customInstructions?: string;
    }
  ): Promise<{
    success: boolean;
    message: string;
    mode: unknown;
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        message: string;
        mode: unknown;
      }>(`${this.baseUrl}/${workspaceId}/modes/${modeSlug}`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 删除 Mode
  async deleteMode(
    workspaceId: string,
    modeSlug: string
  ): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      return await httpClient.delete<{
        success: boolean;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/modes/${modeSlug}`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取 Mode 的 rules.md 内容（支持多个文件）
  async getModeRules(
    workspaceId: string,
    modeSlug: string
  ): Promise<{
    success: boolean;
    rules: Record<string, string>;  // key 是完整文件名（含 .md 扩展名），value 是文件内容
    directory: string | null;
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        rules: Record<string, string>;  // key 是完整文件名（含 .md 扩展名），value 是文件内容
        directory: string | null;
      }>(`${this.baseUrl}/${workspaceId}/modes/${modeSlug}/rules`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新 Mode 的 rules.md 内容（支持多个文件）
  async updateModeRules(
    workspaceId: string,
    modeSlug: string,
    rules: Record<string, string>  // key 是完整文件名（含 .md 扩展名），value 是文件内容
  ): Promise<{
    success: boolean;
    message: string;
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/modes/${modeSlug}/rules`, {
        rules
      });
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取 Mode 列表
  async getModes(workspaceId: string, reload?: boolean): Promise<{
    success: boolean;
    modes: Array<{
      slug: string;
      name: string;
      description: string;
      is_default: boolean;
      source: 'system' | 'user' | 'workspace';
    }>;
  }> {
    try {
      const params = reload ? { reload: true } : undefined;
      return await httpClient.get<{
        success: boolean;
        modes: Array<{
          slug: string;
          name: string;
          description: string;
          is_default: boolean;
          source: 'system' | 'user' | 'workspace';
        }>;
      }>(`${this.baseUrl}/${workspaceId}/modes`, params);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // ==================== Workspace Configuration API ====================

  // 获取工作区配置
  async getWorkspaceConfig(workspaceId: string): Promise<{
    success: boolean;
    config: Record<string, unknown>;
    message?: string;
  }> {
    try {
      return await httpClient.get<{
        success: boolean;
        config: Record<string, unknown>;
        message?: string;
      }>(`${this.baseUrl}/${workspaceId}/config`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新工作区配置
  async updateWorkspaceConfig(
    workspaceId: string,
    data: {
      agent?: Record<string, unknown>;
      checkpoint?: Record<string, unknown>;
      compression?: Record<string, unknown>;
      memory?: Record<string, unknown>;
      skills?: Record<string, unknown>;
      tools?: Record<string, unknown>;
      logging?: Record<string, unknown>;
      monitoring?: Record<string, unknown>;
      analytics?: Record<string, unknown>;
    }
  ): Promise<{
    success: boolean;
    config: Record<string, unknown>;
    message: string;
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        config: Record<string, unknown>;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/config`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 重置工作区配置为默认值
  async resetWorkspaceConfig(workspaceId: string): Promise<{
    success: boolean;
    config: Record<string, unknown>;
    message: string;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        config: Record<string, unknown>;
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/config/reset`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // ==================== Plugins Configuration API (两层配置系统) ====================

  // 获取所有插件配置
  async getPluginsConfig(workspaceId: string): Promise<{
    success: boolean;
    config: {
      plugins: Record<string, {
        enabled: boolean;
        activated: boolean;
        settings: Record<string, unknown>;
        version?: string;
        install_path?: string;
      }>;
      max_plugins: number;
      auto_discovery: boolean;
      enabled: boolean;
    };
    message?: string;
  }> {
    try {
      const response = await httpClient.get<{
        success: boolean;
        config: {
          plugins: Record<string, {
            enabled: boolean;
            activated: boolean;
            settings: Record<string, unknown>;
            version?: string;
            install_path?: string;
          }>;
          max_plugins: number;
          auto_discovery: boolean;
          enabled: boolean;
        };
        message?: string;
      }>(`${this.baseUrl}/${workspaceId}/plugins/config`);
      return response;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新插件配置（批量更新）
  async updatePluginsConfig(
    workspaceId: string,
    data: {
      plugins?: Record<string, {
        enabled?: boolean;
        activated?: boolean;
        settings?: Record<string, unknown>;
        version?: string;
        install_path?: string;
      }>;
      max_plugins?: number;
      auto_discovery?: boolean;
      enabled?: boolean;
    }
  ): Promise<{
    success: boolean;
    config: {
      plugins: Record<string, unknown>;
      max_plugins: number;
      auto_discovery: boolean;
      enabled: boolean;
    };
    message: string;
  }> {
    try {
      return await httpClient.put<{
        success: boolean;
        config: {
          plugins: Record<string, unknown>;
          max_plugins: number;
          auto_discovery: boolean;
          enabled: boolean;
        };
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/plugins/config`, data);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 重置插件配置为默认值
  async resetPluginsConfig(workspaceId: string): Promise<{
    success: boolean;
    config: {
      plugins: Record<string, unknown>;
      max_plugins: number;
      auto_discovery: boolean;
      enabled: boolean;
    };
    message: string;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        config: {
          plugins: Record<string, unknown>;
          max_plugins: number;
          auto_discovery: boolean;
          enabled: boolean;
        };
        message: string;
      }>(`${this.baseUrl}/${workspaceId}/plugins/config/reset`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 获取单个插件配置
  async getPluginConfig(
    workspaceId: string,
    pluginId: string
  ): Promise<{
    plugin_id: string;
    exists: boolean;
    enabled: boolean;
    activated: boolean;
    settings: Record<string, unknown>;
    version: string | null;
    install_path: string | null;
  }> {
    try {
      return await httpClient.get<{
        plugin_id: string;
        exists: boolean;
        enabled: boolean;
        activated: boolean;
        settings: Record<string, unknown>;
        version: string | null;
        install_path: string | null;
      }>(`${this.baseUrl}/${workspaceId}/plugins/${pluginId}/config/new`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 更新单个插件配置 - 统一使用 /plugin-config/config API
  async updatePluginConfig(
    workspaceId: string,
    pluginId: string,
    data: {
      enabled?: boolean;
      settings?: Record<string, unknown>;
    }
  ): Promise<{
    success: boolean;
    plugin_id: string;
    enabled: boolean;
    activated: boolean;
    settings: Record<string, unknown>;
    version: string | null;
    install_path: string | null;
  }> {
    try {
      // 使用统一的 plugin-config/config API
      // 提取纯配置数据（去除 enabled, activated）
      const { settings, ...configOnly } = data;

      const payload = {
        plugin_id: pluginId,
        config: settings || configOnly || {}
      };

      const response = await httpClient.put<{
        success: boolean;
        plugin_id: string;
        enabled: boolean;
        activated: boolean;
        settings: Record<string, unknown>;
        version: string | null;
        install_path: string | null;
      }>(
        `${this.baseUrl}/${workspaceId}/plugin-config/config`,
        payload
      );

      return response;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 启用插件
  async enablePlugin(workspaceId: string, pluginId: string): Promise<{
    success: boolean;
    plugin_id: string;
    enabled: boolean;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        plugin_id: string;
        enabled: boolean;
      }>(`${this.baseUrl}/${workspaceId}/plugins/${pluginId}/enable`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 禁用插件
  async disablePlugin(workspaceId: string, pluginId: string): Promise<{
    success: boolean;
    plugin_id: string;
    enabled: boolean;
  }> {
    try {
      return await httpClient.post<{
        success: boolean;
        plugin_id: string;
        enabled: boolean;
      }>(`${this.baseUrl}/${workspaceId}/plugins/${pluginId}/disable`);
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // 错误处理
  private handleError(error: unknown): never {
    if (error && typeof error === 'object' && 'response' in error) {
      const err = error as { response?: { data?: { message?: string } } };
      if (err.response?.data?.message) {
        throw new Error(err.response.data.message);
      }
    }
    throw error;
  }

}

// 创建工作区API服务实例
export const workspacesApi = new WorkspacesApiService();

// 导出便捷函数
export const {
  getWorkspaces,
  getWorkspaceInfo,
  createWorkspace,
  updateWorkspace,
  deleteWorkspace,
  validatePath,
  getConversations,
  createConversation,
  updateConversation,
  getConversationById,
  deleteConversation,
  deleteAllConversations,
  getFileTree,
  getOpenFiles,
  setActiveWorkspace,
  getWorkspaceStats,
  getGlobalStats,
  searchWorkspace,
  exportWorkspace,
  importWorkspace,
  cloneWorkspace,
  getWorkspaceMembers,
  inviteMember,
  removeMember,
  updateMemberRole,
  getUIEnvironments,
  updateUIEnvironments,
  getProxyConfig,
  updateProxyConfig,
  getUIContext,
  updateUIContext,
  getSystemEnvironments,
  updateSystemEnvironments,
  createFileOrDirectory,
  deleteFileOrDirectory,
  copyFileOrDirectory,
  renameFileOrDirectory,
  downloadFileOrDirectory,
  getLLMSettings,
  getLLMSettingsAllLevels,
  updateLLMSettings,
  createLLMProvider,
  updateLLMProvider,
  testLLMProvider,
  deleteLLMProvider,
  getModeSettings,
  updateModeSettings,
  updateMcpSettings,
  createMode,
  updateMode,
  deleteMode,
  getModeRules,
  getModes,
  getWorkspaceConfig,
  updateWorkspaceConfig,
  resetWorkspaceConfig,
  getPluginsConfig,
  updatePluginsConfig,
  resetPluginsConfig,
  getPluginConfig,
  updatePluginConfig,
  enablePlugin,
  disablePlugin,
  reloadWorkspaceConfig,
  getMCPServers,
  createMCPServer,
  updateMCPServer,
  deleteMCPServer,
  testMCPServer
} = {
  getWorkspaces: workspacesApi.getWorkspaces.bind(workspacesApi),
  getWorkspaceInfo: workspacesApi.getWorkspaceInfo.bind(workspacesApi),
  createWorkspace: workspacesApi.createWorkspace.bind(workspacesApi),
  updateWorkspace: workspacesApi.updateWorkspace.bind(workspacesApi),
  deleteWorkspace: workspacesApi.deleteWorkspace.bind(workspacesApi),
  getConversations: workspacesApi.getConversations.bind(workspacesApi),
  getConversationById: workspacesApi.getConversationById.bind(workspacesApi),
  deleteConversation: workspacesApi.deleteConversation.bind(workspacesApi),
  deleteAllConversations: workspacesApi.deleteAllConversations.bind(workspacesApi),
  getFileTree: workspacesApi.getFileTree.bind(workspacesApi),
  getOpenFiles: workspacesApi.getOpenFiles.bind(workspacesApi),
  setActiveWorkspace: workspacesApi.setActiveWorkspace.bind(workspacesApi),
  getWorkspaceStats: workspacesApi.getWorkspaceStats.bind(workspacesApi),
  getGlobalStats: workspacesApi.getGlobalStats.bind(workspacesApi),
  searchWorkspace: workspacesApi.searchWorkspace.bind(workspacesApi),
  exportWorkspace: workspacesApi.exportWorkspace.bind(workspacesApi),
  importWorkspace: workspacesApi.importWorkspace.bind(workspacesApi),
  cloneWorkspace: workspacesApi.cloneWorkspace.bind(workspacesApi),
  getWorkspaceMembers: workspacesApi.getWorkspaceMembers.bind(workspacesApi),
  inviteMember: workspacesApi.inviteMember.bind(workspacesApi),
  removeMember: workspacesApi.removeMember.bind(workspacesApi),
  updateMemberRole: workspacesApi.updateMemberRole.bind(workspacesApi),
  getUIEnvironments: workspacesApi.getUIEnvironments.bind(workspacesApi),
  updateUIEnvironments: workspacesApi.updateUIEnvironments.bind(workspacesApi),
  getProxyConfig: workspacesApi.getProxyConfig.bind(workspacesApi),
  updateProxyConfig: workspacesApi.updateProxyConfig.bind(workspacesApi),
  getUIContext: workspacesApi.getUIContext.bind(workspacesApi),
  updateUIContext: workspacesApi.updateUIContext.bind(workspacesApi),
  getSystemEnvironments: workspacesApi.getSystemEnvironments.bind(workspacesApi),
  updateSystemEnvironments: workspacesApi.updateSystemEnvironments.bind(workspacesApi),
  createFileOrDirectory: workspacesApi.createFileOrDirectory.bind(workspacesApi),
  deleteFileOrDirectory: workspacesApi.deleteFileOrDirectory.bind(workspacesApi),
  copyFileOrDirectory: workspacesApi.copyFileOrDirectory.bind(workspacesApi),
  renameFileOrDirectory: workspacesApi.renameFileOrDirectory.bind(workspacesApi),
  downloadFileOrDirectory: workspacesApi.downloadFileOrDirectory.bind(workspacesApi),
  getLLMSettings: workspacesApi.getLLMSettings.bind(workspacesApi),
  getLLMSettingsAllLevels: workspacesApi.getLLMSettingsAllLevels.bind(workspacesApi),
  updateLLMSettings: workspacesApi.updateLLMSettings.bind(workspacesApi),
  createLLMProvider: workspacesApi.createLLMProvider.bind(workspacesApi),
  updateLLMProvider: workspacesApi.updateLLMProvider.bind(workspacesApi),
  testLLMProvider: workspacesApi.testLLMProvider.bind(workspacesApi),
  deleteLLMProvider: workspacesApi.deleteLLMProvider.bind(workspacesApi),
  getModeSettings: workspacesApi.getModeSettings.bind(workspacesApi),
  updateModeSettings: workspacesApi.updateModeSettings.bind(workspacesApi),
  updateMcpSettings: workspacesApi.updateMcpSettings.bind(workspacesApi),
  createMode: workspacesApi.createMode.bind(workspacesApi),
  updateMode: workspacesApi.updateMode.bind(workspacesApi),
  deleteMode: workspacesApi.deleteMode.bind(workspacesApi),
  getModeRules: workspacesApi.getModeRules.bind(workspacesApi),
  getModes: workspacesApi.getModes.bind(workspacesApi),
  getWorkspaceConfig: workspacesApi.getWorkspaceConfig.bind(workspacesApi),
  updateWorkspaceConfig: workspacesApi.updateWorkspaceConfig.bind(workspacesApi),
  resetWorkspaceConfig: workspacesApi.resetWorkspaceConfig.bind(workspacesApi),
  getPluginsConfig: workspacesApi.getPluginsConfig.bind(workspacesApi),
  updatePluginsConfig: workspacesApi.updatePluginsConfig.bind(workspacesApi),
  resetPluginsConfig: workspacesApi.resetPluginsConfig.bind(workspacesApi),
  getPluginConfig: workspacesApi.getPluginConfig.bind(workspacesApi),
  updatePluginConfig: workspacesApi.updatePluginConfig.bind(workspacesApi),
  enablePlugin: workspacesApi.enablePlugin.bind(workspacesApi),
  disablePlugin: workspacesApi.disablePlugin.bind(workspacesApi),
  reloadWorkspaceConfig: workspacesApi.reloadWorkspaceConfig.bind(workspacesApi),
  getMCPServers: workspacesApi.getMCPServers.bind(workspacesApi),
  createMCPServer: workspacesApi.createMCPServer.bind(workspacesApi),
  updateMCPServer: workspacesApi.updateMCPServer.bind(workspacesApi),
  deleteMCPServer: workspacesApi.deleteMCPServer.bind(workspacesApi),
  testMCPServer: workspacesApi.testMCPServer.bind(workspacesApi),
  validatePath: workspacesApi.validatePath.bind(workspacesApi)
};