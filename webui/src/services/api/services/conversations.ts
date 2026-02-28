/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';
import type {
  Conversation,
  Message,
  Task,
  PaginatedResponse,
  PaginationParams
} from '../types';

// 对话API服务类
export class ConversationsApiService {
  private baseUrl = '/conversations';

  // 获取对话列表
  async getConversations(params?: {
    workspaceId?: string;
    page?: number;
    limit?: number;
    sortBy?: 'createdAt' | 'updatedAt' | 'lastMessageAt';
    sortOrder?: 'asc' | 'desc';
    search?: string;
    isArchived?: boolean;
    tags?: string[];
    task_type?: 'user' | 'scheduled' | null;
  }): Promise<PaginatedResponse<Conversation>> {
    // Backend endpoint is /api/workspaces/{workspace_id}/conversations
    if (params?.workspaceId) {
      const { workspaceId, task_type, ...queryParams } = params;  // ✅ 从 params 中分离 workspaceId 和 task_type
      return await httpClient.get<PaginatedResponse<Conversation>>(
        `/workspaces/${workspaceId}/conversations`,
        { ...queryParams, taskType: task_type }  // ✅ 只传其他参数作为 query params, 转换 task_type 为 taskType
      );
    }
    return await httpClient.get<PaginatedResponse<Conversation>>(this.baseUrl, params);
  }

  // 获取对话详情
  async getConversation(conversationId: string): Promise<Conversation> {
    return await httpClient.get<Conversation>(`${this.baseUrl}/${conversationId}`);
  }

  // 创建新对话
  async createConversation(data: {
    workspaceId: string;
    title: string;
    message?: string;
    mode?: string;
    tags?: string[];
    metadata?: {
      taskType?: string;
      tools?: string[];
      [key: string]: unknown;
    };
  }): Promise<Conversation> {
    return await httpClient.post<Conversation>(this.baseUrl, data);
  }

  // 更新对话
  async updateConversation(conversationId: string, data: {
    title?: string;
    isArchived?: boolean;
    tags?: string[];
    metadata?: {
      [key: string]: unknown;
    };
  }): Promise<Conversation> {
    return await httpClient.put<Conversation>(`${this.baseUrl}/${conversationId}`, data);
  }

  // 删除对话
  async deleteConversation(conversationId: string, options?: {
    permanent?: boolean;
  }): Promise<void> {
    const params = options || {};
    return await httpClient.delete<void>(`${this.baseUrl}/${conversationId}`, { params });
  }

  // 归档对话
  async archiveConversation(conversationId: string): Promise<Conversation> {
    return await httpClient.post<Conversation>(`${this.baseUrl}/${conversationId}/archive`);
  }

  // 取消归档对话
  async unarchiveConversation(conversationId: string): Promise<Conversation> {
    return await httpClient.post<Conversation>(`${this.baseUrl}/${conversationId}/unarchive`);
  }

  // 复制对话
  async duplicateConversation(conversationId: string, data: {
    title?: string;
    workspaceId?: string;
    includeMessages?: boolean;
  }): Promise<Conversation> {
    return await httpClient.post<Conversation>(`${this.baseUrl}/${conversationId}/duplicate`, data);
  }

  // 获取对话消息
  async getMessages(conversationId: string, params?: PaginationParams & {
    messageType?: 'user' | 'assistant' | 'system';
    since?: string;
    until?: string;
  }): Promise<PaginatedResponse<Message>> {
    return await httpClient.get<PaginatedResponse<Message>>(
      `${this.baseUrl}/${conversationId}/messages`,
      params
    );
  }

  // 发送消息
  async sendMessage(conversationId: string, data: {
    content: string;
    type?: 'user' | 'system';
    metadata?: {
      files?: unknown[];
      mentions?: unknown[];
      taskId?: string;
      mode?: string;
      [key: string]: unknown;
    };
  }): Promise<Message> {
    return await httpClient.post<Message>(`${this.baseUrl}/${conversationId}/messages`, data);
  }

  // 更新消息
  async updateMessage(conversationId: string, messageId: string, data: {
    content?: string;
    metadata?: {
      [key: string]: unknown;
    };
  }): Promise<Message> {
    return await httpClient.put<Message>(
      `${this.baseUrl}/${conversationId}/messages/${messageId}`,
      data
    );
  }

  // 删除消息
  async deleteMessage(conversationId: string, messageId: string): Promise<void> {
    return await httpClient.delete<void>(
      `${this.baseUrl}/${conversationId}/messages/${messageId}`
    );
  }

  // 获取对话任务
  async getTasks(conversationId: string, params?: PaginationParams & {
    status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
    taskType?: string;
  }): Promise<PaginatedResponse<Task>> {
    return await httpClient.get<PaginatedResponse<Task>>(
      `${this.baseUrl}/${conversationId}/tasks`,
      params
    );
  }

  // 创建任务
  async createTask(conversationId: string, data: {
    type: string;
    input?: unknown;
    metadata?: {
      mode?: string;
      tools?: string[];
      [key: string]: unknown;
    };
  }): Promise<Task> {
    return await httpClient.post<Task>(`${this.baseUrl}/${conversationId}/tasks`, data);
  }

  // 获取任务详情
  async getTask(conversationId: string, taskId: string): Promise<Task> {
    return await httpClient.get<Task>(`${this.baseUrl}/${conversationId}/tasks/${taskId}`);
  }

  // 取消任务
  async cancelTask(conversationId: string, taskId: string): Promise<Task> {
    return await httpClient.post<Task>(`${this.baseUrl}/${conversationId}/tasks/${taskId}/cancel`);
  }

