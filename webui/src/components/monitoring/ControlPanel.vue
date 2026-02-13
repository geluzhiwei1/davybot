/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="control-panel">
    <el-card class="control-card" header="交互控制">
      <template #extra>
        <div class="control-status">
          <el-tag 
            :type="connectionStatus.type" 
            size="small"
            effect="dark"
          >
            {{ connectionStatus.text }}
          </el-tag>
        </div>
      </template>

      <!-- 任务控制 -->
      <div class="control-section">
        <h3 class="section-title">任务控制</h3>
        <div class="task-controls">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-select
                v-model="selectedExecutionId"
                placeholder="选择要控制的执行"
                filterable
                @change="onExecutionChange"
              >
                <el-option
                  v-for="execution in controllableExecutions"
                  :key="execution.executionId"
                  :label="`${execution.graphId} (${execution.status})`"
                  :value="execution.executionId"
                />
              </el-select>
            </el-col>
            <el-col :span="12">
              <el-button-group>
                <el-button 
                  :disabled="!canPause"
                  type="warning"
                  @click="pauseExecution"
                >
                  暂停
                </el-button>
                <el-button 
                  :disabled="!canResume"
                  type="success"
                  @click="resumeExecution"
                >
                  恢复
                </el-button>
                <el-button 
                  :disabled="!canRestart"
                  type="primary"
                  @click="restartExecution"
                >
                  重启
                </el-button>
                <el-button 
                  :disabled="!canCancel"
                  type="danger"
                  @click="cancelExecution"
                >
                  取消
                </el-button>
              </el-button-group>
            </el-col>
          </el-row>
          
          <!-- 操作原因 -->
          <el-input
            v-model="controlReason"
            type="textarea"
            :rows="2"
            placeholder="请输入操作原因（可选）"
            style="margin-top: 10px;"
          />
        </div>
      </div>

      <!-- 节点控制 -->
      <div class="control-section">
        <h3 class="section-title">节点控制</h3>
        <div class="node-controls">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-select
                v-model="selectedNodeId"
                placeholder="选择要控制的节点"
                filterable
                @change="onNodeChange"
              >
                <el-option
                  v-for="node in controllableNodes"
                  :key="node.id"
                  :label="`${node.name || node.id} (${node.status})`"
                  :value="node.id"
                />
              </el-select>
            </el-col>
            <el-col :span="12">
              <el-button-group>
                <el-button 
                  :disabled="!canRetryNode"
                  type="primary"
                  @click="retryNode"
                >
                  重试
                </el-button>
                <el-button 
                  :disabled="!canSkipNode"
                  type="warning"
                  @click="skipNode"
                >
                  跳过
                </el-button>
                <el-button 
                  :disabled="!canForceCompleteNode"
                  type="success"
                  @click="forceCompleteNode"
                >
                  强制完成
                </el-button>
              </el-button-group>
            </el-col>
          </el-row>
          
          <!-- 节点参数 -->
          <el-input
            v-model="nodeParameters"
            type="textarea"
            :rows="2"
            placeholder="请输入节点参数（JSON格式，可选）"
            style="margin-top: 10px;"
          />
        </div>
      </div>

      <!-- 批量操作 -->
      <div class="control-section">
        <h3 class="section-title">批量操作</h3>
        <div class="batch-controls">
          <el-row :gutter="20">
            <el-col :span="8">
              <el-select
                v-model="batchOperation"
                placeholder="选择批量操作"
                @change="onBatchOperationChange"
              >
                <el-option label="批量暂停" value="pause" />
                <el-option label="批量恢复" value="resume" />
                <el-option label="批量取消" value="cancel" />
                <el-option label="批量重试失败节点" value="retry-failed" />
                <el-option label="批量跳过等待节点" value="skip-pending" />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-button 
                :disabled="!batchOperation"
                type="primary"
                @click="executeBatchOperation"
              >
                执行批量操作
              </el-button>
            </el-col>
            <el-col :span="8">
              <el-button 
                @click="showBatchDialog = true"
              >
                高级批量操作
              </el-button>
            </el-col>
          </el-row>
        </div>
      </div>

      <!-- 优先级管理 -->
      <div class="control-section">
        <h3 class="section-title">优先级管理</h3>
        <div class="priority-controls">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-select
                v-model="priorityExecutionId"
                placeholder="选择要调整优先级的执行"
                filterable
              >
                <el-option
                  v-for="execution in activeExecutions"
                  :key="execution.executionId"
                  :label="`${execution.graphId} (当前优先级: ${execution.metadata?.priority || 0})`"
                  :value="execution.executionId"
                />
              </el-select>
            </el-col>
            <el-col :span="8">
              <el-input-number
                v-model="newPriority"
                :min="0"
                :max="10"
                placeholder="新优先级"
              />
            </el-col>
            <el-col :span="4">
              <el-button 
                :disabled="!priorityExecutionId"
                type="primary"
                @click="updatePriority"
              >
                更新
              </el-button>
            </el-col>
          </el-row>
        </div>
      </div>

      <!-- 操作历史 -->
      <div class="control-section">
        <h3 class="section-title">操作历史</h3>
        <div class="operation-history">
          <el-table :data="operationHistory" stripe max-height="200">
            <el-table-column prop="timestamp" label="时间" width="180">
              <template #default="{ row }">
                {{ formatTimestamp(row.timestamp, 'time') }}
              </template>
            </el-table-column>
            <el-table-column prop="type" label="类型" width="100">
              <template #default="{ row }">
                <el-tag :type="getOperationTypeColor(row.type)" size="small">
                  {{ getOperationTypeText(row.type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="target" label="目标" width="150" />
            <el-table-column prop="action" label="操作" width="100" />
            <el-table-column prop="reason" label="原因" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.status === 'success' ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- 高级批量操作对话框 -->
    <el-dialog
      v-model="showBatchDialog"
      title="高级批量操作"
      width="600px"
    >
      <el-form :model="batchForm" label-width="100px">
        <el-form-item label="操作类型">
          <el-radio-group v-model="batchForm.operation">
            <el-radio label="pause">暂停</el-radio>
            <el-radio label="resume">恢复</el-radio>
            <el-radio label="cancel">取消</el-radio>
            <el-radio label="restart">重启</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="目标选择">
          <el-checkbox-group v-model="batchForm.targets">
            <el-checkbox label="running">运行中的执行</el-checkbox>
            <el-checkbox label="pending">等待中的执行</el-checkbox>
            <el-checkbox label="failed">失败的执行</el-checkbox>
            <el-checkbox label="all">所有执行</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        
        <el-form-item label="过滤条件">
          <el-row :gutter="10">
            <el-col :span="12">
              <el-select
                v-model="batchForm.graphFilter"
                placeholder="TaskGraph过滤"
                clearable
                multiple
              >
                <el-option
                  v-for="graph in availableGraphs"
                  :key="graph.id"
                  :label="graph.name || graph.id"
                  :value="graph.id"
                />
              </el-select>
            </el-col>
            <el-col :span="12">
              <el-select
                v-model="batchForm.statusFilter"
                placeholder="状态过滤"
                clearable
                multiple
              >
                <el-option label="运行中" value="running" />
                <el-option label="等待中" value="pending" />
                <el-option label="失败" value="failed" />
                <el-option label="已完成" value="completed" />
              </el-select>
            </el-col>
          </el-row>
        </el-form-item>
        
        <el-form-item label="操作原因">
          <el-input
            v-model="batchForm.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入操作原因"
          />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="executeAdvancedBatchOperation">执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatTimestamp } from '@/utils/formatters'

const monitoringStore = useMonitoringStore()
const {
  state,
  controlTask,
  controlNode
} = monitoringStore

// 从state获取active executions
const activeExecutions = computed(() => state.activeExecutions)

// 状态
const selectedExecutionId = ref('')
const selectedNodeId = ref('')
const priorityExecutionId = ref('')
const newPriority = ref(0)
const controlReason = ref('')
const nodeParameters = ref('')
const batchOperation = ref('')
const showBatchDialog = ref(false)

// 批量操作表单
const batchForm = ref({
  operation: 'pause',
  targets: [] as string[],
  graphFilter: [] as string[],
  statusFilter: [] as string[],
  reason: ''
})

// 操作历史
const operationHistory = ref<Array<{
  timestamp: string
  type: 'task' | 'node' | 'batch'
  target: string
  action: string
  reason: string
  status: 'success' | 'failed'
}>>([])

// 可用的TaskGraph
const availableGraphs = ref<Array<{ id: string; name?: string }>>([])

// 连接状态
const connectionStatus = computed(() => {
  if (state.isConnected) {
    return { type: 'success', text: '已连接' }
  } else {
    return { type: 'danger', text: '未连接' }
  }
})

// 可控制的执行
const controllableExecutions = computed(() => {
  return activeExecutions.value.filter(exec => 
    ['running', 'paused', 'failed'].includes(exec.status)
  )
})

// 当前选中的执行
const selectedExecution = computed(() => {
  return activeExecutions.value.find(exec => exec.executionId === selectedExecutionId.value)
})

// 可控制的节点
const controllableNodes = computed(() => {
  if (!selectedExecution.value) return []
  return selectedExecution.value.nodes.filter(node => 
    ['pending', 'running', 'failed'].includes(node.status)
  )
})

// 当前选中的节点
const selectedNode = computed(() => {
  if (!selectedExecution.value) return null
  return selectedExecution.value.nodes.find(node => node.id === selectedNodeId.value)
})

// 任务控制按钮状态
const canPause = computed(() => {
  return selectedExecution.value?.status === 'running'
})

const canResume = computed(() => {
  return selectedExecution.value?.status === 'paused'
})

const canRestart = computed(() => {
  return ['failed', 'cancelled', 'completed'].includes(selectedExecution.value?.status || '')
})

const canCancel = computed(() => {
  return ['running', 'paused', 'pending'].includes(selectedExecution.value?.status || '')
})

// 节点控制按钮状态
const canRetryNode = computed(() => {
  return selectedNode.value?.status === 'failed'
})

const canSkipNode = computed(() => {
  return ['pending', 'running'].includes(selectedNode.value?.status || '')
})

const canForceCompleteNode = computed(() => {
  return ['pending', 'running'].includes(selectedNode.value?.status || '')
})

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 获取操作类型颜色
const getOperationTypeColor = (type: string): string => {
  const types: Record<string, string> = {
    task: 'primary',
    node: 'success',
    batch: 'warning'
  }
  return types[type] || 'info'
}

// 获取操作类型文本
const getOperationTypeText = (type: string): string => {
  const texts: Record<string, string> = {
    task: '任务',
    node: '节点',
    batch: '批量'
  }
  return texts[type] || '未知'
}

// 执行变化处理
const onExecutionChange = () => {
  selectedNodeId.value = ''
}

// 节点变化处理
const onNodeChange = () => {
  // 节点变化时的处理逻辑
}

// 批量操作变化处理
const onBatchOperationChange = () => {
  // 批量操作变化时的处理逻辑
}

// 任务控制操作
const pauseExecution = async () => {
  if (!selectedExecutionId.value) return
  
  try {
    await controlTask({
      executionId: selectedExecutionId.value,
      action: 'pause',
      reason: controlReason.value
    })
    
    addOperationHistory('task', selectedExecutionId.value, 'pause', controlReason.value, 'success')
    ElMessage.success('任务已暂停')
  } catch {
    addOperationHistory('task', selectedExecutionId.value, 'pause', controlReason.value, 'failed')
    ElMessage.error('暂停任务失败')
  }
}

const resumeExecution = async () => {
  if (!selectedExecutionId.value) return
  
  try {
    await controlTask({
      executionId: selectedExecutionId.value,
      action: 'resume',
      reason: controlReason.value
    })
    
    addOperationHistory('task', selectedExecutionId.value, 'resume', controlReason.value, 'success')
    ElMessage.success('任务已恢复')
  } catch {
    addOperationHistory('task', selectedExecutionId.value, 'resume', controlReason.value, 'failed')
    ElMessage.error('恢复任务失败')
  }
}

const restartExecution = async () => {
  if (!selectedExecutionId.value) return
  
  try {
    await ElMessageBox.confirm('确定要重启此执行吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlTask({
      executionId: selectedExecutionId.value,
      action: 'restart',
      reason: controlReason.value
    })
    
    addOperationHistory('task', selectedExecutionId.value, 'restart', controlReason.value, 'success')
    ElMessage.success('任务已重启')
  } catch (error) {
    if (error !== 'cancel') {
      addOperationHistory('task', selectedExecutionId.value, 'restart', controlReason.value, 'failed')
      ElMessage.error('重启任务失败')
    }
  }
}

const cancelExecution = async () => {
  if (!selectedExecutionId.value) return
  
  try {
    await ElMessageBox.confirm('确定要取消此执行吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlTask({
      executionId: selectedExecutionId.value,
      action: 'cancel',
      reason: controlReason.value
    })
    
    addOperationHistory('task', selectedExecutionId.value, 'cancel', controlReason.value, 'success')
    ElMessage.success('任务已取消')
  } catch (error) {
    if (error !== 'cancel') {
      addOperationHistory('task', selectedExecutionId.value, 'cancel', controlReason.value, 'failed')
      ElMessage.error('取消任务失败')
    }
  }
}

