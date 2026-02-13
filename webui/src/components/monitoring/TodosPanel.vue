<!--
  TODO系统观察面板
  提供完整的TODO列表观察和操作功能
-->
<template>
  <div class="todos-panel">
    <!-- 统计摘要头部 -->
    <div class="todos-header">
      <el-row :gutter="20">
        <el-col :span="6">
          <el-statistic title="总TODO" :value="statistics.total_todos">
            <template #suffix>
              <el-icon><List /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="已完成" :value="statistics.completed_todos">
            <template #suffix>
              <el-icon><CircleCheck /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="进行中" :value="statistics.in_progress_todos">
            <template #suffix>
              <el-icon><Loading /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="完成率" :value="statistics.overall_completion_rate" suffix="%">
            <template #prefix>
              <el-icon><TrendCharts /></el-icon>
            </template>
          </el-statistic>
        </el-col>
      </el-row>
    </div>

    <!-- 工具栏 -->
    <div class="todos-toolbar">
      <el-row :gutter="15" align="middle">
        <!-- 视图模式 -->
        <el-col :span="6">
          <el-select v-model="viewModeSelect" placeholder="视图模式" @change="handleViewModeChange">
            <el-option label="全部" value="all" />
            <el-option label="活跃" value="active" />
            <el-option label="已完成" value="completed" />
            <el-option label="按任务" value="by_task" />
            <el-option label="按优先级" value="by_priority" />
          </el-select>
        </el-col>

        <!-- 排序 -->
        <el-col :span="5">
          <el-select v-model="sortBySelect" placeholder="排序方式" @change="handleSortChange">
            <el-option label="创建时间" value="created_at" />
            <el-option label="更新时间" value="updated_at" />
            <el-option label="优先级" value="priority" />
            <el-option label="状态" value="status" />
          </el-select>
        </el-col>

        <!-- 搜索 -->
        <el-col :span="8">
          <el-input
            v-model="searchQuery"
            placeholder="搜索TODO内容或任务ID..."
            clearable
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>

        <!-- 操作按钮 -->
        <el-col :span="5">
          <el-space>
            <el-button @click="handleClearCompleted" :disabled="statistics.completed_todos === 0">
              <el-icon><Delete /></el-icon>
              清除已完成
            </el-button>
            <el-dropdown @command="handleBatchOperation">
              <el-button>
                批量操作
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="complete_all">
                    <el-icon><CircleCheck /></el-icon>
                    全部完成
                  </el-dropdown-item>
                  <el-dropdown-item command="uncomplete_all">
                    <el-icon><RefreshLeft /></el-icon>
                    全部未完成
                  </el-dropdown-item>
                  <el-dropdown-item command="delete_completed" divided>
                    <el-icon><Delete /></el-icon>
                    删除已完成
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </el-space>
        </el-col>
      </el-row>
    </div>

    <!-- 最活跃任务提示 -->
    <div v-if="statistics.most_active_task" class="most-active-task">
      <el-alert
        :title="`最活跃任务: ${statistics.most_active_task}`"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <!-- TODO列表内容 -->
    <div class="todos-content">
      <!-- 空状态 -->
      <el-empty
        v-if="filteredTodos.length === 0"
        :description="emptyText"
        :image-size="200"
      >
        <el-button v-if="hasFilters" type="primary" @click="handleClearFilters">
          清除筛选条件
        </el-button>
      </el-empty>

      <!-- 按任务分组显示 -->
      <template v-else>
        <!-- by_task 模式 -->
        <div v-if="viewMode === 'by_task'" class="todo-groups">
          <el-collapse v-model="activeGroups">
            <el-collapse-item
              v-for="group in groupedByTask"
              :key="group.task_node_id"
              :name="group.task_node_id"
            >
              <template #title>
                <div class="group-header">
                  <div class="group-info">
                    <el-icon class="group-icon"><Folder /></el-icon>
                    <span class="group-name">{{ group.task_description }}</span>
                    <el-tag size="small">{{ group.task_mode }}</el-tag>
                  </div>
                  <div class="group-stats">
                    <el-progress
                      :percentage="group.summary.percentage"
                      :stroke-width="8"
                      :color="getProgressColor(group.summary.percentage)"
                    />
                    <span class="group-count">{{ group.summary.completed }}/{{ group.summary.total }}</span>
                  </div>
                </div>
              </template>

              <!-- 该组的TODO项 -->
              <div class="group-todos">
                <TodoItemCard
                  v-for="todo in sortedTodos(group.todos)"
                  :key="todo.id"
                  :todo="todo"
                  :show-task-node="false"
                  @update="handleTodoUpdate"
                  @delete="handleTodoDelete"
                />
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- by_priority 模式 -->
        <div v-else-if="viewMode === 'by_priority'" class="todo-priorities">
          <el-tabs v-model="activePriority">
            <el-tab-pane label="紧急" name="critical">
              <TodoItemCard
                v-for="todo in filteredByPriority('critical')"
                :key="todo.id"
                :todo="todo"
                @update="handleTodoUpdate"
                @delete="handleTodoDelete"
              />
            </el-tab-pane>
            <el-tab-pane label="高" name="high">
              <TodoItemCard
                v-for="todo in filteredByPriority('high')"
                :key="todo.id"
                :todo="todo"
                @update="handleTodoUpdate"
                @delete="handleTodoDelete"
              />
            </el-tab-pane>
            <el-tab-pane label="中" name="medium">
              <TodoItemCard
                v-for="todo in filteredByPriority('medium')"
                :key="todo.id"
                :todo="todo"
                @update="handleTodoUpdate"
                @delete="handleTodoDelete"
              />
            </el-tab-pane>
            <el-tab-pane label="低" name="low">
              <TodoItemCard
                v-for="todo in filteredByPriority('low')"
                :key="todo.id"
                :todo="todo"
                @update="handleTodoUpdate"
                @delete="handleTodoDelete"
              />
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- 其他模式：平铺显示 -->
        <div v-else class="todo-list">
          <TodoItemCard
            v-for="todo in sortedTodos(filteredTodos)"
            :key="todo.id"
            :todo="todo"
            @update="handleTodoUpdate"
            @delete="handleTodoDelete"
          />
        </div>
      </template>
    </div>

    <!-- 分页（如果需要） -->
    <div v-if="false" class="todos-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="filteredTodos.length"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  List,
  CircleCheck,
  Loading,
  TrendCharts,
  Search,
  Delete,
  ArrowDown,
  Folder,
  RefreshLeft
} from '@element-plus/icons-vue'
import type { TodoItemDetail, TodoViewMode, TodoSortBy } from '@/types/todos'
import { useTodoStore } from '@/stores/todoStore'
import TodoItemCard from './TodoItemCard.vue'

