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
            <el-button 
              size="small" 
              @click="zoomIn"
              :disabled="zoomLevel >= maxZoom"
            >
              <el-icon><ZoomIn /></el-icon>
            </el-button>
            <el-button 
              size="small" 
              @click="zoomOut"
              :disabled="zoomLevel <= minZoom"
            >
              <el-icon><ZoomOut /></el-icon>
            </el-button>
            <el-button size="small" @click="resetZoom">
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

      <!-- 图形容器 -->
      <div 
        ref="graphContainerRef" 
        class="graph-container"
        @wheel="handleWheel"
        @mousedown="handleMouseDown"
        @mousemove="handleMouseMove"
        @mouseup="handleMouseUp"
        @mouseleave="handleMouseUp"
      >
        <div class="graph-content">
          <!-- 简化的SVG图形表示 -->
          <div class="simple-graph">
            <div class="graph-nodes">
              <template v-for="node in layoutNodes" :key="node.id">
                <!-- 节点 -->
                <div
                  class="graph-node"
                  :class="getNodeClass(node.status)"
                  @click="selectNode(node, $event)"
                >
                  <div class="node-icon">{{ getNodeIcon(node.type) }}</div>
                  <div class="node-name">{{ node.name || node.id }}</div>
                  <div class="node-status">{{ getStatusText(node.status) }}</div>
                  <div v-if="node.progress !== undefined" class="node-progress">
                    <div class="progress-bar" :style="{ width: node.progress + '%' }"></div>
                  </div>
                </div>

                <!-- 连接线 -->
                <div
                  v-for="dep in getNodeDependencies(node.id)"
                  :key="`${node.id}-${dep}`"
                  class="node-connection"
                  :class="getConnectionClass(node.id, dep)"
                ></div>
              </template>
            </div>
          </div>
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

    <!-- 节点详情弹窗 -->
    <div
      v-if="selectedNodeDetail"
      ref="nodeTooltipRef"
      class="node-tooltip"
      :style="tooltipStyle"
    >
      <div class="tooltip-header">
        <h4>{{ selectedNodeDetail.name || selectedNodeDetail.id }}</h4>
        <el-button
          size="small"
          text
          @click="hideNodeTooltip"
        >
          <el-icon><CircleClose /></el-icon>
        </el-button>
      </div>
      
      <div class="tooltip-content">
        <el-descriptions :column="1" size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusTagType(selectedNodeDetail.status)" size="small">
              {{ getStatusText(selectedNodeDetail.status) }}
            </el-tag>
          </el-descriptions-item>
          
          <el-descriptions-item label="类型">
            {{ selectedNodeDetail.type }}
          </el-descriptions-item>
          
          <el-descriptions-item label="开始时间">
            {{ formatTimestamp(selectedNodeDetail.startTime, 'time') }}
          </el-descriptions-item>
          
          <el-descriptions-item v-if="selectedNodeDetail.endTime" label="结束时间">
            {{ formatTimestamp(selectedNodeDetail.endTime, 'time') }}
          </el-descriptions-item>
          
          <el-descriptions-item v-if="selectedNodeDetail.duration" label="执行时长">
            {{ formatDuration(selectedNodeDetail.duration, 'standard') }}
          </el-descriptions-item>
          
          <el-descriptions-item v-if="selectedNodeDetail.retryCount > 0" label="重试次数">
            {{ selectedNodeDetail.retryCount }}
          </el-descriptions-item>
          
          <el-descriptions-item v-if="selectedNodeDetail.error" label="错误信息">
            <el-text type="danger" size="small">
              {{ selectedNodeDetail.error }}
            </el-text>
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 控制按钮 -->
        <div class="node-controls" v-if="canControlNode(selectedNodeDetail)">
          <el-button 
            v-if="selectedNodeDetail.status === 'failed'"
            size="small" 
            type="primary"
            @click="retryNode(selectedNodeDetail)"
          >
            重试
          </el-button>
          <el-button 
            v-if="['pending', 'running'].includes(selectedNodeDetail.status)"
            size="small" 
            type="warning"
            @click="skipNode(selectedNodeDetail)"
          >
            跳过
          </el-button>
          <el-button 
            v-if="['pending', 'running'].includes(selectedNodeDetail.status)"
            size="small" 
            type="success"
            @click="forceCompleteNode(selectedNodeDetail)"
          >
            强制完成
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useMonitoringStore } from '@/stores/monitoring'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ZoomIn, ZoomOut, Refresh, CircleClose } from '@element-plus/icons-vue'
import { formatTimestamp, formatDuration } from '@/utils/formatters'
import { storeToRefs } from 'pinia'
import type {
  TaskGraphNode,
  NodeStatus
} from '@/types/monitoring'

const monitoringStore = useMonitoringStore()
const { state } = storeToRefs(monitoringStore)
const {
  controlNode,
  selectExecution
} = monitoringStore

// Access active executions from state
const activeExecutions = computed(() => state.value.activeExecutions)
const selectedExecutionId = ref('')

