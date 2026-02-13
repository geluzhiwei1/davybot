/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-card">
    <!-- 任务头部 -->
    <div class="task-header">
      <div class="task-meta">
        <span class="task-mode">{{ task.nodeType }}</span>
        <span class="task-state">{{ getStateLabel(task.state) }}</span>
      </div>
      <div class="task-time">{{ getElapsedTime(task.createdAt) }}</div>
    </div>

    <!-- 任务描述 -->
    <div class="task-description">{{ task.description }}</div>

    <!-- 进度条 -->
    <div class="task-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: task.progress.percentage + '%' }"></div>
      </div>
      <span class="progress-text">{{ Math.round(task.progress.percentage) }}%</span>
    </div>

    <!-- 展开的详细信息 -->
    <div v-if="task.todos.length > 0" class="task-details">
      <div class="todos-list">
        <div
          v-for="todo in task.todos.slice(0, 5)"
          :key="todo.id"
          class="todo-item"
          :class="todo.status"
        >
          <span class="todo-status">{{ getTodoIcon(todo.status) }}</span>
          <span class="todo-content">{{ todo.content }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ParallelTaskState } from '@/types/parallelTasks'

defineProps<{
  task: unknown
}>()

function getStateLabel(state: ParallelTaskState): string {
  if (state === ParallelTaskState.RUNNING) return 'Running'
  if (state === ParallelTaskState.PENDING) return 'Starting'
  return state
}

function getTodoIcon(status: string): string {
  if (status === 'completed') return '✓'
  if (status === 'in_progress') return '→'
  if (status === 'pending') return '○'
  return '○'
}

function getElapsedTime(date: Date): string {
  const now = new Date()
  const diff = now.getTime() - new Date(date).getTime()
  const seconds = Math.floor(diff / 1000)

  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}
</script>

<style scoped>
.task-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.task-card:hover {
  border-color: #d1d5db;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

/* 任务头部 */
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.task-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}

.task-mode {
  font-size: 11px;
  font-weight: 600;
  color: #111827;
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.task-state {
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
  padding: 4px 8px;
  border-radius: 4px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.task-time {
  font-size: 12px;
  color: #9ca3af;
  font-family: 'IBM Plex Mono', monospace;
}

/* 任务描述 */
.task-description {
  font-size: 14px;
  color: #374151;
  margin-bottom: 12px;
  line-height: 1.5;
}

/* 进度条 */
.task-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-bar {
  flex: 1;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #2563eb;
  transition: width 0.3s ease;
  border-radius: 2px;
}

.progress-text {
  font-size: 12px;
  font-weight: 600;
  color: #111827;
  min-width: 40px;
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
}

/* 任务详情 */
.task-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

.todos-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  padding: 6px 0;
}

.todo-status {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.todo-item.completed .todo-status {
  color: #059669;
}

.todo-item.in_progress .todo-status {
  color: #2563eb;
}

.todo-item.pending .todo-status {
  color: #d1d5db;
}

.todo-content {
  flex: 1;
  color: #4b5563;
  line-height: 1.4;
}

.todo-item.completed .todo-content {
  color: #9ca3af;
  text-decoration: line-through;
}

.todo-item.in_progress .todo-content {
  color: #111827;
  font-weight: 500;
}

/* 响应式 */
@media (max-width: 768px) {
  .task-card {
    padding: 12px;
  }

  .task-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .task-time {
    align-self: flex-end;
  }
}
</style>
