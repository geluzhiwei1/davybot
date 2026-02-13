/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="tool-result-content compact-content" :class="{ 'collapsed': !isExpanded }">
    <!-- 极简头部（始终显示）-->
    <div class="result-header compact-header" @click="toggleExpanded" :class="{ 'clickable': !block.isError }">
      <el-icon><Tools /></el-icon>
      <span class="tool-name compact-code">{{ block.toolName }}</span>
      <el-tag
        :type="block.isError ? 'danger' : 'success'"
        size="small"
        effect="light"
        class="compact-tag"
      >
        {{ block.isError ? '失败' : '成功' }}
      </el-tag>
      <span v-if="block.executionTime" class="execution-time">
        {{ formatExecutionTime(block.executionTime) }}
      </span>
      <el-icon v-if="!block.isError" class="expand-icon" :class="{ 'expanded': isExpanded }">
        <ArrowDown />
      </el-icon>
    </div>

    <!-- 收起状态的摘要显示 -->
    <div v-if="!isExpanded && !block.isError" class="result-summary compact-body" @click="toggleExpanded">
      <div class="summary-content">
        <span class="summary-text">{{ getResultSummary() }}</span>
        <span v-if="isLargeMessage(block.result)" class="message-size-badge">
          {{ getMessageSize(block.result).formatted }}
        </span>
        <span class="expand-hint">点击展开查看详情</span>
      </div>
    </div>

    <!-- 详细内容（仅展开时显示）-->
    <div v-if="isExpanded" class="result-body compact-body">
      <div v-if="block.isError" class="enhanced-error-result">
        <el-alert
          :title="toolHelpers.getErrorTitle(block.errorCode)"
          type="error"
          :closable="false"
          show-icon
        >
          <template #default>
            <div class="error-content">
              <div class="error-message">{{ block.errorMessage || '工具执行失败' }}</div>

              <!-- 错误代码和建议 -->
              <div v-if="block.errorCode" class="error-details compact-mt-sm">
                <div class="error-code">
                  <span class="label">错误代码:</span>
                  <code class="compact-code">{{ block.errorCode }}</code>
                </div>
                <div class="error-suggestion" v-if="toolHelpers.getErrorSuggestion(block.errorCode)">
                  <span class="label">建议:</span>
                  <span>{{ toolHelpers.getErrorSuggestion(block.errorCode) }}</span>
                </div>
              </div>

              <!-- 错误堆栈 -->
              <el-collapse v-if="toolHelpers.shouldShowErrorDetails(block.result)" class="compact-collapse">
                <el-collapse-item title="查看详细错误信息" name="errorDetails">
                  <pre class="error-stack compact-pre">{{ toolHelpers.formatErrorResult(block.result) }}</pre>
                </el-collapse-item>
              </el-collapse>

              <!-- 重试和帮助按钮 -->
              <div class="error-actions compact-actions compact-mt-md">
                <el-button
                  size="small"
                  type="primary"
                  @click="retryToolCall"
                  :icon="RefreshRight"
                  class="compact-btn"
                >
                  重试
                </el-button>
                <el-button
                  size="small"
                  @click="showErrorHelp"
                  :icon="QuestionFilled"
                  class="compact-btn"
                >
                  获取帮助
                </el-button>
              </div>
            </div>
          </template>
        </el-alert>
      </div>

      <div v-else class="success-result">
        <div class="result-actions compact-actions">
          <el-button
            size="small"
            @click.stop="toggleExpanded"
            :icon="Fold"
            class="compact-btn"
          >
            收起
          </el-button>
          <el-button
            v-if="isLargeMessage(block.result)"
            size="small"
            @click.stop="showFullContent = !showFullContent"
            class="compact-btn"
          >
            {{ showFullContent ? '显示截断版本' : '显示完整内容' }}
          </el-button>
          <el-button
            size="small"
            @click.stop="copyResult"
            :icon="DocumentCopy"
            class="compact-btn"
          >
            复制
          </el-button>
        </div>

        <!-- 大消息警告提示 -->
        <div v-if="isLargeMessage(block.result) && !showFullContent" class="large-message-warning">
          <el-alert
            type="warning"
            :closable="false"
            show-icon
          >
            <template #default>
              <div class="warning-content">
                <span class="warning-text">
                  ⚠️ 消息过大 ({{ getMessageSize(block.result).formatted }})，为避免卡顿已截断显示
                </span>
                <el-button
                  size="small"
                  @click="showFullContent = true"
                  class="warning-btn"
                >
                  加载完整内容
                </el-button>
              </div>
            </template>
          </el-alert>
        </div>

        <div class="result-content">
          <pre
            ref="resultRef"
            class="compact-pre"
          >{{ getDisplayResult() }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Tools, DocumentCopy, Fold, RefreshRight, QuestionFilled, ArrowDown } from '@element-plus/icons-vue'
