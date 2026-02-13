/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="tool-call">
    <el-card class="tool-card" shadow="never">
      <template #header>
        <div class="tool-header">
          <div class="tool-icon">
            <el-icon :size="20">
              <Tools />
            </el-icon>
          </div>
          <div class="tool-info">
            <h3>{{ toolCall.tool_name }}</h3>
            <div class="tool-id">ID: {{ toolCall.tool_call_id }}</div>
          </div>
          <div class="tool-status">
            <el-tag
              :type="toolHelpers.getStatusTagType(toolCall.status)"
              size="small"
              effect="light"
              round
            >
              {{ toolHelpers.getStatusText(toolCall.status) }}
            </el-tag>
            <div v-if="toolCall.status === 'in_progress'" class="progress-indicator">
              <el-icon class="is-loading"><Loading /></el-icon>
            </div>
          </div>
        </div>
      </template>
      
      <div class="tool-content">
        <!-- 增强执行进度部分 -->
        <div v-if="showProgress" class="enhanced-progress-section">
          <div class="section-header">
            <h4>执行进度</h4>
          </div>
          
          <!-- 总体进度条 -->
          <div class="overall-progress">
            <el-progress
              :percentage="toolCall.progress_percentage || 0"
              :status="toolHelpers.getProgressStatus(toolCall.status)"
              :stroke-width="8"
              :show-text="true"
            />
            <div class="progress-time">
              <span v-if="toolCall.execution_time">
                已用时: {{ toolHelpers.formatExecutionTime(toolCall.execution_time) }}
              </span>
              <span v-if="toolCall.estimated_remaining_time">
                预计剩余: {{ toolHelpers.formatExecutionTime(toolCall.estimated_remaining_time) }}
              </span>
            </div>
          </div>
          
          <!-- 步骤进度指示器 -->
          <div v-if="toolCall.total_steps && toolCall.total_steps > 1" class="steps-progress">
            <div class="steps-header">
              <h4>执行步骤</h4>
              <span class="steps-count">{{ (toolCall.current_step_index ?? 0) + 1 }}/{{ toolCall.total_steps }}</span>
            </div>
            <div class="steps-indicator">
              <div
                v-for="(step, index) in toolCall.total_steps"
                :key="index"
                :class="['step-item', getStepClass(index)]"
              >
                <div class="step-number">{{ index + 1 }}</div>
                <div class="step-line" v-if="index < toolCall.total_steps - 1"></div>
              </div>
            </div>
            <div class="current-step-description" v-if="toolCall.current_step">
              {{ toolCall.current_step }}
            </div>
          </div>
          
          <!-- 当前步骤 -->
          <div v-if="toolCall.current_step && (!toolCall.total_steps || toolCall.total_steps <= 1)" class="current-step">
            <el-icon><Clock /></el-icon>
            <span class="step-text">{{ toolCall.current_step }}</span>
          </div>
          
          <!-- 进度历史 -->
          <div v-if="toolCall.progress_history && toolCall.progress_history.length > 0" class="progress-history">
            <div class="history-header">
              <h4>执行历史</h4>
              <el-button size="small" text @click="toggleHistoryExpanded">
                {{ isHistoryExpanded ? '收起' : '展开' }}
              </el-button>
            </div>
            <div v-show="isHistoryExpanded" class="history-list">
              <div
                v-for="(item, index) in toolCall.progress_history"
                :key="index"
                class="history-item"
              >
                <span class="history-time">{{ formatTime(item.timestamp) }}</span>
                <span class="history-message">{{ item.message }}</span>
                <span v-if="item.progress_percentage !== undefined" class="history-progress">
                  {{ item.progress_percentage }}%
                </span>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 性能指标展示 -->
        <div v-if="showPerformanceMetrics" class="performance-section">
          <div class="section-header">
            <h4>性能指标</h4>
            <el-button
              size="small"
              text
              @click="togglePerformanceExpanded"
              :icon="isPerformanceExpanded ? 'Fold' : 'Expand'"
            >
              {{ isPerformanceExpanded ? '收起' : '展开' }}
            </el-button>
          </div>
          
          <div v-show="isPerformanceExpanded" class="performance-content">
            <!-- 执行时间 -->
            <div v-if="toolCall.execution_time" class="metric-item">
              <div class="metric-label">执行时间</div>
              <div class="metric-value">{{ toolHelpers.formatExecutionTime(toolCall.execution_time) }}</div>
            </div>
            
            <!-- 性能指标 -->
            <div v-if="toolCall.performance_metrics" class="detailed-metrics">
              <div
                v-for="(value, key) in toolCall.performance_metrics"
                :key="key"
                class="metric-item"
              >
                <div class="metric-label">{{ formatMetricLabel(key) }}</div>
                <div class="metric-value">{{ formatMetricValue(key, value) }}</div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="params-section">
          <div class="section-header" @click="toggleParamsExpanded" :class="{ 'clickable': !isParamsExpanded }">
            <h4>参数</h4>
            <div class="header-actions">
              <el-button
                v-if="isParamsExpanded"
                size="small"
                text
                @click.stop="copyParams"
                :icon="DocumentCopy"
              >
                复制
              </el-button>
              <el-button
                size="small"
                text
                @click.stop="toggleParamsExpanded"
                :icon="isParamsExpanded ? Fold : Expand"
              >
                {{ isParamsExpanded ? '收起' : '展开' }}
              </el-button>
            </div>
          </div>
          <div v-if="!isParamsExpanded" class="section-summary" @click="toggleParamsExpanded">
            {{ getParamsSummary() }}
          </div>
          <el-collapse-transition>
            <div v-show="isParamsExpanded">
              <el-scrollbar height="150px">
                <pre class="params-content">{{ toolHelpers.formatToolInput(toolCall.tool_input) }}</pre>
              </el-scrollbar>
            </div>
          </el-collapse-transition>
        </div>

        <div v-if="toolCall.output" class="output-section">
          <div class="section-header" @click="toggleOutputExpanded" :class="{ 'clickable': !isOutputExpanded }">
            <h4>输出</h4>
            <div class="header-actions">
              <el-button
                v-if="isOutputExpanded"
                size="small"
                text
                @click.stop="copyOutput"
                :icon="DocumentCopy"
              >
                复制
              </el-button>
              <el-button
                size="small"
                text
                @click.stop="toggleOutputExpanded"
                :icon="isOutputExpanded ? Fold : Expand"
              >
                {{ isOutputExpanded ? '收起' : '展开' }}
              </el-button>
            </div>
          </div>
          <div v-if="!isOutputExpanded" class="section-summary" @click="toggleOutputExpanded">
            {{ getOutputSummary() }}
          </div>
          <el-collapse-transition>
            <div v-show="isOutputExpanded" class="output-content">
              <pre>{{ toolHelpers.formatToolOutput(toolCall.output) }}</pre>
            </div>
          </el-collapse-transition>
        </div>

        <div v-if="toolCall.error" class="error-section">
          <div class="section-header" @click="toggleErrorExpanded" :class="{ 'clickable': !isErrorExpanded }">
            <h4>错误</h4>
            <div class="header-actions">
              <el-button
                v-if="isErrorExpanded"
                size="small"
                text
                @click.stop="copyError"
                :icon="DocumentCopy"
              >
                复制
              </el-button>
              <el-button
                size="small"
                text
                @click.stop="toggleErrorExpanded"
                :icon="isErrorExpanded ? Fold : Expand"
              >
                {{ isErrorExpanded ? '收起' : '展开' }}
              </el-button>
            </div>
          </div>
          <div v-if="!isErrorExpanded" class="section-summary error-summary" @click="toggleErrorExpanded">
            {{ getErrorSummary() }}
          </div>
          <el-collapse-transition>
            <div v-show="isErrorExpanded" class="error-content">
              <pre>{{ toolCall.error }}</pre>
            </div>
          </el-collapse-transition>
        </div>
        
        <div class="tool-actions">
          <!-- 主要操作按钮 -->
          <div class="primary-actions">
            <el-button
              v-if="toolCall.status === 'failed'"
              size="small"
              type="primary"
              @click="retryToolCall"
              :icon="RefreshRight"
              :loading="isRetrying"
            >
              重试
            </el-button>
            
            <el-button
              v-if="toolCall.status === 'in_progress' || toolCall.status === 'started'"
              size="small"
              type="danger"
              @click="cancelToolCall"
              :icon="Close"
              :loading="isCancelling"
            >
              取消
            </el-button>
            
            <el-button
              size="small"
              @click="viewDetails"
              :icon="View"
            >
              查看详情
            </el-button>
          </div>
          
          <!-- 更多操作下拉菜单 -->
          <el-dropdown trigger="click" @command="handleMoreAction">
            <el-button size="small" :icon="MoreFilled" circle />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="copy-input" :icon="DocumentCopy">
                  复制输入参数
                </el-dropdown-item>
                <el-dropdown-item command="copy-output" :icon="DocumentCopy" v-if="toolCall.output">
                  复制输出结果
                </el-dropdown-item>
                <el-dropdown-item command="copy-error" :icon="DocumentCopy" v-if="toolCall.error">
                  复制错误信息
                </el-dropdown-item>
                <el-dropdown-item command="export" :icon="Download">
                  导出执行记录
                </el-dropdown-item>
                <el-dropdown-item command="share" :icon="Share">
                  分享工具调用
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElCard, ElIcon, ElTag, ElButton, ElScrollbar, ElMessage, ElProgress, ElCollapseTransition } from 'element-plus'
import {
  Tools,
  Loading,
  DocumentCopy,
  RefreshRight,
  View,
  Clock,
  Expand,
  Fold,
  Close,
  MoreFilled,
  Download,
  Share
} from '@element-plus/icons-vue'
import { copyToClipboard } from '@/utils/clipboard'
import type { ToolCall } from '@/types/websocket'
import { toolHelpers } from '@/utils/toolHelpers'