// 节点控制操作
const retryNode = async () => {
  if (!selectedExecutionId.value || !selectedNodeId.value) return
  
  try {
    let parameters = undefined
    if (nodeParameters.value) {
      try {
        parameters = JSON.parse(nodeParameters.value)
      } catch {
        ElMessage.error('节点参数格式错误，请输入有效的JSON')
        return
      }
    }
    
    await controlNode({
      executionId: selectedExecutionId.value,
      nodeId: selectedNodeId.value,
      action: 'retry',
      parameters
    })
    
    addOperationHistory('node', selectedNodeId.value, 'retry', nodeParameters.value, 'success')
    ElMessage.success('节点已重试')
  } catch {
    addOperationHistory('node', selectedNodeId.value, 'retry', nodeParameters.value, 'failed')
    ElMessage.error('重试节点失败')
  }
}

const skipNode = async () => {
  if (!selectedExecutionId.value || !selectedNodeId.value) return
  
  try {
    await ElMessageBox.confirm('确定要跳过此节点吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlNode({
      executionId: selectedExecutionId.value,
      nodeId: selectedNodeId.value,
      action: 'skip'
    })
    
    addOperationHistory('node', selectedNodeId.value, 'skip', '', 'success')
    ElMessage.success('节点已跳过')
  } catch (error) {
    if (error !== 'cancel') {
      addOperationHistory('node', selectedNodeId.value, 'skip', '', 'failed')
      ElMessage.error('跳过节点失败')
    }
  }
}

