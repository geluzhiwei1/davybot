/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="execution-detail">
    <div class="detail-header">
      <h2>执行详情</h2>
      <el-button @click="$emit('close')" type="primary">
        <el-icon><Close /></el-icon>
        关闭
      </el-button>
    </div>

    <div class="detail-content" v-if="execution">
      <!-- 基本信息 -->
      <el-descriptions title="基本信息" :column="2" border>
        <el-descriptions-item label="执行ID">
          {{ execution.executionId }}
        </el-descriptions-item>
        <el-descriptions-item label="TaskGraph ID">
          {{ execution.graphId }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTagType(execution.status)">
            {{ getStatusText(execution.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="开始时间">
          {{ formatTime(execution.startTime) }}
        </el-descriptions-item>
        <el-descriptions-item label="结束时间">
          {{ execution.endTime ? formatTime(execution.endTime) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="执行时长">
          {{ execution.totalDuration ? formatDuration(execution.totalDuration) : '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="execution.errorMessage">
          <el-text type="danger">{{ execution.errorMessage }}</el-text>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 节点统计 -->
      <el-descriptions title="节点统计" :column="2" border>
        <el-descriptions-item label="总节点数">
          {{ execution.nodesTotal }}
        </el-descriptions-item>
        <el-descriptions-item label="已完成">
          {{ execution.nodesCompleted }}
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          {{ execution.nodesFailed }}
        </el-descriptions-item>
        <el-descriptions-item label="跳过">
          {{ execution.nodesSkipped }}
        </el-descriptions-item>
        <el-descriptions-item label="完成率">
          {{ execution.nodesTotal > 0 ? Math.round((execution.nodesCompleted / execution.nodesTotal) * 100) : 0 }}%
        </el-descriptions-item>
      </el-descriptions>

      <!-- 节点列表 -->
      <div class="nodes-section">
        <h3>节点详情</h3>
        <el-table :data="execution.nodes" stripe max-height="400">
          <el-table-column prop="id" label="节点ID" width="150" />
          <el-table-column prop="name" label="节点名称" width="200">
            <template #default="{ row }">
              {{ row.name || row.id }}
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusTagType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="startTime" label="开始时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.startTime) }}
            </template>
          </el-table-column>
          <el-table-column prop="endTime" label="结束时间" width="180">
            <template #default="{ row }">
              {{ row.endTime ? formatTime(row.endTime) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="duration" label="执行时长" width="120">
            <template #default="{ row }">
              {{ row.duration ? formatDuration(row.duration) : '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="retryCount" label="重试次数" width="100" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button 
                v-if="row.status === 'failed'"
                size="small" 
                type="primary"
                @click="retryNode(row)"
              >
                重试
              </el-button>
              <el-button 
                v-if="['pending', 'running'].includes(row.status)"
                size="small" 
                type="warning"
                @click="skipNode(row)"
              >
                跳过
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'
import type { TaskGraphExecution, TaskGraphNode } from '@/types/monitoring'
import { formatTimestamp, formatDuration } from '@/utils/formatters'

interface Props {
  execution: TaskGraphExecution | null
}

defineProps<Props>()

defineEmits<{
  close: []
}>()

// 获取状态标签类型
const getStatusTagType = (status: string): string => {
  const types: Record<string, string> = {
    running: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
    pending: 'warning'
  }
  return types[status] || 'info'
}

// 获取状态文本
const getStatusText = (status: string): string => {
  const texts: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '取消',
    pending: '等待中'
  }
  return texts[status] || '未知'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）
// formatTimestamp - 格式化时间戳
// formatDuration - 格式化时长

// 格式化时间（别名，用于模板）
const formatTime = (timestamp: string | number | Date): string => {
  // Convert number timestamp to Date
  const date = typeof timestamp === 'number' ? new Date(timestamp) : timestamp
  return formatTimestamp(date, 'time')
}


// 重试节点
const retryNode = (_node: TaskGraphNode) => {
  // 这里应该调用控制节点的API
}

// 跳过节点
const skipNode = (_node: TaskGraphNode) => {
  // 这里应该调用控制节点的API
}
</script>

<style scoped>
.execution-detail {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #e4e7ed;
}

.detail-header h2 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.detail-content {
  margin-bottom: 20px;
}

.nodes-section {
  margin-top: 30px;
}

.nodes-section h3 {
  margin: 0 0 15px 0;
  font-size: 16px;
  color: #303133;
}
</style>