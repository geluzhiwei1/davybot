/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="context-usage-panel">
    <div class="panel-header">
      <h4>上下文使用</h4>
      <div class="usage-summary">
        <span :class="['percentage', level]">{{ stats.percentage.toFixed(1) }}%</span>
        <span class="tokens-text">{{ formatTokens(stats.used) }} / {{ formatTokens(stats.total) }}</span>
      </div>
    </div>

    <!-- 进度条网格可视化 -->
    <div class="usage-grid" :title="`${stats.percentage.toFixed(1)}% 已使用`">
      <div
        v-for="i in 100"
        :key="i"
        :class="[
          'grid-cell',
          {
            filled: i <= stats.percentage,
            warning: stats.percentage > 75 && i <= stats.percentage,
            danger: stats.percentage > 90 && i <= stats.percentage
          }
        ]"
      ></div>
    </div>

    <!-- 详细统计 -->
    <div class="breakdown-section">
      <h5>Token 分布</h5>
      <div class="breakdown-list">
        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-label">系统提示词</span>
            <span class="item-tokens">{{ formatTokens(stats.breakdown.system_prompt) }}</span>
          </div>
          <div class="item-bar">
            <div
              class="bar-fill system-prompt"
              :style="{ width: getPercentage(stats.breakdown.system_prompt) + '%' }"
            ></div>
          </div>
        </div>

        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-label">对话历史</span>
            <span class="item-tokens">{{ formatTokens(stats.breakdown.conversation) }}</span>
          </div>
          <div class="item-bar">
            <div
              class="bar-fill conversation"
              :style="{ width: getPercentage(stats.breakdown.conversation) + '%' }"
            ></div>
          </div>
        </div>

        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-label">工作区文件</span>
            <span class="item-tokens">{{ formatTokens(stats.breakdown.workspace_files) }}</span>
          </div>
          <div class="item-bar">
            <div
              class="bar-fill workspace-files"
              :style="{ width: getPercentage(stats.breakdown.workspace_files) + '%' }"
            ></div>
          </div>
        </div>

        <div class="breakdown-item">
          <div class="item-header">
            <span class="item-label">工具定义</span>
            <span class="item-tokens">{{ formatTokens(stats.breakdown.tool_definitions) }}</span>
          </div>
          <div class="item-bar">
            <div
              class="bar-fill tool-definitions"
              :style="{ width: getPercentage(stats.breakdown.tool_definitions) + '%' }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 文件列表 -->
    <div class="files-section" v-if="stats.breakdown.files.length > 0">
      <div class="section-header">
        <h5>上下文中的文件 ({{ stats.breakdown.files.length }})</h5>
        <button
          v-if="stats.breakdown.files.length > 0"
          @click="clearAllFiles"
          class="clear-btn"
          title="清空所有文件"
        >
          清空全部
        </button>
      </div>

      <div class="files-list">
        <div
          v-for="file in stats.breakdown.files"
          :key="file.path"
          class="file-item"
        >
          <div class="file-info">
            <span class="file-path" :title="file.path">{{ getFileName(file.path) }}</span>
            <span class="file-meta">
              <span class="file-tokens">{{ formatTokens(file.tokens) }}</span>
              <span class="file-percentage">({{ file.percentage.toFixed(1) }}%)</span>
            </span>
          </div>
          <button
            @click="removeFile(file.path)"
            class="remove-btn"
            title="从上下文移除"
          >
            ✕
          </button>
        </div>
      </div>
    </div>

    <!-- 警告信息 -->
    <div class="warnings-section" v-if="warnings.length > 0">
      <div
        v-for="(warning, index) in warnings"
        :key="index"
        :class="['warning-item', getWarningClass(warning)]"
      >
        <span class="warning-icon">⚠️</span>
        <span class="warning-text">{{ warning }}</span>
      </div>
    </div>

    <!-- 剩余空间 -->
    <div class="remaining-section">
      <span class="remaining-label">剩余空间:</span>
      <span class="remaining-value" :class="{ low: stats.remaining < 10000 }">
        {{ formatTokens(stats.remaining) }} tokens
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useWebSocket } from '@/composables/useWebSocket';
import type { ContextUpdateMessage } from '@/types/websocket';
import { MessageType } from '@/types/websocket';

const { subscribe, unsubscribe } = useWebSocket();

// 上下文统计
const stats = ref({
  total: 200000,
  used: 0,
  percentage: 0,
  breakdown: {
    system_prompt: 0,
    conversation: 0,
    workspace_files: 0,
    tool_definitions: 0,
    files: [] as unknown[]
  },
  remaining: 200000
});

const warnings = ref<string[]>([]);

// 计算使用级别
const level = computed(() => {
  if (stats.value.percentage > 90) return 'danger';
  if (stats.value.percentage > 75) return 'warning';
  return 'normal';
});

