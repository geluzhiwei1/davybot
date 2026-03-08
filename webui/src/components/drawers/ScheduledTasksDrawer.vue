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
        <el-table-column prop="name" label="任务名称" width="200" />

        <el-table-column prop="description" label="描述" show-overflow-tooltip />

        <el-table-column prop="cron" label="Cron表达式" width="120">
          <template #default="scope">
            <code style="font-size: 12px;">{{ scope.row.cron }}</code>
          </template>
        </el-table-column>

        <el-table-column prop="command" label="执行命令" show-overflow-tooltip>
          <template #default="scope">
            <code style="font-size: 12px;">{{ scope.row.command }}</code>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 4px; justify-content: center;">
              <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
                {{ scope.row.enabled ? '已启用' : '已禁用' }}
              </el-tag>
              <el-tag v-if="scope.row.status === 'running'" type="warning" size="small">
                运行中
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="下次运行" width="160">
          <template #default="scope">
            {{ scope.row.next_run || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="280" fixed="right">
          <template #default="scope">
            <el-button size="small" type="success" @click="runTaskNow(scope.row.id)" :disabled="!scope.row.enabled">
              立即运行
            </el-button>
            <el-button size="small" @click="toggleTask(scope.row)">
              {{ scope.row.enabled ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" type="primary" @click="editTask(scope.row)">
              编辑
            </el-button>
            <el-button size="small" type="danger" @click="deleteTask(scope.row.id)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loadingTasks && scheduledTasksList.length === 0" description="暂无定时任务" style="margin-top: 40px;">
        <el-button type="primary" @click="showCreateTaskDialog">创建第一个任务</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import { onMounted, watch } from 'vue';
import { useScheduledTasks } from '@/composables/scheduledTasks/useScheduledTasks';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  scheduledTasksList,
  loadingTasks,
  tasksStats,
  loadScheduledTasks,
  showCreateTaskDialog,
  editTask,
  deleteTask,
  toggleTask,
  runTaskNow
} = useScheduledTasks(props.workspaceId || '');

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
</style>
