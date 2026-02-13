/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 任务 API 服务

import { httpClient } from "../http"
import type {
  TaskListItem,
  TaskDetail,
  TaskSummary,
  TaskStatistics,
  TaskProgress,
  TaskSearchParams,
  TaskSearchResult,
  BatchTaskOperationRequest,
  BatchTaskOperationResponse,
} from "../../types/task"

// 任务 API 服务类
export class TasksApiService {
  private baseUrl = "/tasks"

  // 获取任务列表
  async getTasks(params?: TaskSearchParams): Promise<TaskListItem[]> {
    return await httpClient.get<TaskListItem[]>(this.baseUrl, params)
  }

  // 搜索任务
  async searchTasks(params: TaskSearchParams): Promise<TaskSearchResult> {
    return await httpClient.get<TaskSearchResult>(`${this.baseUrl}/search`, params)
  }

  // 获取任务详情
  async getTask(taskId: string): Promise<TaskDetail> {
    return await httpClient.get<TaskDetail>(`${this.baseUrl}/${taskId}`)
  }

  // 获取任务摘要
  async getTaskSummary(taskId: string): Promise<TaskSummary> {
    return await httpClient.get<TaskSummary>(`${this.baseUrl}/${taskId}/summary`)
  }

  // 获取任务统计
  async getTaskStats(taskId: string): Promise<TaskStatistics> {
    return await httpClient.get<TaskStatistics>(`${this.baseUrl}/${taskId}/stats`)
  }

  // 获取任务进度
  async getTaskProgress(taskId: string): Promise<TaskProgress> {
    return await httpClient.get<TaskProgress>(`${this.baseUrl}/${taskId}/progress`)
  }

  // 取消任务
  async cancelTask(taskId: string, reason?: string): Promise<TaskDetail> {
    return await httpClient.post<TaskDetail>(
      `${this.baseUrl}/${taskId}/cancel`,
      { reason }
    )
  }

  // 暂停任务
  async pauseTask(taskId: string, reason?: string): Promise<TaskDetail> {
    return await httpClient.post<TaskDetail>(
      `${this.baseUrl}/${taskId}/pause`,
      { reason }
    )
  }

  // 恢复任务
  async resumeTask(taskId: string, reason?: string): Promise<TaskDetail> {
    return await httpClient.post<TaskDetail>(
      `${this.baseUrl}/${taskId}/resume`,
      { reason }
    )
  }

  // 重试任务
  async retryTask(taskId: string): Promise<TaskDetail> {
    return await httpClient.post<TaskDetail>(`${this.baseUrl}/${taskId}/retry`)
  }

  // 批量操作任务
  async batchOperation(
    data: BatchTaskOperationRequest
  ): Promise<BatchTaskOperationResponse> {
    return await httpClient.post<BatchTaskOperationResponse>(
      `${this.baseUrl}/batch`,
      data
    )
  }

  // 获取运行中的任务
  async getRunningTasks(): Promise<TaskListItem[]> {
    return await httpClient.get<TaskListItem[]>(`${this.baseUrl}/running`)
  }

  // 获取最近任务
  async getRecentTasks(limit?: number): Promise<TaskListItem[]> {
    return await httpClient.get<TaskListItem[]>(`${this.baseUrl}/recent`, {
      limit,
    })
  }

  // 获取任务统计概览
  async getTasksOverview(): Promise<{
    total: number
    running: number
    completed: number
    failed: number
  }> {
    return await httpClient.get(`${this.baseUrl}/overview`)
  }
}

// 创建任务 API 服务实例
export const tasksApi = new TasksApiService()

// 导出便捷函数
export const {
  getTasks,
  searchTasks,
  getTask,
  getTaskSummary,
  getTaskStats,
  getTaskProgress,
  cancelTask,
  pauseTask,
  resumeTask,
  retryTask,
  batchOperation,
  getRunningTasks,
  getRecentTasks,
  getTasksOverview,
} = {
  getTasks: tasksApi.getTasks.bind(tasksApi),
  searchTasks: tasksApi.searchTasks.bind(tasksApi),
  getTask: tasksApi.getTask.bind(tasksApi),
  getTaskSummary: tasksApi.getTaskSummary.bind(tasksApi),
  getTaskStats: tasksApi.getTaskStats.bind(tasksApi),
  getTaskProgress: tasksApi.getTaskProgress.bind(tasksApi),
  cancelTask: tasksApi.cancelTask.bind(tasksApi),
  pauseTask: tasksApi.pauseTask.bind(tasksApi),
  resumeTask: tasksApi.resumeTask.bind(tasksApi),
  retryTask: tasksApi.retryTask.bind(tasksApi),
  batchOperation: tasksApi.batchOperation.bind(tasksApi),
  getRunningTasks: tasksApi.getRunningTasks.bind(tasksApi),
  getRecentTasks: tasksApi.getRecentTasks.bind(tasksApi),
  getTasksOverview: tasksApi.getTasksOverview.bind(tasksApi),
}
