/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="market-installed-panel">
    <!-- Header -->
    <div class="panel-header">
      <div class="header-info">
        <h3>已安装资源</h3>
        <el-text type="info">管理工作区中安装的资源</el-text>
      </div>
      <el-button :icon="Refresh" @click="handleRefresh">刷新</el-button>
    </div>

    <!-- Resource Type Tabs -->
    <el-tabs v-model="activeType" @tab-change="handleTabChange">
      <el-tab-pane label="Skills" name="skill">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <Files />
            </el-icon>
            Skills <el-badge v-if="counts.skill > 0" :value="counts.skill" />
          </span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="Plugins" name="plugin">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <Connection />
            </el-icon>
            Plugins <el-badge v-if="counts.plugin > 0" :value="counts.plugin" />
          </span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="Agents" name="agent">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <User />
            </el-icon>
            Agents <el-badge v-if="counts.agent > 0" :value="counts.agent" />
          </span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- Resources List -->
    <div v-loading="loading" class="resources-list">
      <!-- Skills Table -->
      <el-table v-if="activeType === 'skill'" :data="installedSkills" stripe>
        <el-table-column prop="name" label="名称" width="200" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="install_path" label="安装路径" show-overflow-tooltip />
        <el-table-column prop="installed_at" label="安装时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.installed_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
              {{ scope.row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="scope">
            <el-button size="small" type="danger" @click="handleUninstall(scope.row)">
              卸载
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Plugins Table -->
      <el-table v-else-if="activeType === 'plugin'" :data="installedPlugins" stripe>
        <el-table-column prop="name" label="名称" width="200" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="install_path" label="安装路径" show-overflow-tooltip />
        <el-table-column prop="installed_at" label="安装时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.installed_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
              {{ scope.row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="scope">
            <el-button size="small" type="danger" @click="handleUninstall(scope.row)">
              卸载
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Agents Table -->
      <el-table v-else-if="activeType === 'agent'" :data="installedAgents" stripe>
        <el-table-column prop="name" label="名称" width="200" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="install_path" label="安装路径" show-overflow-tooltip />
        <el-table-column prop="installed_at" label="安装时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.installed_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
              {{ scope.row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="scope">
            <el-button size="small" type="danger" @click="handleUninstall(scope.row)">
              卸载
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <el-empty v-if="!loading && currentResources.length === 0" description="暂无已安装资源">
        <el-button type="primary" @click="handleBrowseMarket">
          浏览集市
        </el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Refresh, Files, Connection, User } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useMarketStore } from '@/stores/market';
import type { InstalledResource, ResourceType } from '@/services/api/services/market';

interface Props {
  workspaceId: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'browse-market'): void;
}>();

const marketStore = useMarketStore();

const activeType = ref<ResourceType>('skill');
const loading = ref(false);

// Computed
const installedSkills = computed(() => marketStore.installedResources.skill);
const installedPlugins = computed(() => marketStore.installedResources.plugin);
const installedAgents = computed(() => marketStore.installedResources.agent);

const currentResources = computed(() => {
  const resourcesMap: Record<ResourceType, InstalledResource[]> = {
    skill: installedSkills.value,
    plugin: installedPlugins.value,
    agent: installedAgents.value
  };
  return resourcesMap[activeType.value];
});

const counts = computed(() => ({
  skill: installedSkills.value.length,
  plugin: installedPlugins.value.length,
  agent: installedAgents.value.length
}));

// Methods
const handleTabChange = async () => {
  // Reload resources for the new tab
  await loadResources();
};

const loadResources = async () => {
  loading.value = true;
  try {
    await marketStore.loadInstalledResources(activeType.value);
  } finally {
    loading.value = false;
  }
};

const handleRefresh = async () => {
  await loadResources();
  ElMessage.success('刷新成功');
};

const handleUninstall = async (resource: InstalledResource) => {
  try {
    await ElMessageBox.confirm(
      `确定要卸载 "${resource.name}" 吗？此操作不可恢复。`,
      '确认卸载',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    if (activeType.value === 'plugin') {
      const success = await marketStore.uninstallPlugin(resource.name);
      if (success) {
        await loadResources();
      }
    } else {
      // TODO: Implement uninstall for skills and agents
      ElMessage.info(`${activeType.value} 卸载功能即将推出`);
    }
  } catch {
    // User cancelled
  }
};

const handleBrowseMarket = () => {
  emit('browse-market');
};

const formatDate = (dateStr: string | undefined) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('zh-CN');
};

// Lifecycle
onMounted(async () => {
  marketStore.setWorkspaceId(props.workspaceId);
  await loadResources();
});
</script>

<style scoped>
.market-installed-panel {
  padding: 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-info h3 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 600;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.resources-list {
  margin-top: 20px;
}
</style>
