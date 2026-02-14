<!--
Copyright (c) 2025 格律至微
SPDX-License-Identifier: AGPL-3.0-only
-->
<template>
  <div class="plugin-config-panel">
    <el-card class="config-card">
      <template #header>
        <div class="card-header">
          <span>{{ $t('workspaceSettings.plugins.pluginConfig.title') }}</span>
          <div class="header-actions">
            <el-button type="success" size="small" @click="openMarketDialog">
              <el-icon>
                <ShoppingCart />
              </el-icon>
              {{ $t('workspaceSettings.plugins.marketInstall') }}
            </el-button>
            <el-button :icon="Refresh" size="small" :loading="loading" @click="loadPluginsConfig">
              {{ $t('common.refresh') }}
            </el-button>
          </div>
        </div>
      </template>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-container">
        <el-skeleton :rows="5" animated />
      </div>

      <!-- 插件配置内容 -->
      <div v-else class="plugins-content">
        <el-divider />

        <!-- 插件列表 -->
        <div class="plugins-list">
          <h4>{{ $t('workspaceSettings.plugins.pluginConfig.pluginList') }}</h4>

          <el-empty v-if="pluginsList.length === 0"
            :description="$t('workspaceSettings.plugins.pluginConfig.noPlugins')" />

          <div v-for="plugin in pluginsList" :key="plugin.id" class="plugin-item">
            <el-card class="plugin-card" :body-style="{ padding: '12px' }">
              <template #header>
                <div class="plugin-header">
                  <div class="plugin-info">
                    <span class="plugin-name">{{ plugin.name || plugin.id }}</span>
                    <el-tag v-if="plugin.version" type="info" size="small">
                      v{{ plugin.version }}
                    </el-tag>
                  </div>
                  <div class="plugin-actions">
                    <!-- 启用/禁用开关 -->
                    <el-switch v-model="plugin.enabled" :loading="plugin._loading" :disabled="!canEdit"
                      @change="togglePluginEnabled(plugin.id, $event)" active-text="启用" inactive-text="禁用"
                      style="margin-right: 8px;" />
                    <!-- 激活/停用开关 -->
                    <el-switch v-model="plugin.activated" :loading="plugin._activating"
                      :disabled="!plugin.enabled || !canEdit" @change="togglePluginActivated(plugin.id, $event)"
                      active-text="激活" inactive-text="停用" style="margin-right: 8px;" />
                    <el-button size="small" :icon="Setting" @click="editPluginSettings(plugin.id)">
                      {{ $t('workspaceSettings.plugins.pluginConfig.settings') }}
                    </el-button>
                    <el-button size="small" type="danger" :icon="Delete" :disabled="!canEdit"
                      @click="uninstallPlugin(plugin.id)">
                      {{ $t('workspaceSettings.plugins.table.uninstall') }}
                    </el-button>
                  </div>
                </div>
              </template>

              <!-- 插件设置预览 -->
              <div class="plugin-settings-preview">
                <div v-if="plugin.description" class="setting-item">
                  <span class="label">描述:</span>
                  <span class="value">{{ plugin.description }}</span>
                </div>
                <div v-if="plugin.version" class="setting-item">
                  <span class="label">{{ $t('workspaceSettings.plugins.pluginConfig.version') }}:</span>
                  <span class="value">{{ plugin.version }}</span>
                </div>
                <div v-if="plugin.install_path" class="setting-item">
                  <span class="label">{{ $t('workspaceSettings.plugins.pluginConfig.installPath') }}:</span>
                  <span class="value">{{ plugin.install_path }}</span>
                </div>
                <div v-if="plugin.type" class="setting-item">
                  <span class="label">类型:</span>
                  <span class="value">{{ plugin.type }}</span>
                </div>
              </div>
            </el-card>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <template #footer>
        <div class="card-footer">
          <el-button @click="loadPluginsConfig" :disabled="loading">
            {{ $t('common.refresh') }}
          </el-button>
          <el-button @click="resetPluginsConfig" :disabled="loading" type="warning">
            {{ $t('workspaceSettings.plugins.pluginConfig.resetToDefaults') }}
          </el-button>
          <el-button v-if="canEdit" type="primary" @click="savePluginsConfig" :loading="saving" :disabled="loading">
            {{ $t('common.save') }}
          </el-button>
        </div>
      </template>
    </el-card>

    <!-- 插件设置对话框 -->
    <PluginSettingsDialog v-model:visible="settingsDialogVisible" :workspace-id="workspaceId"
      :plugin-id="editingPluginId" :plugin-config="editingPluginConfig" @save="onPluginSettingsSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Refresh, Setting, ShoppingCart, Delete } from '@element-plus/icons-vue';
