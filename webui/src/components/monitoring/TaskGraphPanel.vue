/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-graph-panel">
    <!-- Agent信息头部 -->
    <div class="agent-header-card">
      <div class="agent-avatar-large">
        <el-icon><Monitor /></el-icon>
      </div>
      <div class="agent-info-content">
        <div class="agent-name-title">{{ agentName }}</div>
        <div class="agent-meta">
          <el-tag :type="getStatusType(agentState)" size="small">
            {{ getStatusText(agentState) }}
          </el-tag>
          <el-divider direction="vertical" />
          <el-text type="info">
            <el-icon><Clock /></el-icon>
            {{ formatTime(createdAt) }}
          </el-text>
        </div>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="graph-stats">
      <div class="stat-item">
        <div class="stat-icon">
          <el-icon><List /></el-icon>
        </div>
        <div class="stat-details">
          <div class="stat-value">{{ taskNodeCount }}</div>
          <div class="stat-label">任务节点</div>
        </div>
      </div>

      <div class="stat-item">
        <div class="stat-icon">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-details">
          <div class="stat-value">{{ todoStats.completed }}</div>
          <div class="stat-label">已完成 TODO</div>
        </div>
      </div>

      <div class="stat-item">
        <div class="stat-icon">
          <el-icon><Loading /></el-icon>
        </div>
        <div class="stat-details">
          <div class="stat-value">{{ todoStats.inProgress }}</div>
          <div class="stat-label">进行中</div>
        </div>
      </div>

      <div class="stat-item">
        <div class="stat-icon">
          <el-icon><Document /></el-icon>
        </div>
        <div class="stat-details">
          <div class="stat-value">{{ todoStats.total }}</div>
          <div class="stat-label">总 TODO</div>
        </div>
      </div>
    </div>

    <!-- 任务节点列表 -->
    <div class="task-nodes-section">
      <div class="section-header">
        <h3 class="section-title">
          <el-icon><Operation /></el-icon>
          任务节点图
        </h3>
        <el-tag size="small" type="info">{{ taskNodeCount }} 个节点</el-tag>
      </div>

      <div v-if="taskNodeCount === 0" class="empty-state">
        <el-empty description="暂无任务节点">
          <el-text type="info">任务节点将在执行时显示</el-text>
        </el-empty>
      </div>

      <div v-else class="task-nodes-grid">
        <div
          v-for="[nodeId, node] in taskNodes"
          :key="nodeId"
          class="task-node-card"
          :class="`task-node-card--${node.state || 'pending'}`"
          @click="handleNodeClick(nodeId, node)"
        >
          <!-- 节点头部 -->
          <div class="node-header">
            <div class="node-icon">
              <el-icon><Grid /></el-icon>
            </div>
            <div class="node-info">
              <div class="node-name">{{ node.description || '未命名节点' }}</div>
              <div class="node-id">{{ nodeId.slice(0, 8) }}</div>
            </div>
            <div class="node-status">
              <el-tag :type="getNodeType(node.state)" size="small">
                {{ getNodeStatusText(node.state) }}
              </el-tag>
            </div>
          </div>

          <!-- 节点进度 -->
          <div v-if="node.progress !== undefined" class="node-progress">
            <el-progress
              :percentage="Math.round(node.progress * 100)"
              :stroke-width="6"
              :show-text="false"
              :color="getProgressColor(node.state)"
            />
            <div class="progress-text">
              <span class="progress-percent">{{ Math.round(node.progress * 100) }}%</span>
              <span class="progress-message">{{ node.message || '执行中...' }}</span>
            </div>
          </div>

          <!-- TODO统计 -->
          <div v-if="node.todos && node.todos.length > 0" class="node-todos-stats">
            <div class="todos-summary">
              <div class="todo-count">
                <el-text size="small" type="info">
                  <el-icon><List /></el-icon>
                  {{ node.todos.length }} 个 TODO
                </el-text>
              </div>
              <div class="todo-completed">
                <el-text size="small" type="success">
                  <el-icon><CircleCheck /></el-icon>
                  {{ getCompletedTodos(node.todos) }} 已完成
                </el-text>
              </div>
            </div>
            <div class="completion-bar">
              <div
                class="completion-fill"
                :style="{ width: `${getCompletionRate(node.todos)}%` }"
              ></div>
            </div>
          </div>

          <!-- 操作提示 -->
          <div class="node-action-hint">
            <el-text size="small" type="primary">
              <el-icon><View /></el-icon>
              点击查看 TODO 详情
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
import { ElIcon, ElTag, ElEmpty, ElText, ElProgress, ElDivider } from 'element-plus'
import {
  Monitor,
  Clock,
  List,
  CircleCheck,
  Loading,
  Document,
  Operation,
  Grid,
  View
} from '@element-plus/icons-vue'
import { logger } from '@/utils/logger'

