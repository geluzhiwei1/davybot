/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="three-level-monitoring">
    <!-- Agent选择器 -->
    <div v-if="allAgents.length > 1" class="agent-selector">
      <div class="selector-header">
        <el-icon><User /></el-icon>
        <span class="selector-title">选择 Agent</span>
        <el-tag size="small" type="info">{{ allAgents.length }} 个活跃</el-tag>
      </div>
      <div class="agents-list">
        <div
          v-for="agent in allAgents"
          :key="agent.taskId"
          class="agent-item"
          :class="{ 'is-selected': agent.taskId === monitoringStore.selectedAgentId }"
          @click="handleSelectAgent(agent.taskId)"
        >
          <div class="agent-mode-badge" :class="`mode-${agent.mode}`">
            {{ modeIcons[agent.mode] || '🤖' }}
          </div>
          <div class="agent-info">
            <div class="agent-name">{{ agent.taskName || agent.description }}</div>
            <div class="agent-meta">
              <el-tag :type="getAgentStatusType(agent.state)" size="small">
                {{ getAgentStatusText(agent.state) }}
              </el-tag>
              <span class="agent-time">{{ formatTime(agent.createdAt) }}</span>
            </div>
          </div>
          <div v-if="agent.taskId === monitoringStore.selectedAgentId" class="selected-indicator">
            <el-icon><CircleCheck /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- 直接显示当前执行Agent的实时TODO列表 -->
    <real-time-todos-panel
      v-if="selectedAgentData"
      :agent-id="selectedAgentData.taskId"
      :agent-name="selectedAgentData.taskName || selectedAgentData.description || '未命名 Agent'"
      :agent-mode="selectedAgentData.mode || 'orchestrator'"
      :agent-state="selectedAgentData.state || 'running'"
      :todos="selectedAgentData.todos || []"
      :outputs="selectedAgentData.outputs || []"
      @clear-outputs="handleClearOutputs"
      key="current-agent-todos"
    />

    <!-- 无任务时的空状态 -->
    <div v-else class="no-active-tasks">
      <div class="empty-icon">○</div>
      <div class="empty-title">No Active Tasks</div>
      <div class="empty-message">当前没有正在执行的任务</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { ElIcon, ElTag } from 'element-plus'
import { User, CircleCheck } from '@element-plus/icons-vue'
import { useMonitoringStore } from '@/stores/monitoringStore'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import RealTimeTodosPanel from './RealTimeTodosPanel.vue'

const monitoringStore = useMonitoringStore()
const parallelTasksStore = useParallelTasksStore()

// 所有活跃的agents
const allAgents = computed(() => monitoringStore.allAgents)

// 选中的Agent数据（包含TODO列表）
const selectedAgentData = computed(() => {
  if (!monitoringStore.selectedAgentId) return null
  const agent = monitoringStore.allAgents.find(
    agent => agent.taskId === monitoringStore.selectedAgentId
  )
  if (!agent) return null

  // 从parallelTasksStore获取详细的TODO数据
  const detailedTask = parallelTasksStore.allTasks.find(
    t => t.taskId === monitoringStore.selectedAgentId
  )

  return {
    ...agent,
    todos: detailedTask?.todos || [],
    outputs: detailedTask?.outputs || []
  }
})

// Mode图标映射
const modeIcons: Record<string, string> = {
  orchestrator: '🪃',
  architect: '🏗️',
  code: '💻',
  ask: '❓',
  debug: '🪲',
  'patent-engineer': '💡'
}

// 获取Agent状态类型
function getAgentStatusType(state: string) {
  const typeMap: Record<string, unknown> = {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    pending: 'info'
  }
  return typeMap[state] || 'info'
}

// 获取Agent状态文本
function getAgentStatusText(state: string) {
  const textMap: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    pending: '等待中'
  }
  return textMap[state] || state
}

// 格式化时间
function formatTime(date: Date): string {
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return date.toLocaleDateString()
}

// 处理选择Agent
function handleSelectAgent(agentId: string) {
  monitoringStore.selectAgent(agentId)
}

// 处理清空输出
function handleClearOutputs() {
  if (!monitoringStore.selectedAgentId) return
  // 清空parallelTasksStore中该任务的输出
  const task = parallelTasksStore.getTask(monitoringStore.selectedAgentId)
  if (task) {
    task.outputs = []
  }
}

// 监听parallelTasks数据变化，只保留正在运行的任务
watch(
  () => parallelTasksStore.allTasks,
  (tasks) => {
    console.log('[ThreeLevelMonitoring] All tasks from parallelTasksStore:', tasks.length)
    tasks.forEach(task => {
      console.log('  - Task:', task.taskId, 'state:', task.state, 'nodeType:', task.nodeType)
    })

    // 只同步正在运行或等待中的任务，过滤掉已完成和失败的
    const activeTasks = tasks.filter(
      task => task.state === 'running' || task.state === 'pending'
    )

    console.log('[ThreeLevelMonitoring] Filtered active tasks:', activeTasks.length)

    monitoringStore.updateAgents(activeTasks)

    // 如果当前没有选中的agent，自动选择主agent
    if (!monitoringStore.selectedAgentId && activeTasks.length > 0) {
      const mainAgent = findMainAgent(activeTasks)
      if (mainAgent) {
        console.log('[ThreeLevelMonitoring] Auto-selecting main agent:', mainAgent.taskId)
        monitoringStore.selectAgent(mainAgent.taskId)
      }
    }

    console.log('[ThreeLevelMonitoring] Selected agent ID:', monitoringStore.selectedAgentId)
  },
  { deep: true, immediate: true }
)

// 查找主agent（orchestrator或第一个agent）
function findMainAgent(tasks: unknown[]) {
  console.log('[ThreeLevelMonitoring] findMainAgent called with tasks:', tasks.length)

  // 优先查找orchestrator模式的agent（不区分大小写）
  const orchestratorAgent = tasks.find(
    task => {
      const nodeType = task.nodeType?.toLowerCase()
      console.log('[ThreeLevelMonitoring] Checking task:', task.taskId, 'nodeType:', nodeType)
      return nodeType === 'orchestrator'
    }
  )

  if (orchestratorAgent) {
    console.log('[ThreeLevelMonitoring] Found orchestrator agent:', orchestratorAgent.taskId)
    return orchestratorAgent
  }

  // 如果没有orchestrator，返回第一个agent
  console.log('[ThreeLevelMonitoring] No orchestrator found, returning first task')
  return tasks[0] || null
}
</script>

<style scoped>
.three-level-monitoring {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  overflow: hidden;
}

/* Agent选择器 */
.agent-selector {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-light);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.selector-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}

.selector-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}

.agents-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border: 2px solid #e4e7ed;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  background: #f5f7fa;
}

.agent-item:hover {
  border-color: #409eff;
  background: white;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}

.agent-item.is-selected {
  border-color: #409eff;
  background: #ecf5ff;
}

.agent-mode-badge {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 20px;
  flex-shrink: 0;
  background: white;
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.agent-time {
  color: #909399;
}

.selected-indicator {
  color: #409eff;
  font-size: 20px;
  flex-shrink: 0;
}

/* 空状态 */
.no-active-tasks {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
  flex: 1;
}

.empty-icon {
  font-size: 64px;
  color: #e5e7eb;
  margin-bottom: 20px;
}

.empty-title {
  font-size: 20px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.empty-message {
  font-size: 14px;
  color: #6b7280;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .empty-title {
    color: var(--el-text-color-primary);
  }

  .empty-message {
    color: var(--el-text-color-secondary);
  }
}
</style>
