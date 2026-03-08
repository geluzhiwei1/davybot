/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';
import type {
  ScheduledTask,
  ScheduledTaskExecution,
  ScheduledTasksListResponse,
  ScheduledTaskExecutionsResponse
} from '../types';

// 定时任务API服务类
export class ScheduledTasksApiService {
  private baseUrl = '/workspaces';

  // 获取工作区的所有定时任务
  async getScheduledTasks(workspaceId: string): Promise<ScheduledTasksListResponse> {
    return await httpClient.get<ScheduledTasksListResponse>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks`
    );
  }

  // 创建新的定时任务
  async createScheduledTask(
    workspaceId: string,
    task: {
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
    }
  ): Promise<{ success: boolean; task: ScheduledTask; message: string }> {
    return await httpClient.post<{ success: boolean; task: ScheduledTask; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks`,
      task
    );
  }

  // 获取单个定时任务详情
  async getScheduledTask(
    workspaceId: string,
    taskId: string
  ): Promise<{ success: boolean; task: ScheduledTask }> {
    return await httpClient.get<{ success: boolean; task: ScheduledTask }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}`
    );
  }

  // 更新定时任务
  async updateScheduledTask(
    workspaceId: string,
    taskId: string,
    updates: {
      description?: string;
      schedule_type?: 'delay' | 'at_time' | 'recurring' | 'cron';
      trigger_time?: string;
      repeat_interval?: number;
      max_repeats?: number;
      cron_expression?: string;
      execution_type?: 'message';
      execution_data?: {
        message?: string;
        llm?: string;
        mode?: string;
      };
      status?: 'pending' | 'paused' | 'triggered' | 'completed' | 'failed' | 'cancelled';
    }
  ): Promise<{ success: boolean; task: ScheduledTask; message: string }> {
    return await httpClient.put<{ success: boolean; task: ScheduledTask; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}`,
      updates
    );
  }

  // 删除定时任务
  async deleteScheduledTask(
    workspaceId: string,
    taskId: string
  ): Promise<{ success: boolean; message: string }> {
    return await httpClient.delete<{ success: boolean; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}`
    );
  }

  // 暂停定时任务
  async pauseScheduledTask(
    workspaceId: string,
    taskId: string
  ): Promise<{ success: boolean; message: string }> {
    return await httpClient.post<{ success: boolean; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}/pause`
    );
  }

  // 恢复定时任务
  async resumeScheduledTask(
    workspaceId: string,
    taskId: string
  ): Promise<{ success: boolean; message: string }> {
    return await httpClient.post<{ success: boolean; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}/resume`
    );
  }

  // 获取定时任务的执行历史
  async getTaskExecutions(
    workspaceId: string,
    taskId: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<ScheduledTaskExecutionsResponse> {
    return await httpClient.get<ScheduledTaskExecutionsResponse>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}/executions`,
      { params: { page, page_size: pageSize } }
    );
  }

  // 手动触发定时任务
  async triggerScheduledTask(
    workspaceId: string,
    taskId: string
  ): Promise<{ success: boolean; message: string }> {
    return await httpClient.post<{ success: boolean; message: string }>(
      `${this.baseUrl}/${workspaceId}/scheduled-tasks/${taskId}/trigger`
    );
  }
}

// 创建定时任务API服务实例
export const scheduledTasksApi = new ScheduledTasksApiService();

// 导出便捷函数
export const {
  getScheduledTasks,
  createScheduledTask,
  getScheduledTask,
  updateScheduledTask,
  deleteScheduledTask,
  pauseScheduledTask,
  resumeScheduledTask,
  getTaskExecutions,
  triggerScheduledTask
} = {
  getScheduledTasks: scheduledTasksApi.getScheduledTasks.bind(scheduledTasksApi),
  createScheduledTask: scheduledTasksApi.createScheduledTask.bind(scheduledTasksApi),
  getScheduledTask: scheduledTasksApi.getScheduledTask.bind(scheduledTasksApi),
  updateScheduledTask: scheduledTasksApi.updateScheduledTask.bind(scheduledTasksApi),
  deleteScheduledTask: scheduledTasksApi.deleteScheduledTask.bind(scheduledTasksApi),
  pauseScheduledTask: scheduledTasksApi.pauseScheduledTask.bind(scheduledTasksApi),
  resumeScheduledTask: scheduledTasksApi.resumeScheduledTask.bind(scheduledTasksApi),
  getTaskExecutions: scheduledTasksApi.getTaskExecutions.bind(scheduledTasksApi),
  triggerScheduledTask: scheduledTasksApi.triggerScheduledTask.bind(scheduledTasksApi)
};
