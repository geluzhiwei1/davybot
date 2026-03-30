/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Evolution API Service
 *
 * 提供Evolution功能的API接口
 */

import { httpClient } from './http';
import type { ApiResponse } from './types';

// ==================== Type Definitions ====================

/**
 * Evolution配置
 */
export interface EvolutionConfig {
  enabled: boolean;
  schedule: string; // cron表达式，如 "0 * * * *" 表示每小时
  phase_duration: string; // 每个phase的持续时间，如 "15m"
  max_cycles: number; // 最大cycle数
  goals: string[]; // 目标列表
}

/**
 * Phase状态
 */
export interface PhaseStatus {
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  conversation_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  output_file: string;
}

/**
 * Cycle元数据
 */
export interface CycleMetadata {
  cycle_id: string;
  workspace_id: string;
  status: 'pending' | 'running' | 'paused' | 'aborted' | 'completed' | 'failed';
  current_phase: string | null;
  started_at: string;
  completed_at: string | null;
  paused_at: string | null;
  aborted_at: string | null;
  abort_reason: string | null;
  phases: {
    plan: PhaseStatus;
    do: PhaseStatus;
    check: PhaseStatus;
    act: PhaseStatus;
  };
  context: {
    previous_cycle_id: string | null;
    trigger_reason: string;
    goals: string[];
    pause_count: number;
    resume_count: number;
  };
}

/**
 * Evolution状态响应
 */
export interface EvolutionStatusResponse {
  enabled: boolean;
  is_running: boolean;
  is_paused: boolean;
  current_cycle: CycleMetadata | null;
  all_cycles: CycleMetadata[];
  config: EvolutionConfig | null;
}

/**
 * Cycle操作响应
 */
export interface CycleResponse {
  cycle_id: string;
  status: string;
  message?: string;
}

/**
 * Cycle详情响应
 */
export interface CycleDetailResponse {
  metadata: CycleMetadata;
  phases: {
    plan: string;
    do: string;
    check: string;
    act: string;
  };
  workspace_md: string | null;
}

// ==================== API Service ====================

class EvolutionService {
  private readonly basePath = '/workspaces';

  /**
   * 启用evolution功能
   */
  async enableEvolution(workspaceId: string, config: EvolutionConfig): Promise<ApiResponse<{ status: string; workspace_id: string; config: EvolutionConfig }>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/enable`, config);
  }

  /**
   * 禁用evolution功能
   */
  async disableEvolution(workspaceId: string): Promise<ApiResponse<{ status: string; workspace_id: string }>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/disable`);
  }

  /**
   * 获取evolution状态
   */
  async getEvolutionStatus(workspaceId: string): Promise<ApiResponse<EvolutionStatusResponse>> {
    return httpClient.get(`${this.basePath}/${workspaceId}/evolution/status`);
  }

  /**
   * 手动触发evolution cycle
   */
  async triggerEvolution(workspaceId: string): Promise<ApiResponse<CycleResponse>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/trigger`);
  }

  /**
   * 暂停evolution cycle
   */
  async pauseCycle(workspaceId: string, cycleId: string): Promise<ApiResponse<CycleResponse>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/cycles/${cycleId}/pause`);
  }

  /**
   * 恢复evolution cycle
   */
  async resumeCycle(workspaceId: string, cycleId: string): Promise<ApiResponse<CycleResponse>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/cycles/${cycleId}/resume`);
  }

  /**
   * 中止evolution cycle
   */
  async abortCycle(workspaceId: string, cycleId: string, reason?: string): Promise<ApiResponse<CycleResponse>> {
    return httpClient.post(`${this.basePath}/${workspaceId}/evolution/cycles/${cycleId}/abort`, { reason });
  }

  /**
   * 获取cycle详情
   */
  async getCycleDetail(workspaceId: string, cycleId: string): Promise<ApiResponse<CycleDetailResponse>> {
    return httpClient.get(`${this.basePath}/${workspaceId}/evolution/cycles/${cycleId}`);
  }

  /**
   * 删除cycle
   */
  async deleteCycle(workspaceId: string, cycleId: string): Promise<ApiResponse<{ status: string; cycle_id: string }>> {
    return httpClient.delete(`${this.basePath}/${workspaceId}/evolution/cycles/${cycleId}`);
  }
}

// 导出单例
export const evolutionService = new EvolutionService();
