/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 监控系统状态管理
 */

import { ref, computed, reactive } from 'vue'
import { logger } from '@/utils/logger'

import { defineStore } from 'pinia'
import { monitoringService } from '@/services/monitoring'
import type {
  SystemHealthMetrics,
  TaskGraphExecution,
  MonitoringDashboardState,
  MonitoringConfig,
  PerformanceAlert,
  NodeStatus
} from '@/types/monitoring'

export const useMonitoringStore = defineStore('monitoring', () => {
  // 状态定义
  const state = reactive<MonitoringDashboardState>({
    isConnected: false,
    lastUpdate: '',
    systemMetrics: null,
    activeExecutions: [],
    recentAlerts: [],
    statistics: null,
    config: {
      refreshInterval: 5000,      // 5秒刷新间隔
      maxDataPoints: 100,         // 最大数据点数
      enableAlerts: true,          // 启用告警
      enableAutoRefresh: true,      // 自动刷新
      chartUpdateInterval: 1000,   // 图表更新间隔
      logRetentionDays: 30          // 日志保留30天
    },
    selectedExecution: undefined,
    selectedNode: undefined,
    filters: {}
  })

  // WebSocket连接
  let websocket: WebSocket | null = null
  let reconnectTimer: number | null = null
  let refreshTimer: number | null = null

  // 历史数据存储
  const metricsHistory = ref<Array<SystemHealthMetrics>>([])
  const executionsHistory = ref<Array<TaskGraphExecution>>([])

  // 计算属性
  const cpuUsage = computed(() => state.systemMetrics?.cpu.usage || 0)
  const memoryUsage = computed(() => state.systemMetrics?.memory.usage || 0)
  const diskUsage = computed(() => state.systemMetrics?.disk.usage || 0)
  const networkLatency = computed(() => state.systemMetrics?.network.latency || 0)

  const runningExecutions = computed(() => 
    state.activeExecutions.filter(exec => exec.status === 'running')
  )

  const failedExecutions = computed(() => 
    state.activeExecutions.filter(exec => exec.status === 'failed')
  )

  const completedExecutions = computed(() => 
    state.activeExecutions.filter(exec => exec.status === 'completed')
  )

  const criticalAlerts = computed(() => 
    state.recentAlerts.filter(alert => alert.severity === 'critical')
  )

  const highAlerts = computed(() => 
    state.recentAlerts.filter(alert => alert.severity === 'high')
  )

  // WebSocket连接管理
  const connectWebSocket = () => {
    if (websocket?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      websocket = new WebSocket(monitoringService.getEventStreamUrl())
      
      websocket.onopen = () => {
        logger.debug('监控WebSocket连接已建立')
        state.isConnected = true
        state.lastUpdate = new Date().toISOString()
        
        // 清除重连定时器
        if (reconnectTimer) {
          clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
      }

      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleWebSocketMessage(data)
        } catch (error) {
          logger.error('解析WebSocket消息失败:', error)
        }
      }

      websocket.onclose = () => {
        logger.debug('监控WebSocket连接已关闭')
        state.isConnected = false
        
        // 自动重连
        if (state.config.enableAutoRefresh) {
          reconnectTimer = window.setTimeout(() => {
            logger.debug('尝试重新连接监控WebSocket')
            connectWebSocket()
          }, 5000)
        }
      }

      websocket.onerror = (error) => {
        logger.error('监控WebSocket连接错误:', error)
        state.isConnected = false
      }
    } catch (error) {
      logger.error('创建监控WebSocket连接失败:', error)
    }
  }

  // 断开WebSocket连接
  const disconnectWebSocket = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }

    if (websocket) {
      websocket.close()
      websocket = null
    }

    state.isConnected = false
  }

  // 处理WebSocket消息
  const handleWebSocketMessage = (data: unknown) => {
    state.lastUpdate = new Date().toISOString()

    switch (data.type) {
      case 'system_metrics_update':
        if (data.metrics) {
          state.systemMetrics = data.metrics
          // 保存历史数据
          metricsHistory.value.push(data.metrics)
          if (metricsHistory.value.length > state.config.maxDataPoints) {
            metricsHistory.value.shift()
          }
        }
        break

      case 'taskgraph_status_update':
        handleTaskGraphStatusUpdate(data)
        break

      case 'node_status_change':
        handleNodeStatusChange(data)
        break

      case 'performance_alert':
        handlePerformanceAlert(data)
        break

      case 'error_notification':
        handleErrorNotification(data)
        break

      default:
        logger.debug('未知的监控消息类型:', data.type)
    }
  }

  // 处理TaskGraph状态更新
  const handleTaskGraphStatusUpdate = (data: unknown) => {
    const { executionId, status, nodesCompleted, nodesTotal } = data

    // 更新执行列表中的状态
    const executionIndex = state.activeExecutions.findIndex(exec => exec.executionId === executionId)
    if (executionIndex !== -1) {
      state.activeExecutions[executionIndex].status = status
      state.activeExecutions[executionIndex].nodesCompleted = nodesCompleted
      state.activeExecutions[executionIndex].nodesTotal = nodesTotal
    } else {
      // 如果不在列表中，可能是新的执行，需要获取详情
      loadExecutionDetails(executionId)
    }
  }

  // 处理节点状态变化
  const handleNodeStatusChange = (data: unknown) => {
    const { executionId, nodeId, newStatus, error } = data
    
    const executionIndex = state.activeExecutions.findIndex(exec => exec.executionId === executionId)
    if (executionIndex !== -1) {
      const nodeIndex = state.activeExecutions[executionIndex].nodes.findIndex(node => node.id === nodeId)
      if (nodeIndex !== -1) {
        state.activeExecutions[executionIndex].nodes[nodeIndex].status = newStatus as NodeStatus
        if (error) {
          state.activeExecutions[executionIndex].nodes[nodeIndex].error = error
        }
      }
    }
  }

  // 处理性能告警
  const handlePerformanceAlert = (alert: PerformanceAlert) => {
    state.recentAlerts.unshift(alert)
    
    // 限制告警数量
    if (state.recentAlerts.length > 100) {
      state.recentAlerts = state.recentAlerts.slice(0, 100)
    }

    // 如果启用告警，显示通知
    if (state.config.enableAlerts) {
      showAlertNotification(alert)
    }
  }

  // 处理错误通知
  const handleErrorNotification = (notification: unknown) => {
    logger.error('系统错误通知:', notification)
    // 转换为性能告警格式处理
    const alert: PerformanceAlert = {
      type: 'error_notification' as unknown,
      alertId: notification.errorId,
      severity: notification.severity,
      title: notification.title,
      message: notification.message,
      metric: 'error',
      threshold: 0,
      currentValue: 1,
      timestamp: notification.timestamp,
      executionId: notification.executionId,
      nodeId: notification.nodeId
    }
    
    handlePerformanceAlert(alert)
  }

  // 显示告警通知
  const showAlertNotification = (alert: PerformanceAlert) => {
    // 使用Element Plus的通知组件
    if (typeof window !== 'undefined' && (window as unknown).ElNotification) {
      (window as unknown).ElNotification({
        title: alert.title,
        message: alert.message,
        type: alert.severity === 'critical' ? 'error' : 
              alert.severity === 'high' ? 'warning' : 'info',
        duration: alert.severity === 'critical' ? 0 : 5000
      })
    }
  }

  // 加载执行详情
  const loadExecutionDetails = async (executionId: string) => {
    try {
      const execution = await monitoringService.getExecution(executionId)
      
      // 检查是否已存在
      const existingIndex = state.activeExecutions.findIndex(exec => exec.executionId === executionId)
      if (existingIndex !== -1) {
        state.activeExecutions[existingIndex] = execution
      } else {
        state.activeExecutions.push(execution)
        
        // 限制活跃执行数量
        if (state.activeExecutions.length > 50) {
          state.activeExecutions.shift()
        }
      }
    } catch (error) {
      logger.error('加载执行详情失败:', error)
    }
  }

  // 初始化监控
  const initializeMonitoring = async () => {
    try {
      // 加载初始数据
      await loadInitialData()
      
      // 建立WebSocket连接
      connectWebSocket()
      
      // 启动定时刷新
      if (state.config.enableAutoRefresh) {
        startAutoRefresh()
      }
    } catch (error) {
      logger.error('初始化监控失败:', error)
    }
  }

  // 加载初始数据
  const loadInitialData = async () => {
    try {
      // 加载系统指标
      const systemMetrics = await monitoringService.getRealTimeMetrics()
      state.systemMetrics = systemMetrics
      metricsHistory.value.push(systemMetrics)

      // 加载活跃执行
      const executionsData = await monitoringService.getExecutions(undefined, 'running', 50)
      state.activeExecutions = executionsData.executions

      // 加载统计信息
      const statistics = await monitoringService.getStatistics()
      state.statistics = statistics

      // 加载最近告警
      const alerts = await monitoringService.getAlertHistory(20)
      state.recentAlerts = alerts

      state.lastUpdate = new Date().toISOString()
    } catch (error) {
      logger.error('加载初始数据失败:', error)
    }
  }

  // 启动自动刷新
  const startAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
    }

    refreshTimer = window.setInterval(async () => {
      if (state.isConnected) {
        return // WebSocket连接正常时不需要轮询
      }

      try {
        // 轮询获取系统指标
        const systemMetrics = await monitoringService.getRealTimeMetrics()
        state.systemMetrics = systemMetrics
        metricsHistory.value.push(systemMetrics)
        
        if (metricsHistory.value.length > state.config.maxDataPoints) {
          metricsHistory.value.shift()
        }

        state.lastUpdate = new Date().toISOString()
      } catch (error) {
        logger.error('自动刷新失败:', error)
      }
    }, state.config.refreshInterval)
  }

  // 停止自动刷新
  const stopAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  // 控制任务执行
  const controlTask = async (control: TaskControl) => {
    try {
      await monitoringService.controlTask(control)
      
      // 更新本地状态
      const executionIndex = state.activeExecutions.findIndex(exec => exec.executionId === control.executionId)
      if (executionIndex !== -1) {
        if (control.action === 'cancel') {
          state.activeExecutions[executionIndex].status = 'cancelled'
        } else if (control.action === 'pause') {
          state.activeExecutions[executionIndex].status = 'paused'
        } else if (control.action === 'resume') {
          state.activeExecutions[executionIndex].status = 'running'
        }
      }
    } catch (error) {
      logger.error('控制任务失败:', error)
      throw error
    }
  }

  // 控制节点执行
  const controlNode = async (control: NodeControl) => {
    try {
      await monitoringService.controlNode(control)
      
      // 更新本地状态
      const executionIndex = state.activeExecutions.findIndex(exec => exec.executionId === control.executionId)
      if (executionIndex !== -1) {
        const nodeIndex = state.activeExecutions[executionIndex].nodes.findIndex(node => node.id === control.nodeId)
        if (nodeIndex !== -1) {
          if (control.action === 'retry') {
            state.activeExecutions[executionIndex].nodes[nodeIndex].status = NodeStatus.PENDING
            state.activeExecutions[executionIndex].nodes[nodeIndex].retryCount++
          } else if (control.action === 'skip') {
            state.activeExecutions[executionIndex].nodes[nodeIndex].status = NodeStatus.SKIPPED
          } else if (control.action === 'force_complete') {
            state.activeExecutions[executionIndex].nodes[nodeIndex].status = NodeStatus.COMPLETED
          }
        }
      }
    } catch (error) {
      logger.error('控制节点失败:', error)
      throw error
    }
  }

  // 更新配置
  const updateConfig = (newConfig: Partial<MonitoringConfig>) => {
    Object.assign(state.config, newConfig)
    
    // 如果自动刷新配置改变，重新启动
    if ('enableAutoRefresh' in newConfig || 'refreshInterval' in newConfig) {
      stopAutoRefresh()
      if (state.config.enableAutoRefresh) {
        startAutoRefresh()
      }
    }
  }

  // 清除告警
  const clearAlerts = () => {
    state.recentAlerts = []
  }

  // 选择执行
  const selectExecution = (executionId: string | undefined) => {
    state.selectedExecution = executionId
  }

  // 选择节点
  const selectNode = (nodeId: string | undefined) => {
    state.selectedNode = nodeId
  }

  // 更新过滤器
  const updateFilters = (filters: unknown) => {
    Object.assign(state.filters, filters)
  }

  // 刷新数据
  const refreshData = async () => {
    await loadInitialData()
  }

  // 清理资源
  const cleanup = () => {
    disconnectWebSocket()
    stopAutoRefresh()
  }

  return {
    // 状态
    state,
    
    // 计算属性
    cpuUsage,
    memoryUsage,
    diskUsage,
    networkLatency,
    runningExecutions,
    failedExecutions,
    completedExecutions,
    criticalAlerts,
    highAlerts,
    
    // 历史数据
    metricsHistory,
    executionsHistory,
    
    // 方法
    initializeMonitoring,
    connectWebSocket,
    disconnectWebSocket,
    controlTask,
    controlNode,
    updateConfig,
    clearAlerts,
    selectExecution,
    selectNode,
    updateFilters,
    refreshData,
    cleanup
  }
})