<!--
  TODO项卡片组件
  显示单个TODO项的详细信息和操作按钮
-->
<template>
  <div class="todo-item-card" :class="{ completed: todo.status === TodoStatus.COMPLETED }">
    <!-- 复选框 -->
    <div class="todo-checkbox">
      <el-checkbox
        :model-value="todo.status === TodoStatus.COMPLETED"
        :disabled="loading.update"
        @change="handleToggleComplete"
      />
    </div>

    <!-- TODO内容 -->
    <div class="todo-content">
      <div class="todo-text" :class="{ completed: todo.status === TodoStatus.COMPLETED }">
        {{ todo.content }}
      </div>

      <!-- 元数据 -->
      <div class="todo-meta">
        <!-- 状态标签 -->
        <el-tag :type="statusType" size="small">
          {{ statusText }}
        </el-tag>

        <!-- 优先级标签 -->
        <el-tag :type="priorityType" size="small">
          {{ priorityText }}
        </el-tag>

        <!-- 时间 -->
        <span class="todo-time">
          {{ formatTime(todo.updated_at) }}
        </span>

        <!-- 任务节点 -->
        <el-tag v-if="showTaskNode" type="info" size="small">
          {{ taskNodeLabel }}
        </el-tag>
      </div>

      <!-- 子任务（如果有） -->
      <div v-if="todo.subtasks && todo.subtasks.length > 0" class="todo-subtasks">
        <div class="subtask-summary">
          子任务: {{ completedSubtasks }}/{{ todo.subtasks.length }}
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="todo-actions">
      <el-dropdown trigger="click" @command="handleAction">
        <el-button size="small" text :loading="loading.update">
          <el-icon><MoreFilled /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="edit" :disabled="todo.status === TodoStatus.COMPLETED">
              <el-icon><Edit /></el-icon>
              编辑
            </el-dropdown-item>
            <el-dropdown-item command="toggle" :disabled="loading.update">
              <el-icon>
                <Check v-if="todo.status !== TodoStatus.COMPLETED" />
                <RefreshLeft v-else />
              </el-icon>
              {{ todo.status === TodoStatus.COMPLETED ? '标记未完成' : '标记完成' }}
            </el-dropdown-item>
            <el-dropdown-item command="priority">
              <el-icon><Flag /></el-icon>
              优先级
            </el-dropdown-item>
            <el-dropdown-item divided command="delete" :disabled="loading.delete">
              <el-icon><Delete /></el-icon>
              删除
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑TODO"
      width="500px"
    >
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="内容">
          <el-input
            v-model="editForm.content"
            type="textarea"
            :rows="3"
            placeholder="请输入TODO内容"
          />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="editForm.priority" placeholder="请选择优先级">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="critical" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit" :loading="loading.update">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MoreFilled, Edit, Check, RefreshLeft, Flag, Delete } from '@element-plus/icons-vue'
import { TodoStatus } from '@/types/todos'
import type { TodoItemDetail } from '@/types/todos'
import { useTodoStore } from '@/stores/todoStore'

interface Props {
  todo: TodoItemDetail
  showTaskNode?: boolean
}

interface Emits {
  (e: 'update', todoId: string, updates: unknown): void
  (e: 'delete', todoId: string, taskNodeId: string): void
  (e: 'complete', todoId: string): void
}

const props = withDefaults(defineProps<Props>(), {
  showTaskNode: false
})

const emit = defineEmits<Emits>()

const todoStore = useTodoStore()

// 加载状态
const loading = ref({
  update: false,
  delete: false
})

// 编辑对话框
const editDialogVisible = ref(false)
const editForm = ref({
  content: '',
  priority: 'medium' as TodoItemDetail['priority']
})

// 计算属性
const statusType = computed(() => {
  switch (props.todo.status) {
    case TodoStatus.PENDING:
      return 'info'
    case TodoStatus.IN_PROGRESS:
      return 'warning'
    case TodoStatus.COMPLETED:
      return 'success'
    default:
      return 'info'
  }
})

