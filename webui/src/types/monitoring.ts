/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 监控系统类型定义
 */

// 系统健康状况指标
export interface SystemHealthMetrics {
  cpu: {
    usage: number;           // CPU使用率 (0-100)
    cores: number;           // CPU核心数
    loadAverage: number[];   // 负载平均值 [1min, 5min, 15min]
  };
  memory: {
    total: number;          // 总内存 (MB)
    used: number;           // 已使用内存 (MB)
    available: number;       // 可用内存 (MB)
    usage: number;           // 内存使用率 (0-100)
  };
  network: {
    latency: number;        // 网络延迟 (ms)
    bandwidth: number;      // 带宽使用 (Mbps)
    connections: number;    // 连接数
  };
  disk: {
    total: number;          // 总磁盘空间 (GB)
    used: number;           // 已使用空间 (GB)
    available: number;      // 可用空间 (GB)
    usage: number;          // 磁盘使用率 (0-100)
  };
  timestamp: string;       // 时间戳
}

// TaskGraph节点状态
export enum NodeStatus {
  PENDING = 'pending',     // 等待中
  RUNNING = 'running',     // 运行中
  COMPLETED = 'completed', // 已完成
  FAILED = 'failed',       // 失败
  SKIPPED = 'skipped',     // 跳过
  CANCELLED = 'cancelled'  // 取消
}

// TaskGraph节点信息
export interface TaskGraphNode {
  id: string;
  type: string;
  name: string;
  status: NodeStatus;
  startTime: string;
  endTime?: string;
  duration?: number;       // 执行时长 (ms)
  dependencies: string[];   // 依赖的节点ID
  metadata: Record<string, unknown>;
  error?: string;
  retryCount: number;
  progress?: number;       // 进度 (0-100)
  estimatedDuration?: number; // 预估时长 (ms)
}

// TaskGraph执行记录
export interface TaskGraphExecution {
  executionId: string;
  graphId: string;
  status: string;
  startTime: string;
  endTime?: string;
  totalDuration?: number;
  nodes: TaskGraphNode[];
  nodesTotal: number;
  nodesCompleted: number;
  nodesFailed: number;
  nodesSkipped: number;
  errorMessage?: string;
  errorType?: string;
  metadata: Record<string, unknown>;
}

// 监控消息类型
export enum MonitoringMessageType {
  SYSTEM_METRICS_UPDATE = 'system_metrics_update',
  TASKGRAPH_STATUS_UPDATE = 'taskgraph_status_update',
  NODE_STATUS_CHANGE = 'node_status_change',
  PERFORMANCE_ALERT = 'performance_alert',
  ERROR_NOTIFICATION = 'error_notification'
}

// 系统指标更新消息
export interface SystemMetricsUpdate {
  type: MonitoringMessageType.SYSTEM_METRICS_UPDATE;
  timestamp: string;
  metrics: SystemHealthMetrics;
}

// TaskGraph状态更新消息
export interface TaskGraphStatusUpdate {
  type: MonitoringMessageType.TASKGRAPH_STATUS_UPDATE;
  executionId: string;
  graphId: string;
  status: string;
  progress: number;
  nodesCompleted: number;
  nodesTotal: number;
  timestamp: string;
}

// 节点状态变化消息
export interface NodeStatusChange {
  type: MonitoringMessageType.NODE_STATUS_CHANGE;
  executionId: string;
  nodeId: string;
  oldStatus: NodeStatus;
  newStatus: NodeStatus;
  timestamp: string;
  error?: string;
}

// 性能告警
export interface PerformanceAlert {
  type: MonitoringMessageType.PERFORMANCE_ALERT;
  alertId: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  metric: string;
  threshold: number;
  currentValue: number;
  timestamp: string;
  executionId?: string;
  nodeId?: string;
}

// 错误通知
export interface ErrorNotification {
  type: MonitoringMessageType.ERROR_NOTIFICATION;
  errorId: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  errorType: string;
  stackTrace?: string;
  timestamp: string;
  executionId?: string;
  nodeId?: string;
  context?: Record<string, unknown>;
}

// 历史查询参数
export interface HistoryQuery {
  timeRange: {
    start: string;
    end: string;
  };
  filters: {
    graphId?: string;
    status?: string;
    nodeType?: string;
    errorType?: string;
  };
  pagination: {
    page: number;
    pageSize: number;
  };
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

// 告警规则
export interface AlertRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  condition: {
    metric: string;
    operator: '>' | '<' | '=' | '>=' | '<=';
    threshold: number;
    duration: number;  // 持续时间（秒）
  };
  severity: 'low' | 'medium' | 'high' | 'critical';
  notifications: {
    email?: string[];
    webhook?: string;
    inApp: boolean;
  };
  createdAt: string;
  updatedAt: string;
}

// 任务控制操作
export interface TaskControl {
  executionId: string;
  action: 'pause' | 'resume' | 'restart' | 'cancel';
  reason?: string;
  priority?: number;
}

// 节点控制操作
export interface NodeControl {
  executionId: string;
  nodeId: string;
  action: 'retry' | 'skip' | 'force_complete';
  parameters?: Record<string, unknown>;
}

// 统计信息
export interface MonitoringStatistics {
  totalExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  averageExecutionTime: number;
  successRate: number;
  errorRate: number;
  averageNodesPerExecution: number;
  mostCommonErrors: Array<{
    errorType: string;
    count: number;
    lastOccurrence: string;
  }>;
  performanceMetrics: {
    averageCpuUsage: number;
    averageMemoryUsage: number;
    peakCpuUsage: number;
    peakMemoryUsage: number;
  };
}

// 监控配置
export interface MonitoringConfig {
  refreshInterval: number;    // 刷新间隔 (ms)
  maxDataPoints: number;      // 最大数据点数
  enableAlerts: boolean;      // 是否启用告警
  enableAutoRefresh: boolean;  // 是否自动刷新
  chartUpdateInterval: number; // 图表更新间隔 (ms)
  logRetentionDays: number;    // 日志保留天数
}

// 导出选项
export interface ExportOptions {
  format: 'json' | 'csv' | 'xlsx' | 'pdf';
  timeRange: {
    start: string;
    end: string;
  };
  includeMetrics: boolean;
  includeExecutions: boolean;
  includeLogs: boolean;
  includeAlerts: boolean;
  customFields?: string[];
}

// 监控仪表盘状态
export interface MonitoringDashboardState {
  isConnected: boolean;
  lastUpdate: string;
  systemMetrics: SystemHealthMetrics | null;
  activeExecutions: TaskGraphExecution[];
  recentAlerts: PerformanceAlert[];
  statistics: MonitoringStatistics | null;
  config: MonitoringConfig;
  selectedExecution?: string;
  selectedNode?: string;
  filters: {
    status?: string;
    graphId?: string;
    timeRange?: {
      start: string;
      end: string;
    };
  };
}