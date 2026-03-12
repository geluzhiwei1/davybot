/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="system-status-container">
    <!-- 状态栏 -->
    <div class="system-status-bar" :class="{ 'is-active': hasActiveTask }">
      <div class="status-content">
        <!-- 左侧：状态图标和文本 -->
        <div class="status-left">
          <el-icon class="status-icon" :class="{ 'is-loading': hasActiveTask }">
            <component :is="statusIcon" />
          </el-icon>
          <span class="status-text">{{ statusText }}</span>
          <el-tag v-if="activeTaskTag" size="small" :type="activeTaskTag.type" effect="plain">
            {{ activeTaskTag.label }}
          </el-tag>
        </div>

        <!-- 中间：任务进度/内容 -->
        <div class="status-center">
          <div class="progress-info" v-if="currentProgress">
            <el-progress :percentage="currentProgress.percentage" :status="currentProgress.status" :show-text="false"
              :stroke-width="3" />
            <span class="progress-text">{{ currentProgress.text }}</span>
          </div>
          <div v-else class="status-message">
            {{ statusMessage }}
          </div>
        </div>

        <!-- 右侧：额外信息 -->
        <div class="status-right">
          <span v-if="activeTaskDuration" class="duration-text">
            {{ activeTaskDuration }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import { Loading, CircleCheck } from '@element-plus/icons-vue'
import { ElTag, ElProgress, ElIcon } from 'element-plus'

const chatStore = useChatStore()
const parallelTasksStore = useParallelTasksStore()
const llmApiStatus = computed(() => chatStore.llmApiStatus)
const agentStatus = computed(() => chatStore.agentStatus)

// 当前活跃任务信息
interface ActiveTask {
  type: 'llm' | 'tool' | 'task' | 'error' | 'agent' | 'stream'
  message: string
  timestamp: number
  progress?: number
}

const currentTask = ref<ActiveTask | null>(null)

// 是否有活跃任务（综合判断 LLM、工具执行和 Agent 状态）
const hasActiveTask = computed(() => {
  return !!currentTask.value ||
         llmApiStatus.value.isActive ||
         agentStatus.value.isActive ||
         parallelTasksStore.hasActiveTasks
})

// 状态图标
const statusIcon = computed(() => {
  if (hasActiveTask.value) return Loading
  return CircleCheck
})

// 状态文本
const statusText = computed(() => {
  if (hasActiveTask.value) {
    return currentTask.value?.message || '处理中'
  }
  return '就绪'
})

// 活跃任务标签
const activeTaskTag = computed((): {
  type: 'primary' | 'danger' | 'success' | 'warning' | 'info'
  label: string
} | null => {
  if (!hasActiveTask.value) return null

  const type = currentTask.value?.type
  if (type === 'llm') return { type: 'primary', label: 'AI 调用' }
  if (type === 'tool') return { type: 'warning', label: '工具执行' }
  if (type === 'task') return { type: 'info', label: '任务处理' }
  if (type === 'agent') return { type: 'success', label: 'Agent 执行' }
  if (type === 'error') return { type: 'danger', label: '错误' }

  // 如果没有 currentTask 但有活跃任务，检查其他状态
  if (llmApiStatus.value.isActive) return { type: 'primary', label: 'AI 调用' }
  if (parallelTasksStore.hasActiveTasks) return { type: 'warning', label: '工具执行' }
  if (agentStatus.value.isActive) return { type: 'success', label: 'Agent 执行' }

  return { type: 'info', label: '处理中' }
})

// 当前进度
const currentProgress = computed(() => {
  if (!hasActiveTask.value) return null

  const progress = currentTask.value?.progress
  if (typeof progress === 'number') {
    return {
      percentage: progress,
      status: (progress >= 100 ? 'success' : undefined) as '' | 'success' | 'warning' | 'exception' | undefined,
      text: `${progress}%`
    }
  }

  return null
})

// 状态消息
const statusMessage = computed(() => {
  if (hasActiveTask.value) {
    return currentTask.value?.message || '正在处理...'
  }
  return '系统就绪'
})

// 活跃任务持续时间
const activeTaskDuration = computed(() => {
  if (!hasActiveTask.value || !currentTask.value?.timestamp) return null

  const elapsed = Date.now() - currentTask.value.timestamp
  if (elapsed < 1000) return `${elapsed}ms`
  return `${(elapsed / 1000).toFixed(1)}s`
})

// 监听 LLM API 状态变化
watch(() => llmApiStatus.value.isActive, (active) => {
  if (active) {
    currentTask.value = {
      type: 'llm',
      message: 'AI 调用中',
      timestamp: Date.now()
    }
  } else {
    currentTask.value = null
  }
})

// 监听 LLM API 响应内容
watch(() => llmApiStatus.value.responseContent, (content) => {
  if (currentTask.value?.type === 'llm' && content) {
    currentTask.value.message = 'AI 响应中...'
  }
})

// 监听 Agent 状态变化
watch(() => agentStatus.value.isActive, (active) => {
  if (active) {
    const mode = agentStatus.value.agentMode
    currentTask.value = {
      type: 'agent',
      message: `${mode} Agent 执行中`,
      timestamp: Date.now()
    }
  } else if (currentTask.value?.type === 'agent') {
    currentTask.value = null
  }
})

// 监听 Agent 思考内容
watch(() => agentStatus.value.thinking, (thinking) => {
  if (currentTask.value?.type === 'agent' && thinking) {
    currentTask.value.message = 'Agent 思考中...'
  }
})

// 监听并行任务状态变化（工具执行）
watch(() => parallelTasksStore.hasActiveTasks, (hasActive, prevHasActive) => {
  // 从无任务变为有任务
  if (hasActive && !prevHasActive) {
    const activeTasks = parallelTasksStore.activeTasks
    if (activeTasks.length > 0) {
      const task = activeTasks[0]
      currentTask.value = {
        type: 'tool',
        message: `工具执行中: ${task.description || task.nodeType || '未知工具'}`,
        timestamp: Date.now()
      }
    }
  }
  // 从有任务变为无任务
  else if (!hasActive && prevHasActive) {
    if (currentTask.value?.type === 'tool') {
      currentTask.value = null
    }
  }
})

// 处理任务节点进度
const handleTaskNodeProgress = (event: Event) => {
  const customEvent = event as CustomEvent<{progress: number}>
  const detail = customEvent.detail
  if (currentTask.value?.type === 'task' && detail) {
    currentTask.value.message = `任务进度: ${detail.progress}%`
    currentTask.value.progress = detail.progress
  }
}

// 组件卸载时移除事件监听
onUnmounted(() => {
  window.removeEventListener('task-node-progress', handleTaskNodeProgress)
})
</script>

<style scoped>
.system-status-container {
  width: 100%;
}

.system-status-bar {
  background-color: var(--el-bg-color-overlay);
  border-top: 1px solid var(--el-border-color-lighter);
  transition: all 0.3s ease;
  height: 32px;
}

.system-status-bar.is-active {
  background-color: var(--el-color-primary-light-9);
  border-top-color: var(--el-color-primary-light-5);
}

.status-content {
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 12px;
  height: 100%;
}

.status-left {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-icon {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  transition: color 0.3s ease;
}

.system-status-bar.is-active .status-icon {
  color: var(--el-color-primary);
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.status-text {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.status-center {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.progress-info .el-progress {
  flex-shrink: 0;
  width: 80px;
}

.progress-text {
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.status-message {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.duration-text {
  font-size: 11px;
  color: var(--el-color-success);
  font-family: monospace;
  font-weight: 500;
}
</style>
