/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Plugins composable
 *
 * Provides plugin management functionality for workspaces
 */

import { ref } from 'vue';
import { pluginsApi } from '@/services/api/plugins';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { PluginInfo } from '@/types/plugins';
import { marketApi } from '@/services/api/services/market';

export function usePlugins(workspaceId?: string) {
  const pluginList = ref<PluginInfo[]>([]);
  const loadingPlugins = ref(false);

  // Plugin对话框相关
  const showConfigDialog = ref(false);
  const editingPlugin = ref<PluginInfo | null>(null);
  const savingPlugin = ref(false);

  // 市场对话框相关
  const showMarketDialog = ref(false);
  const installingFromMarket = ref(false);

  // 加载插件列表
  const loadPlugins = async (forceReload: boolean = false) => {
    if (!workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    loadingPlugins.value = true;
    try {
      const plugins = await pluginsApi.listPlugins(workspaceId, { plugin_type: undefined });
      pluginList.value = plugins;
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg = err.response?.data?.detail || err.message || '加载插件列表失败';
      ElMessage.error(`加载插件列表失败: ${errorMsg}`);
      console.error('Failed to load plugins:', error);
    } finally {
      loadingPlugins.value = false;
    }
  };

  // 启用插件
  const enablePlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await pluginsApi.enablePlugin(workspaceId, plugin.id);
      ElMessage.success(`插件 "${plugin.name}" 已启用`);
      await loadPlugins(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '启用失败');
      console.error('Failed to enable plugin:', error);
    }
  };

  // 禁用插件
  const disablePlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await pluginsApi.disablePlugin(workspaceId, plugin.id);
      ElMessage.success(`插件 "${plugin.name}" 已禁用`);
      await loadPlugins(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '禁用失败');
      console.error('Failed to disable plugin:', error);
    }
  };

  // 激活插件
  const activatePlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await pluginsApi.activatePlugin(workspaceId, plugin.id);
      ElMessage.success(`插件 "${plugin.name}" 已激活`);
      await loadPlugins(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '激活失败');
      console.error('Failed to activate plugin:', error);
    }
  };

  // 停用插件
  const deactivatePlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await pluginsApi.deactivatePlugin(workspaceId, plugin.id);
      ElMessage.success(`插件 "${plugin.name}" 已停用`);
      await loadPlugins(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '停用失败');
      console.error('Failed to deactivate plugin:', error);
    }
  };

  // 重载插件
  const reloadPlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await pluginsApi.reloadPlugin(workspaceId, plugin.id);
      ElMessage.success(`插件 "${plugin.name}" 已重载`);
      await loadPlugins(true);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '重载失败');
      console.error('Failed to reload plugin:', error);
    }
  };

  // 删除插件
  const deletePlugin = async (plugin: PluginInfo) => {
    if (!workspaceId) return;

    try {
      await ElMessageBox.confirm(
        `确定要删除插件 "${plugin.name}" 吗？此操作不可撤销。`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      const result = await pluginsApi.uninstallPlugin(workspaceId, plugin.id);

      if (result.success) {
        ElMessage.success(result.message || '插件删除成功');
        await loadPlugins(true);
      }
    } catch (error: unknown) {
      if (error !== 'cancel') {
        const err = error as { response?: { data?: { detail?: string } } };
        ElMessage.error(err.response?.data?.detail || '删除失败');
        console.error('Failed to delete plugin:', error);
      }
    }
  };

  // 打开配置对话框
  const openConfigDialog = (plugin: PluginInfo) => {
    editingPlugin.value = plugin;
    showConfigDialog.value = true;
  };

  // 保存配置
  const saveConfig = async (config: Record<string, unknown>) => {
    if (!workspaceId || !editingPlugin.value) return;

    savingPlugin.value = true;
    try {
      const result = await pluginsApi.saveConfig(
        workspaceId,
        editingPlugin.value.id,
        config
      );

      if (result.success) {
        ElMessage.success(result.message || '配置保存成功');
        showConfigDialog.value = false;
        await loadPlugins(true);
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '保存配置失败');
      console.error('Failed to save plugin config:', error);
    } finally {
      savingPlugin.value = false;
    }
  };

  // 打开市场对话框
  const openMarketDialog = (type: 'agent' | 'skill' | 'plugin') => {
    if (type === 'plugin') {
      showMarketDialog.value = true;
    } else {
      ElMessage.info(`${type} 市场功能请使用对应的标签页`);
    }
  };

  // 从市场安装插件
  const installFromMarket = async (pluginName: string, force = false) => {
    if (!workspaceId) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    installingFromMarket.value = true;
    try {
      const response = await marketApi.installPlugin(pluginName, workspaceId, force);

      if (response.success) {
        ElMessage.success(`插件 "${pluginName}" 安装成功`);

        // 关键步骤：调用后端API重新加载配置
        try {
          const result = await apiManager.getWorkspacesApi().reloadWorkspaceConfig(
            workspaceId,
            'tools',  // plugin 对应 tools 配置
            true  // 强制重新加载
          );
          if (result.success) {
            console.log('[Plugins] Config reload result:', result);
          }
        } catch (error) {
          console.error('[Plugins] Failed to reload config:', error);
          // 即使重新加载失败,也继续刷新前端列表
        }

        // 重新加载插件列表
        await loadPlugins(true);
        // 关闭市场对话框
        showMarketDialog.value = false;
      } else {
        ElMessage.error(`安装失败: ${response.message}`);
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '安装失败');
      console.error('Failed to install plugin:', error);
    } finally {
      installingFromMarket.value = false;
    }
  };

  return {
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
    savingPlugin,
    // 市场相关状态
    showMarketDialog,
    installingFromMarket
  };
}
