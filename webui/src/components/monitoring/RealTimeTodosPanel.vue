<!--
实时TODO列表面板
显示agent正在执行的详细TODO列表，实时更新
-->

<template>
  <div class="realtime-todos-panel">
    <!-- Agent头部信息 -->
    <div class="agent-header">
      <div class="agent-avatar">
        <span class="agent-icon">{{ getModeIcon(agentMode) }}</span>
      </div>
      <div class="agent-details">
        <div class="agent-name">{{ agentName }}</div>
        <div class="agent-meta">
          <el-tag :type="getStatusType(agentState)" size="small">
            {{ getStatusText(agentState) }}
          </el-tag>
          <span class="todo-stats">
            <el-icon><List /></el-icon>
            {{ completedCount }}/{{ totalCount }} TODOs
          </span>
        </div>
      </div>
      <div class="progress-ring">
        <svg class="progress-ring__circle" width="60" height="60">
          <circle
            class="progress-ring__circle-bg"
            stroke-width="4"
            fill="transparent"
            r="26"
            cx="30"
            cy="30"
          />
          <circle
            class="progress-ring__circle-bar"
            stroke-width="4"
            fill="transparent"
            r="26"
            cx="30"
            cy="30"
            :stroke-dasharray="circumference"
            :stroke-dashoffset="progressOffset"
          />
        </svg>
        <div class="progress-text">{{ Math.round(progressPercentage) }}%</div>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="overall-progress">
      <el-progress
        :percentage="progressPercentage"
        :stroke-width="8"
        :show-text="false"
        :color="progressColor"
      />
    </div>

    <!-- TODO列表 -->
    <div class="todos-container">
      <div class="todos-header">
        <h4 class="todos-title">
          <el-icon><Grid /></el-icon>
          执行步骤
        </h4>
        <el-tag size="small" type="info">{{ todos.length }} 项</el-tag>
      </div>

      <div v-if="todos.length === 0" class="todos-empty">
        <el-empty description="等待任务开始..." :image-size="80">
          <el-text type="info">TODO列表将在任务执行时实时更新</el-text>
        </el-empty>
      </div>

      <div v-else class="todos-list">
        <TransitionGroup name="todo-slide">
          <div
            v-for="(todo, index) in todos"
            :key="todo.id || index"
            class="todo-item"
            :class="[
              `todo-${todo.status || 'pending'}`,
              { 'is-active': (todo.status || 'pending') === 'in_progress' }
            ]"
          >
            <!-- TODO序号和图标 -->
            <div class="todo-indicator">
              <span class="todo-number">{{ index + 1 }}</span>
              <div class="todo-status-icon">
                <el-icon v-if="(todo.status || 'pending') === 'completed'">
                  <CircleCheck />
                </el-icon>
                <el-icon v-else-if="(todo.status || 'pending') === 'in_progress'" class="is-spinning">
                  <Loading />
                </el-icon>
                <el-icon v-else>
                  <Clock />
                </el-icon>
              </div>
            </div>

            <!-- TODO内容 -->
            <div class="todo-content-wrapper">
              <div class="todo-text">
                <span class="todo-content-text">{{ todo.content }}</span>
              </div>

              <!-- TODO结果（如果有） -->
              <div v-if="todo.result" class="todo-result">
                <div class="result-header">
                  <el-icon><DocumentChecked /></el-icon>
                  <span>执行结果</span>
                </div>
                <div class="result-content">{{ todo.result }}</div>
              </div>

              <!-- TODO错误（如果有） -->
              <div v-if="todo.error" class="todo-error">
                <div class="error-header">
                  <el-icon><Warning /></el-icon>
                  <span>错误信息</span>
                </div>
                <div class="error-content">{{ todo.error }}</div>
              </div>
            </div>

            <!-- TODO状态标签 -->
            <div class="todo-status-tag">
              <el-tag :type="getTodoStatusType(todo.status)" size="small">
                {{ getTodoStatusText(todo.status) }}
              </el-tag>
            </div>
          </div>
        </TransitionGroup>
      </div>
    </div>

    <!-- 实时输出（如果有） -->
    <div v-if="outputs.length > 0" class="outputs-section">
      <div class="section-header">
        <h4 class="section-title">
          <el-icon><ChatLineRound /></el-icon>
          实时输出
        </h4>
        <el-button text size="small" @click="clearOutputs">
          清空
        </el-button>
      </div>
      <div class="outputs-content">
        <div v-for="(output, index) in lastNOutputs(10)" :key="index" class="output-line">
          {{ output }}
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
import { computed } from 'vue'
import type { PropType } from 'vue'
import { ElIcon, ElTag, ElEmpty, ElText, ElProgress, ElButton } from 'element-plus'
import {
  List,
  Grid,
  CircleCheck,
  Clock,
  Loading,
  DocumentChecked,
  Warning,
  ChatLineRound
} from '@element-plus/icons-vue'

