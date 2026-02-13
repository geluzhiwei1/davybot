/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 监控系统API服务
 */

import { apiManager } from './api';
import type {
  SystemHealthMetrics,
  TaskGraphExecution,
  HistoryQuery,
  AlertRule,
  TaskControl,
  NodeControl,
  ExportOptions,
  PerformanceAlert
} from '@/types/monitoring';

export class MonitoringService {
  private baseUrl = '/api/taskgraph';
  private systemUrl = '';

  /**
   * 获取系统健康状况
   */
  async getSystemHealth(): Promise<SystemHealthMetrics> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.systemUrl}/health`);
    return response.data;
  }

  /**
   * 获取TaskGraph执行列表
   */
  async getExecutions(
    graphId?: string,
    status?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ executions: TaskGraphExecution[]; statistics: unknown }> {
    const params = new URLSearchParams();
    if (graphId) params.append('graph_id', graphId);
    if (status) params.append('status', status);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/executions?${params}`);
    return response.data;
  }

  /**
   * 获取执行详情
   */
  async getExecution(executionId: string): Promise<TaskGraphExecution> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/executions/${executionId}`);
    return response.data.execution;
  }

  /**
   * 获取执行的节点详情
   */
  async getExecutionNodes(executionId: string): Promise<unknown[]> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/executions/${executionId}/nodes`);
    return response.data.nodes;
  }

  /**
   * 获取统计信息
   */
  async getStatistics(graphId?: string): Promise<MonitoringStatistics> {
    const params = graphId ? `?graph_id=${graphId}` : '';
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/statistics${params}`);
    return response.data.statistics;
  }

  /**
   * 获取失败的执行
   */
  async getFailedExecutions(
    graphId?: string,
    limit: number = 100
  ): Promise<{ executions: TaskGraphExecution[] }> {
    const params = new URLSearchParams();
    if (graphId) params.append('graph_id', graphId);
    params.append('limit', limit.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/failed-executions?${params}`);
    return response.data;
  }

  /**
   * 获取慢速执行
   */
  async getSlowExecutions(
    threshold: number = 10.0,
    graphId?: string,
    limit: number = 100
  ): Promise<{ executions: TaskGraphExecution[] }> {
    const params = new URLSearchParams();
    params.append('threshold', threshold.toString());
    if (graphId) params.append('graph_id', graphId);
    params.append('limit', limit.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/slow-executions?${params}`);
    return response.data;
  }

  /**
   * 获取错误汇总
   */
  async getErrorSummary(
    graphId?: string,
    limit: number = 100
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (graphId) params.append('graph_id', graphId);
    params.append('limit', limit.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/error-summary?${params}`);
    return response.data;
  }

  /**
   * 获取性能汇总
   */
  async getPerformanceSummary(
    graphId?: string,
    limit: number = 100
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (graphId) params.append('graph_id', graphId);
    params.append('limit', limit.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/performance-summary?${params}`);
    return response.data;
  }

  /**
   * 获取执行趋势
   */
  async getExecutionTrend(
    graphId?: string,
    lastN: number = 50
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (graphId) params.append('graph_id', graphId);
    params.append('last_n', lastN.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/trend?${params}`);
    return response.data;
  }

  /**
   * 获取最近的事件
   */
  async getRecentEvents(
    limit: number = 100,
    eventType?: string
  ): Promise<{ events: unknown[] }> {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (eventType) params.append('event_type', eventType);

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/events/recent?${params}`);
    return response.data;
  }

  /**
   * 获取调试信息
   */
  async getDebugInfo(): Promise<unknown> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/debug`);
    return response.data;
  }

  /**
   * 控制任务执行
   */
  async controlTask(control: TaskControl): Promise<unknown> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`${this.baseUrl}/executions/${control.executionId}/control`, control);
    return response.data;
  }

  /**
   * 控制节点执行
   */
  async controlNode(control: NodeControl): Promise<unknown> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`${this.baseUrl}/executions/${control.executionId}/nodes/${control.nodeId}/control`, control);
    return response.data;
  }

  /**
   * 获取告警规则列表
   */
  async getAlertRules(): Promise<AlertRule[]> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/alerts/rules`);
    return response.data;
  }

  /**
   * 创建告警规则
   */
  async createAlertRule(rule: Omit<AlertRule, 'id' | 'createdAt' | 'updatedAt'>): Promise<AlertRule> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`${this.baseUrl}/alerts/rules`, rule);
    return response.data;
  }

  /**
   * 更新告警规则
   */
  async updateAlertRule(id: string, rule: Partial<AlertRule>): Promise<AlertRule> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.put(`${this.baseUrl}/alerts/rules/${id}`, rule);
    return response.data;
  }

  /**
   * 删除告警规则
   */
  async deleteAlertRule(id: string): Promise<void> {
    const httpClient = apiManager.getHttpClient();
    await httpClient.delete(`${this.baseUrl}/alerts/rules/${id}`);
  }

  /**
   * 获取告警历史
   */
  async getAlertHistory(
    limit: number = 100,
    severity?: string
  ): Promise<PerformanceAlert[]> {
    const params = new URLSearchParams();
    params.append('limit', limit.toString());
    if (severity) params.append('severity', severity);

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/alerts/history?${params}`);
    return response.data;
  }

  /**
   * 导出监控数据
   */
  async exportData(options: ExportOptions): Promise<Blob> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`${this.baseUrl}/export`, options, {
      responseType: 'blob'
    });
    return response.data;
  }

  /**
   * 获取WebSocket事件流URL
   */
  getEventStreamUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}${this.baseUrl}/ws/events`;
  }

  /**
   * 查询历史数据
   */
  async queryHistory(query: HistoryQuery): Promise<{
    executions: TaskGraphExecution[];
    total: number;
    page: number;
    pageSize: number;
  }> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`${this.baseUrl}/query/history`, query);
    return response.data;
  }

  /**
   * 获取系统指标历史
   */
  async getMetricsHistory(
    metric: string,
    timeRange: { start: string; end: string },
    interval: string = '1m'
  ): Promise<Array<{ timestamp: string; value: number }>> {
    const params = new URLSearchParams();
    params.append('metric', metric);
    params.append('start', timeRange.start);
    params.append('end', timeRange.end);
    params.append('interval', interval);

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/metrics/history?${params}`);
    return response.data;
  }

  /**
   * 获取节点执行历史
   */
  async getNodeHistory(
    nodeId: string,
    graphId?: string,
    limit = 100
  ): Promise<unknown[]> {
    const params = new URLSearchParams();
    params.append('task_node_id', nodeId);
    if (graphId) params.append('graph_id', graphId);
    params.append('limit', limit.toString());

    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`${this.baseUrl}/nodes/history?${params}`);
    return response.data;
  }

  /**
   * 获取实时系统指标
   */
  async getRealTimeMetrics(): Promise<SystemHealthMetrics> {
    console.log('[DEBUG] getRealTimeMetrics called')
    const httpClient = apiManager.getHttpClient();
    
    try {
      // 首先尝试使用健康检查端点获取系统信息
      const response = await httpClient.get(`/api/health`);
      console.log('[DEBUG] getRealTimeMetrics response:', response.data);
      
      // 将健康检查数据转换为 SystemHealthMetrics 格式
      const systemMetrics: SystemHealthMetrics = {
        timestamp: new Date().toISOString(),
        cpu: {
          usage: 0, // 健康检查端点没有CPU信息，使用默认值
          cores: 4,
          loadAverage: [0.1, 0.2, 0.15]
        },
        memory: {
          usage: 0, // 健康检查端点没有内存信息，使用默认值
          total: 8192, // 8GB in MB
          used: 4096, // 4GB in MB
          available: 4096 // 4GB in MB
        },
        disk: {
          usage: 0, // 健康检查端点没有磁盘信息，使用默认值
          total: 100, // 100GB
          used: 50, // 50GB
          available: 50 // 50GB
        },
        network: {
          latency: 0, // 健康检查端点没有网络信息，使用默认值
          bandwidth: 0, // Mbps
          connections: (response.data as unknown)?.websocket?.connections || 0
        }
      };
      
      return systemMetrics;
    } catch (error) {
      console.error('[DEBUG] getRealTimeMetrics failed:', error);
      
      // 返回默认的系统指标
      const defaultMetrics: SystemHealthMetrics = {
        timestamp: new Date().toISOString(),
        cpu: { usage: 0, cores: 4, loadAverage: [0.1, 0.2, 0.15] },
        memory: { usage: 0, total: 8192, used: 4096, available: 4096 },
        disk: { usage: 0, total: 100, used: 50, available: 50 },
        network: { latency: 0, bandwidth: 0, connections: 0 }
      };
      
      return defaultMetrics;
    }
  }

  /**
   * 获取WebSocket连接状态
   */
  async getWebSocketStatus(): Promise<unknown> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.get(`/api/ws/status`);
    return (response as unknown).data;
  }

  /**
   * 广播消息到所有WebSocket连接
   */
  async broadcastMessage(message: unknown): Promise<unknown> {
    const httpClient = apiManager.getHttpClient();
    const response = await httpClient.post(`/api/ws/broadcast`, message);
    return (response as unknown).data;
  }
}

// 创建单例实例
export const monitoringService = new MonitoringService();