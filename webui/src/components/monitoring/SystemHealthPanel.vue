/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="system-health-panel">
    <el-card class="health-card" header="系统健康状况">
      <template #extra>
        <div class="health-status">
          <el-tag 
            :type="healthStatus.type" 
            size="small"
            effect="dark"
          >
            {{ healthStatus.text }}
          </el-tag>
          <span class="last-update">
            最后更新: {{ formatTimestamp(monitoringStore.state.lastUpdate, 'time') }}
          </span>
        </div>
      </template>

      <!-- 系统指标概览 -->
      <div class="metrics-overview">
        <div class="metric-item">
          <div class="metric-label">CPU使用率</div>
          <div class="metric-value">
            <el-progress
              :percentage="monitoringStore.cpuUsage"
              :color="getProgressColor(monitoringStore.cpuUsage)"
              :show-text="true"
              :stroke-width="8"
            >
              {{ monitoringStore.cpuUsage.toFixed(1) }}%
            </el-progress>
          </div>
        </div>

        <div class="metric-item">
          <div class="metric-label">内存使用率</div>
          <div class="metric-value">
            <el-progress 
              :percentage="memoryUsage" 
              :color="getProgressColor(memoryUsage)"
              :show-text="true"
              :stroke-width="8"
            >
              {{ memoryUsage.toFixed(1) }}%
            </el-progress>
          </div>
        </div>

        <div class="metric-item">
          <div class="metric-label">磁盘使用率</div>
          <div class="metric-value">
            <el-progress 
              :percentage="diskUsage" 
              :color="getProgressColor(diskUsage)"
              :show-text="true"
              :stroke-width="8"
            >
              {{ diskUsage.toFixed(1) }}%
            </el-progress>
          </div>
        </div>

        <div class="metric-item">
          <div class="metric-label">网络延迟</div>
          <div class="metric-value">
            <span class="latency-value" :class="getLatencyClass(networkLatency)">
              {{ networkLatency.toFixed(0) }}ms
            </span>
          </div>
        </div>
      </div>

      <!-- 详细指标图表 -->
      <el-tabs v-model="activeTab" class="metrics-tabs">
        <el-tab-pane label="CPU趋势" name="cpu">
          <div ref="cpuChartRef" class="chart-container"></div>
        </el-tab-pane>
        <el-tab-pane label="内存趋势" name="memory">
          <div ref="memoryChartRef" class="chart-container"></div>
        </el-tab-pane>
        <el-tab-pane label="网络状态" name="network">
          <div ref="networkChartRef" class="chart-container"></div>
        </el-tab-pane>
        <el-tab-pane label="系统信息" name="system">
          <div class="system-info">
            <el-descriptions :column="2" border>
              <el-descriptions-item label="CPU核心数">
                {{ monitoringStore.state.systemMetrics?.cpu.cores || 'N/A' }}
              </el-descriptions-item>
              <el-descriptions-item label="负载平均值">
                {{ formatLoadAverage(monitoringStore.state.systemMetrics?.cpu.loadAverage) }}
              </el-descriptions-item>
              <el-descriptions-item label="总内存">
                {{ formatMemory(monitoringStore.state.systemMetrics?.memory.total) }}
              </el-descriptions-item>
              <el-descriptions-item label="可用内存">
                {{ formatMemory(monitoringStore.state.systemMetrics?.memory.available) }}
              </el-descriptions-item>
              <el-descriptions-item label="总磁盘空间">
                {{ formatDisk(monitoringStore.state.systemMetrics?.disk.total) }}
              </el-descriptions-item>
              <el-descriptions-item label="可用磁盘空间">
                {{ formatDisk(monitoringStore.state.systemMetrics?.disk.available) }}
              </el-descriptions-item>
              <el-descriptions-item label="网络连接数">
                {{ monitoringStore.state.systemMetrics?.network.connections || 'N/A' }}
              </el-descriptions-item>
              <el-descriptions-item label="带宽使用">
                {{ monitoringStore.state.systemMetrics?.network.bandwidth || 'N/A' }} Mbps
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- 连接状态 -->
      <div class="connection-status">
        <el-alert
          :title="connectionStatus.title"
          :type="connectionStatus.type"
          :closable="false"
          show-icon
        >
          <template #default>
            <div class="connection-actions">
              <span>{{ connectionStatus.message }}</span>
              <el-button
                v-if="!monitoringStore.state.isConnected"
                type="primary"
                size="small"
                @click="reconnect"
              >
                重新连接
              </el-button>
            </div>
          </template>
        </el-alert>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { ElMessage } from 'element-plus'

import { formatTimestamp } from '@/utils/formatters'

const monitoringStore = useMonitoringStore()

// Destructure computed properties from store
const { memoryUsage, diskUsage, networkLatency } = monitoringStore

// 图表引用
const cpuChartRef = ref<HTMLElement>()
const memoryChartRef = ref<HTMLElement>()
const networkChartRef = ref<HTMLElement>()

// 图表实例
const cpuChart: unknown = null
const memoryChart: unknown = null
const networkChart: unknown = null

// 当前激活的标签页
const activeTab = ref('cpu')

// 健康状态
const healthStatus = computed(() => {
  if (!monitoringStore.state.systemMetrics) {
    return { type: 'info', text: '未知' }
  }

  const cpu = monitoringStore.cpuUsage
  const memory = monitoringStore.memoryUsage
  const disk = monitoringStore.diskUsage

  if (cpu > 90 || memory > 90 || disk > 95) {
    return { type: 'danger', text: '严重' }
  } else if (cpu > 70 || memory > 70 || disk > 80) {
    return { type: 'warning', text: '警告' }
  } else if (cpu > 50 || memory > 50 || disk > 60) {
    return { type: 'success', text: '正常' }
  } else {
    return { type: 'success', text: '良好' }
  }
})

