import { ref, computed, onMounted } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { ScheduledTask } from '@/types/scheduledTasks';

export function useScheduledTasks(workspaceId: string) {
  const scheduledTasksList = ref<ScheduledTask[]>([]);
  const loadingTasks = ref(false);

  // 加载定时任务列表
  const loadScheduledTasks = async () => {
    if (!workspaceId) return;

    loadingTasks.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getScheduledTasks(workspaceId);
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
    ElMessage.info('创建定时任务功能开发中...');
  };

  // 编辑任务
  const editTask = (task: ScheduledTask) => {
    ElMessage.info(`编辑定时任务 "${task.name}" 功能开发中...`);
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

      await apiManager.getWorkspacesApi().deleteScheduledTask(workspaceId, taskId);
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
      await apiManager.getWorkspacesApi().updateScheduledTask(workspaceId, task.id, {
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
      await apiManager.getWorkspacesApi().runScheduledTask(workspaceId, taskId);
      ElMessage.success('任务已开始执行');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '执行失败');
      console.error('Failed to run scheduled task:', error);
    }
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
    tasksStats,
    loadScheduledTasks,
    showCreateTaskDialog,
    editTask,
    deleteTask,
    toggleTask,
    runTaskNow
  };
}