interface TaskNodeData {
  description?: string
  state?: string
  progress?: number
  message?: string
  todos?: unknown[]
}

const props = defineProps({
  agentId: {
    type: String,
    required: true,
    // ✅ Fast Fail: 验证 agentId 不为空
    validator: (value: string) => {
      const isValid = value && value.trim() !== ''
      if (!isValid) {
        logger.error('[TaskGraphPanel] Invalid agentId:', value)
      }
      return isValid
    }
  },
  agentName: {
    type: String,
    default: '未命名 Agent'
  },
  agentState: {
    type: String,
    default: 'running',
    // ✅ Fast Fail: 验证 agentState 是有效状态
    validator: (value: string) => {
      const validStates = ['running', 'completed', 'failed', 'pending']
      const isValid = validStates.includes(value)
      if (!isValid) {
        logger.warn('[TaskGraphPanel] Invalid agentState:', value, 'Valid states:', validStates)
      }
      return isValid || value === ''  // Allow empty for default
    }
  },
  createdAt: {
    type: String,
    default: ''
  },
  taskNodes: {
    type: Map as PropType<Map<string, TaskNodeData>>,
    default: () => new Map(),
    // ✅ Fast Fail: 验证 taskNodes 是一个 Map
    validator: (value: Map<string, TaskNodeData>) => {
      const isValid = value instanceof Map
      if (!isValid) {
        logger.error('[TaskGraphPanel] taskNodes must be a Map, got:', typeof value)
      }
      return isValid
    }
  }
})

const emit = defineEmits<{
  'select-node': [nodeId: string, node: TaskNodeData]
  'go-back': []
}>()

// 任务节点数量
const taskNodeCount = computed(() => props.taskNodes.size)

// TODO统计
const todoStats = computed(() => {
  let total = 0
  let completed = 0
  let inProgress = 0

  for (const node of props.taskNodes.values()) {
    if (node.todos && node.todos.length > 0) {
      total += node.todos.length
      completed += node.todos.filter((t: unknown) => t.status === 'completed').length
      inProgress += node.todos.filter((t: unknown) => t.status === 'in_progress').length
    }
  }

  return { total, completed, inProgress }
})

/**
 * 统一的状态配置 - 遵循 DRY 原则
 * 所有状态相关的配置集中管理
 */
const STATUS_CONFIG = {
  running: { type: 'primary', text: '运行中', color: '#667eea' },
  completed: { type: 'success', text: '已完成', color: '#10b981' },
  failed: { type: 'danger', text: '失败', color: '#ef4444' },
  pending: { type: 'info', text: '等待中', color: '#94a3b8' }
} as const

type TaskStatus = keyof typeof STATUS_CONFIG
const DEFAULT_STATUS = 'pending'

/**
 * 获取状态配置的统一入口函数
 */
function getStatusConfig(state?: string) {
  if (!state) return STATUS_CONFIG[DEFAULT_STATUS]
  return STATUS_CONFIG[state as TaskStatus] || STATUS_CONFIG[DEFAULT_STATUS]
}

// 获取状态类型 (Element Plus tag type)
function getStatusType(state: string) {
  return getStatusConfig(state).type
}

// 获取状态文本
function getStatusText(state: string) {
  return getStatusConfig(state).text
}

// 获取节点类型 (别名)
function getNodeType(state?: string) {
  return getStatusConfig(state).type
}

// 获取节点状态文本 (别名)
function getNodeStatusText(state?: string) {
  return getStatusConfig(state).text
}

// 获取进度颜色
function getProgressColor(state?: string) {
  return getStatusConfig(state).color
}

// 获取已完成TODO数量
function getCompletedTodos(todos: unknown[]) {
  return todos.filter(t => t.status === 'completed').length
}

