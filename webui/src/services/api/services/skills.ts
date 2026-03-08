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
  path?: string; // 技能文件路径
}

/**
 * 技能完整内容响应
 */
export interface SkillContent {
  name: string;
  description: string;
  content: string;
  path?: string;
  mode?: string;
  scope?: string;
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

/**
 * 技能删除响应
 */
export interface SkillDeleteResponse {
  success: boolean;
  message: string;
}

/**
 * 技能文件树项
 */
export interface SkillFileTreeItem {
  name: string;
  path: string;
  type: 'file' | 'folder';
  level: number;
  children: SkillFileTreeItem[];
  content?: string; // 文件内容（用于编辑器）
}

/**
 * 技能文件树响应
 */
export interface SkillFileTreeResponse {
  name: string;
  path: string;
  tree: SkillFileTreeItem[];
}

/**
 * 技能文件内容响应
 */
export interface SkillFileContentResponse {
  name: string;
  path: string;
  content: string;
  size: number;
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

  /**
   * 获取技能的完整内容（包括SKILL.md全文）
   */
  async getSkillContent(
    skillName: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<SkillContent> {
    return await httpClient.get<SkillContent>(`${this.baseUrl}/skill/${skillName}/content`, params);
  }

  /**
   * 删除指定技能
   */
  async deleteSkill(
    skillName: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<SkillDeleteResponse> {
    return await httpClient.delete<SkillDeleteResponse>(`${this.baseUrl}/skill/${skillName}`, { params });
  }

  /**
   * 更新指定技能
   */
  async updateSkill(
    skillName: string,
    data: {
      name?: string;
      description?: string;
      content?: string;
    },
    params?: {
      workspace_id?: string;
    }
  ): Promise<Skill> {
    return await httpClient.put<Skill>(`${this.baseUrl}/skill/${skillName}`, data, { params });
  }

  /**
   * 创建新技能
   */
  async createSkill(
    data: {
      name: string;
      description?: string;
      content?: string;
      scope?: string;
    },
    params?: {
      workspace_id?: string;
    }
  ): Promise<Skill> {
    return await httpClient.post<Skill>(`${this.baseUrl}/skill`, data, { params });
  }

  /**
   * 获取技能的文件树结构
   */
  async getSkillFileTree(
    skillName: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<SkillFileTreeResponse> {
    return await httpClient.get<SkillFileTreeResponse>(
      `${this.baseUrl}/skill/${skillName}/tree`,
      params
    );
  }

  /**
   * 获取技能文件的详细内容
   */
  async getSkillFileContent(
    skillName: string,
    filePath: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<SkillFileContentResponse> {
    return await httpClient.get<SkillFileContentResponse>(
      `${this.baseUrl}/skill/${skillName}/file`,
      { file_path: filePath, ...params }
    );
  }

  /**
   * 更新技能文件内容
   */
  async updateSkillFileContent(
    skillName: string,
    filePath: string,
    content: string,
    params?: {
      workspace_id?: string;
    }
  ): Promise<{ success: boolean; message: string }> {
    return await httpClient.put<{ success: boolean; message: string }>(
      `${this.baseUrl}/skill/${skillName}/file`,
      { content },
      { params: { file_path: filePath, ...params } }
    );
  }
}

// 创建并导出单例实例
export const skillsApi = new SkillsApiService();