import {
  getPluginsConfig,
  updatePluginsConfig,
  resetPluginsConfig,
  updatePluginConfig,
  type PluginsConfig
} from '@/services/api/services/workspaces';
import { pluginsApi } from '@/services/api/plugins';

const { t } = useI18n();

// Props
interface Props {
  workspaceId: string;
  canEdit?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  canEdit: true
});

// Emits
const emit = defineEmits<{
  openMarket: [];
}>();

// 状态
const loading = ref(false);
const saving = ref(false);
const pluginsConfig = ref<PluginsConfig>({
  plugins: {}
});
const pluginsList = ref<unknown[]>([]);
const settingsDialogVisible = ref(false);
const editingPluginId = ref<string | null>(null);
const editingPluginConfig = ref<unknown>(null);

// 加载插件配置和列表
const loadPluginsConfig = async () => {
  loading.value = true;
  try {
    // 加载插件列表
    const plugins = await pluginsApi.listPlugins(props.workspaceId);
    // 添加加载状态字段
    pluginsList.value = plugins.map(p => ({
      ...p,
      _loading: false,
      _activating: false
    }));

    // 加载插件配置
    const response = await getPluginsConfig(props.workspaceId);
    if (response.success) {
      pluginsConfig.value = response.config as PluginsConfig;
    }
  } catch (error: unknown) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.loadError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    loading.value = false;
  }
};

// 保存插件配置
const savePluginsConfig = async () => {
  saving.value = true;
  try {
    const response = await updatePluginsConfig(props.workspaceId, {
      plugins: pluginsConfig.value.plugins
    });
    if (response.success) {
      pluginsConfig.value = response.config as PluginsConfig;
      ElMessage.success(t('workspaceSettings.plugins.pluginConfig.saveSuccess'));
    }
  } catch (error: unknown) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.saveError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    saving.value = false;
  }
};