const forceCompleteNode = async () => {
  if (!selectedExecutionId.value || !selectedNodeId.value) return
  
  try {
    await ElMessageBox.confirm('确定要强制完成此节点吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlNode({
      executionId: selectedExecutionId.value,
      nodeId: selectedNodeId.value,
      action: 'force_complete'
    })
    
    addOperationHistory('node', selectedNodeId.value, 'force_complete', '', 'success')
    ElMessage.success('节点已强制完成')
  } catch (error) {
    if (error !== 'cancel') {
      addOperationHistory('node', selectedNodeId.value, 'force_complete', '', 'failed')
      ElMessage.error('强制完成节点失败')
    }
  }
}

// 更新优先级
const updatePriority = async () => {
  if (!priorityExecutionId.value) return
  
  try {
    await controlTask({
      executionId: priorityExecutionId.value,
      action: 'restart', // 使用重启操作来更新优先级
      reason: `更新优先级为${newPriority.value}`,
      priority: newPriority.value
    })
    
    addOperationHistory('task', priorityExecutionId.value, 'update_priority', `优先级: ${newPriority.value}`, 'success')
    ElMessage.success('优先级已更新')
  } catch {
    addOperationHistory('task', priorityExecutionId.value, 'update_priority', `优先级: ${newPriority.value}`, 'failed')
    ElMessage.error('更新优先级失败')
  }
}

