<!--
流线型监控面板 - 直接显示 Agent 状态，无需点击
设计理念：零认知负担，一目了然
-->

<template>
  <div class="streamlined-monitoring">
    <!-- Agent 切换器（仅在有多个agent时显示） -->
    <transition name="selector-slide">
      <div v-if="allAgents.length > 1" class="agent-switcher">
        <div class="switcher-track">
          <div
            v-for="agent in allAgents"
            :key="agent.taskId"
            class="agent-tab"
            :class="{ 'is-active': agent.taskId === selectedAgentId }"
            @click="selectAgent(agent.taskId)"
          >
            <div class="tab-icon">{{ getModeEmoji(agent.mode) }}</div>
            <div class="tab-info">
              <div class="tab-name">{{ agent.taskName || agent.description || 'Agent' }}</div>
              <div class="tab-status" :class="`status-${agent.state}`">
                <span class="status-dot"></span>
                {{ getStatusText(agent.state) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 主内容区 - 直接显示TODO列表 -->
    <div v-if="selectedAgent" class="main-content">
      <!-- Agent 头部卡片 -->
      <div class="agent-hero-card">
        <div class="hero-background">
          <div class="gradient-orb orb-1"></div>
          <div class="gradient-orb orb-2"></div>
          <div class="gradient-orb orb-3"></div>
        </div>

        <div class="hero-content">
          <div class="agent-avatar-large">
            <span class="avatar-emoji">{{ getModeEmoji(selectedAgent.mode) }}</span>
            <div class="avatar-glow"></div>
          </div>

          <div class="agent-details">
            <h2 class="agent-title">{{ selectedAgent.taskName || selectedAgent.description }}</h2>
            <div class="agent-badges">
              <span class="badge badge-mode">{{ selectedAgent.mode || 'orchestrator' }}</span>
              <span class="badge badge-state" :class="`state-${selectedAgent.state}`">
                {{ getStatusText(selectedAgent.state) }}
              </span>
            </div>
          </div>

          <div class="progress-display">
            <svg class="progress-ring" viewBox="0 0 120 120">
              <circle
                class="progress-ring-bg"
                cx="60"
                cy="60"
                r="54"
                fill="none"
                stroke-width="8"
              />
              <circle
                class="progress-ring-bar"
                cx="60"
                cy="60"
                r="54"
                fill="none"
                stroke-width="8"
                :stroke-dasharray="circumference"
                :stroke-dashoffset="progressOffset"
                stroke-linecap="round"
              />
            </svg>
            <div class="progress-text">
              <div class="progress-percent">{{ Math.round(progressPercent) }}%</div>
              <div class="progress-label">{{ completedCount }}/{{ totalCount }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- TODO 时间轴 -->
      <div class="timeline-container">
        <div class="timeline-header">
          <h3 class="timeline-title">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10 2L8 8H2L7 12L5 18L10 14L15 18L13 12L18 8H12L10 2Z"/>
            </svg>
            执行进度
          </h3>
          <div class="timeline-stats">
            <span class="stat-item">
              <span class="stat-icon">✓</span>
              {{ completedCount }} 完成
            </span>
            <span class="stat-item">
              <span class="stat-icon">⟳</span>
              {{ inProgressCount }} 进行中
            </span>
            <span class="stat-item">
              <span class="stat-icon">○</span>
              {{ pendingCount }} 待执行
            </span>
          </div>
        </div>

        <div v-if="todos.length === 0" class="timeline-empty">
          <div class="empty-animation">
            <div class="pulse-ring"></div>
            <div class="pulse-ring delay-1"></div>
            <div class="pulse-ring delay-2"></div>
          </div>
          <p class="empty-text">等待任务开始...</p>
        </div>

        <div v-else class="timeline">
          <transition-group name="timeline-item" tag="div" class="timeline-items">
            <div
              v-for="(todo, index) in todos"
              :key="todo.id || index"
              class="timeline-item"
              :class="[
                `item-${todo.status || 'pending'}`,
                { 'is-active': (todo.status || 'pending') === 'in_progress' }
              ]"
            >
              <!-- 时间轴连接线 -->
              <div class="timeline-connector"></div>

              <!-- 状态图标 -->
              <div class="timeline-icon">
                <div class="icon-background">
                  <transition name="icon-rotate" mode="out-in">
                    <span v-if="(todo.status || 'pending') === 'completed'" key="completed" class="icon-check">✓</span>
                    <span v-else-if="(todo.status || 'pending') === 'in_progress'" key="progress" class="icon-loading">
                      <svg class="spinner" viewBox="0 0 50 50">
                        <circle
                          cx="25"
                          cy="25"
                          r="20"
                          fill="none"
                          stroke-width="4"
                          stroke-dasharray="90 30"
                        />
                      </svg>
                    </span>
                    <span v-else key="pending" class="icon-pending">{{ index + 1 }}</span>
                  </transition>
                </div>
              </div>

              <!-- 内容卡片 -->
              <div class="timeline-content">
                <div class="content-card">
                  <div class="card-header">
                    <h4 class="card-title">{{ todo.content }}</h4>
                    <span class="card-badge" :class="`badge-${todo.status || 'pending'}`">
                      {{ getTodoStatusText(todo.status) }}
                    </span>
                  </div>

                  <!-- 执行结果 -->
                  <transition name="result-expand">
                    <div v-if="todo.result" class="card-result">
                      <div class="result-label">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M8 0L6 6H0L5 10L3 16L8 12L13 16L11 10L16 6H10L8 0Z"/>
                        </svg>
                        执行结果
                      </div>
                      <div class="result-text">{{ todo.result }}</div>
                    </div>
                  </transition>

                  <!-- 错误信息 -->
                  <transition name="error-expand">
                    <div v-if="todo.error" class="card-error">
                      <div class="error-label">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M8 0C3.58 0 0 3.58 0 8C0 12.42 3.58 16 8 16C12.42 16 16 12.42 16 8C16 3.58 12.42 0 8 0ZM9 13H7V11H9V13ZM9 9H7V3H9V9Z"/>
                        </svg>
                        错误
                      </div>
                      <div class="error-text">{{ todo.error }}</div>
                    </div>
                  </transition>
                </div>
              </div>
            </div>
          </transition-group>
        </div>
      </div>

      <!-- 实时输出（可选） -->
      <transition name="output-slide">
        <div v-if="outputs.length > 0" class="output-panel">
          <div class="output-header">
            <h4 class="output-title">实时输出</h4>
            <button class="output-clear" @click="clearOutputs">清空</button>
          </div>
          <div class="output-content">
            <div v-for="(line, idx) in lastNLines(15)" :key="idx" class="output-line">
              <span class="output-timestamp">{{ formatTimestamp(idx) }}</span>
              <span class="output-text">{{ line }}</span>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-illustration">
        <div class="orbit orbit-1">
          <div class="planet planet-1"></div>
        </div>
        <div class="orbit orbit-2">
          <div class="planet planet-2"></div>
        </div>
        <div class="orbit orbit-3">
          <div class="planet planet-3"></div>
        </div>
        <div class="star star-1"></div>
        <div class="star star-2"></div>
        <div class="star star-3"></div>
      </div>
      <h3 class="empty-title">暂无活跃任务</h3>
      <p class="empty-subtitle">开始一个任务，实时监控将自动显示</p>
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

// 监听 parallelTasksStore 的变化，同步到 monitoringStore
watch(
  () => parallelTasksStore.allTasks,
  (tasks) => {
    // 同步活跃任务到 monitoringStore
    const activeTasks = tasks.filter(
      task => task.state === 'running' || task.state === 'pending'
    )

    monitoringStore.updateAgents(activeTasks)

    // 自动选择逻辑：
    // 1. 如果当前没有选中的agent，选择第一个活跃任务
    // 2. 如果当前选中的agent已经不活跃，切换到新的活跃任务
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

// 所有 agents
const allAgents = computed(() => monitoringStore.allAgents)

// Auto-select first agent if none selected
watch(allAgents, (agents) => {
  if (!selectedAgentId.value && agents.length > 0) {
    selectedAgentId.value = agents[0].taskId
  }
}, { immediate: true })

// 选中的 agent
const selectedAgent = computed(() => {
  const agent = allAgents.value.find(a => a.taskId === selectedAgentId.value)
  if (!agent) return null

  const detailedTask = parallelTasksStore.allTasks.find(t => t.taskId === selectedAgentId.value)

  return {
    ...agent,
    todos: detailedTask?.todos || [],
    outputs: detailedTask?.outputs || []
  }
})

// Todos
const todos = computed(() => selectedAgent.value?.todos || [])
const outputs = computed(() => selectedAgent.value?.outputs || [])

// 统计
const totalCount = computed(() => todos.value.length)
const completedCount = computed(() => todos.value.filter(t => (t.status || 'pending') === 'completed').length)
const inProgressCount = computed(() => todos.value.filter(t => (t.status || 'pending') === 'in_progress').length)
const pendingCount = computed(() => todos.value.filter(t => (t.status || 'pending') === 'pending').length)
const progressPercent = computed(() => totalCount.value > 0 ? (completedCount.value / totalCount.value) * 100 : 0)

// 进度环
const circumference = 2 * Math.PI * 54
const progressOffset = computed(() => circumference - (progressPercent.value / 100) * circumference)

// 方法
function selectAgent(taskId: string) {
  selectedAgentId.value = taskId
}

function getModeEmoji(mode?: string) {
  const emojiMap: Record<string, string> = {
    orchestrator: '🎯',
    architect: '🏗️',
    code: '💻',
    ask: '❓',
    debug: '🐛',
    'patent-engineer': '💡'
  }
  return emojiMap[mode || ''] || '🤖'
}

function getStatusText(state?: string) {
  const textMap: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    pending: '待执行'
  }
  return textMap[state || ''] || state || '未知'
}

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

function lastNLines(n: number) {
  return outputs.value.slice(-n)
}

function formatTimestamp(index: number) {
  const now = new Date()
  const time = new Date(now.getTime() - (outputs.value.length - 1 - index) * 1000)
  return time.toLocaleTimeString('zh-CN', { hour12: false })
}

function clearOutputs() {
  if (!selectedAgentId.value) return
  const task = parallelTasksStore.getTask(selectedAgentId.value)
  if (task) {
    task.outputs = []
  }
}
</script>

<style scoped>
/* ===== 基础样式 ===== */
.streamlined-monitoring {
  position: fixed;
  top: 64px;
  right: 0;
  width: 680px;
  max-width: 85vw;
  height: calc(100vh - 64px);
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  overflow-y: auto;
  overflow-x: hidden;
  border-left: 2px solid rgba(148, 163, 184, 0.1);
  box-shadow: -4px 0 30px rgba(0, 0, 0, 0.5);
  z-index: 100;
}

/* ===== Agent 切换器 ===== */
.agent-switcher {
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.switcher-track {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 4px;
  scrollbar-width: none;
}

.switcher-track::-webkit-scrollbar {
  display: none;
}

.agent-tab {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px;
  background: rgba(30, 41, 59, 0.8);
  border: 2px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-width: 200px;
}

.agent-tab:hover {
  border-color: rgba(99, 102, 241, 0.5);
  background: rgba(30, 41, 59, 1);
  transform: translateY(-2px);
}

.agent-tab.is-active {
  border-color: #6366f1;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(139, 92, 246, 0.2) 100%);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
}

.tab-icon {
  font-size: 28px;
  line-height: 1;
}

.tab-info {
  flex: 1;
  min-width: 0;
}

.tab-name {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

.status-running .status-dot {
  color: #3b82f6;
}

.status-completed .status-dot {
  color: #10b981;
  animation: none;
}

.status-failed .status-dot {
  color: #ef4444;
  animation: none;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ===== 主内容区 ===== */
.main-content {
  padding: 24px;
}

/* ===== Agent 英雄卡片 ===== */
.agent-hero-card {
  position: relative;
  margin-bottom: 32px;
  padding: 40px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  border: 2px solid rgba(148, 163, 184, 0.1);
  border-radius: 24px;
  overflow: hidden;
}

.hero-background {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.gradient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
  animation: float 8s ease-in-out infinite;
}

.orb-1 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, #6366f1 0%, transparent 70%);
  top: -100px;
  right: -100px;
  animation-delay: 0s;
}

.orb-2 {
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, #8b5cf6 0%, transparent 70%);
  bottom: -50px;
  left: -50px;
  animation-delay: 2s;
}

.orb-3 {
  width: 150px;
  height: 150px;
  background: radial-gradient(circle, #ec4899 0%, transparent 70%);
  top: 50%;
  left: 50%;
  animation-delay: 4s;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
}

.hero-content {
  position: relative;
  display: flex;
  align-items: center;
  gap: 32px;
}

.agent-avatar-large {
  position: relative;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.8);
  border: 3px solid rgba(99, 102, 241, 0.5);
  border-radius: 24px;
  font-size: 64px;
  flex-shrink: 0;
}

.avatar-glow {
  position: absolute;
  inset: -10px;
  background: conic-gradient(from 0deg, #6366f1, #8b5cf6, #ec4899, #6366f1);
  border-radius: 30px;
  opacity: 0.3;
  filter: blur(20px);
  animation: rotate 8s linear infinite;
  z-index: -1;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.avatar-emoji {
  position: relative;
  z-index: 1;
  animation: bounce 2s ease-in-out infinite;
}

@keyframes bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.agent-details {
  flex: 1;
}

.agent-title {
  font-size: 32px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0 0 16px 0;
  background: linear-gradient(135deg, #f1f5f9 0%, #cbd5e1 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.agent-badges {
  display: flex;
  gap: 12px;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-mode {
  background: rgba(99, 102, 241, 0.2);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.badge-state {
  border: 1px solid;
}

.state-running {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
  border-color: rgba(59, 130, 246, 0.3);
}

.state-completed {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.3);
}

.state-failed {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.3);
}

.progress-display {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}

.progress-ring {
  transform: rotate(-90deg);
}

.progress-ring-bg {
  stroke: rgba(148, 163, 184, 0.2);
}

.progress-ring-bar {
  stroke: url(#progress-gradient);
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}

.progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.progress-percent {
  font-size: 28px;
  font-weight: 700;
  color: #f1f5f9;
  line-height: 1;
}

.progress-label {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 4px;
}

/* ===== 时间轴 ===== */
.timeline-container {
  background: rgba(15, 23, 42, 0.5);
  border: 2px solid rgba(148, 163, 184, 0.1);
  border-radius: 24px;
  padding: 32px;
  backdrop-filter: blur(20px);
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
  padding-bottom: 20px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.timeline-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0;
}

.timeline-stats {
  display: flex;
  gap: 20px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #94a3b8;
}

.stat-icon {
  font-size: 16px;
}

.timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-animation {
  position: relative;
  width: 120px;
  height: 120px;
  margin-bottom: 24px;
}

.pulse-ring {
  position: absolute;
  inset: 0;
  border: 2px solid #6366f1;
  border-radius: 50%;
  opacity: 0;
  animation: pulse-ring 2s ease-out infinite;
}

.pulse-ring.delay-1 {
  animation-delay: 0.5s;
}

.pulse-ring.delay-2 {
  animation-delay: 1s;
}

@keyframes pulse-ring {
  0% { transform: scale(0.8); opacity: 0.8; }
  100% { transform: scale(1.5); opacity: 0; }
}

.empty-text {
  font-size: 16px;
  color: #64748b;
}

.timeline {
  position: relative;
}

.timeline-items {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.timeline-item {
  display: flex;
  gap: 20px;
  position: relative;
}

.timeline-connector {
  position: absolute;
  left: 28px;
  top: 56px;
  bottom: -32px;
  width: 2px;
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.5) 0%, rgba(99, 102, 241, 0.1) 100%);
}

.timeline-item:last-child .timeline-connector {
  display: none;
}

.timeline-icon {
  flex-shrink: 0;
}

.icon-background {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.8);
  border: 2px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  position: relative;
  z-index: 1;
}

.timeline-item.is-active .icon-background {
  border-color: #6366f1;
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.5);
}

.timeline-item.item-completed .icon-background {
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

.icon-check {
  font-size: 24px;
  color: #10b981;
  font-weight: 700;
}

.icon-loading .spinner {
  width: 28px;
  height: 28px;
  animation: spin 1s linear infinite;
}

.icon-loading .spinner circle {
  stroke: #6366f1;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.icon-pending {
  font-size: 18px;
  font-weight: 700;
  color: #64748b;
}

.timeline-content {
  flex: 1;
  min-width: 0;
}

.content-card {
  background: rgba(30, 41, 59, 0.8);
  border: 2px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  padding: 20px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.timeline-item.is-active .content-card {
  border-color: rgba(99, 102, 241, 0.5);
  box-shadow: 0 0 30px rgba(99, 102, 241, 0.2);
}

.timeline-item.item-completed .content-card {
  border-color: rgba(16, 185, 129, 0.3);
  opacity: 0.7;
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.card-title {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  color: #f1f5f9;
  margin: 0;
  line-height: 1.5;
}

.card-badge {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-completed {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.badge-in_progress {
  background: rgba(99, 102, 241, 0.2);
  color: #818cf8;
}

.badge-pending {
  background: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
}

.badge-failed {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.card-result {
  margin-top: 16px;
  padding: 16px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 12px;
}

.result-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #34d399;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-text {
  font-size: 14px;
  color: #a7f3d0;
  line-height: 1.6;
}

.card-error {
  margin-top: 16px;
  padding: 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
}

.error-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #f87171;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.error-text {
  font-size: 14px;
  color: #fecaca;
  line-height: 1.6;
}

/* ===== 实时输出 ===== */
.output-panel {
  margin-top: 24px;
  background: rgba(15, 23, 42, 0.8);
  border: 2px solid rgba(148, 163, 184, 0.1);
  border-radius: 16px;
  overflow: hidden;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: rgba(30, 41, 59, 0.5);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.output-title {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
  margin: 0;
}

.output-clear {
  padding: 6px 16px;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.output-clear:hover {
  background: rgba(148, 163, 184, 0.2);
  border-color: rgba(148, 163, 184, 0.3);
}

.output-content {
  padding: 16px;
  max-height: 250px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.3);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.8;
}

.output-line {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  color: #94a3b8;
}

.output-timestamp {
  flex-shrink: 0;
  color: #64748b;
}

.output-text {
  flex: 1;
  word-break: break-all;
  color: #cbd5e1;
}

/* ===== 空状态 ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 120px 40px;
  text-align: center;
}

.empty-illustration {
  position: relative;
  width: 300px;
  height: 300px;
  margin-bottom: 40px;
}

.orbit {
  position: absolute;
  top: 50%;
  left: 50%;
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 50%;
  animation: orbit-rotate 20s linear infinite;
}

.orbit-1 {
  width: 200px;
  height: 200px;
  margin: -100px 0 0 -100px;
}

.orbit-2 {
  width: 140px;
  height: 140px;
  margin: -70px 0 0 -70px;
  animation-duration: 15s;
  animation-direction: reverse;
}

.orbit-3 {
  width: 80px;
  height: 80px;
  margin: -40px 0 0 -40px;
  animation-duration: 10s;
}

@keyframes orbit-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.planet {
  position: absolute;
  top: 0;
  left: 50%;
  width: 20px;
  height: 20px;
  margin-left: -10px;
  margin-top: -10px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.5);
}

.planet-2 {
  width: 14px;
  height: 14px;
  margin-left: -7px;
  margin-top: -7px;
  background: linear-gradient(135deg, #ec4899 0%, #f43f5e 100%);
  box-shadow: 0 0 15px rgba(236, 72, 153, 0.5);
}

.planet-3 {
  width: 10px;
  height: 10px;
  margin-left: -5px;
  margin-top: -5px;
  background: linear-gradient(135deg, #10b981 0%, #14b8a6 100%);
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
}

.star {
  position: absolute;
  background: #f1f5f9;
  border-radius: 50%;
  animation: twinkle 3s ease-in-out infinite;
}

.star-1 {
  width: 4px;
  height: 4px;
  top: 20%;
  left: 20%;
  animation-delay: 0s;
}

.star-2 {
  width: 3px;
  height: 3px;
  top: 60%;
  right: 25%;
  animation-delay: 1s;
}

.star-3 {
  width: 5px;
  height: 5px;
  bottom: 30%;
  left: 30%;
  animation-delay: 2s;
}

@keyframes twinkle {
  0%, 100% { opacity: 0.3; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.5); }
}

.empty-title {
  font-size: 24px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0 0 12px 0;
}

.empty-subtitle {
  font-size: 16px;
  color: #64748b;
  margin: 0;
}

/* ===== 动画 ===== */
.selector-slide-enter-active,
.selector-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.selector-slide-enter-from,
.selector-slide-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}

.timeline-item-enter-active {
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.timeline-item-enter-from {
  opacity: 0;
  transform: translateX(-30px);
}

.icon-rotate-enter-active,
.icon-rotate-leave-active {
  transition: all 0.3s ease;
}

.icon-rotate-enter-from,
.icon-rotate-leave-to {
  opacity: 0;
  transform: rotate(180deg) scale(0);
}

.result-expand-enter-active,
.result-expand-leave-active {
  transition: all 0.3s ease;
}

.result-expand-enter-from,
.result-expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}

.result-expand-enter-to,
.result-expand-leave-from {
  opacity: 1;
  max-height: 300px;
  margin-top: 16px;
}

.error-expand-enter-active,
.error-expand-leave-active {
  transition: all 0.3s ease;
}

.error-expand-enter-from,
.error-expand-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}

.error-expand-enter-to,
.error-expand-leave-from {
  opacity: 1;
  max-height: 300px;
  margin-top: 16px;
}

.output-slide-enter-active,
.output-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.output-slide-enter-from,
.output-slide-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}

.output-slide-enter-to,
.output-slide-leave-from {
  opacity: 1;
  max-height: 350px;
  margin-top: 24px;
}

/* ===== 滚动条样式 ===== */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.3) transparent;
}

*::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

*::-webkit-scrollbar-track {
  background: transparent;
}

*::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 3px;
}

*::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.5);
}
</style>
