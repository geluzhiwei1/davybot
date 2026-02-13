<!--
极简监控面板 - 下拉式可折叠面板
设计理念：极简、克制、专业、易用
限制在 el-main 区域内，向下展开
-->

<template>
  <div id="activeAgentInfo" class="dropdown-monitoring-panel" :class="{ 'is-collapsed': isCollapsed }">
    <!-- 折叠状态 - 顶部条 -->
    <div class="panel-trigger" @click="toggleCollapse">
      <div class="trigger-left">
        <span class="trigger-text">Active Agents</span>
        <span v-if="allAgents.length > 0" class="task-count">{{ allAgents.length }}</span>
      </div>
      <div class="trigger-right">
        <svg class="chevron" :class="{ 'is-flipped': !isCollapsed }" viewBox="0 0 16 16" fill="currentColor">
          <path d="M3 6l5 5 5-5H3z"/>
        </svg>
      </div>
    </div>

    <!-- 展开状态 - 内容区域 -->
    <div v-show="!isCollapsed" class="panel-content-wrapper">
      <div class="panel-content">
        <!-- 空状态 -->
        <div v-if="!hasActiveAgents" class="empty-state">
          <div class="empty-text">No active tasks</div>
        </div>

        <!-- 活跃Agent -->
        <div v-else class="active-agents">
          <!-- Agent切换器（仅在多个agent时显示） -->
          <div v-if="allAgents.length > 1" class="agent-tabs">
            <button
              v-for="agent in allAgents"
              :key="agent.taskId"
              class="agent-tab"
              :class="{ 'is-active': agent.taskId === selectedAgentId }"
              @click="selectAgent(agent.taskId)"
            >
              <span class="tab-dot"></span>
              <span class="tab-text">{{ getModeLabel(agent.mode) }}</span>
            </button>
          </div>

          <!-- 当前Agent信息 -->
          <div v-if="selectedAgent" class="agent-info">
            <!-- 头部：模式 + 状态 -->
            <div class="agent-header">
              <div class="header-text">
                <div class="mode-label">{{ getModeLabel(selectedAgent.mode) }}</div>
                <div class="task-preview">{{ getTaskPreview(selectedAgent) }}</div>
              </div>
              <div class="status-badge" :class="`status-${selectedAgent.state}`">
                {{ getStatusLabel(selectedAgent.state) }}
              </div>
            </div>

            <!-- 执行进度（仅在有TODO时显示） -->
            <div v-if="hasTodos" class="progress-section">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: progressPercent + '%' }"
                ></div>
              </div>
              <div class="progress-meta">
                <span class="progress-text">{{ completedCount }}/{{ totalCount }} 已完成</span>
                <span class="progress-percent">{{ Math.round(progressPercent) }}%</span>
              </div>
            </div>

            <!-- TODO列表（简化版） -->
            <div v-if="hasTodos" class="todo-list">
              <div
                v-for="(todo, index) in displayTodos"
                :key="index"
                class="todo-item"
                :class="`todo-${todo.state}`"
              >
                <div class="todo-status">
                  <svg v-if="todo.state === 'completed'" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M13.5 3L6 11L2.5 7.5L1 9L6 15L15 5L13.5 3Z"/>
                  </svg>
                  <div v-else class="pending-dot"></div>
                </div>
                <div class="todo-content">
                  <div class="todo-text">{{ todo.title || todo.task_id }}</div>
                  <div v-if="todo.state === 'in_progress'" class="todo-meta">
                    执行中
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMonitoringStore } from '@/stores/monitoringStore'
import { useParallelTasksStore } from '@/stores/parallelTasks'

const monitoringStore = useMonitoringStore()
const parallelTasksStore = useParallelTasksStore()

const selectedAgentId = ref<string | null>(null)

// 折叠状态 - 默认折叠
const isCollapsed = ref(true)

// 切换折叠状态
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

// 监听任务变化
watch(
  () => parallelTasksStore.allTasks,
  (tasks) => {
    const activeTasks = tasks.filter(
      task => task.state === 'running' || task.state === 'pending'
    )

    monitoringStore.updateAgents(activeTasks)

    if (activeTasks.length > 0) {
      const currentSelectedTask = tasks.find(t => t.taskId === selectedAgentId.value)
      const isCurrentTaskInactive = !currentSelectedTask || currentSelectedTask.state === 'completed'

      if (!selectedAgentId.value || isCurrentTaskInactive) {
        selectedAgentId.value = activeTasks[0].taskId
      }
    }
  },
  { deep: true, immediate: true }
)

const allAgents = computed(() => monitoringStore.allAgents)

const hasActiveAgents = computed(() => allAgents.value.length > 0)

