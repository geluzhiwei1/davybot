import { ref, computed } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus';
import type { ScheduledTask } from '@/types/scheduledTasks';

export function useScheduledTasks(workspaceId?: string) {
  const scheduledTasksList = ref<ScheduledTask[]>([]);
  const loadingTasks = ref(false);
  const savingTask = ref(false);

  // 对话框状态
  const taskDialogVisible = ref(false);
  const isEditMode = ref(false);
  const editingTaskId = ref<string | null>(null);
  const taskFormRef = ref<FormInstance>();

  // 任务表单
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

  // Cron表达式验证器
  const validateCronExpression = (rule: unknown, value: string, callback: (error?: Error) => void) => {
    if (!value) {
      callback();
      return;
    }

    // 基本的cron表达式验证
    // 格式: 分 时 日 月 周
    const cronRegex = /^(\*|([0-5]?\d)(\/[0-5]?\d)?(,[0-5]?\d)*)\s+(\*|([01]?\d|2[0-3])(\/[01]?\d)?(,[01]?\d|2[0-3])*)\s+(\*|([1-2]?\d|3[01])(\/[1-2]?\d)?(,[1-2]?\d|3[01])*)\s+(\*|([1]?\d)(\/[1]?\d)?(,[1]?\d)*)\s+(\*|([0-6])(\/[0-6])?(,[0-6])*)$/;

    if (!cronRegex.test(value)) {
      callback(new Error('无效的cron表达式。格式: 分 时 日 月 周 (例如: 0 9 * * 1-5)'));
      return;
    }

    callback();
  };

  const taskFormRules: FormRules = {
    description: [{ required: true, message: '请输入任务描述', trigger: 'blur' }],
    schedule_type: [{ required: true, message: '请选择调度类型', trigger: 'change' }],
    trigger_time: [{ required: true, message: '请选择触发时间', trigger: 'change' }],
    execution_type: [{ required: true, message: '请选择执行类型', trigger: 'change' }],
    cron_expression: [
      { validator: validateCronExpression, trigger: 'blur' }
    ]
  };

  // 加载定时任务列表
  const loadScheduledTasks = async () => {
    if (!workspaceId) return;

    loadingTasks.value = true;
    try {
      const response = await apiManager.getScheduledTasksApi().getScheduledTasks(workspaceId);
      scheduledTasksList.value = response.tasks || [];
    } catch (error: unknown) {
      ElMessage.error('加载定时任务列表失败');
      console.error('Failed to load scheduled tasks:', error);
    } finally {
      loadingTasks.value = false;
    }
  };

  // 显示创建任务对话框
  const showCreateTaskDialog = () => {
    isEditMode.value = false;
    editingTaskId.value = null;
    resetTaskForm();
    taskDialogVisible.value = true;
  };

  // 编辑任务
  const editTask = (task: ScheduledTask) => {
    isEditMode.value = true;
    editingTaskId.value = task.task_id || task.id;
    taskForm.value = {
      description: task.description,
      schedule_type: task.schedule_type,
      trigger_time: task.trigger_time,
      repeat_interval: task.repeat_interval,
      max_repeats: task.max_repeats,
      cron_expression: task.cron_expression || '',
      execution_data: {
        message: task.execution_data?.message || '',
        llm: task.execution_data?.llm || '',
        mode: task.execution_data?.mode || ''
      }
    };
    taskDialogVisible.value = true;
  };

  // 保存任务
  const saveTask = async () => {
    if (!taskFormRef.value || !workspaceId) return;

    await taskFormRef.value.validate(async (valid) => {
      if (!valid) return;

      savingTask.value = true;
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
          await apiManager.getScheduledTasksApi().updateScheduledTask(
            workspaceId,
            editingTaskId.value,
            taskData
          );
          ElMessage.success('定时任务更新成功');
        } else {
          await apiManager.getScheduledTasksApi().createScheduledTask(workspaceId, taskData);
          ElMessage.success('定时任务创建成功');
        }

        taskDialogVisible.value = false;
        await loadScheduledTasks();
      } catch (error: unknown) {
        const err = error as { response?: { data?: { detail?: string } } };
        ElMessage.error(err.response?.data?.detail || '保存失败');
        console.error('Failed to save task:', error);
      } finally {
        savingTask.value = false;
      }
    });
  };

  // 删除任务
  const deleteTask = async (taskId: string) => {
    if (!workspaceId) return;

    try {
      await ElMessageBox.confirm(
        '确定要删除此定时任务吗？此操作不可恢复。',
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      await apiManager.getScheduledTasksApi().deleteScheduledTask(workspaceId, taskId);
      ElMessage.success('定时任务删除成功');
      await loadScheduledTasks();
    } catch (error: unknown) {
      if (error !== 'cancel') {
        const err = error as { response?: { data?: { detail?: string } } };
        ElMessage.error(err.response?.data?.detail || '删除失败');
        console.error('Failed to delete scheduled task:', error);
      }
    }
  };

  // 启用/禁用任务
  const toggleTask = async (task: ScheduledTask) => {
    if (!workspaceId) return;

    try {
      await apiManager.getScheduledTasksApi().updateScheduledTask(workspaceId, task.task_id || task.id, {
        enabled: !task.enabled
      });
      ElMessage.success(task.enabled ? '任务已禁用' : '任务已启用');
      await loadScheduledTasks();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '操作失败');
      console.error('Failed to toggle scheduled task:', error);
    }
  };

  // 立即执行任务
  const runTaskNow = async (taskId: string) => {
    if (!workspaceId) return;

    try {
      await apiManager.getScheduledTasksApi().triggerScheduledTask(workspaceId, taskId);
      ElMessage.success('任务已开始执行');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '执行失败');
      console.error('Failed to run scheduled task:', error);
    }
  };

  // 暂停任务
  const pauseTask = async (taskId: string) => {
    if (!workspaceId) return;

    try {
      await apiManager.getScheduledTasksApi().pauseScheduledTask(workspaceId, taskId);
      ElMessage.success('任务已暂停');
      await loadScheduledTasks();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '暂停失败');
      console.error('Failed to pause scheduled task:', error);
    }
  };

  // 恢复任务
  const resumeTask = async (taskId: string) => {
    if (!workspaceId) return;

    try {
      await apiManager.getScheduledTasksApi().resumeScheduledTask(workspaceId, taskId);
      ElMessage.success('任务已恢复');
      await loadScheduledTasks();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '恢复失败');
      console.error('Failed to resume scheduled task:', error);
    }
  };

  // 重置表单
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

  // 获取任务状态统计
  const tasksStats = computed(() => ({
    total: scheduledTasksList.value.length,
    enabled: scheduledTasksList.value.filter(t => t.enabled).length,
    disabled: scheduledTasksList.value.filter(t => !t.enabled).length,
    running: scheduledTasksList.value.filter(t => t.status === 'running').length
  }));

  return {
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
    taskFormRules,
    resetTaskForm
  };
}