// 批量操作
const executeBatchOperation = async () => {
  if (!batchOperation.value) return
  
  try {
    const targets = getBatchTargets()
    
    for (const target of targets) {
      await controlTask({
        executionId: target,
        action: batchOperation.value as unknown,
        reason: '批量操作'
      })
    }
    
    addOperationHistory('batch', `${targets.length}个执行`, batchOperation.value, batchForm.value.reason, 'success')
    ElMessage.success(`批量操作已完成，影响${targets.length}个执行`)
  } catch {
    addOperationHistory('batch', '', batchOperation.value, batchForm.value.reason, 'failed')
    ElMessage.error('批量操作失败')
  }
}

// 高级批量操作
const executeAdvancedBatchOperation = async () => {
  try {
    const targets = getAdvancedBatchTargets()
    
    for (const target of targets) {
      await controlTask({
        executionId: target,
        action: batchForm.value.operation as unknown,
        reason: batchForm.value.reason
      })
    }
    
    addOperationHistory('batch', `${targets.length}个执行`, batchForm.value.operation, batchForm.value.reason, 'success')
    ElMessage.success(`高级批量操作已完成，影响${targets.length}个执行`)
    showBatchDialog.value = false
  } catch {
    addOperationHistory('batch', '', batchForm.value.operation, batchForm.value.reason, 'failed')
    ElMessage.error('高级批量操作失败')
  }
}