const props = defineProps<{
  toolCall: ToolCall
}>()

const emit = defineEmits<{
  toolAction: [action: string, data: unknown]
}>()

// 响应式变量
const isHistoryExpanded = ref(false)
const isPerformanceExpanded = ref(false)
const isParamsExpanded = ref(false)
const isOutputExpanded = ref(false)
const isErrorExpanded = ref(false)
const isRetrying = ref(false)
const isCancelling = ref(false)

// 计算是否显示进度信息
const showProgress = computed(() => {
  return toolHelpers.shouldShowProgress(
    props.toolCall.progress_percentage,
    props.toolCall.current_step,
    props.toolCall.execution_time,
    props.toolCall.estimated_remaining_time
  )
})

// 计算是否显示性能指标
const showPerformanceMetrics = computed(() => {
  return toolHelpers.shouldShowPerformanceMetrics(
    props.toolCall.execution_time,
    props.toolCall.performance_metrics
  )
})

const copyParams = async () => {
  await toolHelpers.copyToolInput(props.toolCall.tool_input, props.toolCall.tool_name)
}

const copyOutput = async () => {
  await toolHelpers.copyToolOutput(props.toolCall.output, props.toolCall.tool_name)
}

const copyError = async () => {
  await toolHelpers.copyError(props.toolCall.error || '', props.toolCall.tool_name)
}

