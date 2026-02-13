/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="llm-api-complete-content compact-content">
    <div class="complete-header compact-header">
      <div class="header-left">
        <el-icon class="complete-icon"><CircleCheck /></el-icon>
        <span class="complete-title compact-title">LLM API 完成</span>
        <el-tag size="small" type="success" effect="light" class="compact-tag">
          {{ complete.provider }}
        </el-tag>
        <el-tag size="small" type="info" effect="light" class="compact-tag">
          {{ complete.model }}
        </el-tag>
      </div>
      <div class="header-right">
        <el-tag :type="getFinishReasonTag(complete.finish_reason)" size="small" effect="light" class="compact-tag">
          {{ getFinishReasonText(complete.finish_reason) }}
        </el-tag>
      </div>
    </div>

    <div class="complete-body compact-body">
      <!-- Token 使用统计 -->
      <div class="usage-stats compact-stats">
        <div class="stat-item">
          <el-icon><Document /></el-icon>
          <div class="stat-info">
            <div class="stat-label">输入 Tokens</div>
            <div class="stat-value">{{ complete.usage?.prompt_tokens || 0 }}</div>
          </div>
        </div>

        <div class="stat-item">
          <el-icon><ChatLineSquare /></el-icon>
          <div class="stat-info">
            <div class="stat-label">输出 Tokens</div>
            <div class="stat-value">{{ complete.usage?.completion_tokens || 0 }}</div>
          </div>
        </div>

        <div class="stat-item">
          <el-icon><DataAnalysis /></el-icon>
          <div class="stat-info">
            <div class="stat-label">总 Tokens</div>
            <div class="stat-value">{{ complete.usage?.total_tokens || 0 }}</div>
          </div>
        </div>

        <div class="stat-item" v-if="complete.duration_ms">
          <el-icon><Timer /></el-icon>
          <div class="stat-info">
            <div class="stat-label">执行时间</div>
            <div class="stat-value">{{ formatDuration(complete.duration_ms, 'standard') }}</div>
          </div>
        </div>
      </div>

      <!-- 可视化图表 -->
      <div class="token-visualization compact-detail-block" v-if="complete.usage">
        <div class="chart-title">Token 使用分布</div>
        <div class="bar-chart compact-mt-sm">
          <div class="bar-item">
            <div class="bar-label">输入</div>
            <div class="bar-track">
              <div
                class="bar-fill prompt-bar"
                :style="{ width: getPromptPercentage() + '%' }"
              >
                <span class="bar-value">{{ complete.usage.prompt_tokens }}</span>
              </div>
            </div>
          </div>
          <div class="bar-item">
            <div class="bar-label">输出</div>
            <div class="bar-track">
              <div
                class="bar-fill completion-bar"
                :style="{ width: getCompletionPercentage() + '%' }"
              >
                <span class="bar-value">{{ complete.usage.completion_tokens }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 性能指标 -->
      <div class="performance-metrics compact-stats" v-if="complete.duration_ms && complete.usage">
        <div class="metric-item">
          <div class="metric-label">Tokens/秒</div>
          <div class="metric-value compact-code">{{ calculateTokensPerSecond().toFixed(1) }}</div>
        </div>
        <div class="metric-item" v-if="estimatedCost > 0">
          <div class="metric-label">估算成本</div>
          <div class="metric-value compact-code">${{ estimatedCost.toFixed(4) }}</div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="complete-actions compact-actions">
        <el-button size="small" @click="copyUsage" :icon="DocumentCopy" class="compact-btn">
          复制统计
        </el-button>
        <el-button size="small" @click="exportUsage" :icon="Download" class="compact-btn">
          导出
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDuration } from '@/utils/formatters'
import { copyToClipboard } from '@/utils/clipboard'
import { computed } from 'vue'
import {
  CircleCheck,
  Document,
  ChatLineSquare,
  DataAnalysis,
  Timer,
  DocumentCopy,
  Download
} from '@element-plus/icons-vue'
import { ElTag, ElIcon, ElButton, ElMessage } from 'element-plus'

// 定义LLM API完成消息类型
interface LLMApiCompleteBlock {
  type: 'llm_api_complete'
  provider: string
  model: string
  finish_reason?: string
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  duration_ms?: number
}

const props = defineProps<{
  block: LLMApiCompleteBlock
}>()

const complete = computed(() => props.block)

// 计算prompt tokens百分比
const getPromptPercentage = () => {
  const usage = complete.value.usage
  if (!usage || usage.total_tokens === 0) return 0
  return (usage.prompt_tokens / usage.total_tokens) * 100
}

// 计算completion tokens百分比
const getCompletionPercentage = () => {
  const usage = complete.value.usage
  if (!usage || usage.total_tokens === 0) return 0
  return (usage.completion_tokens / usage.total_tokens) * 100
}

