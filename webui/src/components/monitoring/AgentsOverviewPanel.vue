/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="agents-overview-panel">
    <!-- Agents列表 -->
    <div class="agents-section">
      <div class="section-header">
        <h3 class="section-title">
          <el-icon><List /></el-icon>
          并行 Agents 列表
        </h3>
        <el-tag size="small" type="info">{{ filteredAgents.length }} 个</el-tag>
      </div>

      <div v-if="filteredAgents.length === 0" class="empty-state">
        <el-empty description="暂无运行中的 Agents">
          <el-text type="info">当有任务执行时，Agents 将会显示在这里</el-text>
        </el-empty>
      </div>

      <div v-else class="agents-list">
        <div
          v-for="agent in filteredAgents"
          :key="agent.taskId"
          class="agent-card"
          :class="`agent-card--${agent.state}`"
          @click="handleAgentClick(agent)"
        >
          <!-- Agent头部 -->
          <div class="agent-header">
            <div class="agent-info">
              <div class="agent-avatar">
                <el-icon><Monitor /></el-icon>
              </div>
              <div class="agent-details">
                <div class="agent-name">{{ agent.taskName || '未命名任务' }}</div>
                <div class="agent-id">ID: {{ agent.taskId.slice(0, 8) }}</div>
              </div>
            </div>

            <div class="agent-status">
              <el-tag :type="getStatusType(agent.state)" size="small">
                {{ getStatusText(agent.state) }}
              </el-tag>
            </div>
          </div>

          <!-- Agent进度 -->
          <div v-if="agent.progress !== undefined" class="agent-progress">
            <el-progress
              :percentage="Math.round(agent.progress * 100)"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(agent.state)"
            />
            <div class="progress-text">
              <span class="progress-percent">{{ Math.round(agent.progress * 100) }}%</span>
              <span class="progress-message">{{ agent.currentStep || '执行中...' }}</span>
            </div>
          </div>

          <!-- Agent统计 -->
          <div v-if="agent.todos && agent.todos.length > 0" class="agent-stats">
            <div class="stat-item">
              <el-icon><List /></el-icon>
              <span>{{ agent.todos.length }} 个任务</span>
            </div>
            <div class="stat-item">
              <el-icon><CircleCheck /></el-icon>
              <span>{{ getCompletedTodos(agent.todos) }} 已完成</span>
            </div>
          </div>

          <!-- 时间信息 -->
          <div class="agent-time">
            <el-text size="small" type="info">
              <el-icon><Clock /></el-icon>
              {{ formatTime(agent.createdAt) }}
            </el-text>
          </div>

          <!-- 点击提示 -->
          <div class="click-hint">
            <el-text size="small" type="primary">
              <el-icon><ArrowRight /></el-icon>
              点击查看任务图
            </el-text>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PropType } from 'vue'
import type { ParallelTaskInfo } from '@/types/parallelTasks'
import { ElIcon, ElTag, ElEmpty, ElText, ElProgress } from 'element-plus'
import {
  CircleCheck,
  List,
  Monitor,
  Clock,
  ArrowRight
} from '@element-plus/icons-vue'

const props = defineProps({
  agents: {
    type: Array as PropType<ParallelTaskInfo[]>,
    default: () => []
  }
})

const emit = defineEmits<{
  'select-agent': [agentId: string]
}>()

// const monitoringStore = useMonitoringStore()

// 过滤掉已完成的任务
const filteredAgents = computed(() => {
  return props.agents.filter(agent => agent.state !== 'completed')
})

// 获取状态类型
function getStatusType(state: string) {
  const typeMap: Record<string, unknown> = {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    pending: 'info'
  }
  return typeMap[state] || 'info'
}

// 获取状态文本
function getStatusText(state: string) {
  const textMap: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    pending: '等待中'
  }
  return textMap[state] || state
}

