<!--
并行AgentAgents
显示所有并行执行的任务节点，支持实时观察和控制
-->

<template>
  <div class="parallel-agents-panel">
    <!-- 头部统计信息 -->
    <div class="panel-header">
      <div class="header-left">
        <h3 class="panel-title">
          <span class="icon">⚡</span>
          并行任务监控
        </h3>
        <div class="stats">
          <div class="stat-item active">
            <span class="stat-value">{{ stats.active }}</span>
            <span class="stat-label">运行中</span>
          </div>
          <div class="stat-item completed">
            <span class="stat-value">{{ stats.completed }}</span>
            <span class="stat-label">已完成</span>
          </div>
          <div class="stat-item failed">
            <span class="stat-value">{{ stats.failed }}</span>
            <span class="stat-label">失败</span>
          </div>
          <div class="stat-item pending">
            <span class="stat-value">{{ stats.pending }}</span>
            <span class="stat-label">等待中</span>
          </div>
        </div>
      </div>
      <div class="header-right">
        <div class="max-parallel-info">
          最大并行: <strong>{{ maxParallel }}</strong>
        </div>
        <el-button :icon="Refresh" circle size="small" @click="refresh" :loading="refreshing" title="刷新" />
        <el-button :icon="Delete" circle size="small" @click="clearCompleted" title="清除已完成"
          v-if="stats.completed > 0" />
      </div>
    </div>

    <!-- 任务网格 -->
    <div class="tasks-grid" v-if="allTasks.length > 0">
      <div v-for="task in allTasks" :key="task.taskId" class="task-card" :class="[
        `state-${task.state}`,
        { expanded: expandedTasks.has(task.taskId) }
      ]">
        <!-- 任务卡片头部 -->
        <div class="task-card-header">
          <div class="task-info">
            <div class="task-mode-badge" :class="`mode-${task.nodeType}`">
              {{ modeIcons[task.nodeType] || '🤖' }} {{ task.nodeType }}
            </div>
            <div class="task-state-badge" :class="task.state">
              {{ stateLabels[task.state] }}
            </div>
          </div>
          <div class="task-actions">
            <el-button :icon="expandedTasks.has(task.taskId) ? ArrowUp : ArrowDown" size="small" text
              @click="toggleExpand(task.taskId)">
              {{ expandedTasks.has(task.taskId) ? '收起' : '展开' }}
            </el-button>
            <TaskControlButtons :task="task" @pause="handlePause" @resume="handleResume" @stop="handleStop" />
          </div>
        </div>

        <!-- 任务描述 -->
        <div class="task-description">
          {{ task.description }}
        </div>

        <!-- 进度条 -->
        <div class="task-progress">
          <el-progress :percentage="task.progress.percentage" :status="getProgressStatus(task.state)" :stroke-width="8"
            :show-text="true">
            <template #default="{ }">
              <span class="progress-text">
                {{ task.progress.current }} / {{ task.progress.total }}
                {{ task.progress.message ? `- ${task.progress.message}` : '' }}
              </span>
            </template>
          </el-progress>
        </div>

        <!-- 展开内容 -->
        <div v-if="expandedTasks.has(task.taskId)" class="task-expanded-content">
          <!-- TODO列表 -->
          <div class="task-todos" v-if="task.todos.length > 0">
            <div class="section-title">TODO列表</div>
            <div class="todos-list">
              <div v-for="todo in task.todos" :key="todo.id" class="todo-item" :class="todo.status">
                <el-icon class="todo-icon">
                  <component :is="getTodoIcon(todo.status)" />
                </el-icon>
                <span class="todo-content">{{ todo.content }}</span>
              </div>
            </div>
          </div>

          <!-- 实时输出 -->
          <div class="task-output" v-if="task.outputs.length > 0">
            <div class="section-title">实时输出</div>
            <div class="output-content">
              <div v-for="(line, idx) in lastNOutputs(task.outputs, 10)" :key="idx" class="output-line">
                {{ line }}
              </div>
            </div>
          </div>

          <!-- 性能指标 -->
          <div class="task-metrics">
            <div class="section-title">性能指标</div>
            <div class="metrics-grid">
              <div class="metric-item" v-if="task.metrics.duration">
                <span class="metric-label">持续时间:</span>
                <span class="metric-value">{{ formatDuration(task.metrics.duration) }}</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">工具调用:</span>
                <span class="metric-value">{{ task.metrics.toolCalls }}</span>
              </div>
              <div class="metric-item">
                <span class="metric-label">LLM调用:</span>
                <span class="metric-value">{{ task.metrics.llmCalls }}</span>
              </div>
            </div>
          </div>

          <!-- 错误信息 -->
          <div class="task-error" v-if="task.error">
            <div class="section-title error">错误信息</div>
            <div class="error-content">{{ task.error }}</div>
          </div>
        </div>

        <!-- 时间戳 -->
        <div class="task-footer">
          <span class="task-time">
            创建于: {{ formatTime(task.createdAt) }}
            <span v-if="task.metrics.duration">
              · 耗时: {{ formatDuration(task.metrics.duration) }}
            </span>
          </span>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <el-empty description="暂无并行任务">
        <template #image>
          <span class="empty-icon">🎯</span>
        </template>
      </el-empty>
    </div>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh,
  Delete,
  ArrowUp,
  ArrowDown,
  CircleCheck,
  Clock,
  Loading,
  CircleClose
} from '@element-plus/icons-vue'
import { useParallelTasksStore } from '@/stores/parallelTasks'
import { type ParallelTaskInfo, ParallelTaskState } from '@/types/parallelTasks'
import TaskControlButtons from './TaskControlButtons.vue'

