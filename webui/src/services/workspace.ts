/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Workspace Service
 *
 * 工作区 CRUD API 服务
 */

import axios from 'axios'

/**
 * 工作区信息（基础信息，来自 workspaces.json）
 */
export interface WorkspaceBasic {
  id: string
  name: string
  path: string
  created_at: string
  is_active: boolean
}

/**
 * 工作区详细信息（来自 workspace.json）
 */
export interface WorkspaceDetail extends WorkspaceBasic {
  display_name: string
  description?: string
  files_list?: string[]
  system_environments?: unknown
  user_ui_environments?: unknown
  user_ui_context?: unknown
}

/**
 * 创建工作区请求
 */
export interface CreateWorkspaceRequest {
  path: string
  name?: string
  display_name?: string
  description?: string
}

/**
 * 更新工作区请求
 */
export interface UpdateWorkspaceRequest {
  display_name?: string
  description?: string
  is_active?: boolean
}

/**
 * 路径验证请求
 */
export interface ValidatePathRequest {
  path: string
}

/**
 * 路径验证响应
 */
export interface ValidatePathResponse {
  success: boolean
  valid: boolean
  message: string
  exists: boolean
  writable?: boolean
  is_empty?: boolean
  is_workspace?: boolean
}

/**
 * 工作区列表响应
 */
export interface WorkspaceListResponse {
  success: boolean
  workspaces: WorkspaceBasic[]
  total: number
}

/**
 * 工作区响应
 */
export interface WorkspaceResponse {
  success: boolean
  workspace?: WorkspaceDetail
  message?: string
  error?: string
}

/**
 * Workspace Service
 */
export const workspaceService = {
  /**
   * 验证工作区路径
   */
  async validatePath(data: ValidatePathRequest): Promise<ValidatePathResponse> {
    const response = await axios.post<ValidatePathResponse>('/api/workspaces/workspaces/validate-path', data)
    return response.data
  },

  /**
   * 获取工作区列表
   */
  async getWorkspaces(params?: {
    include_inactive?: boolean
  }): Promise<WorkspaceListResponse> {
    const response = await axios.get<WorkspaceListResponse>('/api/workspaces/workspaces', { params })
    return response.data
  },

  /**
   * 获取工作区详情
   */
  async getWorkspaceInfo(workspaceId: string): Promise<WorkspaceResponse> {
    const response = await axios.get<WorkspaceResponse>(`/api/workspaces/workspaces/${workspaceId}/info`)
    return response.data
  },

  /**
   * 创建工作区
   */
  async createWorkspace(data: CreateWorkspaceRequest): Promise<WorkspaceResponse> {
    const response = await axios.post<WorkspaceResponse>('/api/workspaces/workspaces', data)
    return response.data
  },

  /**
   * 更新工作区
   */
  async updateWorkspace(
    workspaceId: string,
    data: UpdateWorkspaceRequest
  ): Promise<WorkspaceResponse> {
    const response = await axios.put<WorkspaceResponse>(`/api/workspaces/workspaces/${workspaceId}`, data)
    return response.data
  },

  /**
   * 删除工作区
   */
  async deleteWorkspace(
    workspaceId: string,
    deleteConfig?: boolean,
    deleteFiles?: boolean
  ): Promise<WorkspaceResponse> {
    const queryParams = new URLSearchParams()
    if (deleteConfig !== undefined) queryParams.append('delete_config', String(deleteConfig))
    if (deleteFiles !== undefined) queryParams.append('delete_files', String(deleteFiles))

    const response = await axios.delete<WorkspaceResponse>(
      `/api/workspaces/workspaces/${workspaceId}?${queryParams.toString()}`
    )
    return response.data
  }
}

export default workspaceService
