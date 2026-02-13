/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Market Store
 *
 * Pinia store for managing market resources (skills, plugins, MCP servers).
 * Handles search, installation, and state management for market operations.
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { marketApi } from '@/services/api';
import type {
  SearchResult,
  InstalledResource,
  ResourceInfo,
  ResourceType,
  InstallResult
} from '@/services/api/services/market';
import { ElMessage } from 'element-plus';

export const useMarketStore = defineStore('market', () => {
  // ========================================================================
  // State
  // ========================================================================

  // Search results by resource type
  const searchResults = ref<Record<ResourceType, SearchResult[]>>({
    skill: [],
    agent: [],
    plugin: []
  });

  // Installed resources by type
  const installedResources = ref<Record<ResourceType, InstalledResource[]>>({
    skill: [],
    agent: [],
    plugin: []
  });

  // Current search query
  const currentQuery = ref<Record<ResourceType, string>>({
    skill: '',
    agent: '',
    plugin: ''
  });

  // Loading states
  const loading = ref<Record<ResourceType, boolean>>({
    skill: false,
    agent: false,
    plugin: false
  });

  const installing = ref<Record<string, boolean>>({});

  // Error states
  const error = ref<Record<ResourceType, string | null>>({
    skill: null,
    agent: null,
    plugin: null
  });

  // Pagination
  const pagination = ref<Record<ResourceType, {
    total: number;
    limit: number;
    offset: number;
  }>>({
    skill: { total: 0, limit: 20, offset: 0 },
    agent: { total: 0, limit: 20, offset: 0 },
    plugin: { total: 0, limit: 20, offset: 0 }
  });

  // Current workspace ID
  const currentWorkspaceId = ref<string | null>(null);

  // Featured resources
  const featuredResources = ref<Record<ResourceType, SearchResult[]>>({
    skill: [],
    agent: [],
    plugin: []
  });

  // ========================================================================
  // Computed
  // ========================================================================

  const hasResults = computed(() => {
    return (type: ResourceType) => searchResults.value[type].length > 0;
  });

  const hasInstalled = computed(() => {
    return (type: ResourceType) => installedResources.value[type].length > 0;
  });

  const isSearching = computed(() => {
    return (type: ResourceType) => loading.value[type];
  });

  const isInstalling = computed(() => {
    return (resourceId: string) => installing.value[resourceId] || false;
  });

  // ========================================================================
  // Actions
  // ========================================================================

  /**
   * Set current workspace ID
   */
  const setWorkspaceId = (workspaceId: string) => {
    currentWorkspaceId.value = workspaceId;
  };

  /**
   * Search for resources in the market
   */
  const searchResources = async (
    type: ResourceType,
    query: string,
    limit: number = 20
  ) => {
    if (!currentWorkspaceId.value) {
      ElMessage.warning('请先选择工作区');
      return;
    }

    loading.value[type] = true;
    error.value[type] = null;
    currentQuery.value[type] = query;

    try {
      const response = await marketApi.searchResources(query, type, limit);

      if (response.success) {
        searchResults.value[type] = response.results;
        pagination.value[type] = {
          total: response.total,
          limit,
          offset: 0
        };
      } else {
        throw new Error('Search failed');
      }
    } catch (err: unknown) {
      error.value[type] = err.message || '搜索失败';
      ElMessage.error(`搜索${type}失败: ${err.message}`);
      searchResults.value[type] = [];
    } finally {
      loading.value[type] = false;
    }
  };

  /**
   * Load featured resources
   */
  const loadFeaturedResources = async (type: ResourceType, limit: number = 10) => {
    try {
      const response = await marketApi.getFeatured(type, limit);
      if (response.success) {
        featuredResources.value[type] = response.resources;
      }
    } catch (err: unknown) {
      console.error('Failed to load featured resources:', err);
      ElMessage.error(`加载推荐资源失败: ${err.message}`);
    }
  };

  /**
   * Get detailed information about a resource
   */
  const getResourceInfo = async (type: ResourceType, name: string): Promise<ResourceInfo | null> => {
    try {
      const response = await marketApi.getResourceInfo(type, name);
      if (response.success && response.resource) {
        return response.resource;
      }
      return null;
    } catch (err: unknown) {
      ElMessage.error(`获取资源信息失败: ${err.message}`);
      return null;
    }
  };

  /**
   * Install a resource from the market
   */
  const installResource = async (
    type: ResourceType,
    name: string,
    force: boolean = false
  ): Promise<InstallResult | null> => {
    if (!currentWorkspaceId.value) {
      ElMessage.warning('请先选择工作区');
      return null;
    }

    const installKey = `${type}:${name}`;
    installing.value[installKey] = true;

    try {
      const response = await marketApi.installResource(
        type,
        name,
        currentWorkspaceId.value,
        force
      );

      if (response.success) {
        ElMessage.success(`安装 ${name} 成功`);

        // Refresh installed resources
        await loadInstalledResources(type);

        return response.result;
      } else {
        throw new Error('Installation failed');
      }
    } catch (err: unknown) {
      ElMessage.error(`安装 ${name} 失败: ${err.message}`);
      return null;
    } finally {
      installing.value[installKey] = false;
    }
  };

  /**
   * Load installed resources for a type
   */
  const loadInstalledResources = async (type: ResourceType) => {
    if (!currentWorkspaceId.value) {
      return;
    }

    try {
      const response = await marketApi.listInstalled(type, currentWorkspaceId.value);

      if (response.success) {
        installedResources.value[type] = response.resources;
      }
    } catch (err: unknown) {
      console.error(`Failed to load installed ${type}:`, err);
      ElMessage.error(`加载已安装${type}失败`);
    }
  };

  /**
   * Load all installed resources
   */
  const loadAllInstalledResources = async () => {
    if (!currentWorkspaceId.value) {
      return;
    }

    try {
      const allInstalled = await marketApi.listAllInstalled(currentWorkspaceId.value);
      installedResources.value = allInstalled;
    } catch (err: unknown) {
      console.error('Failed to load all installed resources:', err);
      ElMessage.error('加载已安装资源失败');
    }
  };

  /**
   * Uninstall a plugin
   */
  const uninstallPlugin = async (name: string) => {
    if (!currentWorkspaceId.value) {
      return;
    }

    try {
      const response = await marketApi.uninstallPlugin(name, currentWorkspaceId.value);

      if (response.success) {
        ElMessage.success(`卸载 ${name} 成功`);
        await loadInstalledResources('plugin');
        return true;
      }
      return false;
    } catch (err: unknown) {
      ElMessage.error(`卸载 ${name} 失败: ${err.message}`);
      return false;
    }
  };

  /**
   * Check if a resource is installed
   */
  const isResourceInstalled = (type: ResourceType, name: string): boolean => {
    return installedResources.value[type].some(
      resource => resource.name === name
    );
  };

  /**
   * Get installed resource by name
   */
  const getInstalledResource = (type: ResourceType, name: string): InstalledResource | undefined => {
    return installedResources.value[type].find(
      resource => resource.name === name
    );
  };

  /**
   * Clear search results
   */
  const clearSearchResults = (type?: ResourceType) => {
    if (type) {
      searchResults.value[type] = [];
      currentQuery.value[type] = '';
      error.value[type] = null;
    } else {
      // Clear all
      (['skill', 'agent', 'plugin'] as ResourceType[]).forEach(t => {
        searchResults.value[t] = [];
        currentQuery.value[t] = '';
        error.value[t] = null;
      });
    }
  };

  /**
   * Reset store state
   */
  const reset = () => {
    searchResults.value = {
      skill: [],
      agent: [],
      plugin: []
    };
    installedResources.value = {
      skill: [],
      agent: [],
      plugin: []
    };
    currentQuery.value = {
      skill: '',
      agent: '',
      plugin: ''
    };
    loading.value = {
      skill: false,
      agent: false,
      plugin: false
    };
    installing.value = {};
    error.value = {
      skill: null,
      agent: null,
      plugin: null
    };
    currentWorkspaceId.value = null;
  };

  return {
    // State
    searchResults,
    installedResources,
    currentQuery,
    loading,
    installing,
    error,
    pagination,
    currentWorkspaceId,
    featuredResources,

    // Computed
    hasResults,
    hasInstalled,
    isSearching,
    isInstalling,

    // Actions
    setWorkspaceId,
    searchResources,
    loadFeaturedResources,
    getResourceInfo,
    installResource,
    loadInstalledResources,
    loadAllInstalledResources,
    uninstallPlugin,
    isResourceInstalled,
    getInstalledResource,
    clearSearchResults,
    reset
  };
});
