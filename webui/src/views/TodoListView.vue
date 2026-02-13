/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { ref, onMounted, computed } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import type { TodoItem } from "../types/graph"
import { TodoStatus } from "../types/graph"
import { graphsApi } from "../services/api/services/graphs"

const props = defineProps<{
  graphId: string
  taskId: string
}>()

const emit = defineEmits<{
  (e: "update", todos: TodoItem[]): void
}>()

const loading = ref(true)
const error = ref<string | null>(null)
const todos = ref<TodoItem[]>([])
const newTodoContent = ref("")
const editingTodoId = ref<string | null>(null)
const editContent = ref("")

// 加载 TODO 列表
const loadTodos = async () => {
  if (!props.taskId) return
  loading.value = true
  error.value = null
  try {
    todos.value = await graphsApi.updateTodos(props.graphId, props.taskId, { todos: [] }) as unknown as TodoItem[]
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load todos"
    console.error("Failed to load todos:", e)
  } finally {
    loading.value = false
  }
}

// 添加 TODO
const addTodo = async () => {
  if (!newTodoContent.value.trim()) {
    ElMessage.warning("请输入 TODO 内容")
    return
  }

  try {
    const newTodo: TodoItem = {
      id: crypto.randomUUID(),
      content: newTodoContent.value.trim(),
      status: TodoStatus.PENDING,
    }

    const updatedTodos = [...todos.value, newTodo]
    await saveTodos(updatedTodos)
    newTodoContent.value = ""
    ElMessage.success("已添加 TODO")
  } catch (e) {
    ElMessage.error("添加 TODO 失败")
    console.error("Failed to add todo:", e)
  }
}

// 保存 TODO 列表
const saveTodos = async (newTodos: TodoItem[]) => {
  try {
    await graphsApi.updateTodos(props.graphId, props.taskId, { todos: newTodos })
    todos.value = newTodos
    emit("update", newTodos)
  } catch (e) {
    throw e
  }
}

// 切换 TODO 状态
const toggleTodoStatus = async (todo: TodoItem) => {
  const newStatus =
    todo.status === TodoStatus.PENDING
      ? TodoStatus.IN_PROGRESS
      : todo.status === TodoStatus.IN_PROGRESS
        ? TodoStatus.COMPLETED
        : TodoStatus.PENDING

  const updatedTodos = todos.value.map((t: TodoItem) =>
    t.id === todo.id ? { ...t, status: newStatus } : t
  )

  try {
    await saveTodos(updatedTodos)
    ElMessage.success("状态已更新")
  } catch (e) {
    ElMessage.error("更新状态失败")
    console.error("Failed to toggle todo status:", e)
  }
}

// 删除 TODO
const deleteTodo = async (todo: TodoItem) => {
  try {
    await ElMessageBox.confirm(`确定要删除 TODO "${todo.content}" 吗？`, "确认删除", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    })

    const updatedTodos = todos.value.filter((t: TodoItem) => t.id !== todo.id)
    await saveTodos(updatedTodos)
    ElMessage.success("已删除 TODO")
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error("删除 TODO 失败")
      console.error("Failed to delete todo:", e)
    }
  }
}

// 开始编辑
const startEdit = (todo: TodoItem) => {
  editingTodoId.value = todo.id
  editContent.value = todo.content
}

// 保存编辑
const saveEdit = async (todo: TodoItem) => {
  if (!editContent.value.trim()) {
    ElMessage.warning("TODO 内容不能为空")
    return
  }

  const updatedTodos = todos.value.map((t: TodoItem) =>
    t.id === todo.id ? { ...t, content: editContent.value.trim() } : t
  )

  try {
    await saveTodos(updatedTodos)
    editingTodoId.value = null
    ElMessage.success("已更新 TODO")
  } catch (e) {
    ElMessage.error("更新 TODO 失败")
    console.error("Failed to update todo:", e)
  }
}

// 取消编辑
const cancelEdit = () => {
  editingTodoId.value = null
  editContent.value = ""
}

// 统计信息
const stats = computed(() => {
  const total = todos.value.length
  const completed = todos.value.filter((t: TodoItem) => t.status === TodoStatus.COMPLETED).length
  const inProgress = todos.value.filter((t: TodoItem) => t.status === TodoStatus.IN_PROGRESS).length
  const pending = todos.value.filter((t: TodoItem) => t.status === TodoStatus.PENDING).length
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, inProgress, pending, progress }
})

// 获取状态类型
const getStatusType = (status: TodoStatus): "" | "success" | "warning" | "info" => {
  const types: Record<string, "" | "success" | "warning" | "info"> = {
    pending: "info",
    in_progress: "warning",
    completed: "success",
  }
  return types[status] || "info"
}

