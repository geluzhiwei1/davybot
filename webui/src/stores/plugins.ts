/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Plugins Store
 *
 * Pinia store for managing plugin state
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PluginInfo, PluginSettings, PluginStatistics } from '@/types/plugins'
import { pluginsApi } from '@/services/api/plugins'

export const usePluginsStore = defineStore('plugins', () => {
  // State
  const plugins = ref<PluginInfo[]>([])
  const currentPlugin = ref<PluginInfo | null>(null)
  const currentPluginSettings = ref<PluginSettings | null>(null)
  const statistics = ref<PluginStatistics | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const enabledPlugins = computed(() =>
    plugins.value.filter(p => p.enabled)
  )

  const activatedPlugins = computed(() =>
    plugins.value.filter(p => p.activated)
  )

  const pluginsByType = computed(() => {
    const grouped: Record<string, PluginInfo[]> = {}

    for (const plugin of plugins.value) {
      if (!grouped[plugin.type]) {
        grouped[plugin.type] = []
      }

      grouped[plugin.type].push(plugin)
    }

    return grouped
  })

  // Actions
  async function fetchPlugins(workspaceId: string, options?: { plugin_type?: string, activated_only?: boolean }) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when fetching plugins')
    }

    loading.value = true
    error.value = null

    try {
      plugins.value = await pluginsApi.listPlugins(workspaceId, options)
    } catch (e: unknown) {
      error.value = e.message || 'Failed to fetch plugins'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchPlugin(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when fetching plugin')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when fetching plugin')
    }

    loading.value = true
    error.value = null

    try {
      currentPlugin.value = await pluginsApi.getPlugin(workspaceId, pluginId)
    } catch (e: unknown) {
      error.value = e.message || 'Failed to fetch plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchPluginSettings(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when fetching plugin settings')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when fetching plugin settings')
    }

    loading.value = true
    error.value = null

    try {
      currentPluginSettings.value = await pluginsApi.getPluginSettings(workspaceId, pluginId)
    } catch (e: unknown) {
      error.value = e.message || 'Failed to fetch plugin settings'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updatePluginSettings(
    workspaceId: string,
    pluginId: string,
    settings: Partial<PluginSettings>
  ) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when updating plugin settings')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when updating plugin settings')
    }
    if (!settings || Object.keys(settings).length === 0) {
      throw new Error('[PluginsStore] settings cannot be empty when updating plugin settings')
    }

    loading.value = true
    error.value = null

    try {
      const result = await pluginsApi.updatePluginSettings(workspaceId, pluginId, settings)

      // Update local state
      currentPluginSettings.value = result.settings

      // Update plugin in list
      const index = plugins.value.findIndex(p => p.id === pluginId)
      if (index !== -1 && settings.enabled !== undefined) {
        plugins.value[index].enabled = settings.enabled
      }

      return result
    } catch (e: unknown) {
      error.value = e.message || 'Failed to update plugin settings'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function enablePlugin(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when enabling plugin')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when enabling plugin')
    }

    loading.value = true
    error.value = null

    try {
      await pluginsApi.enablePlugin(workspaceId, pluginId)

      // Update local state
      const index = plugins.value.findIndex(p => p.id === pluginId)
      if (index !== -1) {
        plugins.value[index].enabled = true
        plugins.value[index].activated = true
      }
    } catch (e: unknown) {
      error.value = e.message || 'Failed to enable plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function disablePlugin(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when disabling plugin')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when disabling plugin')
    }

    loading.value = true
    error.value = null

    try {
      await pluginsApi.disablePlugin(workspaceId, pluginId)

      // Update local state
      const index = plugins.value.findIndex(p => p.id === pluginId)
      if (index !== -1) {
        plugins.value[index].enabled = false
        plugins.value[index].activated = false
      }
    } catch (e: unknown) {
      error.value = e.message || 'Failed to disable plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function activatePlugin(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when activating plugin')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when activating plugin')
    }

    loading.value = true
    error.value = null

    try {
      await pluginsApi.activatePlugin(workspaceId, pluginId)

      // Update local state
      const index = plugins.value.findIndex(p => p.id === pluginId)
      if (index !== -1) {
        plugins.value[index].activated = true
      }
    } catch (e: unknown) {
      error.value = e.message || 'Failed to activate plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function deactivatePlugin(workspaceId: string, pluginId: string) {
    // ✅ Fast Fail: 验证必需参数
    if (!workspaceId || workspaceId.trim() === '') {
      throw new Error('[PluginsStore] workspaceId cannot be empty when deactivating plugin')
    }
    if (!pluginId || pluginId.trim() === '') {
      throw new Error('[PluginsStore] pluginId cannot be empty when deactivating plugin')
    }

    loading.value = true
    error.value = null

    try {
      await pluginsApi.deactivatePlugin(workspaceId, pluginId)

      // Update local state
      const index = plugins.value.findIndex(p => p.id === pluginId)
      if (index !== -1) {
        plugins.value[index].activated = false
      }
    } catch (e: unknown) {
      error.value = e.message || 'Failed to deactivate plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function reloadPlugin(workspaceId: string, pluginId: string) {
    loading.value = true
    error.value = null

    try {
      await pluginsApi.reloadPlugin(workspaceId, pluginId)

      // Refresh plugin list
      await fetchPlugins(workspaceId)
    } catch (e: unknown) {
      error.value = e.message || 'Failed to reload plugin'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchStatistics(workspaceId: string) {
    loading.value = true
    error.value = null

    try {
      statistics.value = await pluginsApi.getStatistics(workspaceId)
    } catch (e: unknown) {
      error.value = e.message || 'Failed to fetch statistics'
      throw e
    } finally {
      loading.value = false
    }
  }

  function clearCurrentPlugin() {
    currentPlugin.value = null
    currentPluginSettings.value = null
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    plugins,
    currentPlugin,
    currentPluginSettings,
    statistics,
    loading,
    error,

    // Computed
    enabledPlugins,
    activatedPlugins,
    pluginsByType,

    // Actions
    fetchPlugins,
    fetchPlugin,
    fetchPluginSettings,
    updatePluginSettings,
    enablePlugin,
    disablePlugin,
    activatePlugin,
    deactivatePlugin,
    reloadPlugin,
    fetchStatistics,
    clearCurrentPlugin,
    clearError
  }
})
