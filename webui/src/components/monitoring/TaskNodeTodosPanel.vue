/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-node-todos-panel">
    <!-- 节点信息头部 -->
    <div class="node-header-card">
      <div class="node-avatar">
        <el-icon><Grid /></el-icon>
      </div>
      <div class="node-info-content">
        <div class="node-title">{{ nodeDescription }}</div>
        <div class="node-meta">
          <el-tag :type="getNodeType(nodeState)" size="small">
            {{ getNodeStatusText(nodeState) }}
          </el-tag>
          <el-divider direction="vertical" />
          <el-text type="info">
            <el-icon><Document /></el-icon>
            {{ todos.length }} 个 TODO
          </el-text>
          <el-divider direction="vertical" />
          <el-text type="success">
            <el-icon><CircleCheck /></el-icon>
            {{ completedCount }} 已完成
          </el-text>
        </div>
      </div>
    </div>

    <!-- 进度概览 -->
    <div class="progress-overview">
      <div class="progress-bar-large">
        <el-progress
          :percentage="completionRate"
          :stroke-width="12"
          :color="getProgressColor()"
        />
      </div>
      <div class="progress-stats">
        <div class="stat-item">
          <span class="stat-label">待处理</span>
          <span class="stat-value pending">{{ pendingCount }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">进行中</span>
          <span class="stat-value in-progress">{{ inProgressCount }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">已完成</span>
          <span class="stat-value completed">{{ completedCount }}</span>
        </div>
      </div>
    </div>

    <!-- 过滤和排序 -->
    <div class="toolbar">
      <div class="filter-group">
        <el-radio-group v-model="filterStatus" size="small">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="pending">待处理</el-radio-button>
          <el-radio-button label="in_progress">进行中</el-radio-button>
          <el-radio-button label="completed">已完成</el-radio-button>
        </el-radio-group>
      </div>

      <div class="sort-group">
        <el-select v-model="sortBy" size="small" placeholder="排序方式" style="width: 120px">
          <el-option label="创建时间" value="created_at" />
          <el-option label="状态" value="status" />
          <el-option label="优先级" value="priority" />
        </el-select>
      </div>
    </div>

    <!-- TODO列表 -->
    <div class="todos-list-section">
      <div v-if="filteredTodos.length === 0" class="empty-state">
        <el-empty :description="emptyStateText">
          <el-text type="info">该状态下暂无 TODO 项</el-text>
        </el-empty>
      </div>

      <div v-else class="todos-list">
        <transition-group name="todo-item">
          <div
            v-for="todo in filteredTodos"
            :key="todo.id"
            class="todo-item"
            :class="`todo-item--${todo.status}`"
          >
            <!-- TODO复选框 -->
            <div class="todo-checkbox">
              <el-checkbox
                :model-value="todo.status === 'completed'"
                @change="handleTodoStatusChange(todo, $event)"
                :disabled="todo.status === 'in_progress'"
              />
            </div>

            <!-- TODO内容 -->
            <div class="todo-content">
              <div class="todo-text" :class="{ 'todo-text--completed': todo.status === 'completed' }">
                {{ todo.content }}
              </div>

              <!-- TODO元数据 -->
              <div v-if="todo.metadata" class="todo-metadata">
                <el-tag
                  v-for="(value, key) in displayMetadata(todo.metadata)"
                  :key="key"
                  size="small"
                  type="info"
                  class="metadata-tag"
                >
                  {{ key }}: {{ value }}
                </el-tag>
              </div>

              <!-- TODO结果 -->
              <div v-if="todo.result" class="todo-result">
                <el-text size="small" type="success">
                  <el-icon><CircleCheck /></el-icon>
                  执行成功
                </el-text>
                <el-collapse class="result-collapse">
                  <el-collapse-item title="查看结果" name="result">
                    <pre class="result-content">{{ todo.result }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>

              <!-- TODO错误 -->
              <div v-if="todo.error" class="todo-error">
                <el-text size="small" type="danger">
                  <el-icon><CircleClose /></el-icon>
                  执行失败
                </el-text>
                <el-alert
                  :title="todo.error"
                  type="error"
                  :closable="false"
                  show-icon
                  class="error-alert"
                />
              </div>

              <!-- 时间信息 -->
              <div class="todo-time">
                <el-text size="small" type="info">
                  <el-icon><Clock /></el-icon>
                  创建于 {{ formatTime(todo.created_at) }}
                  <span v-if="todo.updated_at !== todo.created_at">
                    · 更新于 {{ formatTime(todo.updated_at) }}
                  </span>
                  <span v-if="todo.completed_at">
                    · 完成于 {{ formatTime(todo.completed_at) }}
                  </span>
                </el-text>
              </div>
            </div>

            <!-- TODO操作 -->
            <div class="todo-actions">
              <el-dropdown trigger="click">
                <el-button size="small" text circle>
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-if="todo.status === 'pending'"
                      @click="handleTodoAction(todo, 'start')"
                      :icon="VideoPlay"
                    >
                      开始执行
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="todo.status === 'in_progress'"
                      @click="handleTodoAction(todo, 'complete')"
                      :icon="CircleCheck"
                    >
                      标记完成
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="todo.status !== 'pending'"
                      @click="handleTodoAction(todo, 'reset')"
                      :icon="RefreshLeft"
                    >
                      重置状态
                    </el-dropdown-item>
                    <el-dropdown-item
                      divided
                      @click="handleTodoAction(todo, 'delete')"
                      :icon="Delete"
                      type="danger"
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </transition-group>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PropType } from 'vue'
import type { TodoItemDetail } from '@/types/todos'
import { ElIcon, ElTag, ElText, ElProgress, ElRadioGroup, ElRadioButton, ElSelect, ElOption, ElCheckbox, ElButton, ElDropdown, ElDropdownMenu, ElDropdownItem, ElEmpty, ElCollapse, ElCollapseItem, ElAlert, ElDivider } from 'element-plus'
import {
  Grid,
  Document,
  CircleCheck,
  Clock,
  VideoPlay,
  RefreshLeft,
  Delete,
  MoreFilled,
  CircleClose
} from '@element-plus/icons-vue'

const props = defineProps({
  nodeId: {
    type: String,
    required: true
  },
  nodeDescription: {
    type: String,
    default: '未命名节点'
  },
  nodeState: {
    type: String,
    default: 'running'
  },
  todos: {
    type: Array as PropType<TodoItemDetail[]>,
    default: () => []
  }
})

const emit = defineEmits<{
  'todo-status-change': [todoId: string, status: string]
  'todo-action': [todo: TodoItemDetail, action: string]
  'go-back': []
}>()

// 过滤状态
const filterStatus = ref<string>('all')

// 排序方式
const sortBy = ref<string>('created_at')

// 计算属性
const completedCount = computed(() =>
  props.todos.filter(t => t.status === 'completed').length
)

const pendingCount = computed(() =>
  props.todos.filter(t => t.status === 'pending').length
)

const inProgressCount = computed(() =>
  props.todos.filter(t => t.status === 'in_progress').length
)

const completionRate = computed(() => {
  if (props.todos.length === 0) return 0
  return Math.round((completedCount.value / props.todos.length) * 100)
})

// 过滤后的TODO列表
const filteredTodos = computed(() => {
  let todos = [...props.todos]

  // 应用状态过滤
  if (filterStatus.value !== 'all') {
    todos = todos.filter(t => t.status === filterStatus.value)
  }

  // 应用排序
  todos.sort((a, b) => {
    switch (sortBy.value) {
      case 'created_at':
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      case 'status':
        const statusOrder = { pending: 1, in_progress: 2, completed: 3 }
        return statusOrder[a.status] - statusOrder[b.status]
      case 'priority':
        const priorityOrder = { high: 3, medium: 2, low: 1 }
        return priorityOrder[b.priority] - priorityOrder[a.priority]
      default:
        return 0
    }
  })

  return todos
})

// 空状态文本
const emptyStateText = computed(() => {
  const textMap: Record<string, string> = {
    all: '暂无 TODO',
    pending: '暂无待处理的 TODO',
    in_progress: '暂无进行中的 TODO',
    completed: '暂无已完成的 TODO'
  }
  return textMap[filterStatus.value] || '暂无 TODO'
})

// 获取节点类型
function getNodeType(state: string) {
  const typeMap: Record<string, unknown> = {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    pending: 'info'
  }
  return typeMap[state] || 'info'
}

// 获取节点状态文本
function getNodeStatusText(state: string) {
  const textMap: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    pending: '等待中'
  }
  return textMap[state] || state
}

// 获取进度颜色
function getProgressColor() {
  const rate = completionRate.value
  if (rate < 30) return '#ef4444'
  if (rate < 70) return '#f59e0b'
  return '#10b981'
}

// 显示元数据
function displayMetadata(metadata: unknown) {
  const display: Record<string, string> = {}
  const keysToShow = ['tool', 'file', 'priority', 'assigned_to']

  for (const key of keysToShow) {
    if (metadata[key] !== undefined) {
      display[key] = metadata[key]
    }
  }

  return display
}

// 格式化时间
function formatTime(timestamp: string) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return date.toLocaleDateString()
}

