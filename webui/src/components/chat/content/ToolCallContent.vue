/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="tool-call-content compact-content">
    <el-collapse v-model="activeNames" class="tool-collapse compact-collapse">
      <el-collapse-item name="1" class="tool-item">
        <template #title>
          <div class="collapse-title compact-header">
            <el-icon><Tools /></el-icon>
            <span>Tool Call: <code class="compact-code">{{ block.toolCall.tool_name }}</code></span>
            <el-tag
              :type="statusType"
              size="small"
              effect="light"
              round
              class="status-tag compact-tag"
            >
              {{ toolHelpers.getStatusText(block.toolCall.status) }}
            </el-tag>
            <div v-if="block.toolCall.status === 'in_progress'" class="progress-indicator">
              <el-icon class="is-loading"><Loading /></el-icon>
            </div>
          </div>
        </template>

        <div class="tool-details compact-body">
          <div class="detail-block compact-detail-block">
            <h4 class="compact-detail-title">Input:</h4>
            <div class="input-content">
              <pre class="compact-pre"><code>{{ toolHelpers.formatToolInput(block.toolCall.tool_input) }}</code></pre>
              <el-button
                size="small"
                text
                @click="copyInput"
                :icon="DocumentCopy"
                class="copy-button compact-btn"
              >
                复制
              </el-button>
            </div>
          </div>

          <!-- 进度信息展示 -->
          <div v-if="showProgressInfo" class="detail-block compact-detail-block progress-info-block">
            <h4 class="compact-detail-title">执行进度</h4>
            <div class="progress-info-content">
              <!-- 进度条 -->
              <div v-if="block.toolCall.progress_percentage !== undefined" class="progress-bar-container compact-progress">
                <el-progress
                  :percentage="block.toolCall.progress_percentage"
                  :status="toolHelpers.getProgressStatus(block.toolCall.status)"
                  :stroke-width="4"
                  :show-text="false"
                  class="compact-progress-bar"
                />
                <span class="progress-text compact-progress-text">{{ block.toolCall.progress_percentage }}%</span>
              </div>

              <!-- 当前步骤 -->
              <div v-if="block.toolCall.current_step" class="current-step-info compact-stats">
                <el-icon><Clock /></el-icon>
                <span class="step-text compact-text-truncate">
                  <template v-if="block.toolCall.total_steps && block.toolCall.current_step_index !== undefined">
                    步骤 {{ block.toolCall.current_step_index + 1 }}/{{ block.toolCall.total_steps }}:
                  </template>
                  {{ block.toolCall.current_step }}
                </span>
              </div>

              <!-- 执行时间 -->
              <div v-if="block.toolCall.execution_time" class="execution-time-info compact-stats">
                <el-icon><Timer /></el-icon>
                <span>执行时间: {{ toolHelpers.formatExecutionTime(block.toolCall.execution_time) }}</span>
              </div>

              <!-- 预计剩余时间 -->
              <div v-if="block.toolCall.estimated_remaining_time" class="estimated-time-info compact-stats">
                <el-icon><Clock /></el-icon>
                <span>预计剩余: {{ toolHelpers.formatExecutionTime(block.toolCall.estimated_remaining_time) }}</span>
              </div>
            </div>
          </div>

          <div v-if="block.toolCall.output" class="detail-block compact-detail-block">
            <h4 class="compact-detail-title">Output:</h4>
            <div class="output-content">
              <pre class="compact-pre"><code>{{ toolHelpers.formatToolOutput(block.toolCall.output) }}</code></pre>
              <el-button
                size="small"
                text
                @click="copyOutput"
                :icon="DocumentCopy"
                class="copy-button compact-btn"
              >
                复制
              </el-button>
            </div>
          </div>

          <div v-if="block.toolCall.error" class="detail-block compact-detail-block error-block">
            <h4 class="compact-detail-title">Error:</h4>
            <div class="error-content">
              <pre class="compact-pre">{{ block.toolCall.error }}</pre>
              <el-button
                size="small"
                text
                @click="copyError"
                :icon="DocumentCopy"
                class="copy-button compact-btn"
              >
                复制
              </el-button>
            </div>
          </div>

          <!-- 操作按钮 - 与主消息气泡一致 -->
          <div class="tool-actions assistant-actions">
            <el-button
              size="small"
              circle
              @click="copyToolCall"
            >
              <el-icon><DocumentCopy /></el-icon>
            </el-button>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Tools,
  Loading,
  DocumentCopy,
  Clock,
  Timer
} from '@element-plus/icons-vue'
import {
  ElCollapse,
  ElCollapseItem,
  ElIcon,
  ElTag,
  ElButton,
  ElMessage
} from 'element-plus'
import { copyToClipboard } from '@/utils/clipboard'
import type { ToolCallContentBlock } from '@/types/websocket'
import { toolHelpers } from '@/utils/toolHelpers'

const props = defineProps<{
  block: ToolCallContentBlock
}>()

defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

const activeNames = ref<string[]>([])