interface TodoItem {
  id?: string
  content: string
  status?: string
  result?: string
  error?: string
}

const props = defineProps({
  agentId: {
    type: String,
    required: true
  },
  agentName: {
    type: String,
    default: '未命名 Agent'
  },
  agentMode: {
    type: String,
    default: 'orchestrator'
  },
  agentState: {
    type: String,
    default: 'running'
  },
  todos: {
    type: Array as PropType<TodoItem[]>,
    default: () => []
  },
  outputs: {
    type: Array as PropType<string[]>,
    default: () => []
  }
})

const emit = defineEmits<{
  'clear-outputs': []
}>()

// Mode图标映射
function getModeIcon(mode: string) {
  const iconMap: Record<string, string> = {
    orchestrator: '🪃',
    architect: '🏗️',
    code: '💻',
    ask: '❓',
    debug: '🪲',
    'patent-engineer': '💡'
  }
  return iconMap[mode] || '🤖'
}

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

// 获取TODO状态类型
function getTodoStatusType(status?: string) {
  if (!status) return 'info'
  const typeMap: Record<string, unknown> = {
    completed: 'success',
    in_progress: 'primary',
    pending: 'info',
    failed: 'danger'
  }
  return typeMap[status] || 'info'
}

// 获取TODO状态文本
function getTodoStatusText(status?: string) {
  if (!status) return '待执行'
  const textMap: Record<string, string> = {
    completed: '已完成',
    in_progress: '进行中',
    pending: '待执行',
    failed: '失败'
  }
  return textMap[status] || status
}

// 计算总数
const totalCount = computed(() => props.todos.length)

// 计算已完成数
const completedCount = computed(() => {
  return props.todos.filter(t => (t.status || 'pending') === 'completed').length
})

// 计算进度百分比
const progressPercentage = computed(() => {
  if (totalCount.value === 0) return 0
  return (completedCount.value / totalCount.value) * 100
})

// 进度环
const circumference = 2 * Math.PI * 26
const progressOffset = computed(() => {
  return circumference - (progressPercentage.value / 100) * circumference
})

// 进度颜色
const progressColor = computed(() => {
  if (props.agentState === 'failed') return '#ef4444'
  if (props.agentState === 'completed') return '#10b981'
  return '#667eea'
})

// 取最后N条输出
function lastNOutputs(n: number) {
  return props.outputs.slice(-n)
}

// 清空输出
function clearOutputs() {
  emit('clear-outputs')
}
</script>

<style scoped>
.realtime-todos-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  min-height: 400px;
  border: 1px solid var(--el-border-color-light);
}

/* Agent头部 */
.agent-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  color: var(--el-text-color-primary);
  border: 1px solid var(--el-border-color-light);
}

.agent-avatar {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  flex-shrink: 0;
}

.agent-icon {
  font-size: 24px;
}

