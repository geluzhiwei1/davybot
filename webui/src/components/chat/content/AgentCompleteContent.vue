/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="agent-complete-content compact-content">
    <div class="complete-header compact-header">
      <div class="header-left">
        <el-icon class="complete-icon"><SuccessFilled /></el-icon>
        <span class="complete-title compact-title">Agent 完成</span>
        <el-tag size="small" type="success" effect="light" class="compact-tag">
          {{ complete.agent_mode }}
        </el-tag>
      </div>
      <div class="header-right">
        <!-- eslint-disable-next-line @typescript-eslint/no-explicit-any -->
        <el-tag :type="getDurationTag() as any" size="small" effect="plain" class="compact-tag">
          {{ formatDuration(complete.total_duration_ms, 'standard') }}
        </el-tag>
      </div>
    </div>

    <div class="complete-body compact-body">
      <!-- 结果摘要 -->
      <div class="result-summary compact-detail-block">
        <div class="summary-header">
          <el-icon><Document /></el-icon>
          <span class="summary-title">执行摘要</span>
        </div>
        <p class="summary-text compact-mt-sm">{{ complete.result_summary }}</p>
      </div>

      <!-- 统计卡片 -->
      <div class="stats-cards compact-stats">
        <div class="stat-item">
          <el-icon><List /></el-icon>
          <div class="stat-info">
            <div class="stat-value">{{ complete.tasks_completed }}</div>
            <div class="stat-label">完成任务</div>
          </div>
        </div>

        <div class="stat-item">
          <el-icon><Tools /></el-icon>
          <div class="stat-info">
            <div class="stat-value">{{ complete.tools_used?.length || 0 }}</div>
            <div class="stat-label">使用工具</div>
          </div>
        </div>

        <div class="stat-item">
          <el-icon><Timer /></el-icon>
          <div class="stat-info">
            <div class="stat-value">{{ formatDurationShort(complete.total_duration_ms) }}</div>
            <div class="stat-label">总耗时</div>
          </div>
        </div>
      </div>

      <!-- 使用的工具列表 -->
      <el-collapse v-if="complete.tools_used && complete.tools_used.length > 0" class="tools-collapse compact-collapse">
        <el-collapse-item name="tools" title="使用的工具">
          <div class="tools-list">
            <div
              v-for="(tool, index) in complete.tools_used"
              :key="index"
              class="tool-item"
            >
              <span class="tool-item-icon">{{ getToolIcon(tool) }}</span>
              <span class="tool-item-name compact-code">{{ tool }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 详细元数据 -->
      <el-collapse v-if="complete.metadata && Object.keys(complete.metadata).length > 0" class="metadata-collapse compact-collapse">
        <el-collapse-item name="metadata" title="详细元数据">
          <pre class="metadata-json compact-pre">{{ JSON.stringify(complete.metadata, null, 2) }}</pre>
        </el-collapse-item>
      </el-collapse>

      <!-- 操作按钮 -->
      <div class="complete-actions compact-actions">
        <el-button size="small" @click="copySummary" :icon="DocumentCopy" class="compact-btn">
          复制摘要
        </el-button>
        <el-button size="small" @click="exportReport" :icon="Download" class="compact-btn">
          导出报告
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
  SuccessFilled,
  Document,
  List,
  Tools,
  Timer,
  DocumentCopy,
  Download
} from '@element-plus/icons-vue'
import { ElIcon, ElTag, ElCollapse, ElCollapseItem, ElButton, ElMessage } from 'element-plus'

// 定义Agent完成消息类型
interface AgentCompleteBlock {
  type: 'agent_complete'
  agent_mode: string
  result_summary: string
  total_duration_ms: number
  tasks_completed: number
  tools_used?: string[]
  metadata?: Record<string, unknown>
}

const props = defineProps<{
  block: AgentCompleteBlock
}>()

const complete = computed(() => props.block)

// 获取耗时标签类型
const getDurationTag = (): '' | 'success' | 'warning' | 'danger' => {
  const duration = complete.value.total_duration_ms
  if (duration < 1000) return ''
  if (duration < 10000) return 'success'
  if (duration < 30000) return 'warning'
  return 'danger'
}

// 格式化持续时间（短格式）
const formatDurationShort = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

// 获取工具图标
const getToolIcon = (toolName: string): string => {
  const iconMap: Record<string, string> = {
    'read_file': '📄',
    'write_to_file': '✏️',
    'search_files': '🔍',
    'list_files': '📂',
    'execute_command': '⚡',
    'browser_action': '🌐',
    'ask_followup_question': '❓',
    'attempt_completion': '✅',
    'switch_mode': '🔄',
  }

  // 尝试精确匹配
  if (iconMap[toolName]) {
    return iconMap[toolName]
  }

  // 尝试部分匹配
  for (const [key, icon] of Object.entries(iconMap)) {
    if (toolName.includes(key) || key.includes(toolName)) {
      return icon
    }
  }

  // 默认图标
  return '🔧'
}

// 复制摘要
const copySummary = async () => {
  const summary = complete.value.result_summary
  const success = await copyToClipboard(summary)
  if (success) {
    ElMessage.success('摘要已复制到剪贴板')
  } else {
    ElMessage.error('复制失败')
  }
}

// 导出报告
const exportReport = () => {
  const report = {
    agentMode: complete.value.agent_mode,
    resultSummary: complete.value.result_summary,
    totalDuration: complete.value.total_duration_ms,
    tasksCompleted: complete.value.tasks_completed,
    toolsUsed: complete.value.tools_used || [],
    metadata: complete.value.metadata || {},
    exportTime: new Date().toISOString()
  }

  const dataStr = JSON.stringify(report, null, 2)
  const blob = new Blob([dataStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)

  const a = document.createElement('a')
  a.href = url
  a.download = `agent-report-${Date.now()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)

  ElMessage.success('报告已导出')
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

/* 结果摘要 */
.result-summary {
  margin-bottom: var(--modern-spacing-md);
}

.summary-header {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  margin-bottom: var(--modern-spacing-sm);
}

.summary-header .el-icon {
  font-size: 16px;
  color: var(--modern-color-primary);
}

.summary-title {
  font-size: var(--modern-font-sm);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.summary-text {
  font-size: var(--modern-font-md);
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 0;
}

/* 统计卡片 */
.stats-cards {
  margin-bottom: var(--modern-spacing-md);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
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

.stat-value {
  font-size: var(--modern-font-lg);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.stat-label {
  font-size: var(--modern-font-xs);
  color: var(--el-text-color-secondary);
}

/* 工具列表 */
.tools-collapse,
.metadata-collapse {
  margin-bottom: var(--modern-spacing-md);
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: var(--modern-spacing-sm);
}

.tool-item {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  padding: var(--modern-spacing-sm);
  background: var(--el-bg-color);
  border-radius: var(--modern-radius-sm);
  border: 1px solid var(--modern-border-light);
  transition: all 0.2s ease;
}

.tool-item:hover {
  border-color: var(--modern-color-primary-light);
  background: var(--modern-color-primary-light);
}

.tool-item-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.tool-item-name {
  font-size: var(--modern-font-sm);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  color: var(--el-text-color-primary);
}

/* 元数据显示 */
.metadata-json {
  margin: 0;
}
</style>