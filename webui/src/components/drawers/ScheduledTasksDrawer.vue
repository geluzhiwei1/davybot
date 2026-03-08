<template>
  <div class="scheduled-tasks-drawer">
    <div class="drawer-content" v-loading="loadingTasks">
      <!-- Header -->
      <el-alert title="定时任务管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区定时任务，设置自动化工作流程。支持Cron表达式定时执行命令。
          </p>
        </template>
      </el-alert>

      <!-- Stats -->
      <div style="margin-bottom: 16px; display: flex; gap: 12px;">
        <el-tag>总计: {{ tasksStats.total }}</el-tag>
        <el-tag type="success">启用: {{ tasksStats.enabled }}</el-tag>
        <el-tag type="info">禁用: {{ tasksStats.disabled }}</el-tag>
        <el-tag type="warning">运行中: {{ tasksStats.running }}</el-tag>
      </div>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">定时任务列表</span>
        <el-button type="primary" size="small" @click="showCreateTaskDialog">
          <el-icon><Plus /></el-icon>
          创建任务
        </el-button>
      </div>

      <!-- Scheduled Tasks Table -->
      <el-table :data="scheduledTasksList" stripe style="width: 100%;">
        <el-table-column prop="description" label="任务描述" min-width="200" />

        <el-table-column prop="schedule_type" label="调度类型" width="120">
          <template #default="scope">
            <el-tag size="small">{{ getScheduleTypeLabel(scope.row.schedule_type) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="trigger_time" label="触发时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.trigger_time) }}
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 4px; justify-content: center;">
              <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
                {{ scope.row.enabled ? '已启用' : '已禁用' }}
              </el-tag>
              <el-tag v-if="scope.row.status === 'triggered'" type="warning" size="small">
                运行中
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="repeat_count" label="重复次数" width="100" align="center" />

        <el-table-column label="操作" width="350" fixed="right">
          <template #default="scope">
            <el-button-group>
              <el-button size="small" type="success" @click="runTaskNow(scope.row.task_id || scope.row.id)" :disabled="!scope.row.enabled">
                立即运行
              </el-button>
              <el-button
                v-if="scope.row.status === 'pending'"
                size="small"
                @click="pauseTask(scope.row.task_id || scope.row.id)"
              >
                暂停
              </el-button>
              <el-button
                v-if="scope.row.status === 'paused'"
                size="small"
                @click="resumeTask(scope.row.task_id || scope.row.id)"
              >
                恢复
              </el-button>
              <el-button size="small" @click="toggleTask(scope.row)">
                {{ scope.row.enabled ? '禁用' : '启用' }}
              </el-button>
              <el-button size="small" type="primary" @click="editTask(scope.row)">
                编辑
              </el-button>
              <el-button size="small" type="danger" @click="deleteTask(scope.row.task_id || scope.row.id)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loadingTasks && scheduledTasksList.length === 0" description="暂无定时任务" style="margin-top: 40px;">
        <el-button type="primary" @click="showCreateTaskDialog">创建第一个任务</el-button>
      </el-empty>

      <!-- 创建/编辑任务对话框 -->
      <el-dialog
        v-model="taskDialogVisible"
        :title="isEditMode ? '编辑定时任务' : '创建定时任务'"
        width="700px"
        :close-on-click-modal="false"
      >
        <el-form :model="taskForm" :rules="taskFormRules" ref="taskFormRef" label-width="140px">
          <el-form-item label="任务描述" prop="description">
            <el-input v-model="taskForm.description" placeholder="例如：每天早上9点检查系统状态" />
          </el-form-item>

          <el-form-item label="调度类型" prop="schedule_type">
            <el-select v-model="taskForm.schedule_type" placeholder="请选择调度类型" style="width: 100%;">
              <el-option label="延迟执行" value="delay" />
              <el-option label="指定时间" value="at_time" />
              <el-option label="周期执行" value="recurring" />
              <el-option label="Cron表达式" value="cron" />
            </el-select>
          </el-form-item>

          <el-form-item label="触发时间" prop="trigger_time">
            <el-date-picker
              v-model="taskForm.trigger_time"
              type="datetime"
              placeholder="请选择触发时间"
              style="width: 100%;"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DDTHH:mm:ss"
            />
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'recurring'"
            label="重复间隔(秒)"
            prop="repeat_interval"
          >
            <el-input-number
              v-model="taskForm.repeat_interval"
              :min="60"
              :step="60"
              placeholder="例如: 3600 (每小时)"
              style="width: 100%;"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              单位：秒，最小60秒
            </div>
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'recurring'"
            label="最大重复次数"
            prop="max_repeats"
          >
            <el-input-number
              v-model="taskForm.max_repeats"
              :min="1"
              placeholder="留空表示无限重复"
              style="width: 100%;"
            />
          </el-form-item>

          <el-form-item
            v-if="taskForm.schedule_type === 'cron'"
            label="Cron表达式"
            prop="cron_expression"
          >
            <el-input
              v-model="taskForm.cron_expression"
              placeholder="例如: 0 9 * * * (每天早上9点)"
            />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              格式：分 时 日 月 周
            </div>
          </el-form-item>

          <el-divider content-position="left">执行配置</el-divider>

          <el-form-item label="消息内容" prop="execution_data.message">
            <el-input
              v-model="taskForm.execution_data.message"
              type="textarea"
              :rows="4"
              placeholder="定时任务执行时发送的消息内容"
            />
          </el-form-item>

          <el-form-item label="LLM模型" prop="execution_data.llm">
            <el-input
              v-model="taskForm.execution_data.llm"
              placeholder="留空使用默认模型"
            />
            <span style="margin-left: 8px; font-size: 12px; color: #999;">
              可选
            </span>
          </el-form-item>

          <el-form-item label="Agent模式" prop="execution_data.mode">
            <el-select
              v-model="taskForm.execution_data.mode"
              placeholder="留空使用默认模式"
              allow-clear
              style="width: 100%;"
            >
              <el-option label="Orchestrator" value="orchestrator" />
              <el-option label="Plan" value="plan" />
              <el-option label="Do" value="do" />
              <el-option label="Check" value="check" />
              <el-option label="Act" value="act" />
            </el-select>
            <span style="margin-left: 8px; font-size: 12px; color: #999;">
              可选
            </span>
          </el-form-item>
        </el-form>

        <template #footer>
          <el-button @click="taskDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveTask" :loading="savingTask">
            {{ isEditMode ? '更新' : '创建' }}
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue';
import { watch, onMounted } from 'vue';
import { useScheduledTasks } from '@/composables/scheduledTasks/useScheduledTasks';

const props = defineProps<{
  workspaceId?: string;
}>();

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
    delay: '延迟执行',
    at_time: '指定时间',
    recurring: '周期执行',
    cron: 'Cron表达式'
  };
  return labels[type] || type;
};

onMounted(() => {
  if (props.workspaceId) {
    loadScheduledTasks();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadScheduledTasks();
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