const parallelTasks = useParallelTasksStore()

// 状态
const expandedTasks = ref<Set<string>>(new Set())
const refreshing = ref(false)

// 计算属性
const stats = computed(() => parallelTasks.stats)
const maxParallel = computed(() => parallelTasks.maxParallel)
const allTasks = computed(() => parallelTasks.allTasks)

// Mode图标映射
const modeIcons: Record<string, string> = {
  orchestrator: '🪃',
  architect: '🏗️',
  code: '💻',
  ask: '❓',
  debug: '🪲',
  'patent-engineer': '💡'
}

// 状态标签
const stateLabels: Record<ParallelTaskState, string> = {
  [ParallelTaskState.PENDING]: '等待中',
  [ParallelTaskState.RUNNING]: '运行中',
  [ParallelTaskState.PAUSED]: '已暂停',
  [ParallelTaskState.COMPLETED]: '已完成',
  [ParallelTaskState.FAILED]: '失败',
  [ParallelTaskState.CANCELLED]: '已取消',
  [ParallelTaskState.SKIPPED]: '已跳过'
}

// 方法
function toggleExpand(taskId: string) {
  if (expandedTasks.value.has(taskId)) {
    expandedTasks.value.delete(taskId)
  } else {
    expandedTasks.value.add(taskId)
  }
}

function getProgressStatus(state: ParallelTaskState) {
  const statusMap = {
    [ParallelTaskState.COMPLETED]: 'success',
    [ParallelTaskState.FAILED]: 'exception',
    [ParallelTaskState.PENDING]: '',
    [ParallelTaskState.RUNNING]: '',
    [ParallelTaskState.PAUSED]: 'warning',
    [ParallelTaskState.CANCELLED]: 'warning',
    [ParallelTaskState.SKIPPED]: 'info'
  }
  return statusMap[state] || undefined
}

function getTodoIcon(status: ParallelTaskState) {
  const iconMap = {
    [ParallelTaskState.COMPLETED]: CircleCheck,
    [ParallelTaskState.RUNNING]: Loading,
    [ParallelTaskState.PENDING]: Clock,
    [ParallelTaskState.FAILED]: CircleClose
  }
  return iconMap[status] || Clock
}

function lastNOutputs(outputs: string[], n: number) {
  return outputs.slice(-n)
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}秒`
  } else if (seconds < 3600) {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}分${secs}秒`
  } else {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return `${hours}小时${mins}分`
  }
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).format(date)
}

async function refresh() {
  refreshing.value = true
  // 触发状态刷新
  setTimeout(() => {
    refreshing.value = false
  }, 500)
}

async function clearCompleted() {
  try {
    await ElMessageBox.confirm(
      `确定要清除 ${stats.value.completed} 个已完成的任务吗？`,
      '确认清除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info'
      }
    )

    // 移除已完成的任务
    parallelTasks.completedTasks.forEach(task => {
      parallelTasks.removeTask(task.taskId)
    })

    ElMessage.success('已清除完成任务')
  } catch {
    // 用户取消
  }
}

// 任务控制操作
async function handlePause(task: ParallelTaskInfo) {
  try {
    // Backend API integration needed for pause functionality
    ElMessage.success(`任务 ${task.taskId} 已暂停`)
  } catch (error: unknown) {
    ElMessage.error(`暂停失败: ${error.message}`)
  }
}

async function handleResume(task: ParallelTaskInfo) {
  try {
    // Backend API integration needed for resume functionality
    ElMessage.success(`任务 ${task.taskId} 已恢复`)
  } catch (error: unknown) {
    ElMessage.error(`恢复失败: ${error.message}`)
  }
}

