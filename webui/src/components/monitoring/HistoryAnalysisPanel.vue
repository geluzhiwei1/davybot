/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="history-analysis-panel">
    <el-card class="history-card" header="历史数据分析">
      <template #extra>
        <div class="history-controls">
          <el-button 
            type="primary" 
            size="small"
            @click="showQueryDialog = true"
          >
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button 
            size="small"
            @click="exportData"
          >
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </div>
      </template>

      <!-- 查询条件 -->
      <div class="query-filters">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-date-picker
              v-model="queryTimeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              @change="onTimeRangeChange"
            />
          </el-col>
          <el-col :span="4">
            <el-select
              v-model="queryFilters.status"
              placeholder="执行状态"
              clearable
              @change="onFilterChange"
            >
              <el-option label="全部" value="" />
              <el-option label="运行中" value="running" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
              <el-option label="取消" value="cancelled" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select
              v-model="queryFilters.graphId"
              placeholder="TaskGraph ID"
              clearable
              filterable
              @change="onFilterChange"
            >
              <el-option
                v-for="graph in availableGraphs"
                :key="graph.id"
                :label="graph.name || graph.id"
                :value="graph.id"
              />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select
              v-model="queryFilters.errorType"
              placeholder="错误类型"
              clearable
              @change="onFilterChange"
            >
              <el-option
                v-for="error in availableErrorTypes"
                :key="error.type"
                :label="error.type"
                :value="error.type"
              />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-button-group>
              <el-button @click="refreshData">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
              <el-button @click="resetFilters">
                <el-icon><RefreshLeft /></el-icon>
                重置
              </el-button>
            </el-button-group>
          </el-col>
        </el-row>
      </div>

      <!-- 统计概览 -->
      <div class="statistics-overview">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic 
              title="总执行次数" 
              :value="statistics.totalExecutions"
              :value-style="{ color: '#3f8600' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="成功率"
              :value="parseFloat((statistics.successRate * 100).toFixed(1))"
              suffix="%"
              :value-style="{ color: statistics.successRate > 0.8 ? '#3f8600' : '#cf1322' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="平均执行时间" 
              :value="statistics.averageExecutionTime"
              suffix="s"
              :precision="1"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic
              title="错误率"
              :value="parseFloat((statistics.errorRate * 100).toFixed(1))"
              suffix="%"
              :value-style="{ color: statistics.errorRate < 0.1 ? '#3f8600' : '#cf1322' }"
            />
          </el-col>
        </el-row>
      </div>

      <!-- 简单图表 -->
      <div class="simple-charts">
        <el-row :gutter="20">
          <el-col :span="12">
            <div class="chart-container">
              <h3>执行趋势</h3>
              <div class="chart-placeholder">
                <div class="chart-data">
                  <div v-for="(item, index) in chartData" :key="index" class="chart-item">
                    <div class="chart-bar" :style="{ height: item.height + 'px' }"></div>
                    <div class="chart-label">{{ item.label }}</div>
                  </div>
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="chart-container">
              <h3>性能分析</h3>
              <div class="chart-placeholder">
                <div class="performance-metrics">
                  <div class="metric-item">
                    <span class="metric-label">平均CPU:</span>
                    <span class="metric-value">{{ statistics.performanceMetrics.averageCpuUsage.toFixed(1) }}%</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">平均内存:</span>
                    <span class="metric-value">{{ statistics.performanceMetrics.averageMemoryUsage.toFixed(1) }}%</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">峰值CPU:</span>
                    <span class="metric-value">{{ statistics.performanceMetrics.peakCpuUsage.toFixed(1) }}%</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">峰值内存:</span>
                    <span class="metric-value">{{ statistics.performanceMetrics.peakMemoryUsage.toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>

      <!-- 执行记录表格 -->
      <div class="execution-table">
        <el-table
          :data="executions"
          v-loading="loading"
          stripe
          height="400"
          @sort-change="onSortChange"
        >
          <el-table-column prop="executionId" label="执行ID" width="200" />
          <el-table-column prop="graphId" label="TaskGraph ID" width="150" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusTagType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="startTime" label="开始时间" width="180">
            <template #default="{ row }">
              {{ formatTimestamp(row.startTime, 'time') }}
            </template>
          </el-table-column>
          <el-table-column prop="endTime" label="结束时间" width="180">
            <template #default="{ row }">
              {{ row.endTime ? formatTimestamp(row.endTime, 'time') : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="totalDuration" label="执行时长" width="120" sortable="custom">
            <template #default="{ row }">
              {{ row.totalDuration ? formatDuration(row.totalDuration, 'standard') : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="nodesCompleted" label="完成节点" width="100" />
          <el-table-column prop="nodesTotal" label="总节点" width="80" />
          <el-table-column prop="progress" label="进度" width="120">
            <template #default="{ row }">
              <el-progress 
                v-if="row.status === 'running'"
                :percentage="Math.round((row.nodesCompleted / row.nodesTotal) * 100)"
                :show-text="true"
                :stroke-width="6"
              />
              <span v-else>
                {{ row.nodesTotal > 0 ? Math.round((row.nodesCompleted / row.nodesTotal) * 100) : 0 }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button 
                size="small" 
                type="primary"
                @click="viewExecutionDetail(row)"
              >
                详情
              </el-button>
              <el-button 
                v-if="['running', 'paused'].includes(row.status)"
                size="small" 
                type="warning"
                @click="controlExecution(row, 'cancel')"
              >
                取消
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div class="pagination-container">
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="pagination.total"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="onPageSizeChange"
            @current-change="onPageChange"
          />
        </div>
      </div>
    </el-card>

    <!-- 高级查询对话框 -->
    <el-dialog
      v-model="showQueryDialog"
      title="高级查询"
      width="600px"
    >
      <el-form :model="advancedQuery" label-width="100px">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="advancedQuery.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DD HH:mm:ss"
          />
        </el-form-item>
        
        <el-form-item label="执行状态">
          <el-checkbox-group v-model="advancedQuery.statuses">
            <el-checkbox label="running">运行中</el-checkbox>
            <el-checkbox label="completed">已完成</el-checkbox>
            <el-checkbox label="failed">失败</el-checkbox>
            <el-checkbox label="cancelled">取消</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        
        <el-form-item label="TaskGraph">
          <el-select
            v-model="advancedQuery.graphIds"
            multiple
            placeholder="选择TaskGraph"
            style="width: 100%"
          >
            <el-option
              v-for="graph in availableGraphs"
              :key="graph.id"
              :label="graph.name || graph.id"
              :value="graph.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="执行时长">
          <el-row :gutter="10">
            <el-col :span="11">
              <el-input-number
                v-model="advancedQuery.minDuration"
                placeholder="最小时长(秒)"
                :min="0"
                :max="advancedQuery.maxDuration || undefined"
              />
            </el-col>
            <el-col :span="2" style="text-align: center;">至</el-col>
            <el-col :span="11">
              <el-input-number
                v-model="advancedQuery.maxDuration"
                placeholder="最大时长(秒)"
                :min="advancedQuery.minDuration || 0"
              />
            </el-col>
          </el-row>
        </el-form-item>

        <el-form-item label="节点数量">
          <el-row :gutter="10">
            <el-col :span="11">
              <el-input-number
                v-model="advancedQuery.minNodes"
                placeholder="最小节点数"
                :min="0"
                :max="advancedQuery.maxNodes || undefined"
              />
            </el-col>
            <el-col :span="2" style="text-align: center;">至</el-col>
            <el-col :span="11">
              <el-input-number
                v-model="advancedQuery.maxNodes"
                placeholder="最大节点数"
                :min="advancedQuery.minNodes || 0"
              />
            </el-col>
          </el-row>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showQueryDialog = false">取消</el-button>
        <el-button type="primary" @click="executeAdvancedQuery">查询</el-button>
      </template>
    </el-dialog>

    <!-- 执行详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="执行详情"
      width="80%"
      top="5vh"
    >
      <div v-if="selectedExecution" class="execution-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="执行ID">
            {{ selectedExecution.executionId }}
          </el-descriptions-item>
          <el-descriptions-item label="TaskGraph ID">
            {{ selectedExecution.graphId }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(selectedExecution.status)">
              {{ getStatusText(selectedExecution.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatTimestamp(selectedExecution.startTime, 'time') }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ selectedExecution.endTime ? formatTimestamp(selectedExecution.endTime, 'time') : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="执行时长">
            {{ selectedExecution.totalDuration ? formatDuration(selectedExecution.totalDuration, 'standard') : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="错误信息" v-if="selectedExecution.errorMessage">
            <el-text type="danger">{{ selectedExecution.errorMessage }}</el-text>
          </el-descriptions-item>
        </el-descriptions>

        <h3>节点详情</h3>
        <el-table :data="selectedExecution.nodes" stripe max-height="300">
          <el-table-column prop="id" label="节点ID" width="150" />
          <el-table-column prop="name" label="节点名称" width="200">
            <template #default="{ row }">
              {{ row.name || row.id }}
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusTagType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="startTime" label="开始时间" width="180">
            <template #default="{ row }">
              {{ formatTimestamp(row.startTime, 'time') }}
            </template>
          </el-table-column>
          <el-table-column prop="endTime" label="结束时间" width="180">
            <template #default="{ row }">
              {{ row.endTime ? formatTimestamp(row.endTime, 'time') : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="duration" label="执行时长" width="120">
            <template #default="{ row }">
              {{ row.duration ? formatDuration(row.duration, 'standard') : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="retryCount" label="重试次数" width="100" />
        </el-table>
      </div>
      
      <template #footer>
        <el-button @click="showDetailDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { storeToRefs } from 'pinia'
import { monitoringService } from '@/services/monitoring'
import { ElMessage } from 'element-plus'
import { formatTimestamp, formatDuration } from '@/utils/formatters'
import { Search, Download, Refresh, RefreshLeft } from '@element-plus/icons-vue'
import type { TaskGraphExecution, HistoryQuery } from '@/types/monitoring'

const monitoringStore = useMonitoringStore()
const { state } = storeToRefs(monitoringStore)
const {
  controlTask
} = monitoringStore

// Access executions from state
const runningExecutions = computed(() => state.value.activeExecutions.filter(exec => exec.status === 'running'))
const completedExecutions = computed(() => state.value.activeExecutions.filter(exec => exec.status === 'completed'))
const failedExecutions = computed(() => state.value.activeExecutions.filter(exec => exec.status === 'failed'))

// 状态
const loading = ref(false)
const showQueryDialog = ref(false)
const showDetailDialog = ref(false)
const selectedExecution = ref<TaskGraphExecution | null>(null)

// 查询条件
const queryTimeRange = ref<[string, string]>(['', ''])
const queryFilters = ref({
  status: '',
  graphId: '',
  errorType: ''
})

// 高级查询
const advancedQuery = ref({
  timeRange: [] as string[],
  statuses: [] as string[],
  graphIds: [] as string[],
  minDuration: undefined as number | undefined,
  maxDuration: undefined as number | undefined,
  minNodes: undefined as number | undefined,
  maxNodes: undefined as number | undefined
})

// 分页
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 排序
const sortInfo = ref({
  prop: 'startTime',
  order: 'descending'
})

// 数据
const executions = ref<TaskGraphExecution[]>([])
const statistics = ref<MonitoringStatistics>({
  totalExecutions: 0,
  successfulExecutions: 0,
  failedExecutions: 0,
  averageExecutionTime: 0,
  successRate: 0,
  errorRate: 0,
  averageNodesPerExecution: 0,
  mostCommonErrors: [],
  performanceMetrics: {
    averageCpuUsage: 0,
    averageMemoryUsage: 0,
    peakCpuUsage: 0,
    peakMemoryUsage: 0
  }
})

// 可用的TaskGraph列表
const availableGraphs = ref<Array<{ id: string; name?: string }>>([])

// 可用的错误类型
const availableErrorTypes = ref<Array<{ type: string; count: number }>>([])

// 图表数据
const chartData = computed(() => {
  // 生成简单的柱状图数据
  return [
    { label: '运行中', height: Math.random() * 50 + 20, value: runningExecutions.value.length },
    { label: '已完成', height: Math.random() * 50 + 20, value: completedExecutions.value.length },
    { label: '失败', height: Math.random() * 50 + 20, value: failedExecutions.value.length },
    { label: '取消', height: Math.random() * 50 + 20, value: state.value.activeExecutions.filter(e => e.status === 'cancelled').length }
  ]
})

// 获取状态标签类型
const getStatusTagType = (status: string): string => {
  const types: Record<string, string> = {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
    paused: 'warning'
  }
  return types[status] || 'info'
}

// 获取状态文本
const getStatusText = (status: string): string => {
  const texts: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '取消',
    paused: '暂停'
  }
  return texts[status] || '未知'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 控制执行
// 查看执行详情
const viewExecutionDetail = (execution: TaskGraphExecution) => {
  selectedExecution.value = execution
  showDetailDialog.value = true
}

// 控制执行
const controlExecution = async (execution: TaskGraphExecution, action: string) => {
  try {
    await controlTask({
      executionId: execution.executionId,
      action: action as unknown,
      reason: '用户手动操作'
    })
    ElMessage.success('操作已发送')
    loadData()
  } catch {
    ElMessage.error('操作失败')
  }
}

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const query: HistoryQuery = {
      timeRange: {
        start: queryTimeRange.value[0] || '',
        end: queryTimeRange.value[1] || ''
      },
      filters: {
        status: queryFilters.value.status || undefined,
        graphId: queryFilters.value.graphId || undefined,
        errorType: queryFilters.value.errorType || undefined
      },
      pagination: {
        page: pagination.value.page,
        pageSize: pagination.value.pageSize
      },
      sortBy: sortInfo.value.prop,
      sortOrder: sortInfo.value.order === 'ascending' ? 'asc' : 'desc'
    }

    const result = await monitoringService.queryHistory(query)
    executions.value = result.executions
    pagination.value.total = result.total

    // 加载统计信息
    const stats = await monitoringService.getStatistics(queryFilters.value.graphId)
    statistics.value = stats

    // 加载可用数据
    const execResult = await monitoringService.getExecutions(undefined, undefined, 1000)
    const graphMap = new Map()
    execResult.executions.forEach(exec => {
      if (!graphMap.has(exec.graphId)) {
        graphMap.set(exec.graphId, { id: exec.graphId, name: exec.graphId })
      }
    })
    availableGraphs.value = Array.from(graphMap.values())

    // 加载错误类型
    const errorSummary = await monitoringService.getErrorSummary(queryFilters.value.graphId)
    availableErrorTypes.value = errorSummary.common_errors || []
  } catch (error) {
    console.error('加载历史数据失败:', error)
    ElMessage.error('加载历史数据失败')
  } finally {
    loading.value = false
  }
}

// 时间范围变化处理
const onTimeRangeChange = () => {
  pagination.value.page = 1
  loadData()
}

// 过滤变化处理
const onFilterChange = () => {
  pagination.value.page = 1
  loadData()
}

// 排序变化处理
const onSortChange = ({ prop, order }: { prop: string; order: string }) => {
  sortInfo.value = { prop, order }
  loadData()
}

// 分页变化处理
const onPageChange = (page: number) => {
  pagination.value.page = page
  loadData()
}

const onPageSizeChange = (pageSize: number) => {
  pagination.value.pageSize = pageSize
  pagination.value.page = 1
  loadData()
}

// 刷新数据
const refreshData = () => {
  loadData()
}

// 重置过滤器
const resetFilters = () => {
  queryTimeRange.value = ['', '']
  queryFilters.value = {
    status: '',
    graphId: '',
    errorType: ''
  }
  pagination.value.page = 1
  loadData()
}

// 导出数据
const exportData = async () => {
  try {
    const exportOptions = {
      format: 'xlsx' as const,
      timeRange: {
        start: queryTimeRange.value[0] || '',
        end: queryTimeRange.value[1] || ''
      },
      includeMetrics: true,
      includeExecutions: true,
      includeLogs: false,
      includeAlerts: false
    }

    const blob = await monitoringService.exportData(exportOptions)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `monitoring-data-${new Date().toISOString().split('T')[0]}.xlsx`
    a.click()
    URL.revokeObjectURL(url)

    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

// 执行高级查询
const executeAdvancedQuery = async () => {
  try {
    // 转换高级查询为标准查询格式
    const query: HistoryQuery = {
      timeRange: {
        start: advancedQuery.value.timeRange[0] || '',
        end: advancedQuery.value.timeRange[1] || ''
      },
      filters: {
        status: advancedQuery.value.statuses.length > 0 ? advancedQuery.value.statuses[0] : undefined,
        graphId: advancedQuery.value.graphIds.length > 0 ? advancedQuery.value.graphIds[0] : undefined
      },
      pagination: {
        page: 1,
        pageSize: 100
      },
      sortBy: 'startTime',
      sortOrder: 'desc'
    }

    const result = await monitoringService.queryHistory(query)
    executions.value = result.executions
    pagination.value.total = result.total

    showQueryDialog.value = false
    ElMessage.success('查询完成')
  } catch {
    ElMessage.error('查询失败')
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.history-analysis-panel {
  height: 100%;
}

.history-card {
  height: 100%;
}

.history-controls {
  display: flex;
  gap: 10px;
}

.query-filters {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.statistics-overview {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.simple-charts {
  margin-bottom: 20px;
}

.chart-container {
  height: 200px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 15px;
}

.chart-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: flex-end;
}

.chart-data {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  height: 100%;
}

.chart-bar {
  width: 30px;
  background: linear-gradient(to top, #409eff, #67c23a);
  border-radius: 3px;
  transition: height 0.3s ease;
}

.chart-label {
  font-size: 12px;
  color: #606266;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}

.performance-metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metric-item {
  display: flex;
  justify-content: space-between;
}

.metric-label {
  font-weight: bold;
  color: #303133;
}

.metric-value {
  color: #409eff;
}

.execution-table {
  margin-top: 20px;
}

.pagination-container {
  margin-top: 20px;
  text-align: right;
}

.execution-detail {
  padding: 20px;
}

.execution-detail h3 {
  margin: 0 0 15px 0;
  font-size: 16px;
  color: #303133;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .query-filters .el-col {
    margin-bottom: 10px;
  }
  
  .statistics-overview .el-col {
    margin-bottom: 15px;
  }
  
  .simple-charts .el-col {
    margin-bottom: 15px;
  }
  
  .chart-container {
    height: 150px;
  }
}
</style>