/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="realtime-monitor">
    <!-- 顶部状态栏 -->
    <header class="monitor-header">
      <div class="header-left">
        <div class="status-indicator" :class="{ online: isConnected }">
          <span class="status-dot"></span>
          <span class="status-text">{{ isConnected ? 'System Online' : 'Reconnecting...' }}</span>
        </div>
      </div>
      <div class="header-right">
        <span class="task-count">{{ parallelTasks.stats.active }} active</span>
        <button class="icon-button" @click="refreshData" :disabled="refreshing" title="Refresh">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            <path d="M3 3v5h5"/>
            <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
            <path d="M16 21h5v-5"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="monitor-main">
      <!-- 无任务状态 -->
      <div v-if="!hasActiveTasks" class="no-tasks">
        <div class="no-tasks-icon">○</div>
        <div class="no-tasks-title">No Active Tasks</div>
        <div class="no-tasks-subtitle">System is waiting for tasks to execute</div>
      </div>

      <!-- 任务列表 -->
      <div v-else class="tasks-container">
        <TaskCard
          v-for="task in activeTasks"
          :key="task.taskId"
          :task="task"
        />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import TaskCard from './realtime/TaskCard.vue'

const monitoringStore = useMonitoringStore()
const parallelTasks = useParallelTasksStore()

// State
const refreshing = ref(false)

// Computed
const isConnected = computed(() => monitoringStore.state.isConnected)
const hasActiveTasks = computed(() => parallelTasks.stats.active > 0)

const activeTasks = computed(() => {
  return parallelTasks.allTasks.filter(task =>
    task.state === 'running' || task.state === 'pending'
  )
})

// Methods
async function refreshData() {
  refreshing.value = true
  try {
    await monitoringStore.refreshData()
  } finally {
    setTimeout(() => {
      refreshing.value = false
    }, 500)
  }
}

// Lifecycle
onMounted(() => {
  monitoringStore.initializeMonitoring()
})

onUnmounted(() => {
  monitoringStore.cleanup()
})
</script>

<style scoped>
.realtime-monitor {
  min-height: 100vh;
  background: #ffffff;
  display: flex;
  flex-direction: column;
}

/* ==================== 顶部状态栏 ==================== */
.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
  background: #ffffff;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
}

.status-indicator.online {
  color: #059669;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-indicator.online .status-dot {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.task-count {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  padding: 6px 12px;
  background: #f3f4f6;
  border-radius: 6px;
}

.icon-button {
  background: transparent;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px;
  color: #374151;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-button:hover:not(:disabled) {
  background: #f9fafb;
  border-color: #d1d5db;
}

.icon-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ==================== 主内容区 ==================== */
.monitor-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}

/* 无任务状态 */
.no-tasks {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.no-tasks-icon {
  font-size: 48px;
  color: #e5e7eb;
  margin-bottom: 16px;
}

.no-tasks-title {
  font-size: 18px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.no-tasks-subtitle {
  font-size: 14px;
  color: #6b7280;
}

/* 任务容器 */
.tasks-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 900px;
  margin: 0 auto;
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .monitor-header {
    padding: 12px 16px;
  }

  .monitor-main {
    padding: 16px;
  }
}
</style>