const retryToolCall = () => {
  emit('toolAction', 'retry', {
    toolCall: props.toolCall
  })
}

const viewDetails = () => {
  emit('toolAction', 'details', {
    toolCall: props.toolCall
  })
}

// 切换历史记录展开状态
const toggleHistoryExpanded = () => {
  isHistoryExpanded.value = !isHistoryExpanded.value
}

// 切换性能指标展开状态
const togglePerformanceExpanded = () => {
  isPerformanceExpanded.value = !isPerformanceExpanded.value
}

// 切换参数展开状态
const toggleParamsExpanded = () => {
  isParamsExpanded.value = !isParamsExpanded.value
}

// 切换输出展开状态
const toggleOutputExpanded = () => {
  isOutputExpanded.value = !isOutputExpanded.value
}

// 切换错误展开状态
const toggleErrorExpanded = () => {
  isErrorExpanded.value = !isErrorExpanded.value
}

// 生成参数摘要
const getParamsSummary = () => {
  const input = props.toolCall.tool_input
  if (!input) return '无参数'

  const inputStr = JSON.stringify(input)

  if (Array.isArray(input)) {
    return `${input.length} 个参数`
  } else if (typeof input === 'object' && input !== null) {
    const keys = Object.keys(input)
    return `${keys.length} 个参数: ${keys.slice(0, 3).join(', ')}${keys.length > 3 ? '...' : ''}`
  } else {
    const preview = inputStr.substring(0, 60)
    return preview + (inputStr.length > 60 ? '...' : '')
  }
}