import { ElAlert, ElButton, ElTag, ElIcon, ElCollapse, ElCollapseItem } from 'element-plus'
import type { ToolResultContentBlock } from '@/types/websocket'
import { toolHelpers } from '@/utils/toolHelpers'

const props = defineProps<{
  block: ToolResultContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

// 默认收起状态
const isExpanded = ref(false)
const showFullContent = ref(false)
const resultRef = ref<HTMLElement>()

// 大消息阈值（10KB）
const LARGE_MESSAGE_THRESHOLD = 10 * 1024

// 计算消息大小
const getMessageSize = (result: unknown): { size: number; formatted: string } => {
  const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  const size = resultStr.length

  if (size < 1024) {
    return { size, formatted: `${size} B` }
  } else if (size < 1024 * 1024) {
    return { size, formatted: `${(size / 1024).toFixed(1)} KB` }
  } else {
    return { size, formatted: `${(size / (1024 * 1024)).toFixed(2)} MB` }
  }
}

// 判断是否为大消息
const isLargeMessage = (result: unknown): boolean => {
  const { size } = getMessageSize(result)
  return size > LARGE_MESSAGE_THRESHOLD
}

// 格式化并截断结果
const formatAndTruncateResult = (result: unknown): string => {
  const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  const { size } = getMessageSize(result)

  // 如果是大消息，截断到前 10KB
  if (size > LARGE_MESSAGE_THRESHOLD) {
    const truncatedLength = LARGE_MESSAGE_THRESHOLD
    return resultStr.substring(0, truncatedLength) +
      `\n\n... (剩余 ${getMessageSize(result).formatted} 未显示，点击下方按钮查看完整内容) ...`
  }

  return toolHelpers.formatToolResult(result)
}

// 获取显示的结果
const getDisplayResult = (): string => {
  if (!showFullContent.value && isLargeMessage(props.block.result)) {
    return formatAndTruncateResult(props.block.result)
  }
  return toolHelpers.formatToolResult(props.block.result)
}

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value
}

const copyResult = async () => {
  await toolHelpers.copyToolResult(props.block.result, props.block.toolName)
}