// 获取批量操作目标
const getBatchTargets = (): string[] => {
  switch (batchOperation.value) {
    case 'retry-failed':
      return activeExecutions.value
        .filter(exec => exec.status === 'failed')
        .map(exec => exec.executionId)
    case 'skip-pending':
      return activeExecutions.value
        .filter(exec => exec.status === 'pending')
        .map(exec => exec.executionId)
    default:
      return activeExecutions.value
        .filter(exec => ['running', 'paused'].includes(exec.status))
        .map(exec => exec.executionId)
  }
}

// 获取高级批量操作目标
const getAdvancedBatchTargets = (): string[] => {
  return activeExecutions.value
    .filter(exec => {
      // 状态过滤
      if (batchForm.value.statusFilter.length > 0) {
        if (!batchForm.value.statusFilter.includes(exec.status)) {
          return false
        }
      }
      
      // TaskGraph过滤
      if (batchForm.value.graphFilter.length > 0) {
        if (!batchForm.value.graphFilter.includes(exec.graphId)) {
          return false
        }
      }
      
      // 目标选择
      if (batchForm.value.targets.includes('all')) {
        return true
      }
      
      if (batchForm.value.targets.includes('running') && exec.status === 'running') {
        return true
      }
      
      if (batchForm.value.targets.includes('pending') && exec.status === 'pending') {
        return true
      }
      
      if (batchForm.value.targets.includes('failed') && exec.status === 'failed') {
        return true
      }
      
      return false
    })
    .map(exec => exec.executionId)
}

// 添加操作历史
const addOperationHistory = (
  type: 'task' | 'node' | 'batch',
  target: string,
  action: string,
  reason: string,
  status: 'success' | 'failed'
) => {
  operationHistory.value.unshift({
    timestamp: new Date().toISOString(),
    type,
    target,
    action,
    reason,
    status
  })
  
  // 限制历史记录数量
  if (operationHistory.value.length > 100) {
    operationHistory.value = operationHistory.value.slice(0, 100)
  }
}

// 加载可用数据
const loadAvailableData = () => {
  const graphMap = new Map()
  activeExecutions.value.forEach(exec => {
    if (!graphMap.has(exec.graphId)) {
      graphMap.set(exec.graphId, { id: exec.graphId, name: exec.graphId })
    }
  })
  availableGraphs.value = Array.from(graphMap.values())
}

// 监听执行列表变化
watch(activeExecutions, () => {
  loadAvailableData()
})

onMounted(() => {
  loadAvailableData()
})
</script>

<style scoped>
.control-panel {
  height: 100%;
}

.control-card {
  height: 100%;
}

.control-status {
  display: flex;
  align-items: center;
}

.control-section {
  margin-bottom: 30px;
  padding: 20px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background-color: #fafafa;
}

.section-title {
  margin: 0 0 15px 0;
  font-size: 16px;
  font-weight: bold;
  color: #303133;
}

.task-controls,
.node-controls,
.batch-controls,
.priority-controls {
  margin-bottom: 15px;
}

.operation-history {
  max-height: 300px;
  overflow-y: auto;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .control-section .el-col {
    margin-bottom: 15px;
  }
  
  .task-controls .el-button-group,
  .node-controls .el-button-group {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  
  .batch-controls .el-col {
    margin-bottom: 15px;
  }
  
  .priority-controls .el-col {
    margin-bottom: 15px;
  }
}
</style>