// 生成输出摘要
const getOutputSummary = () => {
  const output = props.toolCall.output
  if (!output) return '无输出'

  const outputStr = typeof output === 'string' ? output : JSON.stringify(output)
  const lineCount = outputStr.split('\n').length
  const charCount = outputStr.length

  if (Array.isArray(output)) {
    return `返回了 ${output.length} 条结果`
  } else if (typeof output === 'object' && typeof output !== null) {
    const keys = Object.keys(output)
    return `返回了对象 (${keys.length} 个字段)`
  } else if (lineCount > 3) {
    return `${lineCount} 行内容 (${charCount} 字符)`
  } else {
    const preview = outputStr.substring(0, 80)
    return preview + (outputStr.length > 80 ? '...' : '')
  }
}

// 生成错误摘要
const getErrorSummary = () => {
  const error = props.toolCall.error
  if (!error) return '未知错误'

  // 获取第一行作为摘要
  const lines = error.split('\n')
  const firstLine = lines[0]

  if (firstLine.length > 80) {
    return firstLine.substring(0, 80) + '...'
  }

  return firstLine
}

// 获取步骤样式类
const getStepClass = (index: number) => {
  if (!props.toolCall.current_step_index) return ''
  
  if (index < props.toolCall.current_step_index) {
    return 'completed'
  } else if (index === props.toolCall.current_step_index) {
    return 'active'
  } else {
    return 'pending'
  }
}

// 格式化时间
const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

// 格式化指标标签
const formatMetricLabel = (key: string) => {
  const labelMap: Record<string, string> = {
    cpu_usage: 'CPU使用率',
    memory_usage: '内存使用',
    disk_io: '磁盘IO',
    network_io: '网络IO',
    cache_hit_rate: '缓存命中率',
    response_time: '响应时间'
  }
  return labelMap[key] || key
}

// 格式化指标值
const formatMetricValue = (key: string, value: unknown) => {
  if (typeof value === 'number') {
    if (key.includes('rate') || key.includes('percentage')) {
      return `${(value * 100).toFixed(2)}%`
    } else if (key.includes('time')) {
      return `${value.toFixed(2)}ms`
    } else if (key.includes('bytes') || key.includes('size')) {
      return formatBytes(value)
    }
  }
  return String(value)
}

// 格式化字节数
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 处理更多操作
const handleMoreAction = (command: string) => {
  switch (command) {
    case 'copy-input':
      copyParams()
      break
    case 'copy-output':
      copyOutput()
      break
    case 'copy-error':
      copyError()
      break
    case 'export':
      exportToolCall()
      break
    case 'share':
      shareToolCall()
      break
  }
}

// 取消工具调用
const cancelToolCall = () => {
  isCancelling.value = true
  emit('toolAction', 'cancel', {
    toolCall: props.toolCall
  })
  // 模拟取消后的状态重置
  setTimeout(() => {
    isCancelling.value = false
  }, 1000)
}