const todoStore = useTodoStore()

// 视图状态
const viewModeSelect = ref<TodoViewMode>('all')
const sortBySelect = ref<TodoSortBy>('created_at')
const searchQuery = ref('')
const activeGroups = ref<string[]>([])
const activePriority = ref('all')

// 分页
const currentPage = ref(1)
const pageSize = ref(20)

// 计算属性
const statistics = computed(() => todoStore.statistics)
const filteredTodos = computed(() => todoStore.viewTodos)
const viewMode = computed(() => todoStore.viewMode)
const filter = computed(() => todoStore.filter)

const hasFilters = computed(() => {
  return Object.keys(filter.value).length > 0
})

const emptyText = computed(() => {
  if (hasFilters.value) return '没有符合条件的TODO项'
  return '暂无TODO项'
})

// 按任务分组
const groupedByTask = computed(() => {
  const groups = Array.from(todoStore.todoGroups.values())
  return groups.filter(group => group.todos.length > 0)
})

// 排序后的TODO列表
function sortedTodos(todos: TodoItemDetail[]) {
  return [...todos].sort((a, b) => {
    const timeCompare = new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    return timeCompare
  })
}

// 按优先级过滤
function filteredByPriority(priority: TodoItemDetail['priority']) {
  return filteredTodos.value.filter(todo => todo.priority === priority)
}

