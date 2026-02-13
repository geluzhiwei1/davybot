/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

// 检查点 API 服务

import { httpClient } from "../http"
import type {
  CheckpointListItem,
  CheckpointListResponse,
  CheckpointStatistics,
  CheckpointData,
  CreateCheckpointRequest,
  CreateCheckpointResponse,
  RestoreCheckpointRequest,
  RestoreCheckpointResponse,
} from "../../types/checkpoint"

// 检查点 API 服务类
export class CheckpointsApiService {
  private baseUrl = "/checkpoints"

  // 获取检查点列表
  async getCheckpoints(params?: {
    task_graph_id?: string
    page?: number
    limit?: number
    sort_by?: "created_at" | "size"
    sort_order?: "asc" | "desc"
  }): Promise<CheckpointListResponse> {
    return await httpClient.get<CheckpointListResponse>(this.baseUrl, params)
  }

  // 获取检查点列表（简化版）
  async list(params?: {
    task_graph_id?: string
    page?: number
    limit?: number
  }): Promise<CheckpointListItem[]> {
    return await httpClient.get<CheckpointListItem[]>(`${this.baseUrl}/list`, params)
  }

  // 获取检查点详情
  async getCheckpoint(checkpointId: string): Promise<CheckpointData> {
    return await httpClient.get<CheckpointData>(`${this.baseUrl}/${checkpointId}`)
  }

  // 创建检查点
  async create(
    data: CreateCheckpointRequest
  ): Promise<CreateCheckpointResponse> {
    return await httpClient.post<CreateCheckpointResponse>(
      `${this.baseUrl}/create`,
      data
    )
  }

  // 恢复检查点
  async restore(
    data: RestoreCheckpointRequest
  ): Promise<RestoreCheckpointResponse> {
    return await httpClient.post<RestoreCheckpointResponse>(
      `${this.baseUrl}/restore`,
      data
    )
  }

  // 删除检查点
  async delete(checkpointId: string): Promise<void> {
    return await httpClient.delete<void>(`${this.baseUrl}/${checkpointId}`)
  }

  // 获取检查点统计
  async getStatistics(): Promise<CheckpointStatistics> {
    return await httpClient.get<CheckpointStatistics>(`${this.baseUrl}/statistics`)
  }

  // 获取任务的检查点列表
  async getCheckpointsByTaskGraph(taskGraphId: string): Promise<CheckpointListItem[]> {
    return await httpClient.get<CheckpointListItem[]>(
      `${this.baseUrl}/task-graph/${taskGraphId}`
    )
  }

  // 下载检查点
  async download(checkpointId: string): Promise<Blob> {
    return await httpClient.download(`${this.baseUrl}/${checkpointId}/download`)
  }

  // 上传检查点
  async upload(
    taskGraphId: string,
    file: File
  ): Promise<{ checkpoint_id: string }> {
    const formData = new FormData()
    formData.append("task_graph_id", taskGraphId)
    formData.append("file", file)
    return await httpClient.post<{ checkpoint_id: string }>(
      `${this.baseUrl}/upload`,
      formData
    )
  }

  // 比较两个检查点
  async compare(
    checkpointId1: string,
    checkpointId2: string
  ): Promise<{
    added_nodes: string[]
    removed_nodes: string[]
    modified_nodes: Record<string, unknown>
  }> {
    return await httpClient.get(`${this.baseUrl}/compare`, {
      checkpoint1: checkpointId1,
      checkpoint2: checkpointId2,
    })
  }
}

// 创建检查点 API 服务实例
export const checkpointsApi = new CheckpointsApiService()

// 导出便捷函数
export const {
  getCheckpoints,
  list,
  getCheckpoint,
  create,
  restore,
  delete: deleteCheckpoint,
  getStatistics,
  getCheckpointsByTaskGraph,
  download,
  upload,
  compare,
} = {
  getCheckpoints: checkpointsApi.getCheckpoints.bind(checkpointsApi),
  list: checkpointsApi.list.bind(checkpointsApi),
  getCheckpoint: checkpointsApi.getCheckpoint.bind(checkpointsApi),
  create: checkpointsApi.create.bind(checkpointsApi),
  restore: checkpointsApi.restore.bind(checkpointsApi),
  delete: checkpointsApi.delete.bind(checkpointsApi),
  getStatistics: checkpointsApi.getStatistics.bind(checkpointsApi),
  getCheckpointsByTaskGraph: checkpointsApi.getCheckpointsByTaskGraph.bind(checkpointsApi),
  download: checkpointsApi.download.bind(checkpointsApi),
  upload: checkpointsApi.upload.bind(checkpointsApi),
  compare: checkpointsApi.compare.bind(checkpointsApi),
}