// 连接状态
const connectionStatus = computed(() => {
  if (monitoringStore.state.isConnected) {
    return {
      type: 'success',
      title: '连接正常',
      message: '实时监控连接已建立'
    }
  } else {
    return {
      type: 'error',
      title: '连接断开',
      message: '实时监控连接已断开，正在尝试重连...'
    }
  }
})

// 获取进度条颜色
const getProgressColor = (percentage: number): string => {
  if (percentage > 90) return '#f56c6c'
  if (percentage > 70) return '#e6a23c'
  if (percentage > 50) return '#409eff'
  return '#67c23a'
}

// 获取延迟样式类
const getLatencyClass = (latency: number): string => {
  if (latency > 200) return 'latency-high'
  if (latency > 100) return 'latency-medium'
  return 'latency-low'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 格式化负载平均值
const formatLoadAverage = (loadAverage?: number[]): string => {
  if (!loadAverage || loadAverage.length === 0) return 'N/A'
  return loadAverage.map(avg => avg.toFixed(2)).join(', ')
}

// 格式化内存
const formatMemory = (memory?: number): string => {
  if (!memory) return 'N/A'
  if (memory < 1024) return `${memory} MB`
  return `${(memory / 1024).toFixed(1)} GB`
}

// 格式化磁盘
const formatDisk = (disk?: number): string => {
  if (!disk) return 'N/A'
  return `${disk.toFixed(1)} GB`
}

// 重新连接
const reconnect = () => {
  monitoringStore.connectWebSocket()
  ElMessage.success('正在尝试重新连接...')
}

// 初始化CPU图表
const initCpuChart = () => {
  if (!cpuChartRef.value) return

  // 使用简单的HTML图表代替echarts
  cpuChartRef.value.innerHTML = `
    <div style="height: 300px; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
      <h3>CPU使用率趋势</h3>
      <div style="font-size: 24px; font-weight: bold; color: #409eff;">
        ${monitoringStore.cpuUsage.toFixed(1)}%
      </div>
      <div style="margin-top: 10px; color: #666;">
        当前CPU使用率
      </div>
    </div>
  `
}

// 初始化内存图表
const initMemoryChart = () => {
  if (!memoryChartRef.value) return

  // 使用简单的HTML图表代替echarts
  memoryChartRef.value.innerHTML = `
    <div style="height: 300px; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
      <h3>内存使用率趋势</h3>
      <div style="font-size: 24px; font-weight: bold; color: #67c23a;">
        ${monitoringStore.memoryUsage.toFixed(1)}%
      </div>
      <div style="margin-top: 10px; color: #666;">
        当前内存使用率
      </div>
    </div>
  `
}

// 初始化网络图表
const initNetworkChart = () => {
  if (!networkChartRef.value) return

  // 使用简单的HTML图表代替echarts
  networkChartRef.value.innerHTML = `
    <div style="height: 300px; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;">
      <h3>网络延迟趋势</h3>
      <div style="font-size: 24px; font-weight: bold; color: #e6a23c;">
        ${monitoringStore.networkLatency.toFixed(0)}ms
      </div>
      <div style="margin-top: 10px; color: #666;">
        当前网络延迟
      </div>
    </div>
  `
}

// 更新图表数据
const updateCharts = () => {
  // 简化图表更新，只显示当前值
  if (cpuChartRef.value) {
    initCpuChart()
  }

  if (memoryChartRef.value) {
    initMemoryChart()
  }

  if (networkChartRef.value) {
    initNetworkChart()
  }
}

// 监听标签页变化
watch(activeTab, (newTab) => {
  nextTick(() => {
    // 延迟渲染图表，确保DOM已更新
    setTimeout(() => {
      if (newTab === 'cpu' && !cpuChart) {
        initCpuChart()
        updateCharts()
      } else if (newTab === 'memory' && !memoryChart) {
        initMemoryChart()
        updateCharts()
      } else if (newTab === 'network' && !networkChart) {
        initNetworkChart()
        updateCharts()
      }
    }, 100)
  })
})

// 监听数据变化
watch(monitoringStore.metricsHistory, () => {
  updateCharts()
}, { deep: true })

// 窗口大小变化时重新渲染图表
const handleResize = () => {
  // 简化处理，不使用复杂的图表库
}

onMounted(() => {
  // 初始化监控
  monitoringStore.initializeMonitoring()
  
  // 延迟初始化图表
  nextTick(() => {
    setTimeout(() => {
      initCpuChart()
      updateCharts()
    }, 100)
  })

  // 监听窗口大小变化
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  // 清理资源
  monitoringStore.cleanup()
  
  // 移除事件监听
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.system-health-panel {
  height: 100%;
}

.health-card {
  height: 100%;
}

.health-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.last-update {
  font-size: 12px;
  color: #909399;
}

.metrics-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.metric-item {
  text-align: center;
}

.metric-label {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 18px;
  font-weight: bold;
}

.latency-value {
  font-size: 24px;
  font-weight: bold;
}

.latency-low {
  color: #67c23a;
}

.latency-medium {
  color: #e6a23c;
}

.latency-high {
  color: #f56c6c;
}

.metrics-tabs {
  margin-top: 20px;
}

.chart-container {
  height: 300px;
  width: 100%;
}

.system-info {
  padding: 20px;
}

.connection-status {
  margin-top: 20px;
}

.connection-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .metrics-overview {
    grid-template-columns: repeat(2, 1fr);
    gap: 15px;
  }
  
  .metric-value {
    font-size: 16px;
  }
  
  .latency-value {
    font-size: 20px;
  }
}

@media (max-width: 480px) {
  .metrics-overview {
    grid-template-columns: 1fr;
  }
  
  .health-status {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>