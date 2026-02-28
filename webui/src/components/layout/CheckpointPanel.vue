<!--
检查点管理面板
集成到工作区设置中
-->
<template>
  <div class="checkpoint-panel">
    <!-- 说明信息 -->
    <el-alert :title="t('workspaceSettings.checkpoints.title')" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
      <template #default>
        <p style="margin: 0; font-size: 13px;">
          {{ t('workspaceSettings.checkpoints.description') }}
        </p>
      </template>
    </el-alert>

    <!-- 统计信息 -->
    <div v-if="statistics" class="statistics">
      <el-card class="stat-card">
        <template #header>{{ t('workspaceSettings.checkpoints.statistics') }}</template>
        <div class="stat-content">
          <div class="stat-item">
            <span class="stat-label">{{ t('workspaceSettings.checkpoints.totalCheckpoints') }}</span>
            <span class="stat-value">{{ statistics.total_checkpoints }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">{{ t('workspaceSettings.checkpoints.totalSize') }}</span>
            <span class="stat-value">{{ formatFileSize(statistics.total_size) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">{{ t('workspaceSettings.checkpoints.latest') }}</span>
            <span class="stat-value">{{ formatTimestamp(statistics.latest_checkpoint || "", 'time') }}</span>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 操作按钮 -->
    <div class="actions">
      <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
        {{ t('workspaceSettings.checkpoints.create') }}
      </el-button>
      <el-button :icon="Refresh" @click="loadCheckpoints" :loading="loading">
        {{ t('workspaceSettings.checkpoints.refresh') }}
      </el-button>
    </div>

    <!-- 检查点列表 -->
    <el-card v-loading="loading" style="margin-top: 16px;">
      <template #header>
        <div class="card-header">
          <span>{{ t('workspaceSettings.checkpoints.list') }}</span>
          <span v-if="checkpoints.length" class="checkpoint-count">
            {{ t('workspaceSettings.checkpoints.total', { count: checkpoints.length }) }}
          </span>
        </div>
      </template>

      <el-table
        :data="checkpoints"
        style="width: 100%"
        @row-click="selectCheckpoint"
        highlight-current-row
      >
        <el-table-column prop="checkpoint_id" :label="t('workspaceSettings.checkpoints.checkpointId')" width="220">
          <template #default="{ row }">
            <span class="checkpoint-id">{{ row.checkpoint_id.substring(0, 8) }}...</span>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" :label="t('workspaceSettings.checkpoints.createdAt')" width="160">
          <template #default="{ row }">
            {{ formatTimestamp(row.created_at, 'time') }}
          </template>
        </el-table-column>

        <el-table-column prop="size" :label="t('workspaceSettings.checkpoints.size')" width="120">
          <template #default="{ row }">
            {{ formatFileSize(row.size) }}
          </template>
        </el-table-column>

        <el-table-column prop="node_count" :label="t('workspaceSettings.checkpoints.nodeCount')" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.node_count }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="notes" :label="t('workspaceSettings.checkpoints.notes')" min-width="150">
          <template #default="{ row }">
            <span v-if="row.notes">{{ row.notes }}</span>
            <span v-else class="no-notes">-</span>
          </template>
        </el-table-column>

        <el-table-column :label="t('workspaceSettings.checkpoints.actions')" width="240" fixed="right">
          <template #default="{ row }">
            <el-button-group size="small">
              <el-button type="primary" @click.stop="restoreCheckpoint(row)">
                {{ t('workspaceSettings.checkpoints.restore') }}
              </el-button>
              <el-button @click.stop="downloadCheckpoint(row)">
                {{ t('workspaceSettings.checkpoints.download') }}
              </el-button>
              <el-button type="danger" @click.stop="deleteCheckpoint(row)">
                {{ t('workspaceSettings.checkpoints.delete') }}
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && checkpoints.length === 0" :description="t('workspaceSettings.checkpoints.empty')">
        <template #description>
          <p>{{ t('workspaceSettings.checkpoints.emptyHint') }}</p>
        </template>
      </el-empty>
    </el-card>

    <!-- 创建检查点对话框 -->
    <el-dialog v-model="showCreateDialog" :title="t('workspaceSettings.checkpoints.createDialog')" width="400px">
      <el-form label-position="top">
        <el-form-item :label="t('workspaceSettings.checkpoints.notesLabel')">
          <el-input
            v-model="createDescription"
            :placeholder="t('workspaceSettings.checkpoints.notesPlaceholder')"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="createCheckpoint">{{ t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Refresh } from '@element-plus/icons-vue';
import { formatTimestamp, formatFileSize } from '@/utils/formatters';
import type { CheckpointListItem, CheckpointStatistics } from '@/types/checkpoint';
import { checkpointsApi } from '@/services/api/services/checkpoints';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();

const loading = ref(true);
const error = ref<string | null>(null);
const checkpoints = ref<CheckpointListItem[]>([]);
const statistics = ref<CheckpointStatistics | null>(null);
const selectedCheckpoint = ref<CheckpointListItem | null>(null);
const showCreateDialog = ref(false);
const createDescription = ref("");

// 加载检查点列表
const loadCheckpoints = async () => {
  loading.value = true;
  error.value = null;
  try {
    const result = await checkpointsApi.list({
      task_graph_id: undefined,
      page: 1,
      limit: 100,
    });
    checkpoints.value = result;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load checkpoints";
    console.error("Failed to load checkpoints:", e);
  } finally {
    loading.value = false;
  }
};

// 加载统计信息
const loadStatistics = async () => {
  try {
    statistics.value = await checkpointsApi.getStatistics();
  } catch (e) {
    console.error("Failed to load statistics:", e);
  }
};

// 创建检查点
const createCheckpoint = async () => {
  try {
    await checkpointsApi.create({
      task_graph_id: "",
      description: createDescription.value,
    });
    ElMessage.success(t('workspaceSettings.checkpoints.createSuccess'));
    showCreateDialog.value = false;
    createDescription.value = "";
    await loadCheckpoints();
    await loadStatistics();
  } catch (e) {
    ElMessage.error(t('workspaceSettings.checkpoints.createFailed'));
    console.error("Failed to create checkpoint:", e);
  }
};

// 恢复检查点
const restoreCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    await ElMessageBox.confirm(
      `${t('workspaceSettings.checkpoints.restoreConfirm')}${checkpoint.checkpoint_id}?`,
      t('workspaceSettings.checkpoints.restoreTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: "warning",
      }
    );

    await checkpointsApi.restore({
      checkpoint_id: checkpoint.checkpoint_id,
      task_graph_id: "",
    });
    ElMessage.success(t('workspaceSettings.checkpoints.restoreSuccess'));
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error(t('workspaceSettings.checkpoints.restoreFailed'));
      console.error("Failed to restore checkpoint:", e);
    }
  }
};