// 处理TODO状态变更
function handleTodoStatusChange(todo: TodoItemDetail, checked: boolean) {
  const newStatus = checked ? 'completed' : 'pending'
  emit('todo-status-change', todo.id, newStatus)
}

// 处理TODO操作
function handleTodoAction(todo: TodoItemDetail, action: string) {
  emit('todo-action', todo, action)
}
</script>

<style scoped>
.task-node-todos-panel {
  padding: var(--modern-spacing-lg);
  background: linear-gradient(135deg, var(--modern-bg-surface) 0%, rgba(249, 250, 251, 0.5) 100%);
  border-radius: var(--modern-radius-lg);
  border: 1px solid var(--modern-border-light);
  box-shadow: var(--modern-shadow-sm);
}

/* 节点头部卡片 */
.node-header-card {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-lg);
  padding: var(--modern-spacing-lg);
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border-radius: var(--modern-radius-md);
  color: white;
  margin-bottom: var(--modern-spacing-lg);
  box-shadow: var(--modern-shadow-md);
}

.node-avatar {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--modern-radius-md);
  font-size: 28px;
  flex-shrink: 0;
  backdrop-filter: blur(10px);
}

.node-info-content {
  flex: 1;
}

.node-title {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 6px;
  color: white;
}

.node-meta {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  color: rgba(255, 255, 255, 0.9);
}