// 重置插件配置
const resetPluginsConfig = async () => {
  try {
    await ElMessageBox.confirm(
      t('workspaceSettings.plugins.pluginConfig.resetConfirm'),
      t('workspaceSettings.plugins.pluginConfig.resetTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    );

    loading.value = true;
    const response = await resetPluginsConfig(props.workspaceId);
    if (response.success) {
      pluginsConfig.value = response.config as PluginsConfig;
      ElMessage.success(t('workspaceSettings.plugins.pluginConfig.resetSuccess'));
    }
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(t('workspaceSettings.plugins.pluginConfig.resetError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  } finally {
    loading.value = false;
  }
};

// 切换插件启用状态
const togglePluginEnabled = async (pluginId: string, enabled: boolean) => {
  const plugin = pluginsList.value.find(p => p.id === pluginId);
  if (!plugin) return;

  plugin._loading = true;
  try {
    if (enabled) {
      await pluginsApi.enablePlugin(props.workspaceId, pluginId);
    } else {
      await pluginsApi.disablePlugin(props.workspaceId, pluginId);
      // 后端的 disable action 已经处理了 deactivate，无需重复调用
      // 直接更新本地状态
      plugin.activated = false;
    }
    plugin.enabled = enabled;
    // 重新加载配置
    await loadPluginsConfig();
  } catch (error: unknown) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.toggleError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
    // 恢复原状态
    plugin.enabled = !enabled;
  } finally {
    plugin._loading = false;
  }
};

// 切换插件激活状态
const togglePluginActivated = async (pluginId: string, activated: boolean) => {
  const plugin = pluginsList.value.find(p => p.id === pluginId);
  if (!plugin || !plugin.enabled) return;

  plugin._activating = true;
  try {
    if (activated) {
      await pluginsApi.activatePlugin(props.workspaceId, pluginId);
    } else {
      await pluginsApi.deactivatePlugin(props.workspaceId, pluginId);
    }
    plugin.activated = activated;
    ElMessage.success(plugin.activated ? '插件已激活' : '插件已停用');
  } catch (error: unknown) {
    ElMessage.error('操作失败: ' + (error instanceof Error ? error.message : 'Unknown error'));
    // 恢复原状态
    plugin.activated = !activated;
  } finally {
    plugin._activating = false;
  }
};

// 编辑插件设置
const editPluginSettings = (pluginId: string) => {
  const plugin = pluginsList.value.find(p => p.id === pluginId);
  if (!plugin) return;

  console.log('[PluginConfigPanel] editPluginSettings called with pluginId:', pluginId);
  console.log('[PluginConfigPanel] Plugin object:', plugin);
  console.log('[PluginConfigPanel] Plugin.id:', plugin.id, 'Type:', typeof plugin.id);

  editingPluginId.value = pluginId;
  editingPluginConfig.value = plugin;
  settingsDialogVisible.value = true;
};

// 插件设置保存回调
const onPluginSettingsSaved = async (pluginId: string, newSettings: Record<string, unknown>) => {
  loading.value = true;
  try {
    const response = await updatePluginConfig(props.workspaceId, pluginId, newSettings);
    if (response.success) {
      // 更新本地配置
      if (pluginsConfig.value.plugins[pluginId]) {
        pluginsConfig.value.plugins[pluginId] = {
          ...pluginsConfig.value.plugins[pluginId],
          ...newSettings
        };
      }
      settingsDialogVisible.value = false;
      ElMessage.success(t('workspaceSettings.plugins.pluginConfig.settingsSaveSuccess'));
    }
  } catch (error: unknown) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.settingsSaveError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    loading.value = false;
  }
};


// 卸载插件
const uninstallPlugin = async (pluginId: string) => {
  try {
    await ElMessageBox.confirm(
      t('workspaceSettings.plugins.confirmUninstall', { name: pluginId }),
      t('common.confirm'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning',
      }
    );

    loading.value = true;
    const response = await pluginsApi.uninstallPlugin(props.workspaceId, pluginId);

    if (response.success) {
      ElMessage.success(t('workspaceSettings.plugins.uninstallSuccess'));

      // 从列表中移除
      const index = pluginsList.value.findIndex(p => p.id === pluginId);
      if (index !== -1) {
        pluginsList.value.splice(index, 1);
      }

      // 重新加载配置
      await loadPluginsConfig();
    } else {
      ElMessage.error(response.message || t('common.error'));
    }
  } catch (error: unknown) {
    ElMessage.error(t('common.error') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    loading.value = false;
  }
};

// 打开集市对话框
const openMarketDialog = () => {
  emit('openMarket');
};

// 组件挂载时加载配置
onMounted(() => {
  loadPluginsConfig();
});
</script>

<style scoped lang="scss">
.plugin-config-panel {
  padding: 20px;

  .config-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 16px;
      font-weight: 600;

      .header-actions {
        display: flex;
        gap: 8px;
        align-items: center;
      }
    }

    .loading-container {
      padding: 20px;
    }

    .plugins-content {
      .global-settings {
        margin-bottom: 24px;
      }

      .plugins-list {
        h4 {
          margin-bottom: 16px;
        }

        .plugin-item {
          margin-bottom: 16px;

          .plugin-card {
            .plugin-header {
              display: flex;
              justify-content: space-between;
              align-items: center;
              gap: 12px;

              .plugin-info {
                display: flex;
                align-items: center;
                gap: 8px;
                flex: 1;

                .plugin-name {
                  font-weight: 600;
                  font-size: 14px;
                }
              }

              .plugin-actions {
                display: flex;
                gap: 8px;
              }
            }

            .plugin-settings-preview {
              margin-top: 12px;

              .setting-item {
                display: flex;
                align-items: flex-start;
                gap: 8px;
                padding: 4px 0;
                font-size: 13px;

                .label {
                  color: var(--el-text-color-secondary);
                  font-weight: 500;
                  flex-shrink: 0;
                  min-width: 60px;
                }

                .value {
                  color: var(--el-text-color-primary);
                  font-weight: 600;
                  text-align: left;
                }
              }
            }
          }
        }
      }
    }

    .card-footer {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
    }
  }
}
</style>