// 订阅上下文更新消息
let contextUpdateHandler: ((message: unknown) => void) | null = null;

onMounted(() => {
  contextUpdateHandler = (message: unknown) => {
    if (message.type === MessageType.CONTEXT_UPDATE) {
      const updateMessage = message as ContextUpdateMessage;
      stats.value = updateMessage.stats;
      warnings.value = updateMessage.warnings;
    }
  };

  subscribe(contextUpdateHandler);

  // 初始请求上下文状态
  requestContextUpdate();
});

onUnmounted(() => {
  if (contextUpdateHandler) {
    unsubscribe(contextUpdateHandler);
  }
});

// 请求上下文更新
function requestContextUpdate() {
  // 发送一个心跳或请求消息来获取当前上下文状态
  // 这里可以通过已有的 WebSocket 连接发送请求
}

// 格式化 token 数量
function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(2)}M`;
  }
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return tokens.toString();
}

// 计算百分比
function getPercentage(value: number): number {
  return (value / stats.value.total) * 100;
}

// 获取文件名
function getFileName(path: string): string {
  const parts = path.split(/[/\\]/);
  return parts[parts.length - 1] || path;
}

// 移除文件
function removeFile(filePath: string) {
  // TODO: 发送移除文件的请求到后端
  console.log('Remove file:', filePath);
  // 这里需要实现实际的文件移除逻辑
}

// 清空所有文件
function clearAllFiles() {
  // TODO: 发送清空文件的请求到后端
  console.log('Clear all files');
}

// 获取警告样式类
function getWarningClass(warning: string): string {
  if (warning.includes('严重') || warning.includes('90%')) {
    return 'danger';
  }
  if (warning.includes('警告') || warning.includes('75%')) {
    return 'warning';
  }
  return 'info';
}
</script>

<style scoped>
.context-usage-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.usage-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}

.percentage {
  font-size: 20px;
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 6px;
}

.percentage.normal {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.percentage.warning {
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.percentage.danger {
  color: var(--el-color-error);
  background: var(--el-color-error-light-9);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.tokens-text {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

/* 网格可视化 */
.usage-grid {
  display: grid;
  grid-template-columns: repeat(50, 1fr);
  gap: 2px;
  margin: 8px 0;
  padding: 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}

.grid-cell {
  width: 100%;
  height: 6px;
  background: var(--el-border-color);
  border-radius: 1px;
  transition: all 0.2s ease;
}

.grid-cell.filled {
  background: var(--el-color-success);
}

.grid-cell.warning {
  background: var(--el-color-warning);
}

.grid-cell.danger {
  background: var(--el-color-error);
  animation: cell-flash 1.5s ease-in-out infinite;
}

@keyframes cell-flash {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* 详细统计 */
.breakdown-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.breakdown-section h5 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.breakdown-item {
  margin-bottom: 8px;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.item-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.item-tokens {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.item-bar {
  height: 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.bar-fill.system-prompt { background: #6366f1; }
.bar-fill.conversation { background: #8b5cf6; }
.bar-fill.workspace-files { background: #06b6d4; }
.bar-fill.tool-definitions { background: #f59e0b; }

/* 文件列表 */
.files-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.clear-btn {
  padding: 4px 12px;
  font-size: 12px;
  color: var(--el-color-danger);
  background: transparent;
  border: 1px solid var(--el-color-danger-light-7);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: var(--el-color-danger-light-9);
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  transition: all 0.2s;
}

.file-item:hover {
  background: var(--el-fill-color);
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.file-path {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-percentage {
  color: var(--el-color-info);
}

.remove-btn {
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
  font-size: 16px;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn:hover {
  background: var(--el-fill-color-dark);
  color: var(--el-color-danger);
}

/* 警告 */
.warnings-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.warning-item {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.warning-item.info {
  background: var(--el-color-info-light-9);
  color: var(--el-color-info);
  border: 1px solid var(--el-color-info-light-5);
}

.warning-item.warning {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
  border: 1px solid var(--el-color-warning-light-5);
}

.warning-item.danger {
  background: var(--el-color-error-light-9);
  color: var(--el-color-error);
  border: 1px solid var(--el-color-error-light-5);
  animation: shake 0.5s ease-in-out;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}

.warning-icon {
  flex-shrink: 0;
}

/* 剩余空间 */
.remaining-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 13px;
}

.remaining-label {
  color: var(--el-text-color-secondary);
}

.remaining-value {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.remaining-value.low {
  color: var(--el-color-error);
  font-weight: 700;
}

/* 滚动条样式 */
.files-list::-webkit-scrollbar {
  width: 6px;
}

.files-list::-webkit-scrollbar-track {
  background: var(--el-fill-color-light);
  border-radius: 3px;
}

.files-list::-webkit-scrollbar-thumb {
  background: var(--el-border-color-darker);
  border-radius: 3px;
}

.files-list::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-dark);
}
</style>
