/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="thinking-steps-container">
    <el-collapse v-if="thinkingSteps.length > 0" class="thinking-steps" v-model="activeNames">
      <el-collapse-item
        v-for="(step, index) in thinkingSteps"
        :key="step.step_id"
        :name="step.step_id"
        class="thinking-step"
      >
        <template #title>
          <div class="step-header">
            <div class="step-number">{{ index + 1 }}</div>
            <div class="step-title">
              <span>思考步骤 {{ index + 1 }}</span>
              <el-tag 
                :type="getStepStatusType(step.status)" 
                size="small" 
                effect="light"
                class="step-status"
              >
                {{ getStepStatusText(step.status) }}
              </el-tag>
            </div>
            <div class="step-indicator">
              <el-icon 
                :class="getStepStatusClass(step.status)"
                :color="getStepStatusColor(step.status)"
              >
                <component :is="getStepStatusIcon(step.status)" />
              </el-icon>
            </div>
          </div>
        </template>
        
        <div class="step-content">
          <div class="thought-section">
            <h4>思考过程:</h4>
            <div class="thought-content">
              <p>{{ step.thought }}</p>
            </div>
          </div>
          
          <div v-if="step.details && step.details.toolCall" class="tool-section">
            <h4>工具调用:</h4>
            <ToolCall :tool-call="step.details.toolCall" />
          </div>
          
          <div v-if="step.details" class="details-section">
            <el-collapse>
              <el-collapse-item name="details" title="详细信息">
                <pre>{{ JSON.stringify(step.details, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
    
    <!-- 空状态 -->
    <div v-else class="empty-state">
      <el-empty description="暂无思考步骤" :image-size="100">
        <template #description>
          <p>大微正在思考如何回答您的问题...</p>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { 
  Loading, 
  CircleCheck, 
  CircleClose, 
  QuestionFilled 
} from '@element-plus/icons-vue'
import { 
  ElCollapse, 
  ElCollapseItem, 
  ElTag, 
  ElIcon, 
  ElEmpty 
} from 'element-plus'
import ToolCall from './ToolCall.vue'
import type { ThinkingStep } from '@/types/websocket'

interface Props {
  steps?: ThinkingStep[]
}

const props = withDefaults(defineProps<Props>(), {
  steps: () => []
})


const activeNames = ref<string[]>([])

const thinkingSteps = computed(() => {
  return props.steps || []
})

const getStepStatusType = (status: string) => {
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

const getStepStatusText = (status: string) => {
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

const getStepStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return CircleCheck
    case 'failed':
      return CircleClose
    case 'in_progress':
      return Loading
    default:
      return QuestionFilled
  }
}

const getStepStatusClass = (status: string) => {
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

const getStepStatusColor = (status: string) => {
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
.thinking-steps-container {
  margin-bottom: 16px;
  border-left: 2px solid var(--el-border-color);
  padding-left: 16px;
  margin-left: 8px;
  background-color: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.thinking-steps {
  border: none;
  background-color: transparent;
}

.thinking-step {
  margin-bottom: 8px;
  background-color: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}

.thinking-step:last-child {
  margin-bottom: 0;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background-color: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-lighter);
  width: 100%;
}

.step-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: var(--el-color-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
}

.step-title {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.step-status {
  flex-shrink: 0;
}

.step-indicator {
  flex-shrink: 0;
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
  padding: 16px;
}

.thought-section,
.tool-section,
.details-section {
  margin-bottom: 16px;
}

.thought-section:last-child,
.tool-section:last-child,
.details-section:last-child {
  margin-bottom: 0;
}

.thought-section h4,
.tool-section h4,
.details-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0 0 8px 0;
}

.thought-content p {
  margin: 0;
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.details-section :deep(.el-collapse) {
  border: none;
}

.details-section :deep(.el-collapse-item__header) {
  padding: 8px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border: none;
}

.details-section :deep(.el-collapse-item__content) {
  padding: 8px 0;
}

.details-section pre {
  background-color: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-state {
  padding: 24px;
  text-align: center;
  background-color: var(--el-fill-color-light);
  border-radius: 8px;
  border: 1px dashed var(--el-border-color-lighter);
}

.empty-state p {
  margin: 8px 0 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .thinking-steps-container {
    margin-left: 4px;
    padding-left: 12px;
  }
  
  .step-header {
    padding: 10px 12px;
    gap: 8px;
  }
  
  .step-content {
    padding: 12px;
  }
}
</style>