/* 进度概览 */
.progress-overview {
  margin-bottom: var(--modern-spacing-lg);
  padding: var(--modern-spacing-lg);
  background: var(--modern-bg-surface);
  border-radius: var(--modern-radius-md);
  border: 1px solid var(--modern-border-light);
}

.progress-bar-large {
  margin-bottom: var(--modern-spacing-md);
}

.progress-stats {
  display: flex;
  justify-content: space-around;
  gap: var(--modern-spacing-md);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--modern-spacing-xs);
}

.stat-label {
  font-size: var(--modern-font-sm);
  color: #64748b;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
}

.stat-value.pending {
  color: #94a3b8;
}

.stat-value.in-progress {
  color: #3b82f6;
}

.stat-value.completed {
  color: #10b981;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--modern-spacing-md);
  padding: var(--modern-spacing-md);
  background: var(--modern-bg-surface);
  border-radius: var(--modern-radius-md);
  border: 1px solid var(--modern-border-light);
}

/* TODO列表区域 */
.todos-list-section {
  margin-top: var(--modern-spacing-lg);
}

.empty-state {
  padding: var(--modern-spacing-xl) 0;
  text-align: center;
}

.todos-list {
  display: flex;
  flex-direction: column;
  gap: var(--modern-spacing-md);
}

/* TODO项 */
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: var(--modern-spacing-md);
  padding: var(--modern-spacing-md);
  background: var(--modern-bg-surface);
  border: 1px solid var(--modern-border-light);
  border-radius: var(--modern-radius-md);
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.todo-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--modern-border-medium);
}

.todo-item--pending::before {
  background: #94a3b8;
}

.todo-item--in_progress::before {
  background: #3b82f6;
}

.todo-item--completed::before {
  background: #10b981;
}

.todo-item:hover {
  box-shadow: var(--modern-shadow-sm);
  transform: translateX(2px);
}

.todo-checkbox {
  padding-top: 2px;
  flex-shrink: 0;
}

.todo-content {
  flex: 1;
  min-width: 0;
}

.todo-text {
  font-size: var(--modern-font-md);
  color: #1e293b;
  line-height: 1.6;
  margin-bottom: var(--modern-spacing-sm);
}

.todo-text--completed {
  text-decoration: line-through;
  color: #94a3b8;
}

.todo-metadata {
  display: flex;
  flex-wrap: wrap;
  gap: var(--modern-spacing-xs);
  margin-bottom: var(--modern-spacing-sm);
}

.metadata-tag {
  font-size: var(--modern-font-xs);
}

.todo-result {
  margin: var(--modern-spacing-sm) 0;
  padding: var(--modern-spacing-sm);
  background: var(--modern-color-success-light);
  border-radius: var(--modern-radius-sm);
}

.result-collapse {
  margin-top: var(--modern-spacing-sm);
}

.result-content {
  margin: 0;
  padding: var(--modern-spacing-sm);
  background: #1e293b;
  color: #e2e8f0;
  border-radius: var(--modern-radius-sm);
  font-size: var(--modern-font-sm);
  font-family: 'JetBrains Mono', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.todo-error {
  margin: var(--modern-spacing-sm) 0;
}

.error-alert {
  margin-top: var(--modern-spacing-sm);
}

.todo-time {
  margin-top: var(--modern-spacing-sm);
  display: flex;
  align-items: center;
  gap: 4px;
}

.todo-actions {
  flex-shrink: 0;
}

/* 动画 */
.todo-item-enter-active,
.todo-item-leave-active {
  transition: all 0.3s ease;
}

.todo-item-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.todo-item-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .node-title {
    color: white;
  }

  .stat-label {
    color: #94a3b8;
  }

  .todo-text {
    color: #e2e8f0;
  }

  .todo-text--completed {
    color: #64748b;
  }
}
</style>
