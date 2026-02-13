/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="thinking-content compact-content">
    <el-collapse v-model="activeNames" class="thinking-collapse compact-collapse">
      <el-collapse-item name="thinking" class="thinking-item">
        <template #title>
          <div class="thinking-header compact-header">
            <el-icon><Operation /></el-icon>
            <span class="compact-title">思考过程</span>
            <el-tag
              :type="getOverallStatusType()"
              size="small"
              effect="light"
              class="status-tag compact-tag"
            >
              {{ getOverallStatusText() }}
            </el-tag>
          </div>
        </template>

        <div class="thinking-steps compact-body">
          <div
            v-for="(step, index) in block.steps"
            :key="step.step_id"
            class="thinking-step"
            :class="{ 'step-error': step.status === 'failed' }"
          >
            <div class="step-header">
              <div class="step-number">{{ index + 1 }}</div>
              <div class="step-status">
                <el-icon
                  :class="getStatusClass(step.status)"
                  :color="getStatusColor(step.status)"
                >
                  <component :is="getStatusIcon(step.status)" />
                </el-icon>
              </div>
            </div>
            <div class="step-content">
              <div class="step-thought">{{ step.thought }}</div>
              <div v-if="step.details" class="step-details compact-mt-sm">
                <el-collapse class="compact-collapse">
                  <el-collapse-item name="details" title="详细信息">
                    <pre class="compact-pre">{{ JSON.stringify(step.details, null, 2) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  Operation,
  Loading,
  CircleCheck,
  CircleClose
} from '@element-plus/icons-vue'
import { ElCollapse, ElCollapseItem, ElIcon, ElTag } from 'element-plus'
import type { ThinkingContentBlock } from '@/types/websocket'

const props = defineProps<{
  block: ThinkingContentBlock
}>()


const activeNames = ref<string[]>([])

// 获取整体状态
const getOverallStatus = () => {
  const steps = props.block.steps
  if (steps.some(step => step.status === 'failed')) {
    return 'failed'
  } else if (steps.some(step => step.status === 'in_progress')) {
    return 'in_progress'
  } else {
    return 'completed'
  }
}

const getOverallStatusType = () => {
  const status = getOverallStatus()
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'danger'
    case 'in_progress':
      return 'warning'
    default:
      return 'info'
  }
}

const getOverallStatusText = () => {
  const status = getOverallStatus()
  switch (status) {
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'in_progress':
      return '进行中'
    default:
      return '未知'
  }
}

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return CircleCheck
    case 'failed':
      return CircleClose
    case 'in_progress':
      return Loading
    default:
      return Loading
  }
}

const getStatusClass = (status: string) => {
  switch (status) {
    case 'completed':
      return 'status-completed'
    case 'failed':
      return 'status-failed'
    case 'in_progress':
      return 'status-in-progress is-loading'
    default:
      return 'status-unknown'
  }
}

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return '#67c23a'
    case 'failed':
      return '#f56c6c'
    case 'in_progress':
      return '#e6a23c'
    default:
      return '#909399'
  }
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.thinking-item :deep(.el-collapse-item__header) {
  background-color: var(--el-fill-color-light);
}

.status-tag {
  margin-left: auto;
}

.thinking-steps {
  padding: var(--compact-padding-lg);
}

.thinking-step {
  display: flex;
  gap: var(--compact-padding-md);
  margin-bottom: var(--compact-padding-md);
  padding: var(--compact-padding-sm) var(--compact-padding-md);
  background-color: var(--el-bg-color);
  border-radius: var(--compact-radius-md);
  border: 1px solid var(--el-border-color-lighter);
}

.thinking-step:last-child {
  margin-bottom: 0;
}

.thinking-step.step-error {
  border-color: var(--el-color-danger-light-7);
  background-color: var(--el-color-danger-light-9);
}

.step-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--compact-gap-xs);
  flex-shrink: 0;
}

.step-number {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: var(--el-color-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--compact-font-xs);
  font-weight: 500;
}

.step-status {
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-completed {
  color: var(--el-color-success);
}

.status-failed {
  color: var(--el-color-danger);
}

.status-in-progress {
  color: var(--el-color-warning);
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-thought {
  font-size: var(--compact-font-md);
  line-height: 1.4;
  color: var(--el-text-color-primary);
  margin-bottom: var(--compact-padding-xs);
}

.step-details {
  margin-top: var(--compact-padding-xs);
}

.step-details :deep(.el-collapse-item__header) {
  padding: var(--compact-padding-xs) 0;
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-secondary);
  border: none;
}

.step-details :deep(.el-collapse-item__content) {
  padding: var(--compact-padding-xs) 0;
}
</style>