// 进度条颜色
function getProgressColor(percentage: number): string {
  if (percentage >= 80) return '#67c23a'
  if (percentage >= 50) return '#e6a23c'
  return '#f56c6c'
}

// 事件处理
function handleViewModeChange(mode: TodoViewMode) {
  todoStore.setViewMode(mode)
  activeGroups.value = []
}

function handleSortChange(sortBy: TodoSortBy) {
  todoStore.setSort(sortBy, 'desc')
}

function handleSearch(query: string) {
  todoStore.setFilter({ search_query: query || undefined })
}

function handleClearFilters() {
  todoStore.clearFilter()
  searchQuery.value = ''
}

async function handleClearCompleted() {
  try {
    await ElMessageBox.confirm(
      '确定要清除所有已完成的TODO项吗？',
      '批量清除',
      {
        confirmButtonText: '清除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 按任务节点清除已完成的TODO
    for (const [taskNodeId] of todoStore.todoGroups.keys()) {
      await todoStore.removeCompletedTodos(taskNodeId)
    }

    ElMessage.success('已清除所有已完成的TODO项')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(`操作失败: ${error.message}`)
    }
  }
}

async function handleBatchOperation(command: string) {
  try {
    const confirmMessage = {
      complete_all: '确定要将所有TODO标记为完成吗？',
      uncomplete_all: '确定要将所有TODO标记为未完成吗？',
      delete_completed: '确定要删除所有已完成的TODO项吗？'
    }

    await ElMessageBox.confirm(
      confirmMessage[command as keyof typeof confirmMessage],
      '批量操作确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 收集所有TODO ID
    const taskNodeIds = new Set(filteredTodos.value.map(t => t.task_node_id))

    // 执行批量操作
    for (const taskNodeId of taskNodeIds) {
      const taskTodos = filteredTodos.value
        .filter(t => t.task_node_id === taskNodeId)
        .map(t => t.id)

      await todoStore.batchOperation({
        task_node_id: taskNodeId,
        todo_ids: taskTodos,
        operation: command === 'complete_all' ? 'complete' : command
      })
    }

    ElMessage.success('批量操作完成')
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(`操作失败: ${error.message}`)
    }
  }
}

function handleTodoUpdate(todoId: string, updates: unknown) {
  console.log('TODO updated:', todoId, updates)
}

function handleTodoDelete(todoId: string, taskNodeId: string) {
  console.log('TODO deleted:', todoId, taskNodeId)
}

function handleSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
}

function handleCurrentChange(page: number) {
  currentPage.value = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// 生命周期
onMounted(() => {
  // 默认展开第一个组
  if (groupedByTask.value.length > 0) {
    activeGroups.value = [groupedByTask.value[0].task_node_id]
  }
})
</script>

<style scoped>
.todos-panel {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.todos-header {
  margin-bottom: 20px;
  padding: 20px;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.todos-toolbar {
  margin-bottom: 20px;
  padding: 15px 20px;
  background: var(--el-bg-color-page);
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.most-active-task {
  margin-bottom: 15px;
}

.todos-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0 20px;
}

.group-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.group-icon {
  font-size: 20px;
  color: var(--el-color-primary);
}

.group-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.group-stats {
  display: flex;
  align-items: center;
  gap: 15px;
  flex: 1;
  max-width: 300px;
}

.group-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.group-todos {
  padding: 10px 0;
}

.todo-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.todo-priorities {
  min-height: 400px;
}

.todos-pagination {
  margin-top: 20px;
  padding: 20px;
  display: flex;
  justify-content: center;
  background: var(--el-bg-color-page);
  border-radius: 8px;
}

/* 滚动条美化 */
.todos-content::-webkit-scrollbar {
  width: 6px;
}

.todos-content::-webkit-scrollbar-track {
  background: var(--el-fill-color-light);
  border-radius: 3px;
}

.todos-content::-webkit-scrollbar-thumb {
  background: var(--el-border-color-darker);
  border-radius: 3px;
}

.todos-content::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-dark);
}
</style>