// 删除检查点
const deleteCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    await ElMessageBox.confirm(
      `${t('workspaceSettings.checkpoints.deleteConfirm')}${checkpoint.checkpoint_id}?`,
      t('workspaceSettings.checkpoints.deleteTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: "warning",
      }
    );

    await checkpointsApi.delete(checkpoint.checkpoint_id);
    ElMessage.success(t('workspaceSettings.checkpoints.deleteSuccess'));
    await loadCheckpoints();
    await loadStatistics();
  } catch (e) {
    if (e !== "cancel") {
      ElMessage.error(t('workspaceSettings.checkpoints.deleteFailed'));
      console.error("Failed to delete checkpoint:", e);
    }
  }
};

// 下载检查点
const downloadCheckpoint = async (checkpoint: CheckpointListItem) => {
  try {
    const blob = await checkpointsApi.download(checkpoint.checkpoint_id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `checkpoint-${checkpoint.checkpoint_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success(t('workspaceSettings.checkpoints.downloadSuccess'));
  } catch (e) {
    ElMessage.error(t('workspaceSettings.checkpoints.downloadFailed'));
    console.error("Failed to download checkpoint:", e);
  }
};

// 选择检查点
const selectCheckpoint = (checkpoint: CheckpointListItem) => {
  selectedCheckpoint.value = checkpoint;
};

// 生命周期
onMounted(() => {
  loadCheckpoints();
  loadStatistics();
});
</script>

<style scoped lang="scss">
.checkpoint-panel {
  height: 100%;
  padding: 16px;

  .statistics {
    margin-bottom: 16px;
  }

  .stat-card {
    width: 100%;
  }

  .stat-content {
    display: flex;
    gap: 48px;
  }

  .stat-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .stat-label {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .stat-value {
    font-size: 18px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .actions {
    display: flex;
    gap: 12px;
  }

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .checkpoint-count {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .checkpoint-id {
    font-family: monospace;
    font-size: 12px;
  }

  .no-notes {
    color: var(--el-text-color-placeholder);
  }
}
</style>
