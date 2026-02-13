/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { formatTimestamp, formatFileSize } from '@/utils/formatters'
import { ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import type { CheckpointListItem, CheckpointStatistics } from "../types/checkpoint"
import { checkpointsApi } from "../services/api/services/checkpoints"

const props = defineProps<{
  taskGraphId?: string
}>()

const loading = ref(true)
const error = ref<string | null>(null)
const checkpoints = ref<CheckpointListItem[]>([])
const statistics = ref<CheckpointStatistics | null>(null)
const selectedCheckpoint = ref<CheckpointListItem | null>(null)
const showCreateDialog = ref(false)
const showRestoreDialog = ref(false)
const createDescription = ref("")

// 分页
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

// 加载检查点列表
const loadCheckpoints = async () => {
  loading.value = true
  error.value = null
  try {
    const result = await checkpointsApi.list({
      task_graph_id: props.taskGraphId,
      page: currentPage.value,
      limit: pageSize.value,
    })
    checkpoints.value = result
    total.value = result.length
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load checkpoints"
    console.error("Failed to load checkpoints:", e)
  } finally {
    loading.value = false
  }
}

// 加载统计信息
const loadStatistics = async () => {
  try {
    statistics.value = await checkpointsApi.getStatistics()
  } catch (e) {
    console.error("Failed to load statistics:", e)
  }
}

// 创建检查点
const createCheckpoint = async () => {
  try {
    await checkpointsApi.create({
      task_graph_id: props.taskGraphId || "",
      description: createDescription.value,
    })
    ElMessage.success("检查点创建成功")
    showCreateDialog.value = false
    createDescription.value = ""
    await loadCheckpoints()
    await loadStatistics()
  } catch (e) {
    ElMessage.error("创建检查点失败")
    console.error("Failed to create checkpoint:", e)
  }
}

// 恢复检查点
const restoreCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    await ElMessageBox.confirm(
      `确定要从检查点 "${checkpoint.checkpoint_id}" 恢复吗？这将覆盖当前状态。`,
      "确认恢复",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    )

    await checkpointsApi.restore({
      checkpoint_id: checkpoint.checkpoint_id,
      task_graph_id: props.taskGraphId || "",
    })
    ElMessage.success("检查点恢复成功")
    showRestoreDialog.value = false
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error("恢复检查点失败")
      console.error("Failed to restore checkpoint:", e)
    }
  }
}

// 删除检查点
const deleteCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除检查点 "${checkpoint.checkpoint_id}" 吗？`,
      "确认删除",
      {
        confirmButtonText: "确定",
        cancelButtonText: "取消",
        type: "warning",
      }
    )

    await checkpointsApi.delete(checkpoint.checkpoint_id)
    ElMessage.success("检查点已删除")
    await loadCheckpoints()
    await loadStatistics()
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error("删除检查点失败")
      console.error("Failed to delete checkpoint:", e)
    }
  }
}

// 下载检查点
const downloadCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    const blob = await checkpointsApi.download(checkpoint.checkpoint_id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `checkpoint-${checkpoint.checkpoint_id}.json`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success("检查点下载成功")
  } catch (e) {
    ElMessage.error("下载检查点失败")
    console.error("Failed to download checkpoint:", e)
  }
}

// 选择检查点
const selectCheckpoint = (checkpoint: CheckpointListItem) => {
  selectedCheckpoint.value = checkpoint
}

// 格式化时间
</script>

<template>
  <div class="checkpoint-view">
    <!-- 头部 -->
    <div class="header">
      <h2>检查点管理</h2>
      <div class="actions">
        <el-button type="primary" @click="showCreateDialog = true">
          创建检查点
        </el-button>
        <el-button @click="loadCheckpoints" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 统计信息 -->
    <div v-if="statistics" class="statistics">
      <el-card class="stat-card">
        <template #header>统计概览</template>
        <div class="stat-content">
          <div class="stat-item">
            <span class="stat-label">总检查点数</span>
            <span class="stat-value">{{ statistics.total_checkpoints }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总大小</span>
            <span class="stat-value">{{ formatFileSize(statistics.total_size) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">最新检查点</span>
            <span class="stat-value">{{ formatTimestamp(statistics.latest_checkpoint || "", 'time') }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 错误提示 -->
    <el-alert v-if="error" :title="error" type="error" show-icon class="error-alert" />

    <!-- 检查点列表 -->
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>检查点列表</span>
          <span v-if="checkpoints.length" class="checkpoint-count">
            共 {{ checkpoints.length }} 个检查点
          </span>
        </div>
      </template>

      <el-table
        :data="checkpoints"
        style="width: 100%"
        @row-click="selectCheckpoint"
        :row-class-name="({ row }: { row: CheckpointListItem }) => (row.checkpoint_id === selectedCheckpoint?.checkpoint_id ? 'selected-row' : '')"
        highlight-current-row
      >
        <el-table-column prop="checkpoint_id" label="检查点ID" width="220">
          <template #default="{ row }">
            <span class="checkpoint-id">{{ row.checkpoint_id.substring(0, 8) }}...</span>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatTimestamp(row.created_at, 'time') }}
          </template>
        </el-table-column>

        <el-table-column prop="size" label="大小" width="120">
          <template #default="{ row }">
            {{ formatFileSize(row.size) }}
          </template>
        </el-table-column>

        <el-table-column prop="node_count" label="节点数" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.node_count }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="notes" label="备注" min-width="150">
          <template #default="{ row }">
            <span v-if="row.notes">{{ row.notes }}</span>
            <span v-else class="no-notes">-</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button-group size="small">
              <el-button type="primary" @click.stop="restoreCheckpoint(row)">
                恢复
              </el-button>
              <el-button @click.stop="downloadCheckpoint(row)">
                下载
              </el-button>
              <el-button type="danger" @click.stop="deleteCheckpoint(row)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && checkpoints.length === 0" description="暂无检查点数据">
        <template #description>
          <p>创建第一个检查点来保存当前状态</p>
        </template>
      </el-empty>
    </el-card>

    <!-- 创建检查点对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建检查点" width="400px">
      <el-form label-position="top">
        <el-form-item label="备注（可选）">
          <el-input
            v-model="createDescription"
            placeholder="添加检查点备注..."
            type="textarea"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createCheckpoint">创建</el-button>
      </template>
    </el-dialog>

    <!-- 恢复确认对话框 -->
    <el-dialog v-model="showRestoreDialog" title="恢复检查点" width="400px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="警告"
        description="恢复检查点将覆盖当前所有状态，此操作不可撤销。"
        style="margin-bottom: 16px"
      />
      <template #footer>
        <el-button @click="showRestoreDialog = false">取消</el-button>
        <el-button type="primary" @click="restoreCheckpoint(selectedCheckpoint!)">
          确认恢复
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.checkpoint-view {
  padding: 20px;
  height: 100%;
  overflow: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 12px;
}

.statistics {
  margin-bottom: 20px;
}

.stat-card {
  width: 100%;
}

.stat-content {
  display: flex;
  gap: 48px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.error-alert {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.checkpoint-count {
  font-size: 12px;
  color: #909399;
}

.checkpoint-id {
  font-family: monospace;
  font-size: 12px;
  color: #606266;
}

.no-notes {
  color: #c0c4cc;
}

.selected-row {
  background-color: #ecf5ff !important;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: #f5f7fa;
}
</style>
