<template>
  <div class="scheduled-tasks-drawer">
    <div class="drawer-content" v-loading="loadingTasks">
      <!-- Header -->
      <el-alert :title="t('workspaceSettings.scheduledTasks.title')" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            {{ t('workspaceSettings.scheduledTasks.description') }}
          </p>
        </template>
      </el-alert>

      <!-- Stats -->
      <div style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-tag>{{ t('scheduledTasks.total') }}: {{ tasksStats.total }}</el-tag>
        <el-tag type="success">{{ t('scheduledTasks.enabled') }}: {{ tasksStats.enabled }}</el-tag>
        <el-tag type="info">{{ t('scheduledTasks.disabled') }}: {{ tasksStats.disabled }}</el-tag>
        <el-tag type="warning">{{ t('scheduledTasks.running') }}: {{ tasksStats.running }}</el-tag>
      </div>

      <!-- Filters -->
      <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center;">
        <el-select
          v-model="filters.status"
          :placeholder="t('scheduledTasks.filterByStatus')"
          clearable
          @change="loadTasks"
          style="width: 150px;"
        >
          <el-option :label="t('scheduledTasks.allStatus')" value="" />
          <el-option :label="t('scheduledTasks.statusPending')" value="pending" />
          <el-option :label="t('scheduledTasks.statusTriggered')" value="triggered" />
          <el-option :label="t('scheduledTasks.statusPaused')" value="paused" />
          <el-option :label="t('scheduledTasks.statusCompleted')" value="completed" />
          <el-option :label="t('scheduledTasks.statusFailed')" value="failed" />
        </el-select>

        <el-select
          v-model="filters.scheduleType"
          :placeholder="t('scheduledTasks.filterByScheduleType')"
          clearable
          @change="loadTasks"
          style="width: 150px;"
        >
          <el-option :label="t('scheduledTasks.allTypes')" value="" />
          <el-option :label="t('scheduledTasks.typeDelay')" value="delay" />
          <el-option :label="t('scheduledTasks.typeAtTime')" value="at_time" />
          <el-option :label="t('scheduledTasks.typeRecurring')" value="recurring" />
          <el-option :label="t('scheduledTasks.typeCron')" value="cron" />
        </el-select>

        <el-input
          v-model="filters.search"
          :placeholder="t('scheduledTasks.searchPlaceholder')"
          clearable
          @change="loadTasks"
          style="width: 250px;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <div style="flex: 1;"></div>

        <el-button type="primary" size="small" @click="showCreateTaskDialog">
          <el-icon><Plus /></el-icon>
          {{ t('scheduledTasks.createTask') }}
        </el-button>
      </div>

      <!-- Scheduled Tasks Table -->
      <el-table :data="scheduledTasksList" stripe style="width: 100%;">
        <el-table-column prop="description" :label="t('scheduledTasks.description')" min-width="200" />

        <el-table-column prop="schedule_type" :label="t('scheduledTasks.scheduleType')" width="120">
          <template #default="scope">
            <el-tag size="small">{{ getScheduleTypeLabel(scope.row.schedule_type) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="trigger_time" :label="t('scheduledTasks.triggerTime')" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.trigger_time) }}
          </template>
        </el-table-column>

        <el-table-column :label="t('scheduledTasks.status')" width="120" align="center">
          <template #default="scope">
            <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
              <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
                {{ scope.row.enabled ? t('scheduledTasks.enabled') : t('scheduledTasks.disabled') }}
              </el-tag>
              <el-tag :type="getStatusType(scope.row.status)" size="small" v-if="scope.row.status">
                {{ getStatusLabel(scope.row.status) }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="repeat_count" :label="t('scheduledTasks.repeatCount')" width="100" align="center" />

        <el-table-column :label="t('scheduledTasks.actions')" width="420" fixed="right">
          <template #default="scope">
            <el-button-group>
              <el-button size="small" :icon="View" @click="handleViewExecutions(scope.row)">
                {{ t('scheduledTasks.viewHistory') }}
              </el-button>
              <el-button
                size="small"
                type="success"
                :icon="CaretRight"
                @click="runTaskNow(scope.row.task_id || scope.row.id)"
                :disabled="!scope.row.enabled"
              >
                {{ t('scheduledTasks.runNow') }}
              </el-button>
              <el-button
                v-if="scope.row.status === 'pending'"
                size="small"
                :icon="VideoPause"
                @click="pauseTask(scope.row.task_id || scope.row.id)"
              >
                {{ t('scheduledTasks.pause') }}
              </el-button>
              <el-button
                v-if="scope.row.status === 'paused'"
                size="small"
                :icon="VideoPlay"
                @click="resumeTask(scope.row.task_id || scope.row.id)"
              >
                {{ t('scheduledTasks.resume') }}
              </el-button>
              <el-button size="small" :icon="scope.row.enabled ? 'Hide' : 'View'" @click="toggleTask(scope.row)">
                {{ scope.row.enabled ? t('scheduledTasks.disable') : t('scheduledTasks.enable') }}
              </el-button>
              <el-button size="small" :icon="Edit" type="primary" @click="editTask(scope.row)">
                {{ t('scheduledTasks.edit') }}
              </el-button>
              <el-button size="small" :icon="Delete" type="danger" @click="deleteTask(scope.row.task_id || scope.row.id)">
                {{ t('scheduledTasks.delete') }}
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loadingTasks && scheduledTasksList.length === 0" :description="t('scheduledTasks.noTasks')" style="margin-top: 40px;">
        <el-button type="primary" @click="showCreateTaskDialog">{{ t('scheduledTasks.createFirstTask') }}</el-button>
      </el-empty>

      <!-- 创建/编辑任务对话框 -->
      <el-dialog
        v-model="taskDialogVisible"
        :title="isEditMode ? t('scheduledTasks.editTask') : t('scheduledTasks.createTask')"
        width="700px"
        :close-on-click-modal="false"
      >
        <el-form :model="taskForm" :rules="taskFormRules" ref="taskFormRef" label-width="140px">
          <el-form-item :label="t('scheduledTasks.description')" prop="description">
            <el-input v-model="taskForm.description" :placeholder="t('scheduledTasks.descriptionPlaceholder')" />
          </el-form-item>

          <el-form-item :label="t('scheduledTasks.scheduleType')" prop="schedule_type">
            <el-select v-model="taskForm.schedule_type" :placeholder="t('scheduledTasks.selectScheduleType')" style="width: 100%;">
              <el-option :label="t('scheduledTasks.typeDelay')" value="delay" />
              <el-option :label="t('scheduledTasks.typeAtTime')" value="at_time" />
              <el-option :label="t('scheduledTasks.typeRecurring')" value="recurring" />
              <el-option :label="t('scheduledTasks.typeCron')" value="cron" />
            </el-select>
          </el-form-item>

          <el-form-item :label="t('scheduledTasks.triggerTime')" prop="trigger_time">
            <el-date-picker
              v-model="taskForm.trigger_time"
              type="datetime"
              :placeholder="t('scheduledTasks.selectTriggerTime')"
              style="width: 100%;"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DDTHH:mm:ss"
            />
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'recurring'"
            :label="t('scheduledTasks.repeatInterval')"
            prop="repeat_interval"
          >
            <el-input-number
              v-model="taskForm.repeat_interval"
              :min="60"
              :step="60"
              :placeholder="t('scheduledTasks.repeatIntervalPlaceholder')"
              style="width: 100%;"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              {{ t('scheduledTasks.repeatIntervalHint') }}
            </div>
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'recurring'"
            :label="t('scheduledTasks.maxRepeats')"
            prop="max_repeats"
          >
            <el-input-number
              v-model="taskForm.max_repeats"
              :min="1"
              :placeholder="t('scheduledTasks.maxRepeatsPlaceholder')"
              style="width: 100%;"
            />
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'cron'"
            :label="t('scheduledTasks.cronExpression')"
            prop="cron_expression"
          >
            <el-input
              v-model="taskForm.cron_expression"
              :placeholder="t('scheduledTasks.cronExpressionPlaceholder')"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              {{ t('scheduledTasks.cronExpressionHint') }}
            </div>
          </el-form-item>

          <el-divider content-position="left">{{ t('scheduledTasks.executionConfig') }}</el-divider>

          <el-form-item :label="t('scheduledTasks.messageContent')" prop="execution_data.message">
            <el-input
              v-model="taskForm.execution_data.message"
              type="textarea"
              :rows="4"
              :placeholder="t('scheduledTasks.messageContentPlaceholder')"
            />
          </el-form-item>

          <el-form-item :label="t('scheduledTasks.llmModel')" prop="execution_data.llm">
            <el-input
              v-model="taskForm.execution_data.llm"
              :placeholder="t('scheduledTasks.llmModelPlaceholder')"
            />
            <span style="margin-left: 8px; font-size: 12px; color: #999;">
              {{ t('scheduledTasks.optional') }}
            </span>
          </el-form-item>

          <el-form-item :label="t('scheduledTasks.agentMode')" prop="execution_data.mode">
            <el-select
              v-model="taskForm.execution_data.mode"
              :placeholder="t('scheduledTasks.agentModePlaceholder')"
              allow-clear
              style="width: 100%;"
            >
              <el-option label="Orchestrator" value="orchestrator" />
              <el-option label="PDCA" value="pdca" />
            </el-select>
            <span style="margin-left: 8px; font-size: 12px; color: #999;">
              {{ t('scheduledTasks.optional') }}
            </span>
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="taskDialogVisible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" @click="saveTask" :loading="savingTask">
            {{ isEditMode ? t('common.update') : t('common.create') }}
          </el-button>
        </template>
      </el-dialog>

      <!-- 执行历史对话框 -->
      <el-dialog
        v-model="executionsDialogVisible"
        :title="t('scheduledTasks.executionHistory')"
        width="800px"
      >
        <el-table :data="executions" v-loading="loadingExecutions" stripe>
          <el-table-column prop="conversation_id" :label="t('scheduledTasks.conversationId')" width="250" />
          <el-table-column prop="title" :label="t('scheduledTasks.title')" min-width="200" />
          <el-table-column prop="repeat_count" :label="t('scheduledTasks.repeatCount')" width="100" />
          <el-table-column prop="triggered_at" :label="t('scheduledTasks.triggeredAt')" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.triggered_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="message_count" :label="t('scheduledTasks.messageCount')" width="100" />
          <el-table-column :label="t('scheduledTasks.actions')" width="100">
            <template #default="scope">
              <el-button size="small" :icon="View" @click="handleViewConversation(scope.row)">
                {{ t('scheduledTasks.view') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
          <el-pagination
            v-model:current-page="executionsPagination.page"
            v-model:page-size="executionsPagination.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="executionsPagination.total"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="handleExecutionsPageChange"
            @current-change="handleExecutionsPageChange"
          />
        </div>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, View, Edit, Delete, VideoPause, VideoPlay, Search, CaretRight } from '@element-plus/icons-vue';
import { watch, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useScheduledTasks } from '@/composables/scheduledTasks/useScheduledTasks';
import { apiManager } from '@/services/api';
import type { ScheduledTaskExecution } from '@/services/api/types';

const props = defineProps<{
  workspaceId?: string;
}>();

const { t } = useI18n();
const router = useRouter();

// Filters
const filters = ref({
  status: '',
  scheduleType: '',
  search: ''
});

// Auto refresh
const refreshInterval = ref<NodeJS.Timeout | null>(null);
const REFRESH_INTERVAL = 5000; // 5 seconds

// Executions
const executionsDialogVisible = ref(false);
const executions = ref<ScheduledTaskExecution[]>([]);
const loadingExecutions = ref(false);
const currentTaskId = ref<string | null>(null);
const executionsPagination = ref({
  page: 1,
  pageSize: 20,
  total: 0,
  totalPages: 0
});

const {
  scheduledTasksList,
  loadingTasks,
  savingTask,
  tasksStats,
  loadScheduledTasks,
  showCreateTaskDialog,
  editTask,
  saveTask,
  deleteTask,
  toggleTask,
  runTaskNow,
  pauseTask,
  resumeTask,
  // 对话框状态
  taskDialogVisible,
  isEditMode,
  taskForm,
  taskFormRef,
  taskFormRules
} = useScheduledTasks(props.workspaceId);

// Load tasks with filters
const loadTasks = async () => {
  if (!props.workspaceId) return;

  loadingTasks.value = true;
  try {
    const response = await apiManager.getScheduledTasksApi().getScheduledTasks(props.workspaceId);
    if (response.success) {
      // Client-side filtering
      let filteredTasks = response.tasks;

      // Filter by status
      if (filters.value.status) {
        filteredTasks = filteredTasks.filter(task => task.status === filters.value.status);
      }

      // Filter by schedule type
      if (filters.value.scheduleType) {
        filteredTasks = filteredTasks.filter(task => task.schedule_type === filters.value.scheduleType);
      }

      // Filter by search text (description)
      if (filters.value.search) {
        const searchLower = filters.value.search.toLowerCase();
        filteredTasks = filteredTasks.filter(task =>
          task.description.toLowerCase().includes(searchLower)
        );
      }

      scheduledTasksList.value = filteredTasks;
    }
  } catch (error) {
    console.error('Failed to load scheduled tasks:', error);
  } finally {
    loadingTasks.value = false;
  }
};

// View execution history
const handleViewExecutions = async (task: any) => {
  currentTaskId.value = task.task_id || task.id;
  executionsDialogVisible.value = true;
  loadingExecutions.value = true;
  executionsPagination.value.page = 1; // Reset to first page

  try {
    const response = await apiManager.getScheduledTasksApi().getTaskExecutions(
      props.workspaceId!,
      currentTaskId.value,
      executionsPagination.value.page,
      executionsPagination.value.pageSize
    );
    if (response.success) {
      executions.value = response.executions;
      executionsPagination.value.total = response.total;
      executionsPagination.value.totalPages = response.total_pages;
    }
  } catch (error) {
    console.error('Failed to load executions:', error);
  } finally {
    loadingExecutions.value = false;
  }
};

// Handle executions page change
const handleExecutionsPageChange = async () => {
  if (!currentTaskId.value || !props.workspaceId) return;

  loadingExecutions.value = true;
  try {
    const response = await apiManager.getScheduledTasksApi().getTaskExecutions(
      props.workspaceId,
      currentTaskId.value,
      executionsPagination.value.page,
      executionsPagination.value.pageSize
    );
    if (response.success) {
      executions.value = response.executions;
      executionsPagination.value.total = response.total;
      executionsPagination.value.totalPages = response.total_pages;
    }
  } catch (error) {
    console.error('Failed to load executions:', error);
  } finally {
    loadingExecutions.value = false;
  }
};

// View conversation
const handleViewConversation = (execution: ScheduledTaskExecution) => {
  // Navigate to conversation view
  router.push({
    name: 'chat',
    params: { workspaceId: props.workspaceId },
    query: { conversationId: execution.conversation_id }
  });
};

// 格式化日期
const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

// 获取调度类型标签
const getScheduleTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    delay: t('scheduledTasks.typeDelay'),
    at_time: t('scheduledTasks.typeAtTime'),
    recurring: t('scheduledTasks.typeRecurring'),
    cron: t('scheduledTasks.typeCron')
  };
  return labels[type] || type;
};