// 计算每秒tokens数
const calculateTokensPerSecond = () => {
  const duration = complete.value.duration_ms
  const usage = complete.value.usage
  if (!duration || !usage) return 0
  const seconds = duration / 1000
  if (seconds === 0) return 0
  return usage.total_tokens / seconds
}

// 估算成本（简化版本，实际应该根据provider和model计算）
const estimatedCost = computed(() => {
  const usage = complete.value.usage
  if (!usage) return 0

  // 简化的成本计算（每1M tokens的价格）
  // 实际应该根据provider和model从配置中获取价格
  const promptPrice = 0.0001 // $0.0001 per 1K tokens
  const completionPrice = 0.0002 // $0.0002 per 1K tokens

  const promptCost = (usage.prompt_tokens / 1000) * promptPrice
  const completionCost = (usage.completion_tokens / 1000) * completionPrice

  return promptCost + completionCost
})

// 获取完成原因标签颜色
const getFinishReasonTag = (reason?: string) => {
  switch (reason) {
    case 'stop':
      return 'success'
    case 'length':
      return 'warning'
    case 'content_filter':
      return 'danger'
    case 'tool_calls':
      return 'info'
    default:
      return 'info'
  }
}

// 获取完成原因文本
const getFinishReasonText = (reason?: string) => {
  switch (reason) {
    case 'stop':
      return '正常完成'
    case 'length':
      return '达到长度限制'
    case 'content_filter':
      return '内容过滤'
    case 'tool_calls':
      return '工具调用'
    default:
      return reason || '未知'
  }
}

// 复制使用统计
const copyUsage = async () => {
  const usage = complete.value.usage
  if (!usage) return

  const text = `LLM API 使用统计:
Provider: ${complete.value.provider}
Model: ${complete.value.model}
输入 Tokens: ${usage.prompt_tokens}
输出 Tokens: ${usage.completion_tokens}
总 Tokens: ${usage.total_tokens}
执行时间: ${complete.value.duration_ms ? formatDuration(complete.value.duration_ms, 'standard') : 'N/A'}
估算成本: $${estimatedCost.value.toFixed(4)}`

  const success = await copyToClipboard(text)
  if (success) {
    ElMessage.success('使用统计已复制到剪贴板')
  } else {
    ElMessage.error('复制失败')
  }
}

// 导出使用统计
const exportUsage = () => {
  try {
    const data = {
      provider: complete.value.provider,
      model: complete.value.model,
      finish_reason: complete.value.finish_reason,
      usage: complete.value.usage,
      duration_ms: complete.value.duration_ms,
      estimated_cost: estimatedCost.value,
      timestamp: new Date().toISOString()
    }

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `llm-usage-${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    ElMessage.success('使用统计已导出')
  } catch (error) {
    console.error('Failed to export usage:', error)
    ElMessage.error('导出失败')
  }
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.complete-header {
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
}

.complete-icon {
  font-size: 16px;
  color: var(--modern-color-success);
}

/* 统计信息 */
.usage-stats {
  margin-bottom: var(--modern-spacing-md);
}

.stat-item .el-icon {
  font-size: 18px;
  color: var(--modern-color-primary);
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: var(--modern-font-xs);
  color: var(--el-text-color-secondary);
}

.stat-value {
  font-size: var(--modern-font-lg);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* 可视化图表 */
.token-visualization {
  margin-bottom: var(--modern-spacing-md);
}

.chart-title {
  font-size: var(--modern-font-sm);
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.bar-chart {
  display: flex;
  flex-direction: column;
  gap: var(--modern-spacing-sm);
}

.bar-item {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
}

.bar-label {
  width: 60px;
  font-size: var(--modern-font-sm);
  color: var(--el-text-color-secondary);
  text-align: right;
  flex-shrink: 0;
}

.bar-track {
  flex: 1;
  height: 24px;
  background-color: var(--modern-bg-subtle);
  border-radius: var(--modern-radius-sm);
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: var(--modern-spacing-sm);
  transition: width 0.5s ease;
  font-size: var(--modern-font-xs);
  font-weight: 600;
  color: white;
}

.prompt-bar {
  background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
}

.completion-bar {
  background: linear-gradient(90deg, #10b981 0%, #059669 100%);
}

.bar-value {
  color: white;
}

/* 性能指标 */
.performance-metrics {
  margin-bottom: var(--modern-spacing-md);
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--modern-spacing-sm);
}

.metric-label {
  font-size: var(--modern-font-xs);
  color: var(--el-text-color-secondary);
}

.metric-value {
  font-size: var(--modern-font-sm);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