// 图形参数
// const svgWidth = ref(800)
// const svgHeight = ref(600)
const zoomLevel = ref(1)
const minZoom = 0.5
const maxZoom = 3

// 交互状态
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const panOffset = ref({ x: 0, y: 0 })

// 节点详情
const selectedNodeDetail = ref<TaskGraphNode | null>(null)
const tooltipPosition = ref({ x: 0, y: 0 })

// 当前执行
const currentExecution = computed(() => {
  if (!selectedExecutionId.value) return null
  return activeExecutions.value.find(exec => exec.executionId === selectedExecutionId.value)
})

// 布局后的节点
const layoutNodes = computed(() => {
  const execution = currentExecution.value
  if (!execution || !execution.nodes) return []
  
  // 简单的网格布局
  const nodes = execution.nodes
  const cols = Math.ceil(Math.sqrt(nodes.length))

  const layoutNodes: Array<TaskGraphNode & { x: number; y: number }> = []

  nodes.forEach((node: TaskGraphNode, index: number) => {
    const row = Math.floor(index / cols)
    const col = index % cols
    
    layoutNodes.push({
      ...node,
      x: col * 120 + 60,
      y: row * 120 + 60
    })
  })
  
  return layoutNodes
})

// 获取节点样式类
const getNodeClass = (status: NodeStatus): string => {
  return `node-${status}`
}

// 获取节点图标
const getNodeIcon = (type: string): string => {
  const icons: Record<string, string> = {
    'tool': '🔧',
    'llm': '🤖',
    'file': '📄',
    'api': '🌐',
    'data': '💾',
    'default': '⚙️'
  }
  const icon = icons[type] ?? icons.default
  return icon as string
}

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

// 获取连接线样式类
const getConnectionClass = (fromId: string, toId: string): string => {
  if (!currentExecution.value?.nodes) return ''

  const fromNode = currentExecution.value.nodes.find((n: TaskGraphNode) => n.id === fromId)
  const toNode = currentExecution.value.nodes.find((n: TaskGraphNode) => n.id === toId)

  if (!fromNode || !toNode) return ''

  const fromStatus = fromNode.status
  const toStatus = toNode.status

  if (fromStatus === 'completed' && toStatus === 'completed') {
    return 'connection-success'
  } else if (fromStatus === 'failed' || toStatus === 'failed') {
    return 'connection-error'
  } else if (fromStatus === 'running' || toStatus === 'running') {
    return 'connection-active'
  } else {
    return 'connection-pending'
  }
}

// 获取节点依赖
const getNodeDependencies = (nodeId: string): string[] => {
  if (!currentExecution.value?.nodes) return []
  const node = currentExecution.value.nodes.find((n: TaskGraphNode) => n.id === nodeId)
  if (!node) return []
  return node.dependencies || []
}

// 判断是否可以控制节点
const canControlNode = (node: TaskGraphNode | null): boolean => {
  if (!node) return false
  return ['failed', 'pending', 'running'].includes(node.status)
}

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 工具提示样式
const tooltipStyle = computed(() => ({
  left: `${tooltipPosition.value.x}px`,
  top: `${tooltipPosition.value.y}px`
}))

// 缩放功能
const zoomIn = () => {
  if (zoomLevel.value < maxZoom) {
    zoomLevel.value += 0.2
  }
}

const zoomOut = () => {
  if (zoomLevel.value > minZoom) {
    zoomLevel.value -= 0.2
  }
}

const resetZoom = () => {
  zoomLevel.value = 1
  panOffset.value = { x: 0, y: 0 }
}

// 鼠标事件处理
const handleWheel = (event: WheelEvent) => {
  event.preventDefault()
  const delta = event.deltaY > 0 ? -0.1 : 0.1
  const newZoom = Math.max(minZoom, Math.min(maxZoom, zoomLevel.value + delta))
  zoomLevel.value = newZoom
}

const handleMouseDown = (event: MouseEvent) => {
  isDragging.value = true
  dragStart.value = { x: event.clientX, y: event.clientY }
}

const handleMouseMove = (event: MouseEvent) => {
  if (!isDragging.value) return
  
  const deltaX = event.clientX - dragStart.value.x
  const deltaY = event.clientY - dragStart.value.y
  
  panOffset.value.x += deltaX
  panOffset.value.y += deltaY
  
  dragStart.value = { x: event.clientX, y: event.clientY }
}

const handleMouseUp = () => {
  isDragging.value = false
}

// 选择节点
const selectNode = (node: TaskGraphNode, event: MouseEvent) => {
  selectedNodeDetail.value = node
  tooltipPosition.value = {
    x: event.clientX + 10,
    y: event.clientY + 10
  }
}

// 隐藏节点详情
const hideNodeTooltip = () => {
  selectedNodeDetail.value = null
}

// 执行变化处理
const onExecutionChange = () => {
  selectExecution(selectedExecutionId.value)
}

