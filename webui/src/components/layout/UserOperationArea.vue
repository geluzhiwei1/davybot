/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <!-- Agent 控制面板 -->
  <div v-if="showAgentControls" class="agent-controls-area">
    <div class="agent-controls-header">
      <span class="agent-status-text">
        <el-icon class="status-icon" :class="agentStatusClass">
          <Loading v-if="agentStatus.isActive" />
          <CircleCheck v-else />
        </el-icon>
        {{ agentStatusText }}
      </span>
      <span class="agent-mode-badge">{{ agentStatus.agentMode }}</span>
    </div>

    <div class="agent-control-buttons">
      <!-- 始终显示停止按钮 -->
      <el-button type="danger" :icon="Close" @click="handleStopAgent" size="small">
        停止
      </el-button>
    </div>
  </div>

  <!-- 其他操作确认区域 -->
  <div v-if="showOperations" class="user-operation-area">
    <el-alert :title="operationMessage" type="warning" :closable="false" show-icon class="operation-alert">
      <template #default>
        <div class="operation-content">
          <div v-if="operationDetails" class="operation-details">
            <pre>{{ operationDetails }}</pre>
          </div>
          <div class="operation-buttons">
            <el-button @click="handleCancel">取消</el-button>
            <el-button type="primary" @click="handleConfirm">
              {{ confirmButtonText }}
            </el-button>
          </div>
        </div>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAgentStore } from '@/stores/agent'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import { storeToRefs } from 'pinia'
import { Loading, CircleCheck, Close } from '@element-plus/icons-vue'

interface Operation {
  type: 'file_edit' | 'tool_call' | 'task_execution'
  message: string
  details?: string
  confirmText?: string
}

const chatStore = useChatStore()
const agentStore = useAgentStore()
const parallelTasksStore = useParallelTasksStore()
const { agentStatus, currentTaskId } = storeToRefs(chatStore)

const currentOperation = ref<Operation | null>(null)

// Agent 控制相关
// 使用 parallelTasksStore.hasActiveTasks 判断是否有活跃任务，避免子任务场景下提前隐藏
const showAgentControls = computed(() =>
  parallelTasksStore.hasActiveTasks ||
  agentStatus.value.isActive
)

const agentStatusText = computed(() => {
  if (agentStatus.value.isActive) return 'Agent 执行中'
  return 'Agent 空闲'
})

const agentStatusClass = computed(() => {
  if (agentStatus.value.isActive) return 'status-running'
  return 'status-idle'
})

// 操作确认相关
const showOperations = computed(() => currentOperation.value !== null)

const operationMessage = computed(() => {
  return currentOperation.value?.message || 'AI需要您的确认'
})

const operationDetails = computed(() => {
  return currentOperation.value?.details || ''
})

const confirmButtonText = computed(() => {
  return currentOperation.value?.confirmText || '确认'
})

// Agent 控制方法
const handleStopAgent = async () => {
  const activeTasks = parallelTasksStore.activeTasks

  if (activeTasks.length === 0) {
    if (agentStatus.value.isActive && currentTaskId.value) {
      await chatStore.stopAgent(currentTaskId.value)
    } else if (agentStatus.value.isActive) {
      console.warn('[UserOperationArea] Agent处于活跃状态但没有taskId，强制清理状态')
      agentStore.stopAgent()
      parallelTasksStore.clearAllTasks()
    } else {
      console.warn('[UserOperationArea] 没有活跃任务可停止')
    }
    return
  }

  // 停止所有活跃任务
  for (const task of activeTasks) {
    await chatStore.stopAgent(task.taskId)
  }
}

// 操作确认方法
const simulateOperationRequest = () => {
  currentOperation.value = {
    type: 'file_edit',
    message: 'AI正在请求修改文件 ChatView.vue',
    details: `将要应用以下更改：
+ 添加新的三栏布局结构
+ 更新组件导入
+ 调整样式定义`,
    confirmText: '应用更改'
  }
}

const handleCancel = () => {
  currentOperation.value = null
}

const handleConfirm = () => {
  currentOperation.value = null
}

defineExpose({
  simulateOperationRequest
})
</script>

<style scoped>
/* Agent 控制面板 */
.agent-controls-area {
  padding: 12px 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8eef5 100%);
  border-bottom: 1px solid var(--el-border-color-light);
  animation: slideDown 0.3s ease-out;
}

.agent-controls-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.agent-status-text {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.status-icon {
  font-size: 16px;
}

.status-running {
  color: var(--el-color-primary);
  animation: rotate 1s linear infinite;
}

.status-paused {
  color: var(--el-color-warning);
}

.status-idle {
  color: var(--el-color-success);
}

.agent-mode-badge {
  padding: 4px 12px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.agent-control-buttons {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* 其他操作区域 */
.user-operation-area {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  animation: slideDown 0.3s ease-out;
}

.operation-alert {
  padding: 16px;
}

:deep(.el-alert__content) {
  width: 100%;
}

.operation-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.operation-details {
  background-color: var(--el-fill-color-light);
  padding: 8px 12px;
  border-radius: 4px;
  margin-top: 8px;
}

.operation-details pre {
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.operation-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>