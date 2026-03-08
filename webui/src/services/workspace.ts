/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Workspace Service
 *
 * 工作区 CRUD API 服务
 */

import { httpClient } from './api/http'

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
 * Workspace CRUD Service
 *
 * 工作区CRUD操作服务
 */
export class WorkspaceCrudService {
  private baseUrl = '/workspaces'

  /**
   * 验证工作区路径
   */
  async validatePath(data: ValidatePathRequest): Promise<ValidatePathResponse> {
    return await httpClient.post<ValidatePathResponse>(`${this.baseUrl}/validate-path`, data)
  }

  /**
   * 获取工作区列表
   */
  async getWorkspaces(params?: {
    include_inactive?: boolean
  }): Promise<WorkspaceListResponse> {
    return await httpClient.get<WorkspaceListResponse>(this.baseUrl, params)
  }

  /**
   * 获取工作区详情
   */
  async getWorkspaceInfo(workspaceId: string): Promise<WorkspaceResponse> {
    return await httpClient.get<WorkspaceResponse>(`${this.baseUrl}/${workspaceId}/info`)
  }

  /**
   * 创建工作区
   */
  async createWorkspace(data: CreateWorkspaceRequest): Promise<WorkspaceResponse> {
    return await httpClient.post<WorkspaceResponse>(this.baseUrl, data)
  }

  /**
   * 更新工作区
   */
  async updateWorkspace(
    workspaceId: string,
    data: UpdateWorkspaceRequest
  ): Promise<WorkspaceResponse> {
    return await httpClient.put<WorkspaceResponse>(`${this.baseUrl}/${workspaceId}`, data)
  }

  /**
   * 删除工作区
   */
  async deleteWorkspace(
    workspaceId: string,
    deleteConfig?: boolean,
    deleteFiles?: boolean
  ): Promise<WorkspaceResponse> {
    const params: Record<string, string> = {}
    if (deleteConfig !== undefined) params.delete_config = String(deleteConfig)
    if (deleteFiles !== undefined) params.delete_files = String(deleteFiles)

    return await httpClient.delete<WorkspaceResponse>(
      `${this.baseUrl}/${workspaceId}`,
      { params }
    )
  }
}

// 创建单例实例
const workspaceCrudService = new WorkspaceCrudService()

// 导出兼容的对象接口（向后兼容）
export const workspaceService = {
  validatePath: (data: ValidatePathRequest) => workspaceCrudService.validatePath(data),
  getWorkspaces: (params?: { include_inactive?: boolean }) => workspaceCrudService.getWorkspaces(params),
  getWorkspaceInfo: (workspaceId: string) => workspaceCrudService.getWorkspaceInfo(workspaceId),
  createWorkspace: (data: CreateWorkspaceRequest) => workspaceCrudService.createWorkspace(data),
  updateWorkspace: (workspaceId: string, data: UpdateWorkspaceRequest) => workspaceCrudService.updateWorkspace(workspaceId, data),
  deleteWorkspace: (workspaceId: string, deleteConfig?: boolean, deleteFiles?: boolean) => workspaceCrudService.deleteWorkspace(workspaceId, deleteConfig, deleteFiles)
}

export default workspaceService