const statusText = computed(() => {
  switch (props.todo.status) {
    case TodoStatus.PENDING:
      return '待处理'
    case TodoStatus.IN_PROGRESS:
      return '进行中'
    case TodoStatus.COMPLETED:
      return '已完成'
    default:
      return '未知'
  }
})

const priorityType = computed(() => {
  switch (props.todo.priority) {
    case 'low':
      return 'info'
    case 'medium':
      return ''
    case 'high':
      return 'warning'
    case 'critical':
      return 'danger'
    default:
      return ''
  }
})

const priorityText = computed(() => {
  const map = {
    low: '低',
    medium: '中',
    high: '高',
    critical: '紧急'
  }
  return map[props.todo.priority] || '中'
})

const taskNodeLabel = computed(() => {
  return props.todo.task_node_id?.substring(0, 8) + '...'
})

const completedSubtasks = computed(() => {
  if (!props.todo.subtasks) return 0
  return props.todo.subtasks.filter(st => st.status === TodoStatus.COMPLETED).length
})

// 方法
function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString()
}

async function handleToggleComplete() {
  const newStatus = props.todo.status === TodoStatus.COMPLETED
    ? TodoStatus.PENDING
    : TodoStatus.COMPLETED

  loading.value.update = true
  try {
    await todoStore.updateTodo({
      todo_id: props.todo.id,
      task_node_id: props.todo.task_node_id || '',
      status: newStatus
    })
    ElMessage.success('TODO状态已更新')
    emit('update', props.todo.id, { status: newStatus })
  } catch (error: unknown) {
    ElMessage.error(`更新失败: ${error.message}`)
  } finally {
    loading.value.update = false
  }
}

function handleAction(command: string) {
  switch (command) {
    case 'edit':
      openEditDialog()
      break
    case 'toggle':
      handleToggleComplete()
      break
    case 'priority':
      // 优先级选择可以在下拉菜单中实现
      ElMessage.info('请在编辑对话框中修改优先级')
      openEditDialog()
      break
    case 'delete':
      handleDelete()
      break
  }
}

function openEditDialog() {
  editForm.value = {
    content: props.todo.content,
    priority: props.todo.priority
  }
  editDialogVisible.value = true
}

async function handleSaveEdit() {
  loading.value.update = true
  try {
    await todoStore.updateTodo({
      todo_id: props.todo.id,
      task_node_id: props.todo.task_node_id || '',
      content: editForm.value.content,
      priority: editForm.value.priority
    })
    ElMessage.success('TODO已更新')
    editDialogVisible.value = false
    emit('update', props.todo.id, {
      content: editForm.value.content,
      priority: editForm.value.priority
    })
  } catch (error: unknown) {
    ElMessage.error(`更新失败: ${error.message}`)
  } finally {
    loading.value.update = false
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(
      `确定要删除TODO "${props.todo.content}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    loading.value.delete = true
    await todoStore.batchOperation({
      task_node_id: props.todo.task_node_id || '',
      todo_ids: [props.todo.id],
      operation: 'delete'
    })

    ElMessage.success('TODO已删除')
    emit('delete', props.todo.id, props.todo.task_node_id || '')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(`删除失败: ${error.message}`)
    }
  } finally {
    loading.value.delete = false
  }
}
</script>

<style scoped>
.todo-item-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  transition: all 0.3s;
}

.todo-item-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.todo-item-card.completed {
  opacity: 0.7;
}

.todo-checkbox {
  padding-top: 2px;
}

.todo-content {
  flex: 1;
  min-width: 0;
}

.todo-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
  word-break: break-word;
}

.todo-text.completed {
  text-decoration: line-through;
  color: var(--el-text-color-secondary);
}

.todo-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.todo-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.todo-subtasks {
  margin-top: 8px;
}

.subtask-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.todo-actions {
  flex-shrink: 0;
}
</style>
