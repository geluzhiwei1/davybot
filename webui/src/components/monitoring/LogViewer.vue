/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="log-viewer">
    <el-card class="log-card" header="日志查看器">
      <template #extra>
        <div class="log-controls">
          <el-switch
            v-model="autoScroll"
            active-text="自动滚动"
            inactive-text="手动滚动"
          />
          <el-button 
            size="small"
            @click="clearLogs"
          >
            <el-icon><Delete /></el-icon>
            清除
          </el-button>
          <el-button 
            size="small"
            @click="exportLogs"
          >
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </div>
      </template>

      <!-- 日志过滤 -->
      <div class="log-filters">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-select
              v-model="logLevel"
              placeholder="日志级别"
              @change="onFilterChange"
            >
              <el-option label="全部" value="" />
              <el-option label="错误" value="error" />
              <el-option label="警告" value="warning" />
              <el-option label="信息" value="info" />
              <el-option label="调试" value="debug" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-select
              v-model="logSource"
              placeholder="日志来源"
              @change="onFilterChange"
            >
              <el-option label="全部" value="" />
              <el-option label="系统" value="system" />
              <el-option label="任务" value="task" />
              <el-option label="节点" value="node" />
              <el-option label="网络" value="network" />
            </el-select>
          </el-col>
          <el-col :span="6">
            <el-input
              v-model="searchText"
              placeholder="搜索日志内容"
              clearable
              @input="onSearchInput"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
          <el-col :span="6">
            <el-date-picker
              v-model="timeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              @change="onTimeRangeChange"
            />
          </el-col>
        </el-row>
      </div>

      <!-- 日志统计 -->
      <div class="log-statistics">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic 
              title="错误日志" 
              :value="logStatistics.error"
              :value-style="{ color: '#f56c6c' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="警告日志" 
              :value="logStatistics.warning"
              :value-style="{ color: '#e6a23c' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="信息日志" 
              :value="logStatistics.info"
              :value-style="{ color: '#409eff' }"
            />
          </el-col>
          <el-col :span="6">
            <el-statistic 
              title="调试日志" 
              :value="logStatistics.debug"
              :value-style="{ color: '#67c23a' }"
            />
          </el-col>
        </el-row>
      </div>

      <!-- 日志内容 -->
      <div class="log-content">
        <div 
          ref="logContainerRef" 
          class="log-container"
          @scroll="onScroll"
        >
          <div
            v-for="log in filteredLogs"
            :key="log.id"
            class="log-entry"
            :class="getLogEntryClass(log)"
          >
            <div class="log-header">
              <span class="log-time">{{ formatTimestamp(log.timestamp, 'time') }}</span>
              <el-tag :type="getLogLevelType(log.level)" size="small">
                {{ log.level.toUpperCase() }}
              </el-tag>
              <el-tag :type="getLogSourceType(log.source)" size="small">
                {{ log.source }}
              </el-tag>
              <span class="log-source" v-if="log.executionId">
                执行: {{ log.executionId }}
              </span>
              <span class="log-source" v-if="log.nodeId">
                节点: {{ log.nodeId }}
              </span>
            </div>
            <div class="log-message">{{ log.message }}</div>
            <div v-if="log.details" class="log-details">
              <el-collapse>
                <el-collapse-item title="详细信息">
                  <pre>{{ JSON.stringify(log.details, null, 2) }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
            <div v-if="log.stackTrace" class="log-stack-trace">
              <el-collapse>
                <el-collapse-item title="堆栈跟踪">
                  <pre>{{ log.stackTrace }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
        </div>
      </div>

      <!-- 日志分页 -->
      <div class="log-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[50, 100, 200, 500]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="onPageSizeChange"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Download, Search } from '@element-plus/icons-vue'
import { formatTimestamp } from '@/utils/formatters'

interface LogEntry {
  id: string
  timestamp: string
  level: 'error' | 'warning' | 'info' | 'debug'
  source: 'system' | 'task' | 'node' | 'network'
  message: string
  executionId?: string
  nodeId?: string
  details?: unknown
  stackTrace?: string
}

// 状态
const logs = ref<LogEntry[]>([])
const logLevel = ref('')
const logSource = ref('')
const searchText = ref('')
const timeRange = ref<[string, string]>(['', ''])
const autoScroll = ref(true)
const pagination = ref({
  page: 1,
  pageSize: 100,
  total: 0
})

// 引用
const logContainerRef = ref<HTMLElement>()

// 日志统计
const logStatistics = computed(() => {
  const stats = {
    error: 0,
    warning: 0,
    info: 0,
    debug: 0
  }
  
  logs.value.forEach(log => {
    stats[log.level]++
  })
  
  return stats
})

// 过滤后的日志
const filteredLogs = computed(() => {
  let filtered = [...logs.value]
  
  // 级别过滤
  if (logLevel.value) {
    filtered = filtered.filter(log => log.level === logLevel.value)
  }
  
  // 来源过滤
  if (logSource.value) {
    filtered = filtered.filter(log => log.source === logSource.value)
  }
  
  // 时间范围过滤
  if (timeRange.value[0] && timeRange.value[1]) {
    const startTime = new Date(timeRange.value[0]).getTime()
    const endTime = new Date(timeRange.value[1]).getTime()
    filtered = filtered.filter(log => {
      const logTime = new Date(log.timestamp).getTime()
      return logTime >= startTime && logTime <= endTime
    })
  }
  
  // 搜索过滤
  if (searchText.value) {
    const searchLower = searchText.value.toLowerCase()
    filtered = filtered.filter(log => 
      log.message.toLowerCase().includes(searchLower) ||
      (log.executionId && log.executionId.toLowerCase().includes(searchLower)) ||
      (log.nodeId && log.nodeId.toLowerCase().includes(searchLower))
    )
  }

  // 分页
  const start = (pagination.value.page - 1) * pagination.value.pageSize
  const end = start + pagination.value.pageSize

  // Update pagination total (side effect - but necessary for pagination)
  // eslint-disable-next-line vue/no-side-effects-in-computed-properties
  pagination.value.total = filtered.length

  return filtered.slice(start, end)
})

// 获取日志条目样式类
const getLogEntryClass = (log: LogEntry): string => {
  return `log-entry-${log.level} log-entry-${log.source}`
}

// 获取日志级别标签类型
const getLogLevelType = (level: string): string => {
  const types: Record<string, string> = {
    error: 'danger',
    warning: 'warning',
    info: 'primary',
    debug: 'success'
  }
  return types[level] || 'info'
}

// 获取日志来源标签类型
const getLogSourceType = (source: string): string => {
  const types: Record<string, string> = {
    system: 'info',
    task: 'primary',
    node: 'success',
    network: 'warning'
  }
  return types[source] || 'info'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 过滤变化处理
const onFilterChange = () => {
  pagination.value.page = 1
}

// 搜索输入处理
const onSearchInput = () => {
  pagination.value.page = 1
}

// 时间范围变化处理
const onTimeRangeChange = () => {
  pagination.value.page = 1
}

// 分页变化处理
const onPageChange = (page: number) => {
  pagination.value.page = page
}

const onPageSizeChange = (pageSize: number) => {
  pagination.value.pageSize = pageSize
  pagination.value.page = 1
}

// 滚动处理
const onScroll = (event: Event) => {
  const target = event.target as HTMLElement
  const isAtBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 10
  
  if (isAtBottom) {
    autoScroll.value = true
  } else {
    autoScroll.value = false
  }
}

// 清除日志
const clearLogs = () => {
  logs.value = []
  pagination.value.total = 0
  ElMessage.success('日志已清除')
}

// 导出日志
const exportLogs = () => {
  const exportData = filteredLogs.value.map(log => ({
    时间: formatTimestamp(log.timestamp, 'time'),
    级别: log.level,
    来源: log.source,
    消息: log.message,
    执行ID: log.executionId || '',
    节点ID: log.nodeId || '',
    详细信息: log.details ? JSON.stringify(log.details) : '',
    堆栈跟踪: log.stackTrace || ''
  }))
  
  const csv = [
    Object.keys(exportData[0] || {}).join(','),
    ...exportData.map(row => Object.values(row).map(value => `"${value}"`).join(','))
  ].join('\n')
  
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `logs-${new Date().toISOString().split('T')[0]}.csv`
  a.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('日志已导出')
}

// 模拟日志数据生成
const generateMockLogs = (): LogEntry[] => {
  const mockLogs: LogEntry[] = []
  const levels: LogEntry['level'][] = ['error', 'warning', 'info', 'debug']
  const sources: LogEntry['source'][] = ['system', 'task', 'node', 'network']
  const messages = [
    '系统启动完成',
    '任务执行开始',
    '节点处理中',
    '网络连接建立',
    '内存使用率过高',
    '任务执行失败',
    '节点超时',
    '数据同步完成',
    '配置更新成功',
    '性能监控启动',
    '错误：连接超时',
    '警告：磁盘空间不足',
    '信息：用户登录成功',
    '调试：处理请求'
  ]
  
  for (let i = 0; i < 500; i++) {
    const timestamp = new Date(Date.now() - Math.random() * 24 * 60 * 60 * 1000).toISOString()
    const level = levels[Math.floor(Math.random() * levels.length)] as 'error' | 'warning' | 'info' | 'debug'
    const source = sources[Math.floor(Math.random() * sources.length)] as 'system' | 'node' | 'task' | 'network'
    const message = messages[Math.floor(Math.random() * messages.length)] || 'Log message'

    mockLogs.push({
      id: `log-${i}`,
      timestamp,
      level,
      source,
      message,
      executionId: Math.random() > 0.7 ? `exec-${Math.floor(Math.random() * 100)}` : undefined,
      nodeId: Math.random() > 0.8 ? `node-${Math.floor(Math.random() * 50)}` : undefined,
      details: Math.random() > 0.9 ? {
        cpu: Math.random() * 100,
        memory: Math.random() * 100,
        network: Math.random() * 1000
      } : undefined,
      stackTrace: level === 'error' && Math.random() > 0.8 ?
        `Error: ${message}\n  at async function (${timestamp})\n  at main (${timestamp})` : undefined
    })
  }
  
  return mockLogs.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).reverse()
}

// 监听自动滚动
watch(autoScroll, (newValue) => {
  if (newValue && logContainerRef.value) {
    nextTick(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
      }
    })
  }
})