// 计算是否显示进度信息
const showProgressInfo = computed(() => {
  return toolHelpers.shouldShowProgress(
    props.block.toolCall.progress_percentage,
    props.block.toolCall.current_step,
    props.block.toolCall.execution_time,
    props.block.toolCall.estimated_remaining_time
  )
})

const statusType = computed(() => {
  return toolHelpers.getStatusTagType(props.block.toolCall.status)
})

const copyInput = async () => {
  await toolHelpers.copyToolInput(props.block.toolCall.tool_input, props.block.toolCall.tool_name)
}

const copyOutput = async () => {
  await toolHelpers.copyToolOutput(props.block.toolCall.output, props.block.toolCall.tool_name)
}

const copyError = async () => {
  await toolHelpers.copyError(props.block.toolCall.error || '', props.block.toolCall.tool_name)
}

// 复制整个工具调用信息
const copyToolCall = async () => {
  const toolCallText = `Tool: ${props.block.toolCall.tool_name}\n` +
    `Status: ${props.block.toolCall.status}\n` +
    `Input: ${JSON.stringify(props.block.toolCall.tool_input, null, 2)}` +
    (props.block.toolCall.output ? `\nOutput: ${JSON.stringify(props.block.toolCall.output, null, 2)}` : '') +
    (props.block.toolCall.error ? `\nError: ${props.block.toolCall.error}` : '')

  const success = await copyToClipboard(toolCallText)
  if (success) {
    ElMessage.success('工具调用已复制到剪贴板')
  } else {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* ============================================================================
   极简工具调用气泡样式 - 内容优先,无边框
   ============================================================================ */

/* 工具调用容器 - 完全透明 */
.tool-call-content {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

/* 折叠面板 - 隐藏边框 */
.tool-collapse {
  border: none !important;
}

.tool-collapse :deep(.el-collapse-item__header) {
  background: transparent !important;
  border: none !important;
  padding: 4px 0 !important;
  font-size: 13px;
  color: #64748b;
  font-weight: 500;
}

.tool-collapse :deep(.el-collapse-item__header:hover) {
  background: transparent !important;
  color: #0f172a;
}

.tool-collapse :deep(.el-collapse-item__wrap) {
  border: none !important;
}

.tool-collapse :deep(.el-collapse-item__content) {
  padding: 0 0 8px 0 !important;
  background: transparent !important;
  border: none !important;
}

/* 折叠箭头 - 弱化显示 */
.tool-collapse :deep(.el-collapse-item__arrow) {
  color: #cbd5e1;
  margin-left: 6px;
}

/* 内容区域 - 无边框 */
.tool-details {
  padding: 0;
  border: none;
}

.detail-block {
  background: transparent !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 4px 0 !important;
  margin-top: 0 !important;
}

/* 标题 - 弱化显示 */
.compact-detail-title {
  font-size: 11px;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 4px;
  text-transform: none;
  letter-spacing: normal;
}

/* 代码块 - 最小化边框 */
.compact-pre {
  background: #f8fafc !important;
  border: 1px solid #f1f5f9 !important;
  color: #475569;
  padding: 8px 10px;
  font-size: 12px;
  border-radius: 4px;
  line-height: 1.5;
}

.compact-pre code {
  font-family: 'JetBrains Mono', 'Monaco', 'Menlo', monospace;
  font-size: 12px;
}

/* 进度信息 - 极简样式 */
.progress-info-block {
  background: transparent !important;
  border: none !important;
  padding: 4px 0 !important;
}

/* 错误块 - 轻量样式 */
.error-block .compact-detail-title {
  color: #f87171;
}

.error-block .compact-pre {
  background: #fef2f2 !important;
  border: 1px solid #fee2e2 !important;
  color: #dc2626;
}

/* ============================================================================
   操作按钮 - 极简样式
   ============================================================================ */
.tool-actions.assistant-actions {
  padding: 6px 0 0 0;
  background: transparent;
  border: none;
  border-top: none;
}

.assistant-actions .el-button {
  color: #cbd5e1;
  background: transparent;
  border: 1px solid #f1f5f9;
  font-size: 12px;
  padding: 4px;
  height: 28px;
  width: 28px;
}

.assistant-actions .el-button:hover {
  color: #64748b;
  background: #f8fafc;
  border-color: #e2e8f0;
}

/* 箭头旋转动画 */
.rotate-180 {
  transform: rotate(180deg);
}

.assistant-actions .el-icon {
  transition: transform 0.3s ease;
  font-size: 14px;
}

/* 标签样式 - 弱化 */
.compact-tag {
  font-size: 11px;
  padding: 2px 6px;
  border: none;
  opacity: 0.8;
}

/* 代码标签 - 弱化 */
.compact-code {
  background: transparent;
  border: none;
  color: #475569;
  padding: 0;
  font-size: 13px;
}

/* 图标样式 - 弱化 */
.collapse-title .el-icon {
  color: #94a3b8;
  font-size: 14px;
}
</style>