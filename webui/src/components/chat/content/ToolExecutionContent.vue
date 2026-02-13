/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div name="ToolExecutionContent" class="tool-execution-content compact-content">
    <!-- 工具执行头部 -->
    <div class="execution-header compact-header">
      <div class="header-left">
        <el-icon class="tool-icon"><Tools /></el-icon>
        <span class="tool-name compact-code">{{ block.toolName }}</span>
        <el-tag
          :type="toolHelpers.getStatusTagType(block.status)"
          size="small"
          effect="light"
          class="compact-tag"
        >
          {{ toolHelpers.getStatusText(block.status) }}
        </el-tag>
      </div>
      <div class="header-right">
        <span v-if="block.executionTime" class="execution-time">
          {{ block.executionTime }}ms
        </span>
      </div>
    </div>

    <!-- 工具执行主体 -->
    <div class="execution-body compact-body">
      <!-- 工具输入 -->
      <div v-if="block.toolInput" class="tool-input-section compact-detail-block">
        <div class="section-header">
          <span>工具输入</span>
          <el-button
            size="small"
            text
            @click="toggleInputExpanded"
            :icon="isInputExpanded ? 'Hide' : 'View'"
            class="compact-btn"
          >
            {{ isInputExpanded ? '隐藏' : '显示' }}
          </el-button>
        </div>
        <div v-if="isInputExpanded" class="section-content compact-mt-sm">
          <pre class="compact-pre">{{ toolHelpers.formatToolInput(block.toolInput) }}</pre>
        </div>
      </div>

      <!-- 进度条（如果有） -->
      <div v-if="block.progressPercentage !== undefined" class="progress-section compact-detail-block">
        <div class="progress-header-row">
          <span class="progress-label">执行进度</span>
          <span class="progress-value">{{ block.progressPercentage }}%</span>
        </div>
        <el-progress
          :percentage="block.progressPercentage"
          :status="toolHelpers.getProgressStatus(block.status)"
          :stroke-width="4"
          :show-text="false"
        />
        <div v-if="block.currentStep" class="current-step compact-mt-sm">
          <span class="step-label">当前步骤:</span>
          <span class="step-text">{{ block.currentStep }}</span>
          <span v-if="block.totalSteps" class="step-count">
            ({{ block.currentStepIndex || 0 }}/{{ block.totalSteps }})
          </span>
        </div>
      </div>

      <!-- 流式输出（实时显示） -->
      <div v-if="block.streamOutput && block.streamOutput.length > 0" class="stream-output-section compact-detail-block">
        <div class="section-header">
          <span>实时输出</span>
          <el-tag size="small" type="success" effect="plain">流式</el-tag>
        </div>
        <div class="stream-output-content compact-mt-sm">
          <div
            v-for="(output, index) in block.streamOutput"
            :key="index"
            class="stream-line"
          >
            <span class="stream-index">{{ index + 1 }}.</span>
            <span class="stream-text">{{ output }}</span>
          </div>
        </div>
      </div>

      <!-- 进度历史 -->
      <el-collapse v-if="block.progressHistory && block.progressHistory.length > 0" class="progress-history-collapse compact-collapse">
        <el-collapse-item name="history" title="执行历史">
          <div class="progress-history-list">
            <div
              v-for="(entry, index) in block.progressHistory"
              :key="index"
              class="history-entry"
            >
              <span class="history-time">{{ formatTimestamp(entry.timestamp, 'time') }}</span>
              <span v-if="entry.message" class="history-message">{{ entry.message }}</span>
              <span v-if="entry.progress_percentage !== undefined" class="history-progress">
                {{ entry.progress_percentage }}%
              </span>
              <span v-if="entry.step" class="history-step">{{ entry.step }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 执行结果 -->
      <div v-if="block.result !== undefined" class="result-section compact-detail-block">
        <div class="section-header">
          <span>执行结果</span>
          <el-button
            size="small"
            @click="toggleResultExpanded"
            :icon="isResultExpanded ? 'Fold' : 'Expand'"
            class="compact-btn"
          >
            {{ isResultExpanded ? '收起' : '展开' }}
          </el-button>
        </div>
        <div class="result-content compact-mt-sm">
          <div v-if="block.isError" class="error-result">
            <el-alert
              :title="toolHelpers.getErrorTitle(block.errorCode)"
              type="error"
              :closable="false"
              show-icon
            >
              <template #default>
                <div class="error-details">
                  <div v-if="block.errorMessage" class="error-message">
                    {{ block.errorMessage }}
                  </div>
                  <pre
                    v-if="isResultExpanded"
                    class="error-stack compact-pre"
                  >{{ toolHelpers.formatToolResult(block.result) }}</pre>
                </div>
              </template>
            </el-alert>
          </div>
          <div v-else class="success-result">
            <pre
              :class="{ 'collapsed': !isResultExpanded }"
              class="compact-pre"
            >{{ toolHelpers.formatToolResult(block.result) }}</pre>
          </div>
        </div>
      </div>

      <!-- 性能指标 -->
      <div v-if="block.performanceMetrics" class="metrics-section compact-stats">
        <div class="metrics-title">性能指标</div>
        <div class="metrics-grid">
          <div
            v-for="(value, key) in block.performanceMetrics"
            :key="key"
            class="metric-item"
          >
            <span class="metric-key">{{ key }}:</span>
            <span class="metric-value">{{ value }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Tools } from '@element-plus/icons-vue'
import { ElIcon, ElTag, ElButton, ElProgress, ElCollapse, ElCollapseItem, ElAlert } from 'element-plus'
import type { ToolExecutionContentBlock } from '@/types/websocket'
import { formatTimestamp } from '@/utils/formatters'
import { toolHelpers } from '@/utils/toolHelpers'

defineProps<{
  block: ToolExecutionContentBlock
}>()

defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

const isInputExpanded = ref(false)
const isResultExpanded = ref(false)

const toggleInputExpanded = () => {
  isInputExpanded.value = !isInputExpanded.value
}

const toggleResultExpanded = () => {
  isResultExpanded.value = !isResultExpanded.value
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.execution-header {
  background: linear-gradient(135deg, #f5f7fa 0%, #e8eef5 100%);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--compact-gap-sm);
}

.tool-icon {
  font-size: 14px;
  color: var(--el-color-primary);
}

.tool-name {
  font-weight: 600;
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-primary);
}

.execution-time {
  font-size: var(--compact-font-xs);
  color: var(--el-text-color-secondary);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

/* 工具输入部分 */
.tool-input-section {
  margin-bottom: var(--compact-padding-md);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--compact-font-sm);
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: var(--compact-padding-xs);
}

.section-content {
  background-color: var(--el-fill-color-lighter);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-sm);
}

/* 进度条部分 */
.progress-section {
  margin-bottom: var(--compact-padding-md);
}

.progress-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--compact-padding-xs);
}

