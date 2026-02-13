/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';

/**
 * 技能响应模型
 */
export interface Skill {
  name: string;
  description: string;
  mode?: string;
  scope?: string;
  icon: string;
  category?: string;
}

/**
 * 技能列表响应
 */
export interface SkillsListResponse {
  skills: Skill[];
  total: number;
}

/**
 * 技能搜索响应
 */
export interface SkillSearchResponse {
  query: string;
  results: Skill[];
  total: number;
}

// Skills API 服务类
export class SkillsApiService {
  private baseUrl = '/skills';

  /**
   * 获取所有可用的技能列表
   */
  async listSkills(params?: {
    mode?: string;
    scope?: string;
    workspace_id?: string;
  }): Promise<SkillsListResponse> {
    return await httpClient.get<SkillsListResponse>(`${this.baseUrl}/list`, params);
  }

  /**
   * 搜索匹配的技能
   */
  async searchSkills(
    query: string,
    limit: number = 10,
    params?: {
      workspace_id?: string;
    }
  ): Promise<SkillSearchResponse> {
    return await httpClient.get<SkillSearchResponse>(
      `${this.baseUrl}/search/${query}`,
      { limit, ...params }
    );
  }

  /**
   * 获取特定技能的详细信息
   */
  async getSkill(
    skillName: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<Skill> {
    return await httpClient.get<Skill>(`${this.baseUrl}/skill/${skillName}`, params);
  }
}

// 创建并导出单例实例
export const skillsApi = new SkillsApiService();
