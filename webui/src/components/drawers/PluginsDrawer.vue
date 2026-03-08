<template>
  <div class="plugins-drawer">
    <div class="drawer-content" v-loading="loadingPlugins">
      <!-- Header -->
      <el-alert title="插件管理" type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #default>
          <p style="margin: 0; font-size: 13px;">
            管理工作区插件。插件可以扩展Dawei的功能，添加新的工具和能力。
          </p>
        </template>
      </el-alert>

      <!-- Actions -->
      <div style="margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-weight: 600;">当前插件 ({{ pluginList.length }})</span>
        <div>
          <el-button type="success" size="small" @click="openMarketDialog('plugin')">
            <el-icon><ShoppingCart /></el-icon>
            市场安装
          </el-button>
          <el-button type="primary" size="small" @click="loadPlugins" :loading="loadingPlugins" style="margin-left: 8px;">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <!-- Plugins Table -->
      <el-table :data="pluginList" stripe style="width: 100%;" max-height="calc(100vh - 300px)">
        <el-table-column prop="name" label="名称" width="200" />

        <el-table-column prop="type" label="类型" width="100">
          <template #default="scope">
            <el-tag :type="getTypeTagType(scope.row.type)" size="small">
              {{ getTypeLabel(scope.row.type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="version" label="版本" width="100" />

        <el-table-column prop="author" label="作者" width="150" show-overflow-tooltip />

        <el-table-column prop="description" label="描述" show-overflow-tooltip />

        <el-table-column label="状态" width="120">
          <template #default="scope">
            <div style="display: flex; gap: 4px;">
              <el-tag v-if="scope.row.enabled" type="success" size="small">启用</el-tag>
              <el-tag v-else type="info" size="small">禁用</el-tag>
              <el-tag v-if="scope.row.activated" type="primary" size="small">激活</el-tag>
              <el-tag v-else type="warning" size="small">未激活</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="320" fixed="right">
          <template #default="scope">
            <el-button
              v-if="!scope.row.enabled"
              link
              type="success"
              size="small"
              @click="enablePlugin(scope.row)"
            >
              启用
            </el-button>
            <el-button
              v-else
              link
              type="warning"
              size="small"
              @click="disablePlugin(scope.row)"
            >
              禁用
            </el-button>
            <el-button
              v-if="!scope.row.activated"
              link
              type="primary"
              size="small"
              @click="activatePlugin(scope.row)"
            >
              激活
            </el-button>
            <el-button
              v-else
              link
              type="info"
              size="small"
              @click="deactivatePlugin(scope.row)"
            >
              停用
            </el-button>
            <el-button link type="primary" size="small" @click="reloadPlugin(scope.row)">
              重载
            </el-button>
            <el-button link type="primary" size="small" @click="openConfigDialog(scope.row)">
              配置
            </el-button>
            <el-button link type="danger" size="small" @click="deletePlugin(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Plugin Config Dialog -->
      <el-dialog
        v-model="showConfigDialog"
        :title="`配置插件 - ${editingPlugin?.name || ''}`"
        width="700px"
        :close-on-click-modal="false"
      >
        <PluginConfigForm
          v-if="showConfigDialog && editingPlugin && workspaceId"
          :workspace-id="workspaceId"
          :plugin-id="editingPlugin.id"
          @saved="handleConfigSaved"
          @cancel="showConfigDialog = false"
        />
      </el-dialog>

      <!-- Market Dialog -->
      <MarketDialog
        v-if="workspaceId"
        v-model="showMarketDialog"
        :workspace-id="workspaceId"
        initial-type="plugin"
        @installed="handleMarketInstalled"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Refresh, ShoppingCart } from '@element-plus/icons-vue';
import { watch, onMounted } from 'vue';
import { usePlugins } from '@/composables/plugins/usePlugins';
import PluginConfigForm from '@/components/workspace/PluginConfigForm.vue';
import MarketDialog from '@/components/market/MarketDialog.vue';
import type { PluginInfo } from '@/types/plugins';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  pluginList,
  loadingPlugins,
  loadPlugins,
  enablePlugin,
  disablePlugin,
  activatePlugin,
  deactivatePlugin,
  reloadPlugin,
  deletePlugin,
  openConfigDialog,
  saveConfig,
  openMarketDialog,
  installFromMarket,
  // 对话框状态
  showConfigDialog,
  editingPlugin,
  // 市场相关状态
  showMarketDialog
} = usePlugins(props.workspaceId);

// 获取类型标签颜色
const getTypeTagType = (type: string) => {
  const typeMap: Record<string, string> = {
    channel: 'success',
    tool: 'primary',
    service: 'warning',
    memory: 'info'
  };
  return typeMap[type] || 'info';
};

// 获取类型标签文本
const getTypeLabel = (type: string) => {
  const typeMap: Record<string, string> = {
    channel: '通道',
    tool: '工具',
    service: '服务',
    memory: '记忆'
  };
  return typeMap[type] || type;
};

// 处理配置保存成功
const handleConfigSaved = async (config: Record<string, unknown>) => {
  await saveConfig(config);
};

// 处理市场安装成功事件
const handleMarketInstalled = async (type: string) => {
  if (type === 'plugin') {
    // 重新加载插件列表
    await loadPlugins(true);
  }
};

onMounted(() => {
  if (props.workspaceId) {
    loadPlugins();
  }
});

watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadPlugins();
  }
});
</script>

<style scoped>
.plugins-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