// 获取状态标签
const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: t('scheduledTasks.statusPending'),
    paused: t('scheduledTasks.statusPaused'),
    triggered: t('scheduledTasks.statusTriggered'),
    completed: t('scheduledTasks.statusCompleted'),
    failed: t('scheduledTasks.statusFailed'),
    cancelled: t('scheduledTasks.statusCancelled')
  };
  return labels[status] || status;
};

// 获取状态类型
const getStatusType = (status: string) => {
  const types: Record<string, any> = {
    pending: 'info',
    paused: 'warning',
    triggered: 'primary',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info'
  };
  return types[status] || 'info';
};

// Lifecycle
onMounted(() => {
  if (props.workspaceId) {
    loadTasks();
    // Start auto refresh
    refreshInterval.value = setInterval(() => {
      loadTasks();
    }, REFRESH_INTERVAL);
  }
});

onUnmounted(() => {
  // Clear auto refresh
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value);
    refreshInterval.value = null;
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadTasks();
    // Restart auto refresh
    if (refreshInterval.value) {
      clearInterval(refreshInterval.value);
    }
    refreshInterval.value = setInterval(() => {
      loadTasks();
    }, REFRESH_INTERVAL);
  }
});
</script>

<style scoped>
.scheduled-tasks-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}

code {
  background-color: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.9em;
}
</style>
