/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="task-history-panel">
    <div v-if="loading" class="loading">
      <el-skeleton :rows="3" animated />
    </div>

    <el-empty v-else-if="error" :description="error" />

    <div v-else-if="!graphs || graphs.length === 0" class="empty">
      <el-empty description="暂无历史任务图" />
    </div>

    <div v-else class="graph-list">
      <el-timeline>
        <el-timeline-item
          v-for="graph in graphs"
          :key="graph.task_id"
          :timestamp="formatDate(graph.updated_at)"
          placement="top"
        >
          <el-card class="graph-card" @click="handleSelectGraph(graph)">
            <div class="graph-header">
              <h4>{{ graph.task_id }}</h4>
              <div class="header-actions">
                <el-tag :type="getGraphStatusType(graph)" size="small">
                  {{ getGraphStatusText(graph) }}
                </el-tag>
                <el-button
                  size="small"
                  type="danger"
                  text
                  @click.stop="handleDeleteGraph(graph)"
                  :loading="deletingGraphId === graph.task_id"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>

            <div class="graph-info">
              <el-space direction="vertical" :size="4">
                <div class="info-item">
                  <el-icon><Clock /></el-icon>
                  <span>创建于: {{ formatDate(graph.created_at) }}</span>
                </div>
                <div class="info-item">
                  <el-icon><Operation /></el-icon>
                  <span>任务数: {{ getTaskCount(graph) }}</span>
                </div>
              </el-space>
            </div>

            <el-divider />

            <div class="graph-stats">
              <el-space :size="16">
                <div class="stat">
                  <span class="stat-label">总计:</span>
                  <span class="stat-value">{{ graph.total_tasks || 0 }}</span>
                </div>
                <div class="stat">
                  <span class="stat-label">完成:</span>
                  <span class="stat-value completed">{{ getCompletedCount(graph) }}</span>
                </div>
              </el-space>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next"
      @current-change="loadGraphs"
      @size-change="loadGraphs"
      small
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Clock, Operation, Delete } from "@element-plus/icons-vue"

// 临时类型定义（TODO: 从正确的模块导入）
interface TaskGraph {
  task_id: string
  created_at: string
  updated_at: string
  total_tasks?: number
  status?: string
  data?: unknown
  nodes?: Record<string, unknown>
}

// 临时的graphs API stub（TODO: 实现真正的API）
const graphsApi = {
  getHistoryGraphs: async (): Promise<TaskGraph[]> => {
    // Stub implementation
    return []
  },
  deleteHistoryGraph: async (): Promise<void> => {
    // Stub implementation
  }
}

// Props
const props = defineProps<{
  workspaceId?: string
}>()

// Emits
const emit = defineEmits<{
  (e: "select", _graphId: string): void
  (e: "deleted", _graphId: string): void
}>()

// 状态
const loading = ref(false)
const error = ref<string | null>(null)
const graphs = ref<TaskGraph[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const deletingGraphId = ref<string | null>(null)

// 加载历史任务图
const loadGraphs = async () => {
  if (!props.workspaceId) return

  loading.value = true
  error.value = null

  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const result = await graphsApi.getHistoryGraphs(
      props.workspaceId,
      pageSize.value,
      offset
    )
    graphs.value = result
    // 假设API返回总数，这里简单处理
    total.value = result.length
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败"
    ElMessage.error("加载历史任务图失败")
  } finally {
    loading.value = false
  }
}

// 选择任务图
const handleSelectGraph = (graph: TaskGraph) => {
  emit("select", graph.task_id)
}

// 删除任务图
const handleDeleteGraph = async (graph: TaskGraph) => {
  if (!props.workspaceId) return

  try {
    await ElMessageBox.confirm(
      `确定要删除任务图 "${graph.task_id}" 吗？此操作不可撤销。`,
      "确认删除",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      }
    )

    deletingGraphId.value = graph.task_id

    await graphsApi.deleteHistoryGraph(props.workspaceId, graph.task_id)

    ElMessage.success("任务图已删除")

    // 从列表中移除已删除的任务图
    graphs.value = graphs.value.filter(g => g.task_id !== graph.task_id)
    total.value--

    // 触发删除事件
    emit("deleted", graph.task_id)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error("删除任务图失败")
    }
  } finally {
    deletingGraphId.value = null
  }
}

// 辅助方法
const formatDate = (): string => {
  return new Date().toLocaleDateString()
}

const getTaskCount = (graph: TaskGraph): number => {
  return Object.keys(graph.nodes || {}).length
}

const getCompletedCount = (graph: TaskGraph): number => {
  const nodes = Object.values(graph.nodes || {})
  return nodes.filter((node: unknown) => node.data?.status === "completed").length
}

const getGraphStatusType = (graph: TaskGraph): string => {
  const completed = getCompletedCount(graph)
  const total = getTaskCount(graph)

  if (total === 0) return "info"
  if (completed === total) return "success" // 全部完成
  if (completed > 0) return "warning" // 部分完成
  return "info" // 未开始
}

const getGraphStatusText = (graph: TaskGraph): string => {
  const completed = getCompletedCount(graph)
  const total = getTaskCount(graph)

  if (total === 0) return "未开始"
  if (completed === total) return "已完成"
  if (completed > 0) return "进行中"
  return "未开始"
}

// 初始化
onMounted(() => {
  loadGraphs()
})

// 暴露方法供父组件调用
defineExpose({
  loadGraphs,
})
</script>

<style scoped lang="scss">
.task-history-panel {
  padding: 16px;

  .loading {
    padding: 16px;
  }

  .empty {
    padding: 40px 0;
  }

  .graph-list {
    .graph-card {
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        transform: translateY(-2px);
      }

      .graph-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;

        h4 {
          margin: 0;
          font-size: 14px;
          font-weight: 600;
          color: #303133;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1;
          margin-right: 8px;
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      }

      .graph-info {
        margin-bottom: 12px;

        .info-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: #606266;
        }
      }

      .graph-stats {
        .stat {
          display: flex;
          gap: 4px;
          font-size: 12px;

          .stat-label {
            color: #909399;
          }

          .stat-value {
            font-weight: 600;

            &.completed {
              color: #67C23A;
            }
          }
        }
      }
    }
  }

  .el-pagination {
    margin-top: 20px;
    display: flex;
    justify-content: center;
  }
}
</style>