// 获取完成率
function getCompletionRate(todos: unknown[]) {
  if (!todos || todos.length === 0) return 0
  const completed = todos.filter(t => t.status === 'completed').length
  return Math.round((completed / todos.length) * 100)
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

// 处理节点点击
function handleNodeClick(nodeId: string, node: TaskNodeData) {
  emit('select-node', nodeId, node)
}
</script>

<style scoped>
.task-graph-panel {
  padding: var(--modern-spacing-lg);
  background: linear-gradient(135deg, var(--modern-bg-surface) 0%, rgba(249, 250, 251, 0.5) 100%);
  border-radius: var(--modern-radius-lg);
  border: 1px solid var(--modern-border-light);
  box-shadow: var(--modern-shadow-sm);
}

/* Agent头部卡片 */
.agent-header-card {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-lg);
  padding: var(--modern-spacing-lg);
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: var(--modern-radius-md);
  color: white;
  margin-bottom: var(--modern-spacing-lg);
  box-shadow: var(--modern-shadow-md);
}

.agent-avatar-large {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--modern-radius-md);
  font-size: 32px;
  flex-shrink: 0;
  backdrop-filter: blur(10px);
}

.agent-info-content {
  flex: 1;
}

.agent-name-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 6px;
  color: white;
}

.agent-meta {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  color: rgba(255, 255, 255, 0.9);
}

/* 统计概览 */
.graph-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--modern-spacing-md);
  margin-bottom: var(--modern-spacing-lg);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-md);
  padding: var(--modern-spacing-md);
  background: var(--modern-bg-surface);
  border-radius: var(--modern-radius-md);
  border: 1px solid var(--modern-border-light);
  transition: all 0.3s ease;
}

.stat-item:hover {
  border-color: var(--modern-color-primary-light);
  background: var(--modern-color-primary-light);
  transform: translateY(-2px);
}

.stat-icon {
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

.stat-details {
  flex: 1;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.stat-label {
  font-size: var(--modern-font-xs);
  color: #64748b;
  margin-top: 2px;
}

/* 任务节点区域 */
.task-nodes-section {
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

.task-nodes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--modern-spacing-md);
}

/* 任务节点卡片 */
.task-node-card {
  background: var(--modern-bg-surface);
  border: 1px solid var(--modern-border-light);
  border-radius: var(--modern-radius-md);
  padding: var(--modern-spacing-md);
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.task-node-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--modern-border-medium);
  transition: background 0.3s ease;
}

.task-node-card:hover {
  border-color: var(--modern-color-primary);
  box-shadow: var(--modern-shadow-md);
  transform: translateY(-2px);
}

.task-node-card:hover::before {
  background: linear-gradient(180deg, var(--modern-color-primary) 0%, #764ba2 100%);
}

.task-node-card--running::before {
  background: #3b82f6;
}

.task-node-card--completed::before {
  background: #10b981;
}

.task-node-card--failed::before {
  background: #ef4444;
}

/* 节点头部 */
.node-header {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  margin-bottom: var(--modern-spacing-md);
}

.node-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: var(--modern-radius-sm);
  font-size: 16px;
  flex-shrink: 0;
}

.node-info {
  flex: 1;
  min-width: 0;
}

.node-name {
  font-size: var(--modern-font-md);
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-id {
  font-size: var(--modern-font-xs);
  color: #64748b;
  font-family: 'JetBrains Mono', monospace;
}

/* 节点进度 */
.node-progress {
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* TODO统计 */
.node-todos-stats {
  margin-top: var(--modern-spacing-md);
  padding: var(--modern-spacing-sm);
  background: var(--modern-bg-subtle);
  border-radius: var(--modern-radius-sm);
}

.todos-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--modern-spacing-sm);
}

.completion-bar {
  height: 4px;
  background: var(--modern-border-medium);
  border-radius: 2px;
  overflow: hidden;
}

.completion-fill {
  height: 100%;
  background: linear-gradient(90deg, #10b981 0%, #059669 100%);
  transition: width 0.3s ease;
}

/* 操作提示 */
.node-action-hint {
  margin-top: var(--modern-spacing-sm);
  padding-top: var(--modern-spacing-sm);
  border-top: 1px solid var(--modern-border-light);
  text-align: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.task-node-card:hover .node-action-hint {
  opacity: 1;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .agent-name-title {
    color: white;
  }

  .stat-value {
    color: #e2e8f0;
  }

  .stat-label {
    color: #94a3b8;
  }

  .section-title {
    color: #e2e8f0;
  }

  .node-name {
    color: #e2e8f0;
  }

  .node-id {
    color: #94a3b8;
  }

  .progress-message {
    color: #94a3b8;
  }
}
</style>