// 导出工具调用记录
const exportToolCall = () => {
  const exportData = {
    toolName: props.toolCall.tool_name,
    toolCallId: props.toolCall.tool_call_id,
    status: props.toolCall.status,
    input: props.toolCall.tool_input,
    output: props.toolCall.output,
    error: props.toolCall.error,
    executionTime: props.toolCall.execution_time,
    timestamp: new Date().toISOString()
  }
  
  const dataStr = JSON.stringify(exportData, null, 2)
  const blob = new Blob([dataStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  
  const a = document.createElement('a')
  a.href = url
  a.download = `tool-call-${props.toolCall.tool_call_id}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  
  ElMessage.success('工具调用记录已导出')
}

// 分享工具调用
const shareToolCall = async () => {
  const shareData = {
    toolName: props.toolCall.tool_name,
    toolCallId: props.toolCall.tool_call_id,
    status: props.toolCall.status,
    result: props.toolCall.output || props.toolCall.error
  }

  const success = await copyToClipboard(JSON.stringify(shareData, null, 2))
  if (success) {
    ElMessage.success('工具调用信息已复制到剪贴板，可以分享给其他人')
  } else {
    ElMessage.error('分享失败')
  }
}
</script>

<style scoped>
.tool-call {
  margin-bottom: 12px;
}

.tool-card {
  border-left: 3px solid var(--el-color-primary);
  border-radius: 8px;
  overflow: hidden;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0;
}

.tool-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.tool-info {
  flex: 1;
  min-width: 0;
}

.tool-info h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.tool-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.tool-status {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.progress-indicator {
  display: flex;
  align-items: center;
}

.tool-content {
  padding: 0;
}

.progress-section {
  margin-bottom: 16px;
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}

.progress-bar-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.progress-text {
  min-width: 50px;
  text-align: right;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.current-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background-color: var(--el-color-primary-light-9);
  border-radius: 4px;
  margin-bottom: 8px;
}

.step-text {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.execution-time {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.params-section,
.output-section,
.error-section {
  margin-bottom: 16px;
}

.section-header.clickable {
  cursor: pointer;
  user-select: none;
}

.section-header.clickable:hover h4 {
  color: var(--el-color-primary);
}

.section-summary {
  padding: 8px 12px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  border-left: 3px solid var(--el-border-color);
}

.section-summary:hover {
  background-color: var(--el-fill-color-light);
  border-left-color: var(--el-color-primary);
  color: var(--el-text-color-primary);
}

.error-summary {
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  border-left-color: var(--el-color-danger);
}

.error-summary:hover {
  background-color: var(--el-color-danger-light-8);
  border-left-color: var(--el-color-danger-dark-2);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}

.section-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.header-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.params-content {
  background-color: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  color: var(--el-text-color-regular);
}

.output-content,
.error-content {
  margin-top: 8px;
  background-color: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 8px 0 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  color: var(--el-text-color-regular);
}

.error-content {
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  border: 1px solid var(--el-color-danger-light-7);
}

.tool-actions {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .tool-header {
    gap: 8px;
  }
  
  .tool-icon {
    width: 32px;
    height: 32px;
  }
  
  .tool-info h3 {
    font-size: 14px;
  }
  
  .tool-id {
    font-size: 11px;
  }
}

/* 增强进度样式 */
.overall-progress {
  margin-bottom: 16px;
}

.progress-time {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.steps-progress {
  margin-bottom: 16px;
}

.steps-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.steps-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background-color: var(--el-fill-color);
  padding: 2px 8px;
  border-radius: 12px;
}

.steps-indicator {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.step-item {
  display: flex;
  align-items: center;
}

.step-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  margin-right: 4px;
}

.step-line {
  width: 40px;
  height: 2px;
  background-color: var(--el-border-color-light);
  margin: 0 4px;
}

.step-item.completed .step-number {
  background-color: var(--el-color-success);
  color: white;
}

.step-item.completed .step-line {
  background-color: var(--el-color-success);
}

.step-item.active .step-number {
  background-color: var(--el-color-primary);
  color: white;
  box-shadow: 0 0 0 4px rgba(var(--el-color-primary-rgb), 0.3);
}

.step-item.pending .step-number {
  background-color: var(--el-fill-color);
  color: var(--el-text-color-secondary);
}

.current-step-description {
  padding: 8px 12px;
  background-color: var(--el-color-primary-light-9);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}

.progress-history {
  margin-bottom: 16px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.history-list {
  max-height: 200px;
  overflow-y: auto;
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}

.history-time {
  color: var(--el-text-color-secondary);
  margin-right: 8px;
  font-family: monospace;
  min-width: 80px;
}

.history-message {
  flex: 1;
  color: var(--el-text-color-regular);
}

.history-progress {
  color: var(--el-color-primary);
  font-weight: 600;
  margin-left: 8px;
  min-width: 40px;
  text-align: right;
}

/* 性能指标样式 */
.performance-section {
  margin-bottom: 16px;
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}

.performance-content {
  margin-top: 8px;
}

.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.metric-item:last-child {
  border-bottom: none;
}

.metric-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-family: monospace;
}

.detailed-metrics {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 主要操作按钮样式 */
.primary-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

/* 下拉菜单样式 */
:deep(.el-dropdown-menu__item) {
  font-size: 12px;
}
</style>