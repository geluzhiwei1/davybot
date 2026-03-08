<template>
  <div class="agents-drawer">
    <div class="drawer-content" v-loading="loadingAgents">
      <!-- Header -->
      <el-alert title="智能体管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区智能体。智能体是具有特定角色和行为的AI代理。
          </p>
        </template>
      </el-alert>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">当前智能体 ({{ modeList.length }})</span>
        <div>
          <el-button type="success" size="small" @click="openMarketDialog('agent')">
            <el-icon><ShoppingCart /></el-icon>
            市场安装
          </el-button>
          <el-button type="primary" size="small" @click="showCreateModeDialog" style="margin-left: 8px;">
            <el-icon><Plus /></el-icon>
            添加智能体
          </el-button>
        </div>
      </div>

      <!-- Agents Table -->
      <el-table :data="modeList" stripe style="width: 100%;">
        <el-table-column prop="name" label="名称" width="200">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>{{ scope.row.name }}</span>
              <el-tag v-if="scope.row.is_default" type="success" size="small">默认</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="slug" label="标识符" width="180" />

        <el-table-column prop="source" label="来源" width="100">
          <template #default="scope">
            <el-tag
              :type="scope.row.source === 'system' ? 'info' : scope.row.source === 'user' ? 'warning' : 'success'"
              size="small">
              {{ scope.row.source === 'system' ? '系统' : scope.row.source === 'user' ? '用户' : '工作区' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="description" label="描述" show-overflow-tooltip />

        <el-table-column label="操作" width="280" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" @click="editMode(scope.row)"
              :disabled="scope.row.source === 'system'">编辑</el-button>
            <el-button size="small" type="warning" @click="editModeRules(scope.row)">
              <el-icon><Document /></el-icon>
              规则
            </el-button>
            <el-button size="small" type="danger" @click="deleteMode(scope.row.slug)"
              :disabled="scope.row.source === 'system'">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import { onMounted, watch } from 'vue';
import { useAgents } from '@/composables/agents/useAgents';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  modeList,
  loadingAgents,
  loadAgents,
  showCreateModeDialog,
  editMode,
  editModeRules,
  deleteMode,
  openMarketDialog
} = useAgents(props.workspaceId || '');

onMounted(() => {
  if (props.workspaceId) {
    loadAgents();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadAgents();
  }
});
</script>

<style scoped>
.agents-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