  // 重试任务
  async retryTask(conversationId: string, taskId: string): Promise<Task> {
    return await httpClient.post<Task>(`${this.baseUrl}/${conversationId}/tasks/${taskId}/retry`);
  }

  // 搜索对话
  async searchConversations(params: {
    query: string;
    workspaceId?: string;
    searchIn?: 'title' | 'content' | 'all';
    dateRange?: {
      start: string;
      end: string;
    };
    tags?: string[];
    limit?: number;
  }): Promise<{
    conversations: Array<{
      id: string;
      title: string;
      workspaceId: string;
      lastMessageAt: string;
      messageCount: number;
      matches: Array<{
        messageId: string;
        content: string;
        type: string;
        timestamp: string;
      }>;
      score: number;
    }>;
    total: number;
    searchTime: number;
  }> {
    return await httpClient.get(`${this.baseUrl}/search`, params);
  }

  // 导出对话
  async exportConversation(conversationId: string, params?: {
    format?: 'json' | 'markdown' | 'html' | 'pdf';
    includeMetadata?: boolean;
    includeTasks?: boolean;
  }): Promise<{
    downloadUrl: string;
    filename: string;
    format: string;
    size: number;
    expiresAt: string;
  }> {
    return await httpClient.post(`${this.baseUrl}/${conversationId}/export`, params);
  }

  // 导入对话
  async importConversation(data: {
    workspaceId: string;
    file: File;
    format?: 'json' | 'markdown';
    overwrite?: boolean;
  }): Promise<Conversation> {
    const formData = new FormData();
    formData.append('workspaceId', data.workspaceId);
    formData.append('file', data.file);
    if (data.format) {
      formData.append('format', data.format);
    }
    if (data.overwrite !== undefined) {
      formData.append('overwrite', data.overwrite.toString());
    }

    return await httpClient.upload<Conversation>(`${this.baseUrl}/import`, formData);
  }

  // 获取对话统计
  async getConversationStats(conversationId: string): Promise<{
    messageCount: number;
    userMessageCount: number;
    assistantMessageCount: number;
    systemMessageCount: number;
    taskCount: number;
    completedTaskCount: number;
    failedTaskCount: number;
    totalTokens: number;
    averageResponseTime: number;
    duration: number;
    createdAt: string;
    lastMessageAt: string;
  }> {
    return await httpClient.get(`${this.baseUrl}/${conversationId}/stats`);
  }

  // 获取对话摘要
  async getConversationSummary(conversationId: string, options?: {
    includeTasks?: boolean;
    maxLength?: number;
  }): Promise<{
    summary: string;
    keyPoints: string[];
    tasksCompleted: number;
    topics: string[];
    generatedAt: string;
  }> {
    const params = options || {};
    return await httpClient.get(`${this.baseUrl}/${conversationId}/summary`, params);
  }

  // 标记消息为重要
  async markMessageImportant(conversationId: string, messageId: string): Promise<Message> {
    return await httpClient.post<Message>(
      `${this.baseUrl}/${conversationId}/messages/${messageId}/important`
    );
  }

  // 取消标记消息为重要
  async unmarkMessageImportant(conversationId: string, messageId: string): Promise<Message> {
    return await httpClient.delete<Message>(
      `${this.baseUrl}/${conversationId}/messages/${messageId}/important`
    );
  }

  // 获取重要消息
  async getImportantMessages(conversationId: string): Promise<Message[]> {
    return await httpClient.get<Message[]>(
      `${this.baseUrl}/${conversationId}/messages/important`
    );
  }

}

// 创建对话API服务实例
export const conversationsApi = new ConversationsApiService();

// 导出便捷函数
export const {
  getConversations,
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
} = {
  getConversations: conversationsApi.getConversations.bind(conversationsApi),
  getConversation: conversationsApi.getConversation.bind(conversationsApi),
  createConversation: conversationsApi.createConversation.bind(conversationsApi),
  updateConversation: conversationsApi.updateConversation.bind(conversationsApi),
  deleteConversation: conversationsApi.deleteConversation.bind(conversationsApi),
  archiveConversation: conversationsApi.archiveConversation.bind(conversationsApi),
  unarchiveConversation: conversationsApi.unarchiveConversation.bind(conversationsApi),
  duplicateConversation: conversationsApi.duplicateConversation.bind(conversationsApi),
  getMessages: conversationsApi.getMessages.bind(conversationsApi),
  sendMessage: conversationsApi.sendMessage.bind(conversationsApi),
  updateMessage: conversationsApi.updateMessage.bind(conversationsApi),
  deleteMessage: conversationsApi.deleteMessage.bind(conversationsApi),
  getTasks: conversationsApi.getTasks.bind(conversationsApi),
  createTask: conversationsApi.createTask.bind(conversationsApi),
  getTask: conversationsApi.getTask.bind(conversationsApi),
  cancelTask: conversationsApi.cancelTask.bind(conversationsApi),
  retryTask: conversationsApi.retryTask.bind(conversationsApi),
  searchConversations: conversationsApi.searchConversations.bind(conversationsApi),
  exportConversation: conversationsApi.exportConversation.bind(conversationsApi),
  importConversation: conversationsApi.importConversation.bind(conversationsApi),
  getConversationStats: conversationsApi.getConversationStats.bind(conversationsApi),
  getConversationSummary: conversationsApi.getConversationSummary.bind(conversationsApi),
  markMessageImportant: conversationsApi.markMessageImportant.bind(conversationsApi),
  unmarkMessageImportant: conversationsApi.unmarkMessageImportant.bind(conversationsApi),
  getImportantMessages: conversationsApi.getImportantMessages.bind(conversationsApi)
};