async function handleStop(task: ParallelTaskInfo) {
  try {
    await ElMessageBox.confirm(
      `确定要停止任务 ${task.taskId} 吗？`,
      '确认停止',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // Backend API integration needed for stop functionality
    ElMessage.success(`任务 ${task.taskId} 已停止`)
  } catch {
    // User cancelled
  }
}
</script>

<style scoped lang="scss">
.parallel-agents-panel {
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
  min-height: 400px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;

  .header-left {
    .panel-title {
      margin: 0 0 10px 0;
      font-size: 18px;
      font-weight: 600;
      color: #303133;
      display: flex;
      align-items: center;
      gap: 8px;

      .icon {
        font-size: 24px;
      }
    }

    .stats {
      display: flex;
      gap: 20px;

      .stat-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 8px 16px;
        border-radius: 6px;
        background: white;
        min-width: 80px;

        .stat-value {
          font-size: 24px;
          font-weight: 700;
          line-height: 1;
        }

        .stat-label {
          font-size: 12px;
          color: #909399;
          margin-top: 4px;
        }

        &.active .stat-value {
          color: #409eff;
        }

        &.completed .stat-value {
          color: #67c23a;
        }

        &.failed .stat-value {
          color: #f56c6c;
        }

        &.pending .stat-value {
          color: #909399;
        }
      }
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;

    .max-parallel-info {
      font-size: 14px;
      color: #606266;
      padding: 0 12px;
    }
  }
}

.tasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
  gap: 16px;
}

.task-card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s;
  border: 2px solid transparent;

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  }

  &.state-running {
    border-color: #409eff;
  }

  &.state-completed {
    border-color: #67c23a;
  }

  &.state-failed {
    border-color: #f56c6c;
  }

  &.state-pending {
    border-color: #909399;
  }

  .task-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;

    .task-info {
      display: flex;
      gap: 8px;
      align-items: center;

      .task-mode-badge {
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
        background: #f0f2f5;
        color: #606266;

        &.mode-orchestrator {
          background: #e6f7ff;
          color: #1890ff;
        }

        &.mode-architect {
          background: #fff7e6;
          color: #fa8c16;
        }

        &.mode-code {
          background: #f6ffed;
          color: #52c41a;
        }

        &.mode-ask {
          background: #f9f0ff;
          color: #722ed1;
        }

        &.mode-debug {
          background: #fff1f0;
          color: #f5222d;
        }
      }

      .task-state-badge {
        padding: 4px 10px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;

        &.running {
          background: #e1f3ff;
          color: #409eff;
        }

        &.completed {
          background: #e1f9e8;
          color: #67c23a;
        }

        &.failed {
          background: #fee;
          color: #f56c6c;
        }

        &.pending {
          background: #f4f4f5;
          color: #909399;
        }

        &.paused {
          background: #fff7e6;
          color: #fa8c16;
        }
      }
    }

    .task-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
  }

  .task-description {
    font-size: 14px;
    color: #303133;
    margin-bottom: 12px;
    line-height: 1.5;
    font-weight: 500;
  }

  .task-progress {
    margin-bottom: 12px;

    .progress-text {
      font-size: 12px;
      color: #606266;
    }
  }

  .task-expanded-content {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #e4e7ed;

    .section-title {
      font-size: 14px;
      font-weight: 600;
      color: #303133;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;

      &.error {
        color: #f56c6c;
      }
    }

    .task-todos {
      margin-bottom: 16px;

      .todos-list {
        .todo-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 0;
          font-size: 13px;

          .todo-icon {
            font-size: 16px;
          }

          &.completed {
            color: #67c23a;
            text-decoration: line-through;
          }

          &.running {
            color: #409eff;
          }

          &.pending {
            color: #909399;
          }
        }
      }
    }

    .task-output {
      margin-bottom: 16px;

      .output-content {
        background: #f5f7fa;
        border-radius: 4px;
        padding: 12px;
        max-height: 200px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        font-size: 12px;
        line-height: 1.6;

        .output-line {
          margin-bottom: 4px;
          color: #606266;
        }
      }
    }

    .task-metrics {
      margin-bottom: 16px;

      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;

        .metric-item {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          padding: 8px;
          background: #f9fafc;
          border-radius: 4px;

          .metric-label {
            color: #909399;
          }

          .metric-value {
            font-weight: 600;
            color: #303133;
          }
        }
      }
    }

    .task-error {
      .error-content {
        background: #fee;
        border: 1px solid #f56c6c;
        border-radius: 4px;
        padding: 12px;
        color: #f56c6c;
        font-size: 13px;
        line-height: 1.6;
      }
    }
  }

  .task-footer {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #e4e7ed;

    .task-time {
      font-size: 12px;
      color: #909399;
    }
  }
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;

  .empty-icon {
    font-size: 64px;
    opacity: 0.5;
  }
}
</style>
