<!--
定时任务管理面板
集成到工作区设置中
-->
<template>
  <div class="scheduled-tasks-panel">
    <!-- 说明信息 -->
    <el-alert :title="t('workspaceSettings.scheduledTasks.title')" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
      <template #default>
        <p style="margin: 0; font-size: 13px;">
          {{ t('workspaceSettings.scheduledTasks.description') }}
        </p>
      </template>
    </el-alert>

    <!-- 过滤器 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.status"
        :placeholder="t('scheduledTasks.filterByStatus')"
        clearable
        @change="loadTasks"
        style="width: 150px; margin-right: 12px;"
      >
        <el-option label="全部状态" value="" />
        <el-option label="待执行" value="pending" />
        <el-option label="执行中" value="triggered" />
        <el-option label="已暂停" value="paused" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
      </el-select>

      <el-select
        v-model="filters.scheduleType"
        :placeholder="t('scheduledTasks.filterByScheduleType')"
        clearable
        @change="loadTasks"
        style="width: 150px; margin-right: 12px;"
      >
        <el-option label="全部类型" value="" />
        <el-option label="延迟执行" value="delay" />
        <el-option label="指定时间" value="at_time" />
        <el-option label="周期执行" value="recurring" />
        <el-option label="Cron表达式" value="cron" />
      </el-select>

      <el-input
        v-model="filters.search"
        :placeholder="t('scheduledTasks.searchPlaceholder')"
        clearable
        @change="loadTasks"
        style="width: 250px; margin-right: auto;"
      />

      <el-button type="primary" :icon="Plus" @click="handleCreateTask">
        {{ t('scheduledTasks.createTask') }}
      </el-button>
    </div>

    <!-- 任务列表 -->
    <el-card v-loading="loading" style="margin-top: 16px;">
      <el-empty v-if="!loading && tasks.length === 0" :description="t('scheduledTasks.noTasks')" />

      <el-table v-else :data="tasks" stripe>
        <el-table-column prop="description" :label="t('scheduledTasks.description')" min-width="200" />
        <el-table-column prop="schedule_type" :label="t('scheduledTasks.scheduleType')" width="120">
          <template #default="{ row }">
            <el-tag>{{ getScheduleTypeLabel(row.schedule_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_time" :label="t('scheduledTasks.triggerTime')" width="180">
          <template #default="{ row }">
            {{ formatDate(row.trigger_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" :label="t('scheduledTasks.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="repeat_count" :label="t('scheduledTasks.repeatCount')" width="100" />
        <el-table-column :label="t('scheduledTasks.actions')" width="280" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" :icon="View" @click="handleViewExecutions(row)">
                {{ t('scheduledTasks.viewHistory') }}
              </el-button>
              <el-button
                v-if="row.status === 'pending' || row.status === 'failed'"
                size="small"
                :icon="CaretRight"
                @click="handleTriggerTask(row)"
                :disabled="row.status === 'triggered'"
              >
                立即执行
              </el-button>
              <el-button
                v-if="row.status === 'pending'"
                size="small"
                :icon="VideoPause"
                @click="handlePauseTask(row)"
              >
                {{ t('scheduledTasks.pause') }}
              </el-button>
              <el-button
                v-if="row.status === 'paused'"
                size="small"
                :icon="VideoPlay"
                @click="handleResumeTask(row)"
              >
                {{ t('scheduledTasks.resume') }}
              </el-button>
              <el-button size="small" :icon="Edit" @click="handleEditTask(row)" />
              <el-button size="small" type="danger" :icon="Delete" @click="handleDeleteTask(row)" />
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑任务对话框 -->
    <el-dialog
      v-model="taskDialogVisible"
      :title="isEditMode ? t('scheduledTasks.editTask') : t('scheduledTasks.createTask')"
      width="600px"
    >
      <el-form :model="taskForm" :rules="taskFormRules" ref="taskFormRef" label-width="140px">
        <el-form-item :label="t('scheduledTasks.description')" prop="description">
          <el-input v-model="taskForm.description" :placeholder="t('scheduledTasks.descriptionPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('scheduledTasks.scheduleType')" prop="schedule_type">
          <el-select v-model="taskForm.schedule_type" :placeholder="t('scheduledTasks.selectScheduleType')">
            <el-option label="延迟执行" value="delay" />
            <el-option label="指定时间" value="at_time" />
            <el-option label="周期执行" value="recurring" />
            <el-option label="Cron表达式" value="cron" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('scheduledTasks.triggerTime')" prop="trigger_time">
          <el-date-picker
            v-model="taskForm.trigger_time"
            type="datetime"
            :placeholder="t('scheduledTasks.selectTriggerTime')"
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
          />
          <span style="margin-left: 8px">{{ t('scheduledTasks.seconds') }}</span>
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
        </el-form-item>

        <el-form-item
          :label="t('scheduledTasks.messageContent')"
          prop="execution_data.message"
        >
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
          >
            <el-option label="Orchestrator" value="orchestrator" />
            <el-option label="Plan" value="plan" />
            <el-option label="Do" value="do" />
            <el-option label="Check" value="check" />
            <el-option label="Act" value="act" />
          </el-select>
          <span style="margin-left: 8px; font-size: 12px; color: #999;">
            {{ t('scheduledTasks.optional') }}
          </span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="taskDialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSaveTask" :loading="saving">
          {{ t('common.save') }}
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
          <template #default="{ row }">
            {{ formatDate(row.triggered_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="message_count" :label="t('scheduledTasks.messageCount')" width="100" />
        <el-table-column :label="t('scheduledTasks.actions')" width="100">
          <template #default="{ row }">
            <el-button size="small" :icon="View" @click="handleViewConversation(row)">
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
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { apiManager } from '@/services/api';
import type {
  ScheduledTask,
  ScheduledTaskExecution
} from '@/services/api/types';
import {
  Plus,
  View,
  Edit,
  Delete,
  VideoPause,
  VideoPlay,
  Search,
  CaretRight
} from '@element-plus/icons-vue';
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules
} from 'element-plus';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();
const router = useRouter();

// Data
const tasks = ref<ScheduledTask[]>([]);
const loading = ref(false);
const saving = ref(false);
const taskDialogVisible = ref(false);
const isEditMode = ref(false);
const editingTaskId = ref<string | null>(null);

// Auto refresh
const refreshInterval = ref<NodeJS.Timeout | null>(null);
const REFRESH_INTERVAL = 5000; // 5 seconds

// Filters
const filters = ref({
  status: '',
  scheduleType: '',
  search: ''
});

const taskFormRef = ref<FormInstance>();
const taskForm = ref({
  description: '',
  schedule_type: 'at_time' as 'delay' | 'at_time' | 'recurring' | 'cron',
  trigger_time: '',
  repeat_interval: undefined as number | undefined,
  max_repeats: undefined as number | undefined,
  cron_expression: '',
  execution_data: {
    message: '',
    llm: '',
    mode: ''
  }
});

const taskFormRules: FormRules = {
  description: [{ required: true, message: t('scheduledTasks.descriptionRequired'), trigger: 'blur' }],
  schedule_type: [{ required: true, message: t('scheduledTasks.scheduleTypeRequired'), trigger: 'change' }],
  trigger_time: [{ required: true, message: t('scheduledTasks.triggerTimeRequired'), trigger: 'change' }],
  execution_type: [{ required: true, message: t('scheduledTasks.executionTypeRequired'), trigger: 'change' }]
};

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

// Methods
const loadTasks = async () => {
  loading.value = true;
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

      tasks.value = filteredTasks;
    }
  } catch (error) {
    console.error('Failed to load scheduled tasks:', error);
    ElMessage.error(t('scheduledTasks.loadFailed'));
  } finally {
    loading.value = false;
  }
};

const handleCreateTask = () => {
  isEditMode.value = false;
  editingTaskId.value = null;
  resetTaskForm();
  taskDialogVisible.value = true;
};

const handleEditTask = (task: ScheduledTask) => {
  isEditMode.value = true;
  editingTaskId.value = task.task_id;
  taskForm.value = {
    description: task.description,
    schedule_type: task.schedule_type,
    trigger_time: task.trigger_time,
    repeat_interval: task.repeat_interval,
    max_repeats: task.max_repeats,
    cron_expression: task.cron_expression || '',
    execution_data: {
      message: task.execution_data.message || '',
      llm: task.execution_data.llm || '',
      mode: task.execution_data.mode || ''
    }
  };
  taskDialogVisible.value = true;
};

const handleSaveTask = async () => {
  if (!taskFormRef.value) return;

  await taskFormRef.value.validate(async (valid) => {
    if (!valid) return;

    saving.value = true;
    try {
      const taskData = {
        description: taskForm.value.description,
        schedule_type: taskForm.value.schedule_type,
        trigger_time: new Date(taskForm.value.trigger_time).toISOString(),
        repeat_interval: taskForm.value.repeat_interval,
        max_repeats: taskForm.value.max_repeats,
        cron_expression: taskForm.value.cron_expression,
        execution_type: 'message' as const,
        execution_data: taskForm.value.execution_data
      };

      if (isEditMode.value && editingTaskId.value) {
        await apiManager.getScheduledTasksApi().updateScheduledTask(props.workspaceId, editingTaskId.value, taskData);
        ElMessage.success(t('scheduledTasks.updateSuccess'));
      } else {
        await apiManager.getScheduledTasksApi().createScheduledTask(props.workspaceId, taskData);
        ElMessage.success(t('scheduledTasks.createSuccess'));
      }

      taskDialogVisible.value = false;
      await loadTasks();
    } catch (error) {
      console.error('Failed to save task:', error);
      ElMessage.error(t('scheduledTasks.saveFailed'));
    } finally {
      saving.value = false;
    }
  });
};

const handleDeleteTask = async (task: ScheduledTask) => {
  try {
    await ElMessageBox.confirm(
      t('scheduledTasks.deleteConfirm'),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    );

    await apiManager.getScheduledTasksApi().deleteScheduledTask(props.workspaceId, task.task_id);
    ElMessage.success(t('scheduledTasks.deleteSuccess'));
    await loadTasks();
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete task:', error);
      ElMessage.error(t('scheduledTasks.deleteFailed'));
    }
  }
};

const handlePauseTask = async (task: ScheduledTask) => {
  try {
    await apiManager.getScheduledTasksApi().pauseScheduledTask(props.workspaceId, task.task_id);
    ElMessage.success(t('scheduledTasks.pauseSuccess'));
    await loadTasks();
  } catch (error) {
    console.error('Failed to pause task:', error);
    ElMessage.error(t('scheduledTasks.pauseFailed'));
  }
};

const handleResumeTask = async (task: ScheduledTask) => {
  try {
    await apiManager.getScheduledTasksApi().resumeScheduledTask(props.workspaceId, task.task_id);
    ElMessage.success(t('scheduledTasks.resumeSuccess'));
    await loadTasks();
  } catch (error) {
    console.error('Failed to resume task:', error);
    ElMessage.error(t('scheduledTasks.resumeFailed'));
  }
};

const handleTriggerTask = async (task: ScheduledTask) => {
  try {
    await apiManager.getScheduledTasksApi().triggerScheduledTask(props.workspaceId, task.task_id);
    ElMessage.success('任务已触发执行');
    await loadTasks();
  } catch (error: any) {
    console.error('Failed to trigger task:', error);
    const errorMsg = error?.response?.data?.detail || '触发任务失败';
    ElMessage.error(errorMsg);
  }
};

const handleViewExecutions = async (task: ScheduledTask) => {
  currentTaskId.value = task.task_id;
  executionsDialogVisible.value = true;
  loadingExecutions.value = true;
  executionsPagination.value.page = 1; // Reset to first page

  try {
    const response = await apiManager.getScheduledTasksApi().getTaskExecutions(
      props.workspaceId,
      task.task_id,
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
    ElMessage.error(t('scheduledTasks.loadExecutionsFailed'));
  } finally {
    loadingExecutions.value = false;
  }
};

const handleExecutionsPageChange = async () => {
  if (!currentTaskId.value) return;

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
    ElMessage.error(t('scheduledTasks.loadExecutionsFailed'));
  } finally {
    loadingExecutions.value = false;
  }
};

const handleViewConversation = (execution: ScheduledTaskExecution) => {
  // Navigate to conversation view
  router.push({
    name: 'chat',
    params: { workspaceId: props.workspaceId },
    query: { conversationId: execution.conversation_id }
  });
};

const resetTaskForm = () => {
  taskForm.value = {
    description: '',
    schedule_type: 'at_time',
    trigger_time: '',
    repeat_interval: undefined,
    max_repeats: undefined,
    cron_expression: '',
    execution_data: {
      message: '',
      llm: '',
      mode: ''
    }
  };
  taskFormRef.value?.clearValidate();
};

// Helper functions
const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('zh-CN');
};

const getScheduleTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    delay: '延迟执行',
    at_time: '指定时间',
    recurring: '周期执行',
    cron: 'Cron表达式'
  };
  return labels[type] || type;
};

const getStatusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: '待执行',
    paused: '已暂停',
    triggered: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  };
  return labels[status] || status;
};

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
  loadTasks();
  // Start auto refresh
  refreshInterval.value = setInterval(() => {
    loadTasks();
  }, REFRESH_INTERVAL);
});

onUnmounted(() => {
  // Clear auto refresh
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value);
    refreshInterval.value = null;
  }
});
</script>

<style scoped lang="scss">
.scheduled-tasks-panel {
  height: 100%;
  padding: 16px;

  .filter-bar {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}
</style>