// 节点控制操作
const retryNode = async (node: TaskGraphNode) => {
  if (!currentExecution.value) return
  
  try {
    await controlNode({
      executionId: currentExecution.value.executionId,
      nodeId: node.id,
      action: 'retry'
    })
    ElMessage.success('节点重试已发送')
  } catch {
    ElMessage.error('节点重试失败')
  }
}

const skipNode = async (node: TaskGraphNode) => {
  if (!currentExecution.value) return
  
  try {
    await ElMessageBox.confirm('确定要跳过此节点吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlNode({
      executionId: currentExecution.value.executionId,
      nodeId: node.id,
      action: 'skip'
    })
    ElMessage.success('节点跳过已发送')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('节点跳过失败')
    }
  }
}

const forceCompleteNode = async (node: TaskGraphNode) => {
  if (!currentExecution.value) return
  
  try {
    await ElMessageBox.confirm('确定要强制完成此节点吗？', '确认操作', {
      type: 'warning'
    })
    
    await controlNode({
      executionId: currentExecution.value.executionId,
      nodeId: node.id,
      action: 'force_complete'
    })
    ElMessage.success('强制完成已发送')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('强制完成失败')
    }
  }
}

// 监听执行变化
watch(selectedExecutionId, (newExecutionId) => {
  if (newExecutionId) {
    selectedNodeDetail.value = null
  }
})

onMounted(() => {
  // 初始化时选择第一个执行
  if (activeExecutions.value && activeExecutions.value.length > 0 && activeExecutions.value[0]) {
    selectedExecutionId.value = activeExecutions.value[0].executionId
  }
})

onUnmounted(() => {
  // 清理资源
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

.graph-container {
  position: relative;
  width: 100%;
  height: 500px;
  border: 1px solid #ddd;
  border-radius: 4px;
  overflow: hidden;
  cursor: grab;
}

.graph-container:active {
  cursor: grabbing;
}

.graph-content {
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: 20px;
}

.simple-graph {
  position: relative;
  width: 100%;
  height: 100%;
}

.graph-nodes {
  position: relative;
  width: 100%;
  height: 100%;
}

.graph-node {
  position: absolute;
  width: 100px;
  height: 80px;
  border: 2px solid #ddd;
  border-radius: 8px;
  background-color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
}

.graph-node:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.node-pending {
  border-color: #e6a23c;
  background-color: #fdf6ec;
}

.node-running {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.node-completed {
  border-color: #67c23a;
  background-color: #f0f9ff;
}

.node-failed {
  border-color: #f56c6c;
  background-color: #fef0f0;
}

.node-skipped {
  border-color: #909399;
  background-color: #f0f9ff;
}

.node-cancelled {
  border-color: #c0c4cc;
  background-color: #f0f0f0;
}

.node-icon {
  font-size: 24px;
  margin-bottom: 5px;
}

.node-name {
  font-weight: bold;
  margin-bottom: 5px;
  text-align: center;
}

.node-status {
  font-size: 12px;
  color: #666;
  text-align: center;
}

.node-progress {
  width: 100%;
  height: 4px;
  background-color: #e4e7ed;
  border-radius: 2px;
  margin-top: 5px;
}

.progress-bar {
  height: 100%;
  background-color: #409eff;
  border-radius: 2px;
  transition: width 0.3s;
}

.node-connection {
  position: absolute;
  background-color: #ddd;
  z-index: -1;
}

.connection-success {
  background-color: #67c23a;
}

.connection-error {
  background-color: #f56c6c;
}

.connection-active {
  background-color: #409eff;
}

.connection-pending {
  background-color: #e6a23c;
}

.execution-stats {
  margin-top: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.node-tooltip {
  position: fixed;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  max-width: 400px;
  max-height: 500px;
  overflow-y: auto;
}

.tooltip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid #eee;
}

.tooltip-header h4 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.tooltip-content {
  padding: 15px;
}

.node-controls {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #eee;
  display: flex;
  gap: 8px;
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
  
  .graph-container {
    height: 400px;
  }
  
  .graph-node {
    width: 80px;
    height: 60px;
    padding: 5px;
  }
  
  .node-icon {
    font-size: 18px;
    margin-bottom: 3px;
  }
  
  .node-name {
    font-size: 12px;
    margin-bottom: 3px;
  }
  
  .node-status {
    font-size: 10px;
  }
  
  .node-tooltip {
    max-width: 300px;
    max-height: 400px;
  }
}

@media (max-width: 480px) {
  .graph-legend {
    flex-direction: column;
    gap: 5px;
  }
  
  .graph-container {
    height: 300px;
  }
  
  .graph-node {
    width: 60px;
    height: 50px;
    padding: 3px;
  }
  
  .node-icon {
    font-size: 16px;
    margin-bottom: 2px;
  }
  
  .node-name {
    font-size: 10px;
    margin-bottom: 2px;
  }
  
  .node-status {
    font-size: 9px;
  }
  
  .node-tooltip {
    max-width: 250px;
    max-height: 300px;
  }
}
</style>