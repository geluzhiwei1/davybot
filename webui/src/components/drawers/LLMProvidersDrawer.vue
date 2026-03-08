<template>
  <div class="llm-providers-drawer">
    <div class="drawer-content" v-loading="loading">
      <!-- Provider Header -->
      <div class="provider-header">
        <el-alert title="Provider 管理" type="info" :closable="false" show-icon>
          <template #default>
            <p style="margin: 0; font-size: 13px;">
              管理用户和工作区的 LLM Provider 配置。所有配置保存在 <code>settings.json</code>
            </p>
          </template>
        </el-alert>

        <div class="provider-actions" style="margin-top: 16px; display: flex; gap: 8px;">
          <el-button type="primary" @click="showCreateProviderDialog">
            <el-icon><Plus /></el-icon>
            添加 Provider
          </el-button>
          <el-button @click="loadLLMSettings" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <!-- Provider 列表 -->
      <el-table :data="providerList" style="width: 100%; margin-top: 16px;" border>
        <el-table-column prop="name" label="名称" width="200">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>{{ scope.row.name }}</span>
              <el-tag v-if="scope.row.name === llmSettings.currentApiConfigName" type="success"
                size="small">默认</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="source" label="来源" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.source === 'user' ? 'warning' : 'success'" size="small">
              {{ scope.row.source === 'user' ? '用户级' : '工作区级' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="apiProvider" label="类型" width="150">
          <template #default="scope">
            <el-tag :type="getProviderTagType(scope.row.apiProvider)" size="small">
              {{ getProviderDisplayName(scope.row.apiProvider) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="modelId" label="模型 ID" width="200" show-overflow-tooltip />

        <el-table-column prop="baseUrl" label="Base URL" show-overflow-tooltip />

        <el-table-column label="高级设置" width="180">
          <template #default="scope">
            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
              <el-tag v-if="scope.row.config.config?.diffEnabled || scope.row.config.diffEnabled" size="small"
                type="info">Diff</el-tag>
              <el-tag v-if="scope.row.config.config?.todoListEnabled || scope.row.config.todoListEnabled"
                size="small" type="info">TODO</el-tag>
              <el-tag
                v-if="scope.row.config.config?.enableReasoningEffort || scope.row.config.enableReasoningEffort"
                size="small" type="warning">推理</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="viewProvider(scope.row)">查看</el-button>
            <el-button size="small" type="primary" @click="editProvider(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteProvider(scope.row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh } from '@element-plus/icons-vue';
import { onMounted, watch } from 'vue';
import { useLLMProviders } from '@/composables/llm/useLLMProviders';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  llmSettings,
  loading,
  providerList,
  loadLLMSettings,
  showCreateProviderDialog,
  viewProvider,
  editProvider,
  deleteProvider,
  getProviderDisplayName,
  getProviderTagType
} = useLLMProviders(props.workspaceId || '');

// Load settings on mount
onMounted(() => {
  if (props.workspaceId) {
    loadLLMSettings();
  }
});

// Reload when workspaceId changes
watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadLLMSettings();
  }
});
</script>

<style scoped>
.llm-providers-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