// 监听过滤后的日志变化，自动滚动到底部
watch(filteredLogs, () => {
  if (autoScroll.value && logContainerRef.value) {
    nextTick(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
      }
    })
  }
})

onMounted(() => {
  // 生成模拟日志数据
  logs.value = generateMockLogs()
  pagination.value.total = logs.value.length
})
</script>

<style scoped>
.log-viewer {
  height: 100%;
}

.log-card {
  height: 100%;
}

.log-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.log-filters {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.log-statistics {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.log-content {
  margin-bottom: 20px;
}

.log-container {
  height: 400px;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background-color: #1e1e1e;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  padding: 10px;
}

.log-entry {
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 4px;
  border-left: 3px solid #666;
}

.log-entry-error {
  border-left-color: #f56c6c;
  background-color: #fef0f0;
}

.log-entry-warning {
  border-left-color: #e6a23c;
  background-color: #fdf6ec;
}

.log-entry-info {
  border-left-color: #409eff;
  background-color: #ecf5ff;
}

.log-entry-debug {
  border-left-color: #67c23a;
  background-color: #f0f9ff;
}

.log-entry-system {
  border-left-color: #909399;
  background-color: #f0f9ff;
}

.log-entry-task {
  border-left-color: #409eff;
  background-color: #ecf5ff;
}

.log-entry-node {
  border-left-color: #67c23a;
  background-color: #f0f9ff;
}

.log-entry-network {
  border-left-color: #e6a23c;
  background-color: #fdf6ec;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 5px;
  flex-wrap: wrap;
}

.log-time {
  font-size: 11px;
  color: #909399;
  font-weight: bold;
}

.log-source {
  font-size: 11px;
  color: #606266;
  background-color: #f0f0f0;
  padding: 2px 6px;
  border-radius: 2px;
}

.log-message {
  color: #303133;
  line-height: 1.4;
  margin-bottom: 5px;
}

.log-details,
.log-stack-trace {
  margin-top: 10px;
}

.log-details pre,
.log-stack-trace pre {
  background-color: #f8f8f8;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  padding: 10px;
  font-size: 11px;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
}

.log-pagination {
  text-align: right;
  margin-top: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .log-controls {
    flex-direction: column;
    align-items: stretch;
  }
  
  .log-filters .el-col {
    margin-bottom: 10px;
  }
  
  .log-statistics .el-col {
    margin-bottom: 15px;
  }
  
  .log-container {
    height: 300px;
    font-size: 11px;
  }
  
  .log-entry {
    padding: 8px;
  }
  
  .log-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }
}

@media (max-width: 480px) {
  .log-filters .el-col {
    margin-bottom: 10px;
  }
  
  .log-statistics .el-col {
    margin-bottom: 15px;
  }
  
  .log-container {
    height: 250px;
    font-size: 10px;
  }
  
  .log-entry {
    padding: 6px;
  }
  
  .log-header {
    gap: 3px;
  }
}
</style>