// 获取进度颜色
function getProgressColor(state: string) {
  const colorMap: Record<string, string> = {
    running: '#667eea',
    completed: '#10b981',
    failed: '#ef4444',
    pending: '#94a3b8'
  }
  return colorMap[state] || '#667eea'
}

// 获取已完成TODO数量
function getCompletedTodos(todos: unknown[]) {
  return todos.filter(t => t.status === 'completed').length
}

// 格式化时间
function formatTime(timestamp?: string) {
  if (!timestamp) return '刚刚'
  const date = new Date(timestamp)
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return date.toLocaleDateString()
}

// 处理Agent点击
function handleAgentClick(agent: ParallelTaskInfo) {
  emit('select-agent', agent.taskId)
}
</script>

<style scoped>
.agents-overview-panel {
  padding: var(--modern-spacing-lg);
  background: linear-gradient(135deg, var(--modern-bg-surface) 0%, rgba(249, 250, 251, 0.5) 100%);
  border-radius: var(--modern-radius-lg);
  border: 1px solid var(--modern-border-light);
  box-shadow: var(--modern-shadow-sm);
}

/* Agents列表 */
.agents-section {
  margin-top: var(--modern-spacing-lg);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--modern-spacing-md);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  font-size: var(--modern-font-lg);
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.empty-state {
  padding: var(--modern-spacing-xl) 0;
  text-align: center;
}

.agents-list {
  display: flex;
  flex-direction: column;
  gap: var(--modern-spacing-md);
}

/* Agent卡片 */
.agent-card {
  background: var(--modern-bg-surface);
  border: 1px solid var(--modern-border-light);
  border-radius: var(--modern-radius-md);
  padding: var(--modern-spacing-md);
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.agent-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--modern-border-medium);
  transition: background 0.3s ease;
}

.agent-card:hover {
  border-color: var(--modern-color-primary);
  box-shadow: var(--modern-shadow-md);
  transform: translateY(-2px);
}

.agent-card:hover::before {
  background: linear-gradient(180deg, var(--modern-color-primary) 0%, #764ba2 100%);
}

.agent-card--running {
  border-left-color: #3b82f6;
}

.agent-card--completed {
  border-left-color: #10b981;
}

.agent-card--failed {
  border-left-color: #ef4444;
}

/* Agent头部 */
.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--modern-spacing-md);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-md);
}

.agent-avatar {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: var(--modern-radius-sm);
  font-size: 20px;
  flex-shrink: 0;
}

.agent-details {
  flex: 1;
}

.agent-name {
  font-size: var(--modern-font-md);
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 2px;
}

.agent-id {
  font-size: var(--modern-font-xs);
  color: #64748b;
  font-family: 'JetBrains Mono', monospace;
}

/* Agent进度 */
.agent-progress {
  margin: var(--modern-spacing-md) 0;
}

.progress-text {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  font-size: var(--modern-font-sm);
}

.progress-percent {
  font-weight: 600;
  color: var(--modern-color-primary);
}

.progress-message {
  color: #64748b;
}

/* Agent统计 */
.agent-stats {
  display: flex;
  gap: var(--modern-spacing-md);
  margin-top: var(--modern-spacing-md);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--modern-font-sm);
  color: #64748b;
}

/* 时间信息 */
.agent-time {
  margin-top: var(--modern-spacing-sm);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 点击提示 */
.click-hint {
  margin-top: var(--modern-spacing-sm);
  padding-top: var(--modern-spacing-sm);
  border-top: 1px solid var(--modern-border-light);
  text-align: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.agent-card:hover .click-hint {
  opacity: 1;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .stat-value {
    color: #e2e8f0;
  }

  .stat-label {
    color: #94a3b8;
  }

  .section-title {
    color: #e2e8f0;
  }

  .agent-name {
    color: #e2e8f0;
  }

  .agent-id {
    color: #94a3b8;
  }

  .progress-message {
    color: #94a3b8;
  }

  .stat-item {
    color: #94a3b8;
  }
}
</style>