// 格式化执行时间
const formatExecutionTime = (ms: number) => {
  if (ms < 1000) {
    return `${ms}ms`
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`
  } else {
    const minutes = Math.floor(ms / 60000)
    const seconds = ((ms % 60000) / 1000).toFixed(0)
    return `${minutes}m ${seconds}s`
  }
}

// 获取结果摘要
const getResultSummary = () => {
  const result = props.block.result
  const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2)

  // 计算字符数和行数
  const charCount = resultStr.length
  const lineCount = resultStr.split('\n').length

  // 根据内容类型生成摘要
  if (Array.isArray(result)) {
    return `返回了 ${result.length} 条结果`
  } else if (typeof result === 'object' && result !== null) {
    const keys = Object.keys(result)
    return `返回了对象 (${keys.length} 个字段)`
  } else if (lineCount > 5) {
    return `返回了 ${lineCount} 行内容 (${charCount} 字符)`
  } else {
    // 截取前 80 个字符作为预览
    const preview = resultStr.substring(0, 80)
    return preview + (resultStr.length > 80 ? '...' : '')
  }
}

// 重试工具调用
const retryToolCall = () => {
  emit('contentAction', 'tool-retry', {
    toolName: props.block.toolName,
    result: props.block.result
  })
}

// 显示错误帮助
const showErrorHelp = () => {
  emit('contentAction', 'tool-help', {
    toolName: props.block.toolName,
    errorCode: props.block.errorCode,
    errorMessage: props.block.errorMessage
  })
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.result-header {
  background-color: var(--el-fill-color);
  cursor: default;
  transition: all 0.2s ease;
}

.result-header.clickable {
  cursor: pointer;
  user-select: none;
}

.result-header.clickable:hover {
  background-color: var(--el-fill-color-light);
}

.result-header.clickable:active {
  transform: scale(0.99);
}

/* 展开箭头图标 */
.expand-icon {
  margin-left: auto;
  transition: transform 0.3s ease;
  opacity: 0.6;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.result-header.clickable:hover .expand-icon {
  opacity: 1;
}

/* 执行时间显示 */
.execution-time {
  margin-left: var(--compact-gap-sm);
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-secondary);
  font-weight: 500;
  padding: 2px 8px;
  background-color: var(--el-fill-color-lighter);
  border-radius: var(--compact-radius-sm);
}

/* 收起状态 */
.tool-result-content.collapsed {
  max-height: none;
}

.tool-result-content.collapsed .result-header {
  border-radius: var(--compact-radius-md) var(--compact-radius-md) 0 0;
}

/* 摘要内容区域 */
.result-summary {
  background-color: var(--el-fill-color-lighter);
  padding: var(--compact-padding-sm) var(--compact-padding-md);
  cursor: pointer;
  border-left: 3px solid var(--el-color-success);
  transition: all 0.2s ease;
}

.result-summary:hover {
  background-color: var(--el-fill-color-light);
  border-left-color: var(--el-color-success-dark-2);
}

.summary-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--compact-gap-md);
}

.summary-text {
  flex: 1;
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-regular);
  line-height: 1.5;
  font-family: monospace;
}

.expand-hint {
  font-size: var(--compact-font-xs);
  color: var(--el-color-primary);
  white-space: nowrap;
  font-weight: 500;
}

/* 展开动画 */
.result-body {
  padding: 0;
  animation: expandContent 0.3s ease-out;
}

@keyframes expandContent {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.success-result {
  display: flex;
  flex-direction: column;
  gap: var(--compact-padding-md);
}

.result-actions {
  padding: 0;
  border: none;
}

.result-content pre {
  margin: 0;
  max-height: 500px;
  overflow-y: auto;
}

/* 滚动条美化 */
.result-content pre::-webkit-scrollbar {
  width: 6px;
}

.result-content pre::-webkit-scrollbar-track {
  background: var(--el-fill-color-lighter);
  border-radius: 3px;
}

.result-content pre::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 3px;
}

.result-content pre::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-darker);
}

/* 错误样式增强 */
.error-message {
  margin-bottom: var(--compact-padding-md);
  font-size: var(--compact-font-md);
  color: var(--el-text-color-primary);
}

.error-details {
  margin-bottom: var(--compact-padding-md);
  padding: var(--compact-padding-sm) var(--compact-padding-md);
  background-color: var(--el-fill-color-lighter);
  border-radius: var(--compact-radius-md);
}

.error-code {
  margin-bottom: var(--compact-padding-xs);
}

.error-code .label {
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-right: var(--compact-gap-sm);
}

.error-code code {
  font-family: monospace;
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  padding: 2px 6px;
  border-radius: var(--compact-radius-sm);
  font-size: var(--compact-font-sm);
}

.error-suggestion {
  display: flex;
  align-items: flex-start;
}

.error-suggestion .label {
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-right: var(--compact-gap-sm);
  flex-shrink: 0;
}

.error-stack {
  margin-top: var(--compact-padding-sm);
}

.error-actions {
  margin-top: var(--compact-padding-md);
}

/* Message size badge */
.message-size-badge {
  display: inline-block;
  padding: 2px 6px;
  background-color: var(--el-color-warning);
  color: white;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  margin-left: 4px;
}

/* Large message warning */
.large-message-warning {
  margin-bottom: var(--compact-padding-md);
}

.warning-content {
  display: flex;
  align-items: center;
  gap: var(--compact-gap-md);
}

.warning-text {
  flex: 1;
  font-size: var(--compact-font-sm);
}

.warning-btn {
  flex-shrink: 0;
}
</style>