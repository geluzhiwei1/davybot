<!--
任务控制按钮组件
提供暂停、恢复、停止等控制功能
-->

<template>
  <div class="task-control-buttons">
    <!-- 暂停按钮 -->
    <el-tooltip content="暂停任务" placement="top" v-if="canPause">
      <el-button
        :icon="VideoPause"
        size="small"
        type="warning"
        circle
        @click="handlePause"
        :loading="loading.pause"
      />
    </el-tooltip>

    <!-- 恢复按钮 -->
    <el-tooltip content="恢复任务" placement="top" v-if="canResume">
      <el-button
        :icon="VideoPlay"
        size="small"
        type="success"
        circle
        @click="handleResume"
        :loading="loading.resume"
      />
    </el-tooltip>

    <!-- 停止按钮 -->
    <el-tooltip content="停止任务" placement="top" v-if="canStop">
      <el-button
        :icon="CircleClose"
        size="small"
        type="danger"
        circle
        @click="handleStop"
        :loading="loading.stop"
      />
    </el-tooltip>

    <!-- 重试按钮 -->
    <el-tooltip content="重试任务" placement="top" v-if="canRetry">
      <el-button
        :icon="RefreshRight"
        size="small"
        type="primary"
        circle
        @click="handleRetry"
        :loading="loading.retry"
      />
    </el-tooltip>
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
  VideoPause,
  VideoPlay,
  CircleClose,
  RefreshRight
} from '@element-plus/icons-vue'
import type { ParallelTaskInfo } from '@/types/parallelTasks'
import { ParallelTaskState as TaskState } from '@/types/parallelTasks'
import { useConnectionStore } from '@/stores/connection'
import { MessageType } from '@/services/websocket/types'

interface Props {
  task: ParallelTaskInfo
}

const props = defineProps<Props>()

const emit = defineEmits<{
  pause: [task: ParallelTaskInfo]
  resume: [task: ParallelTaskInfo]
  stop: [task: ParallelTaskInfo]
  retry: [task: ParallelTaskInfo]
}>()

// WebSocket连接store
const connectionStore = useConnectionStore()

// 加载状态
const loading = ref({
  pause: false,
  resume: false,
  stop: false,
  retry: false
})

// 计算属性：控制按钮显示
const canPause = computed(() => {
  return props.task.state === TaskState.RUNNING
})

const canResume = computed(() => {
  return props.task.state === TaskState.PAUSED
})

const canStop = computed(() => {
  return [
    TaskState.RUNNING,
    TaskState.PENDING,
    TaskState.PAUSED
  ].includes(props.task.state)
})

const canRetry = computed(() => {
  return props.task.state === TaskState.FAILED
})

// 暂停任务
async function handlePause() {
  try {
    loading.value.pause = true

    // 发送暂停请求到后端
    await connectionStore.send({
      type: MessageType.TASK_NODE_PAUSE,
      task_node_id: props.task.taskId,
      reason: 'User requested'
    })

    emit('pause', props.task)
    ElMessage.success('暂停请求已发送')
  } catch (error: unknown) {
    ElMessage.error(`暂停失败: ${error.message}`)
  } finally {
    loading.value.pause = false
  }
}

// 恢复任务
async function handleResume() {
  try {
    loading.value.resume = true

    // 发送恢复请求到后端
    await connectionStore.send({
      type: MessageType.TASK_NODE_RESUME,
      task_node_id: props.task.taskId
    })

    emit('resume', props.task)
    ElMessage.success('恢复请求已发送')
  } catch (error: unknown) {
    ElMessage.error(`恢复失败: ${error.message}`)
  } finally {
    loading.value.resume = false
  }
}

// 停止任务
async function handleStop() {
  try {
    await ElMessageBox.confirm(
      `确定要停止任务 "${props.task.description}" 吗？此操作不可撤销。`,
      '确认停止',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    loading.value.stop = true

    // 发送停止请求到后端
    await connectionStore.send({
      type: MessageType.TASK_NODE_STOP,
      task_node_id: props.task.taskId,
      reason: 'User requested stop'
    })

    emit('stop', props.task)
    ElMessage.success('停止请求已发送')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(`停止失败: ${error.message}`)
    }
  } finally {
    loading.value.stop = false
  }
}

// 重试任务
async function handleRetry() {
  try {
    await ElMessageBox.confirm(
      `确定要重试任务 "${props.task.description}" 吗？`,
      '确认重试',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'info'
      }
    )

    loading.value.retry = true

    // 发送重试请求 - 使用task_node_start重新启动任务
    await connectionStore.send({
      type: MessageType.TASK_NODE_START,
      task_node_id: props.task.taskId,
      parent_node_id: props.task.taskNodeId,
      node_type: props.task.nodeType,
      description: props.task.description
    })

    emit('retry', props.task)
    ElMessage.success('重试请求已发送')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(`重试失败: ${error.message}`)
    }
  } finally {
    loading.value.retry = false
  }
}
</script>

<style scoped lang="scss">
.task-control-buttons {
  display: flex;
  gap: 4px;
}
</style>
