/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-card">
    <div class="task-header">
      <div class="task-meta">
        <span class="task-mode">{{ task.nodeType }}</span>
        <span class="task-status" :class="task.state">{{ getStateLabel(task.state) }}</span>
      </div>
      <button class="expand-button" @click="$emit('expand', task.taskId)">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
    </div>

    <div class="task-description">{{ task.description }}</div>

    <div class="task-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: task.progress.percentage + '%' }"></div>
      </div>
      <div class="progress-text">{{ task.progress.percentage.toFixed(0) }}%</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ParallelTaskState } from '@/types/parallelTasks'

defineProps<{
  task: unknown
}>()

defineEmits<{
  (e: 'expand', taskId: string): void
}>()

function getStateLabel(state: ParallelTaskState): string {
  const labels = {
    [ParallelTaskState.PENDING]: 'Pending',
    [ParallelTaskState.RUNNING]: 'Running',
    [ParallelTaskState.PAUSED]: 'Paused',
    [ParallelTaskState.COMPLETED]: 'Completed',
    [ParallelTaskState.FAILED]: 'Failed',
    [ParallelTaskState.CANCELLED]: 'Cancelled',
    [ParallelTaskState.SKIPPED]: 'Skipped'
  }
  return labels[state] || state
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
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.task-meta {
  display: flex;
  gap: 8px;
}

.task-mode {
  font-size: 11px;
  font-weight: 600;
  color: #374151;
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.task-status {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.task-status.running {
  background: #eff6ff;
  color: #2563eb;
}

.task-status.completed {
  background: #f0fdf4;
  color: #059669;
}

.task-status.failed {
  background: #fef2f2;
  color: #dc2626;
}

.task-status.pending {
  background: #f9fafb;
  color: #6b7280;
}

.expand-button {
  background: transparent;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s;
}

.expand-button:hover {
  background: #f3f4f6;
  color: #374151;
}

.task-description {
  font-size: 14px;
  color: #374151;
  margin-bottom: 12px;
  line-height: 1.5;
}

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
}

.task-status.completed .progress-fill {
  background: #059669;
}

.task-status.failed .progress-fill {
  background: #dc2626;
}

.progress-text {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  min-width: 40px;
  text-align: right;
  font-family: 'IBM Plex Mono', monospace;
}
</style>