.progress-label {
  font-size: var(--compact-font-sm);
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.progress-value {
  font-size: var(--compact-font-md);
  font-weight: 600;
  color: var(--el-color-primary);
}

.current-step {
  display: flex;
  align-items: center;
  gap: var(--compact-gap-xs);
  font-size: var(--compact-font-xs);
  color: var(--el-text-color-secondary);
  margin-top: var(--compact-padding-xs);
}

.step-label {
  font-weight: 500;
}

.step-text {
  color: var(--el-text-color-primary);
}

.step-count {
  color: var(--el-text-color-placeholder);
}

/* 流式输出部分 */
.stream-output-section {
  margin-bottom: var(--compact-padding-md);
  background-color: var(--el-color-success-light-9);
  border: 1px solid var(--el-color-success-light-7);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-md);
}

.stream-output-content {
  max-height: 300px;
  overflow-y: auto;
  background-color: var(--el-bg-color);
  border-radius: var(--compact-radius-sm);
  padding: var(--compact-padding-sm);
}

.stream-line {
  display: flex;
  gap: var(--compact-gap-sm);
  padding: var(--compact-padding-xs) 0;
  font-size: var(--compact-font-xs);
  line-height: 1.4;
}

.stream-line:not(:last-child) {
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.stream-index {
  color: var(--el-color-success);
  font-weight: 600;
  flex-shrink: 0;
  min-width: 24px;
}

.stream-text {
  color: var(--el-text-color-primary);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  word-break: break-all;
  /* Fix horizontal overflow */
  word-wrap: break-word;
  overflow-wrap: break-word;
  min-width: 0;
  flex: 1;
}

/* 进度历史 */
.progress-history-collapse {
  margin-bottom: var(--compact-padding-md);
}

.progress-history-collapse :deep(.el-collapse-item__header) {
  padding: var(--compact-padding-xs) 0;
  font-size: var(--compact-font-sm);
  border: none;
}

.progress-history-list {
  max-height: 200px;
  overflow-y: auto;
  background-color: var(--el-fill-color-lighter);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-sm);
}

.history-entry {
  display: flex;
  align-items: center;
  gap: var(--compact-gap-sm);
  padding: var(--compact-padding-xs) 0;
  font-size: var(--compact-font-xs);
}

.history-entry:not(:last-child) {
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.history-time {
  color: var(--el-text-color-placeholder);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  flex-shrink: 0;
  min-width: 70px;
}

.history-message {
  color: var(--el-text-color-primary);
  flex: 1;
}

.history-progress {
  color: var(--el-color-primary);
  font-weight: 600;
  flex-shrink: 0;
}

.history-step {
  color: var(--el-text-color-secondary);
  font-size: var(--compact-font-xs);
  flex-shrink: 0;
}

/* 执行结果 */
.result-section {
  margin-bottom: var(--compact-padding-md);
}

.result-content pre.collapsed {
  max-height: 200px;
  overflow: hidden;
  position: relative;
}

.result-content pre.collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 30px;
  background: linear-gradient(transparent, var(--el-fill-color-lighter));
  pointer-events: none;
}

.error-result .error-details {
  margin-top: var(--compact-padding-sm);
}

.error-result .error-message {
  margin-bottom: var(--compact-padding-sm);
  font-size: var(--compact-font-md);
  color: var(--el-text-color-primary);
}

.error-result .error-stack {
  background-color: var(--el-fill-color-light);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-sm);
}

/* 性能指标 */
.metrics-section {
  background-color: var(--el-fill-color-lighter);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-md);
}

.metrics-title {
  font-size: var(--compact-font-sm);
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-bottom: var(--compact-padding-sm);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--compact-padding-sm);
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: var(--compact-gap-xs);
  padding: var(--compact-padding-sm);
  background-color: var(--el-bg-color);
  border-radius: var(--compact-radius-sm);
  border: 1px solid var(--el-border-color-lighter);
}

.metric-key {
  font-size: var(--compact-font-xs);
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.metric-value {
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-primary);
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  word-break: break-all;
}
</style>
