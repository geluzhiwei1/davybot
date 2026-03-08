/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from './http';
import type {
  SecuritySettingsResponse,
  UserSecuritySettings,
  WorkspaceSecuritySettings,
} from './types';

/**
 * 用户级安全配置 API 服务
 */
export class UsersSecurityApiService {
  private baseUrl = '/users/me/security';

  /**
   * 获取用户安全配置
   */
  async getUserSecuritySettings(): Promise<SecuritySettingsResponse> {
    return await httpClient.get<UserSecuritySettings>(this.baseUrl);
  }

  /**
   * 更新用户安全配置
   */
  async updateUserSecuritySettings(
    settings: Partial<UserSecuritySettings>
  ): Promise<SecuritySettingsResponse> {
    return await httpClient.put<UserSecuritySettings>(this.baseUrl, settings);
  }

  /**
   * 重置用户安全配置为默认值
   */
  async resetUserSecuritySettings(): Promise<SecuritySettingsResponse> {
    return await httpClient.post<UserSecuritySettings>(`${this.baseUrl}/reset`);
  }
}

/**
 * 工作区级安全配置 API 服务
 */
export class WorkspaceSecurityApiService {
  private baseUrl: string;

  constructor(workspaceId: string) {
    this.baseUrl = `/workspaces/${workspaceId}/security-settings`;
  }

  /**
   * 获取工作区安全配置
   */
  async getWorkspaceSecuritySettings(): Promise<SecuritySettingsResponse> {
    return await httpClient.get<WorkspaceSecuritySettings>(this.baseUrl);
  }

  /**
   * 更新工作区安全配置
   */
  async updateWorkspaceSecuritySettings(
    settings: Partial<WorkspaceSecuritySettings>
  ): Promise<SecuritySettingsResponse> {
    return await httpClient.put<WorkspaceSecuritySettings>(this.baseUrl, settings);
  }

  /**
   * 重置工作区安全配置为默认值
   */
  async resetWorkspaceSecuritySettings(): Promise<SecuritySettingsResponse> {
    return await httpClient.post<WorkspaceSecuritySettings>(`${this.baseUrl}/reset`);
  }
}

// 导出单例实例
export const usersSecurityApi = new UsersSecurityApiService();

// 导出工厂函数
export const getWorkspaceSecurityApi = (workspaceId: string) => {
  return new WorkspaceSecurityApiService(workspaceId);
};