.agent-details {
  flex: 1;
  min-width: 0;
}

.agent-name {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: rgba(255, 255, 255, 0.9);
}

.todo-stats {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
}

/* 进度环 */
.progress-ring {
  position: relative;
  flex-shrink: 0;
}

.progress-ring__circle {
  transform: rotate(-90deg);
}

.progress-ring__circle-bg {
  stroke: rgba(255, 255, 255, 0.2);
}

.progress-ring__circle-bar {
  stroke: white;
  transition: stroke-dashoffset 0.5s ease;
  stroke-linecap: round;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 14px;
  font-weight: 700;
  color: white;
}

/* 总进度条 */
.overall-progress {
  padding: 0 4px;
}

/* TODO容器 */
.todos-container {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid #e4e7ed;
}

.todos-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #f1f5f9;
}

.todos-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.todos-empty {
  padding: 40px 20px;
  text-align: center;
}

.todos-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* TODO项 */
.todo-item {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
  border: 2px solid #e4e7ed;
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
  width: 4px;
  background: #94a3b8;
  transition: background 0.3s ease;
}

.todo-item:hover {
  border-color: #667eea;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.1);
}

.todo-item.is-active {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.todo-item.is-active::before {
  background: #3b82f6;
}

.todo-item.todo-completed {
  background: #f0fdf4;
  border-color: #86efac;
}

.todo-item.todo-completed::before {
  background: #10b981;
}

.todo-item.todo-completed .todo-content-text {
  text-decoration: line-through;
  color: #86b6a2;
}

.todo-item.todo-failed {
  background: #fef2f2;
  border-color: #fca5a5;
}

.todo-item.todo-failed::before {
  background: #ef4444;
}

.todo-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.todo-number {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.todo-status-icon {
  font-size: 20px;
  color: #64748b;
}

.todo-item.is-active .todo-status-icon {
  color: #3b82f6;
}

.todo-item.todo-completed .todo-status-icon {
  color: #10b981;
}

.todo-item.todo-failed .todo-status-icon {
  color: #ef4444;
}

.todo-content-wrapper {
  flex: 1;
  min-width: 0;
}

.todo-text {
  margin-bottom: 8px;
}

.todo-content-text {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  line-height: 1.6;
}

.todo-result,
.todo-error {
  margin-top: 8px;
  padding: 10px;
  border-radius: 6px;
  font-size: 13px;
}

.todo-result {
  background: #f0fdf4;
  border: 1px solid #86efac;
}

.todo-result .result-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  color: #16a34a;
  margin-bottom: 6px;
}

.todo-result .result-content {
  color: #15803d;
  line-height: 1.5;
}

.todo-error {
  background: #fef2f2;
  border: 1px solid #fca5a5;
}

.todo-error .error-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 6px;
}

.todo-error .error-content {
  color: #b91c1c;
  line-height: 1.5;
}

.todo-status-tag {
  flex-shrink: 0;
  align-self: flex-start;
}

/* 旋转动画 */
.is-spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* TODO项滑入动画 */
.todo-slide-enter-active {
  transition: all 0.3s ease;
}

.todo-slide-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

/* 实时输出 */
.outputs-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid #e4e7ed;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f1f5f9;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.outputs-content {
  background: #1e293b;
  border-radius: 8px;
  padding: 12px;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.output-line {
  color: #94a3b8;
  margin-bottom: 4px;
  word-break: break-all;
}

.output-line:last-child {
  margin-bottom: 0;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .todos-container,
  .outputs-section {
    background: var(--el-bg-color);
    border-color: var(--el-border-color);
  }

  .todos-title,
  .section-title {
    color: var(--el-text-color-primary);
  }

  .todo-item {
    background: #334155;
    border-color: #475569;
  }

  .todo-content-text {
    color: #e2e8f0;
  }

  .todo-item.todo-completed .todo-content-text {
    color: #86b6a2;
  }
}
</style>
