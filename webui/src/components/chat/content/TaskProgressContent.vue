/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-progress-content compact-content">
    <div class="progress-header compact-header">
      <div class="header-left">
        <el-icon class="progress-icon"><DataAnalysis /></el-icon>
        <span class="progress-title compact-title">任务进度</span>
        <el-tag size="small" :type="getStatusTagType(progress.status)" effect="light" class="compact-tag">
          {{ getStatusText(progress.status) }}
        </el-tag>
      </div>
      <div class="header-right">
        <span class="task-id">ID: {{ progress.task_id?.substring(0, 8) }}...</span>
      </div>
    </div>

    <div class="progress-body compact-body">
      <!-- 进度条 -->
      <div class="progress-bar-section compact-detail-block">
        <div class="progress-header-row">
          <span class="progress-label">完成进度</span>
          <span class="progress-value">{{ progress.progress }}%</span>
        </div>
        <el-progress
          :percentage="progress.progress"
          :status="getProgressStatus()"
          :stroke-width="6"
          :show-text="false"
        />
      </div>

      <!-- 进度描述 -->
      <div class="progress-description compact-stats compact-mb-sm">
        <el-icon><Document /></el-icon>
        <span>{{ progress.message }}</span>
      </div>

      <!-- 详细数据 -->
      <el-collapse v-if="progress.data && Object.keys(progress.data).length > 0" class="data-collapse compact-collapse">
        <el-collapse-item name="data" title="详细数据">
          <div class="data-content">
            <div class="data-grid">
              <div v-for="(value, key) in progress.data" :key="key" class="data-item">
                <span class="data-key">{{ key }}:</span>
                <span class="data-value">{{ formatValue(value) }}</span>
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 时间信息 -->
      <div v-if="progress.timestamp" class="timestamp-info compact-stats">
        <el-icon><Clock /></el-icon>
        <span>更新时间: {{ formatTimestamp(progress.timestamp, 'time') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatTimestamp } from '@/utils/formatters'
import { computed } from 'vue'
import { DataAnalysis, Document, Clock } from '@element-plus/icons-vue'
import { ElIcon, ElTag, ElProgress, ElCollapse, ElCollapseItem } from 'element-plus'

// 定义任务进度消息类型
interface TaskProgressBlock {
  type: 'task_progress'
  task_id: string
  progress: number
  status: 'planning' | 'executing' | 'completed' | 'error'
  message: string
  data?: Record<string, unknown>
  timestamp?: string
}

const props = defineProps<{
  block: TaskProgressBlock
}>()

const progress = computed(() => props.block)

// 获取状态标签类型
const getStatusTagType = (status: string) => {
  switch (status) {
    case 'planning':
      return 'info'
    case 'executing':
      return 'warning'
    case 'completed':
      return 'success'
    case 'error':
      return 'danger'
    default:
      return 'info'
  }
}

// 获取状态文本
const getStatusText = (status: string) => {
  switch (status) {
    case 'planning':
      return '规划中'
    case 'executing':
      return '执行中'
    case 'completed':
      return '已完成'
    case 'error':
      return '错误'
    default:
      return status
  }
}

// 获取进度条状态
const getProgressStatus = () => {
  const status = progress.value.status
  if (status === 'completed') return 'success'
  if (status === 'error') return 'exception'
  return undefined
}

// 格式化值
const formatValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return 'N/A'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   Task Progress - 任务进度展示组件样式
   ============================================================================ */

/* 数据网格 */
.data-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--modern-spacing-sm);
}

.data-item {
  display: flex;
  gap: var(--modern-spacing-sm);
  padding: var(--modern-spacing-sm);
  background: var(--modern-bg-subtle);
  border-radius: var(--modern-radius-sm);
}

.data-key {
  font-weight: 600;
  color: #64748b;
  font-size: var(--modern-font-sm);
}

.data-value {
  color: #1e293b;
  font-size: var(--modern-font-sm);
  word-break: break-word;
}

/* 进度头部行 */
.progress-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--modern-spacing-sm);
}

.progress-label {
  font-size: var(--modern-font-sm);
  font-weight: 600;
  color: #64748b;
}

.progress-value {
  font-size: var(--modern-font-md);
  font-weight: 600;
  color: var(--modern-color-primary);
}

/* 头部区域 */
.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
}

.task-id {
  font-size: var(--modern-font-xs);
  color: #64748b;
  font-family: monospace;
}

/* 进度图标 */
.progress-icon {
  font-size: 18px;
  color: var(--modern-color-primary);
}
</style>