onMounted(() => {
  loadTodos()
})
</script>

<template>
  <div class="todo-list-view">
    <!-- 头部 -->
    <div class="header">
      <h3>TODO 列表</h3>
      <div class="stats">
        <span class="stat-item">
          总计: {{ stats.total }}
        </span>
        <span class="stat-item completed">
          已完成: {{ stats.completed }}
        </span>
        <span class="stat-item in-progress">
          进行中: {{ stats.inProgress }}
        </span>
        <span class="stat-item pending">
          待处理: {{ stats.pending }}
        </span>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="progress-section">
      <el-progress :percentage="stats.progress" :stroke-width="8">
        <span class="progress-text">完成进度</span>
      </el-progress>
    </div>

    <!-- 添加 TODO -->
    <div class="add-todo">
      <el-input
        v-model="newTodoContent"
        placeholder="添加新的 TODO..."
        @keyup.enter="addTodo"
        clearable
      >
        <template #append>
          <el-button @click="addTodo">
            <el-icon><Plus /></el-icon>
          </el-button>
        </template>
      </el-input>
    </div>

    <!-- 错误提示 -->
    <el-alert v-if="error" :title="error" type="error" show-icon class="error-alert" />

    <!-- TODO 列表 -->
    <div v-loading="loading" class="todo-container">
      <transition-group name="todo-list" tag="div" class="todo-list">
        <div
          v-for="todo in todos"
          :key="todo.id"
          class="todo-item"
          :class="{ completed: todo.status === TodoStatus.COMPLETED }"
        >
          <!-- 状态复选框 -->
          <el-checkbox
            :model-value="todo.status === TodoStatus.COMPLETED"
            @change="toggleTodoStatus(todo)"
            class="todo-checkbox"
          />

          <!-- 编辑模式 -->
          <template v-if="editingTodoId === todo.id">
            <el-input
              v-model="editContent"
              class="edit-input"
              @keyup.enter="saveEdit(todo)"
              @keyup.escape="cancelEdit"
              autofocus
            />
            <el-button-group class="edit-actions">
              <el-button type="primary" size="small" @click="saveEdit(todo)">
                保存
              </el-button>
              <el-button size="small" @click="cancelEdit">取消</el-button>
            </el-button-group>
          </template>

          <!-- 显示模式 -->
          <template v-else>
            <span class="todo-content" @dblclick="startEdit(todo)">
              {{ todo.content }}
            </span>
            <div class="todo-actions">
              <el-tag :type="getStatusType(todo.status)" size="small">
                {{ todo.status === TodoStatus.PENDING ? "待处理" : todo.status === TodoStatus.IN_PROGRESS ? "进行中" : "已完成" }}
              </el-tag>
              <el-button-group size="small">
                <el-button @click="startEdit(todo)">
                  <el-icon><Edit /></el-icon>
                </el-button>
                <el-button type="danger" @click="deleteTodo(todo)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-button-group>
            </div>
          </template>
        </div>
      </transition-group>

      <el-empty v-if="!loading && todos.length === 0" description="暂无 TODO 数据">
        <template #description>
          <p>添加一个 TODO 开始追踪任务</p>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<style scoped>
.todo-list-view {
  padding: 16px;
  height: 100%;
  overflow: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
}

.stat-item {
  color: #606266;
}

.stat-item.completed {
  color: #67c23a;
}

.stat-item.in-progress {
  color: #e6a23c;
}

.stat-item.pending {
  color: #909399;
}

.progress-section {
  margin-bottom: 16px;
}

.progress-text {
  font-size: 12px;
  color: #909399;
}

.add-todo {
  margin-bottom: 16px;
}

.error-alert {
  margin-bottom: 16px;
}

.todo-container {
  min-height: 100px;
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 6px;
  transition: all 0.3s;
}

.todo-item:hover {
  background: #ecf5ff;
}

.todo-item.completed {
  opacity: 0.6;
}

.todo-item.completed .todo-content {
  text-decoration: line-through;
}

.todo-checkbox {
  flex-shrink: 0;
}

.todo-content {
  flex: 1;
  cursor: pointer;
  word-break: break-word;
}

.edit-input {
  flex: 1;
}

.edit-actions {
  flex-shrink: 0;
}

.todo-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* 过渡动画 */
.todo-list-enter-active,
.todo-list-leave-active {
  transition: all 0.3s ease;
}

.todo-list-enter-from,
.todo-list-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

.todo-list-move {
  transition: transform 0.3s ease;
}
</style>