// Auto-select first agent if none selected
watch(allAgents, (agents) => {
  if (!selectedAgentId.value && agents.length > 0) {
    selectedAgentId.value = agents[0].taskId
  }
}, { immediate: true })

const selectedAgent = computed(() => {

  const agent = allAgents.value.find(a => a.taskId === selectedAgentId.value)
  if (!agent) return null

  const detailedTask = parallelTasksStore.allTasks.find(
    t => t.taskId === selectedAgentId.value
  )

  return {
    ...agent,
    todos: detailedTask?.todos || []
  }
})

// 计算TODO相关
const hasTodos = computed(() => {
  return selectedAgent.value?.todos && selectedAgent.value.todos.length > 0
})

const todos = computed(() => {
  return selectedAgent.value?.todos || []
})

const completedCount = computed(() => {
  return todos.value.filter(t => t.state === 'completed').length
})

const totalCount = computed(() => {
  return todos.value.length
})

const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  return (completedCount.value / totalCount.value) * 100
})

// 显示的TODO（最多5个）
const displayTodos = computed(() => {
  return todos.value.slice(0, 5)
})

// 方法
const selectAgent = (taskId: string) => {
  selectedAgentId.value = taskId
}

const getModeLabel = (mode: string) => {
  const labels: Record<string, string> = {
    orchestrator: 'Orchestrator',
    ask: 'Ask',
    code: 'Code',
    architect: 'Architect',
    plan: 'Plan',
    debug: 'Debug'
  }
  return labels[mode] || mode
}

const getStatusLabel = (state: string) => {
  const labels: Record<string, string> = {
    running: 'Running',
    completed: 'Completed',
    pending: 'Pending',
    failed: 'Failed'
  }
  return labels[state] || state
}

const getTaskPreview = (agent: unknown) => {
  const desc = agent.taskName || agent.description || ''
  return desc.length > 30 ? desc.substring(0, 30) + '...' : desc
}
</script>

<style scoped>
.dropdown-monitoring-panel {
  width: 100%;
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  transition: all 0.2s ease;
}

/* 触发条 */
.panel-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--el-fill-color-light);
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid transparent;
  transition: all 0.2s ease;
}

.panel-trigger:hover {
  background: var(--el-fill-color);
}

.trigger-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.trigger-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.task-count {
  background: var(--el-color-primary);
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  min-width: 18px;
  text-align: center;
}

.trigger-right {
  display: flex;
  align-items: center;
}

.chevron {
  width: 16px;
  height: 16px;
  transition: transform 0.2s ease;
  color: var(--el-text-color-secondary);
}

.chevron.is-flipped {
  transform: rotate(180deg);
}

/* 内容区域 */
.panel-content-wrapper {
  max-height: 400px;
  overflow: hidden;
  animation: slideDown 0.2s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 400px;
  }
}

.panel-content {
  padding: 16px;
  overflow-y: auto;
  max-height: 400px;
  background: var(--el-bg-color-page);
}

.panel-content::-webkit-scrollbar {
  width: 4px;
}

.panel-content::-webkit-scrollbar-track {
  background: transparent;
}

.panel-content::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 2px;
}

.panel-content::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-darker);
}

/* 空状态 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--el-text-color-placeholder);
}

.empty-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* Agent标签 */
.agent-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.agent-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-bg-color);
  color: var(--el-text-color-regular);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 500;
}

.agent-tab:hover {
  border-color: var(--el-border-color-dark);
  background: var(--el-fill-color-light);
}

.agent-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

/* Agent信息 */
.agent-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-light);
}

.header-text {
  flex: 1;
  min-width: 0;
}

.mode-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 2px;
}

.task-preview {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.status-badge.status-running {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.status-badge.status-completed {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.status-badge.status-pending {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}

.status-badge.status-failed {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

/* 进度条 */
.progress-section {
  padding: 0 2px;
}

.progress-bar {
  height: 3px;
  background: var(--el-border-color-lighter);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 6px;
}

.progress-fill {
  height: 100%;
  background: var(--el-color-primary);
  transition: width 0.3s ease;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.progress-percent {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* TODO列表 */
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  background: var(--el-bg-color);
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
}

.todo-item.todo-completed {
  opacity: 0.5;
}

.todo-item.todo-in_progress {
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.todo-status {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.todo-status svg {
  width: 100%;
  height: 100%;
  color: var(--el-color-success);
}

.pending-dot {
  width: 6px;
  height: 6px;
  margin: 4px;
  border-radius: 50%;
  border: 2px solid var(--el-color-primary);
}

.todo-content {
  flex: 1;
  min-width: 0;
}

.todo-text {
  color: var(--el-text-color-primary);
  word-break: break-word;
  line-height: 1.5;
}

.todo-meta {
  font-size: 11px;
  color: var(--el-color-primary);
  margin-top: 2px;
}
</style>
