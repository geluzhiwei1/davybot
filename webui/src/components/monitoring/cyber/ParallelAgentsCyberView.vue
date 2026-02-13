/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="parallel-agents-cyber">
    <!-- 任务网格 -->
    <div class="tasks-grid">
      <div
        v-for="task in allTasks"
        :key="task.taskId"
        class="cyber-task-card"
        :class="[
          `state-${task.state}`,
          `mode-${task.nodeType}`,
          { expanded: expandedTasks.has(task.taskId) }
        ]"
      >
        <!-- 全息边框 -->
        <div class="holo-border"></div>
        <div class="scan-line"></div>

        <!-- 任务头部 -->
        <div class="task-header">
          <div class="task-meta">
            <div class="task-mode" :class="`mode-${task.nodeType}`">
              <span class="mode-icon">{{ getModeIcon(task.nodeType) }}</span>
              <span class="mode-text">{{ task.nodeType.toUpperCase() }}</span>
            </div>
            <div class="task-state" :class="task.state">
              <span class="state-dot"></span>
              <span class="state-text">{{ getStateLabel(task.state) }}</span>
            </div>
          </div>

          <div class="task-actions">
            <button
              class="cyber-action-btn"
              @click="toggleExpand(task.taskId)"
              :title="expandedTasks.has(task.taskId) ? '收起' : '展开'"
            >
              <span :class="{ rotated: expandedTasks.has(task.taskId) }">▼</span>
            </button>
          </div>
        </div>

        <!-- 任务描述 -->
        <div class="task-description">
          {{ task.description }}
        </div>

        <!-- 进度条 -->
        <div class="task-progress">
          <div class="progress-track">
            <div
              class="progress-fill"
              :style="{
                width: task.progress.percentage + '%',
                background: `linear-gradient(90deg, ${getProgressColor(task.state)}, ${getProgressColor(task.state)}88)`
              }"
            >
              <div class="progress-glow"></div>
            </div>
          </div>
          <div class="progress-text">
            <span>{{ task.progress.current }}/{{ task.progress.total }}</span>
            <span>{{ task.progress.percentage.toFixed(0) }}%</span>
          </div>
        </div>

        <!-- 展开内容 -->
        <transition name="expand">
          <div v-if="expandedTasks.has(task.taskId)" class="task-details">
            <!-- TODO列表 -->
            <div class="detail-section" v-if="task.todos.length > 0">
              <h4 class="section-title">
                <span class="title-icon">◉</span>
                TASK SEQUENCE
              </h4>
              <div class="todos-grid">
                <div
                  v-for="todo in task.todos.slice(0, 6)"
                  :key="todo.id"
                  class="todo-item"
                  :class="todo.status"
                >
                  <div class="todo-indicator"></div>
                  <div class="todo-content">{{ todo.content }}</div>
                </div>
              </div>
            </div>

            <!-- 性能指标 -->
            <div class="detail-section metrics">
              <h4 class="section-title">
                <span class="title-icon">⚡</span>
                PERFORMANCE
              </h4>
              <div class="metrics-grid">
                <div class="metric-item">
                  <span class="metric-label">Duration</span>
                  <span class="metric-value">{{ formatDuration(task.metrics.duration) }}</span>
                </div>
                <div class="metric-item">
                  <span class="metric-label">Tool Calls</span>
                  <span class="metric-value">{{ task.metrics.toolCalls }}</span>
                </div>
                <div class="metric-item">
                  <span class="metric-label">LLM Calls</span>
                  <span class="metric-value">{{ task.metrics.llmCalls }}</span>
                </div>
              </div>
            </div>

            <!-- 实时输出 -->
            <div class="detail-section" v-if="task.outputs.length > 0">
              <h4 class="section-title">
                <span class="title-icon">⬢</span>
                OUTPUT STREAM
              </h4>
              <div class="output-console">
                <div
                  v-for="(line, idx) in task.outputs.slice(-5)"
                  :key="idx"
                  class="output-line"
                >
                  <span class="line-prefix">></span>
                  <span class="line-content">{{ line }}</span>
                </div>
              </div>
            </div>
          </div>
        </transition>

        <!-- 时间戳 -->
        <div class="task-footer">
          <div class="creation-time">
            <span class="time-icon">◷</span>
            <span>{{ formatTime(task.createdAt) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import { ParallelTaskState } from '@/types/parallelTasks'

const parallelTasks = useParallelTasksStore()

const expandedTasks = ref<Set<string>>(new Set())

const allTasks = computed(() => parallelTasks.allTasks)

function toggleExpand(taskId: string) {
  if (expandedTasks.value.has(taskId)) {
    expandedTasks.value.delete(taskId)
  } else {
    expandedTasks.value.add(taskId)
  }
}

function getModeIcon(mode: string): string {
  const icons = {
    orchestrator: '🪃',
    architect: '🏗️',
    code: '💻',
    ask: '❓',
    debug: '🪲',
    'patent-engineer': '💡'
  }
  return icons[mode as keyof typeof icons] || '🤖'
}

function getStateLabel(state: ParallelTaskState): string {
  const labels = {
    [ParallelTaskState.PENDING]: 'PENDING',
    [ParallelTaskState.RUNNING]: 'ACTIVE',
    [ParallelTaskState.PAUSED]: 'PAUSED',
    [ParallelTaskState.COMPLETED]: 'DONE',
    [ParallelTaskState.FAILED]: 'ERROR',
    [ParallelTaskState.CANCELLED]: 'STOPPED',
    [ParallelTaskState.SKIPPED]: 'SKIPPED'
  }
  return labels[state] || state.toUpperCase()
}

function getProgressColor(state: ParallelTaskState): string {
  const colors = {
    [ParallelTaskState.PENDING]: '#6b7280',
    [ParallelTaskState.RUNNING]: '#00f0ff',
    [ParallelTaskState.PAUSED]: '#ffeb3b',
    [ParallelTaskState.COMPLETED]: '#00ff9f',
    [ParallelTaskState.FAILED]: '#ff003c',
    [ParallelTaskState.CANCELLED]: '#ff9800',
    [ParallelTaskState.SKIPPED]: '#9c27b0'
  }
  return colors[state] || '#00f0ff'
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`
  } else if (seconds < 3600) {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}m ${secs}s`
  } else {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${mins}m`
  }
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date)
}
</script>

<style scoped>
.parallel-agents-cyber {
  width: 100%;
}

.tasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

/* ==================== 任务卡片 ==================== */
.cyber-task-card {
  position: relative;
  background: rgba(10, 14, 39, 0.6);
  border: 1px solid rgba(0, 240, 255, 0.2);
  border-radius: 8px;
  padding: 20px;
  overflow: hidden;
  transition: all 0.3s;
  backdrop-filter: blur(10px);
}

.cyber-task-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    135deg,
    rgba(0, 240, 255, 0.05) 0%,
    transparent 50%
  );
  pointer-events: none;
}

.cyber-task-card:hover {
  transform: translateY(-3px);
  box-shadow:
    0 8px 24px rgba(0, 240, 255, 0.2),
    0 0 20px rgba(0, 240, 255, 0.1);
}

.cyber-task-card.state-running {
  border-color: rgba(0, 240, 255, 0.5);
  animation: cardPulse 2s ease-in-out infinite;
}

@keyframes cardPulse {
  0%, 100% {
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
  }
  50% {
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.4);
  }
}

.cyber-task-card.state-completed {
  border-color: rgba(0, 255, 159, 0.5);
}

.cyber-task-card.state-failed {
  border-color: rgba(255, 0, 60, 0.5);
  animation: errorPulse 1s ease-in-out infinite;
}

@keyframes errorPulse {
  0%, 100% {
    box-shadow: 0 0 10px rgba(255, 0, 60, 0.2);
  }
  50% {
    box-shadow: 0 0 20px rgba(255, 0, 60, 0.4);
  }
}

/* 全息边框 */
.holo-border {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: 1px solid transparent;
  background: linear-gradient(
    90deg,
    rgba(0, 240, 255, 0.2),
    transparent,
    rgba(0, 240, 255, 0.2)
  );
  background-size: 200% 100%;
  animation: borderFlow 3s linear infinite;
  pointer-events: none;
}

@keyframes borderFlow {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 200% 50%;
  }
}

/* 扫描线 */
.scan-line {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(0, 240, 255, 0.6),
    transparent
  );
  animation: scanMove 2.5s ease-in-out infinite;
  pointer-events: none;
}

@keyframes scanMove {
  0%, 100% {
    top: 0;
    opacity: 0;
  }
  50% {
    opacity: 1;
  }
  100% {
    top: 100%;
  }
}

/* ==================== 任务头部 ==================== */
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.task-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.task-mode {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  background: rgba(0, 240, 255, 0.1);
  border: 1px solid rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}

.mode-icon {
  font-size: 12px;
}

.task-state {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.task-state.running {
  background: rgba(0, 240, 255, 0.1);
  border: 1px solid rgba(0, 240, 255, 0.3);
  color: #00f0ff;
}

.task-state.completed {
  background: rgba(0, 255, 159, 0.1);
  border: 1px solid rgba(0, 255, 159, 0.3);
  color: #00ff9f;
}

.task-state.failed {
  background: rgba(255, 0, 60, 0.1);
  border: 1px solid rgba(255, 0, 60, 0.3);
  color: #ff003c;
}

.task-state.pending {
  background: rgba(107, 114, 128, 0.1);
  border: 1px solid rgba(107, 114, 128, 0.3);
  color: #6b7280;
}

.state-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: dotPulse 1.5s ease-in-out infinite;
}

@keyframes dotPulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.2);
  }
}

.task-actions {
  display: flex;
  gap: 8px;
}

.cyber-action-btn {
  background: transparent;
  border: 1px solid rgba(0, 240, 255, 0.3);
  color: #00f0ff;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
  font-size: 10px;
}

.cyber-action-btn:hover {
  background: rgba(0, 240, 255, 0.1);
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
}

.cyber-action-btn span {
  transition: transform 0.3s;
  display: inline-block;
}

.cyber-action-btn span.rotated {
  transform: rotate(180deg);
}

/* ==================== 任务描述 ==================== */
.task-description {
  font-size: 14px;
  color: #e0e6ed;
  margin-bottom: 15px;
  line-height: 1.5;
  font-weight: 500;
}

/* ==================== 进度条 ==================== */
.task-progress {
  margin-bottom: 12px;
}

.progress-track {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 3px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
  position: relative;
}

.progress-glow {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.4),
    transparent
  );
  animation: shimmer 2s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.progress-text {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 11px;
  color: #9ca3af;
  font-family: 'Orbitron', monospace;
}

/* ==================== 展开内容 ==================== */
.task-details {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid rgba(0, 240, 255, 0.2);
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 1000px;
}

.detail-section {
  padding: 15px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 6px;
  border: 1px solid rgba(0, 240, 255, 0.1);
}

.section-title {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #00f0ff;
  letter-spacing: 2px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.title-icon {
  font-size: 14px;
}

/* TODO网格 */
.todos-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: rgba(0, 240, 255, 0.03);
  border-left: 2px solid #00f0ff;
  border-radius: 4px;
  font-size: 12px;
  color: #e0e6ed;
  transition: all 0.3s;
}

.todo-item:hover {
  background: rgba(0, 240, 255, 0.08);
  transform: translateX(3px);
}

.todo-item.completed {
  border-left-color: #00ff9f;
  opacity: 0.6;
}

.todo-item.running {
  border-left-color: #00f0ff;
  background: rgba(0, 240, 255, 0.1);
}

.todo-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.todo-item.completed .todo-indicator {
  background: #00ff9f;
}

.todo-item.running .todo-indicator {
  background: #00f0ff;
  animation: dotPulse 1.5s ease-in-out infinite;
}

.todo-content {
  flex: 1;
  line-height: 1.4;
}

/* 性能指标 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px;
  background: rgba(0, 240, 255, 0.03);
  border-radius: 4px;
  text-align: center;
}

.metric-label {
  font-size: 10px;
  color: #9ca3af;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.metric-value {
  font-size: 16px;
  font-weight: 700;
  color: #00f0ff;
  font-family: 'Orbitron', monospace;
}

/* 输出控制台 */
.output-console {
  background: rgba(0, 0, 0, 0.5);
  border-radius: 4px;
  padding: 12px;
  font-family: 'Orbitron', monospace;
  font-size: 11px;
  max-height: 120px;
  overflow-y: auto;
}

.output-line {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  color: #00ff9f;
}

.line-prefix {
  color: #00f0ff;
  opacity: 0.7;
}

.line-content {
  flex: 1;
  color: #e0e6ed;
  word-break: break-all;
}

/* ==================== 任务底部 ==================== */
.task-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 240, 255, 0.1);
}

.creation-time {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #6b7280;
  font-family: 'Orbitron', monospace;
}

.time-icon {
  font-size: 12px;
}

/* ==================== 响应式设计 ==================== */
@media (max-width: 1200px) {
  .tasks-grid {
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  }
}

@media (max-width: 768px) {
  .tasks-grid {
    grid-template-columns: 1fr;
  }

  .metrics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
