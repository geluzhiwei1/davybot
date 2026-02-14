/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="taskgraph-visualization">
    <el-card class="graph-card" header="TaskGraph执行流程">
      <template #extra>
        <div class="graph-controls">
          <el-button-group>
            <el-button size="small" @click="refreshData">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-button-group>
          
          <el-select 
            v-model="selectedExecutionId" 
            placeholder="选择执行"
            size="small"
            style="width: 200px; margin-left: 10px;"
            @change="onExecutionChange"
          >
            <el-option
              v-for="execution in activeExecutions"
              :key="execution.executionId"
              :label="`${execution.graphId} (${execution.status})`"
              :value="execution.executionId"
            />
          </el-select>
        </div>
      </template>

      <!-- 图例 -->
      <div class="graph-legend">
        <div class="legend-item">
          <div class="legend-color" style="background-color: #e6a23c;"></div>
          <span>等待中</span>
        </div>
        <div class="legend-item">
          <div class="legend-color" style="background-color: #409eff;"></div>
          <span>运行中</span>
        </div>
        <div class="legend-item">
          <div class="legend-color" style="background-color: #67c23a;"></div>
          <span>已完成</span>
        </div>
        <div class="legend-item">
          <div class="legend-color" style="background-color: #f56c6c;"></div>
          <span>失败</span>
        </div>
        <div class="legend-item">
          <div class="legend-color" style="background-color: #909399;"></div>
          <span>跳过</span>
        </div>
        <div class="legend-item">
          <div class="legend-color" style="background-color: #c0c4cc;"></div>
          <span>取消</span>
        </div>
      </div>

      <!-- 简化的节点列表 -->
      <div class="nodes-list">
        <div v-if="!currentExecution" class="no-execution">
          <el-empty description="请选择一个执行记录" />
        </div>
        
        <div v-else class="nodes-container">
          <el-table :data="currentExecution.nodes" style="width: 100%">
            <el-table-column prop="id" label="节点ID" width="200" />
            <el-table-column prop="name" label="节点名称" width="200" />
            <el-table-column prop="type" label="类型" width="120" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="scope">
                <el-tag :type="getStatusTagType(scope.row.status)" size="small">
                  {{ getStatusText(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="startTime" label="开始时间" width="180">
              <template #default="scope">
                {{ formatTimestamp(scope.row.startTime, 'time') }}
              </template>
            </el-table-column>
            <el-table-column prop="duration" label="执行时长" width="120">
              <template #default="scope">
                {{ formatDuration(scope.row.duration, 'standard') }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="scope">
                <el-button 
                  v-if="scope.row.status === 'failed'"
                  size="small" 
                  type="primary"
                  @click="retryNode(scope.row)"
                >
                  重试
                </el-button>
                <el-button 
                  v-if="['pending', 'running'].includes(scope.row.status)"
                  size="small" 
                  type="warning"
                  @click="skipNode(scope.row)"
                >
                  跳过
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 执行统计 -->
      <div class="execution-stats">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="总节点数" :value="currentExecution?.nodesTotal || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="已完成" :value="currentExecution?.nodesCompleted || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="失败" :value="currentExecution?.nodesFailed || 0" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="跳过" :value="currentExecution?.nodesSkipped || 0" />
          </el-col>
        </el-row>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { formatTimestamp, formatDuration } from '@/utils/formatters'
import type {
  TaskGraphNode,
  NodeStatus
} from '@/types/monitoring'

const monitoringStore = useMonitoringStore()

// 选中的执行ID
const selectedExecutionId = ref('')

// 当前执行 - 直接从 store 访问以保持响应性
const currentExecution = computed(() => {
  if (!selectedExecutionId.value) return null

  const executions = monitoringStore.state.activeExecutions
  if (!executions || !Array.isArray(executions)) {
    return null
  }

  const execution = executions.find(exec => exec && exec.executionId === selectedExecutionId.value)
  return execution || null
})

// 为了在模板中使用，创建计算属性
const activeExecutions = computed(() => {
  return monitoringStore.state.activeExecutions || []
})

// 获取状态文本
const getStatusText = (status: NodeStatus): string => {
  const texts: Record<NodeStatus, string> = {
    'pending': '等待中',
    'running': '运行中',
    'completed': '已完成',
    'failed': '失败',
    'skipped': '跳过',
    'cancelled': '取消'
  }
  return texts[status] || '未知'
}

// 获取状态标签类型
const getStatusTagType = (status: NodeStatus): string => {
  const types: Record<NodeStatus, string> = {
    'pending': 'warning',
    'running': 'primary',
    'completed': 'success',
    'failed': 'danger',
    'skipped': 'info',
    'cancelled': 'info'
  }
  return types[status] || 'info'
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 执行变化处理
const onExecutionChange = () => {
  monitoringStore.selectExecution(selectedExecutionId.value)
}

// 节点控制操作
const retryNode = async (node: TaskGraphNode) => {
  const execution = currentExecution.value
  if (!execution) return
  
  try {
    await monitoringStore.controlNode({
      executionId: execution.executionId,
      nodeId: node.id,
      action: 'retry'
    })
    ElMessage.success('节点重试已发送')
  } catch (error) {
    console.error('[DEBUG] retryNode failed:', error)
    ElMessage.error('节点重试失败')
  }
}

const skipNode = async (node: TaskGraphNode) => {
  const execution = currentExecution.value
  if (!execution) return
  
  try {
    await ElMessageBox.confirm('确定要跳过此节点吗？', '确认操作', {
      type: 'warning'
    })
    
    await monitoringStore.controlNode({
      executionId: execution.executionId,
      nodeId: node.id,
      action: 'skip'
    })
    ElMessage.success('节点跳过已发送')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[DEBUG] skipNode failed:', error)
      ElMessage.error('节点跳过失败')
    }
  }
}

// 刷新数据
const refreshData = async () => {
  try {
    await monitoringStore.refreshData()
  } catch (error) {
    console.error('[DEBUG] refreshData failed:', error)
  }
}

onMounted(() => {
  // 初始化时选择第一个执行
  if (activeExecutions.value && activeExecutions.value.length > 0 && activeExecutions.value[0]) {
    selectedExecutionId.value = activeExecutions.value[0].executionId
  }
})
</script>

<style scoped>
.taskgraph-visualization {
  height: 100%;
}

.graph-card {
  height: 100%;
}

.graph-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.graph-legend {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid #ddd;
}

.nodes-list {
  margin-bottom: 20px;
}

.nodes-container {
  max-height: 400px;
  overflow-y: auto;
}

.no-execution {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
}

.execution-stats {
  margin-top: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .graph-controls {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  
  .graph-legend {
    gap: 10px;
  }
}
</style>