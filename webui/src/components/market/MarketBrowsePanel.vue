/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="market-browse-panel">
    <!-- Market Info Banner -->
    <div class="market-info-banner">
      <el-icon color="#409EFF">
        <InfoFilled />
      </el-icon>
      <span class="info-text">集市资源来源于 </span>
      <el-link type="primary" :href="marketUrl" target="_blank" :underline="false">
        {{ marketUrl }}
        <el-icon class="link-icon">
          <TopRight />
        </el-icon>
      </el-link>
    </div>

    <!-- Search Section -->
    <div class="search-section">
      <el-input v-model="searchQuery" placeholder="搜索资源..." clearable size="large" @keyup.enter="handleSearch">
        <template #prefix>
          <el-icon>
            <Search />
          </el-icon>
        </template>
        <template #append>
          <el-button :icon="Search" @click="handleSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <!-- Resource Type Tabs -->
    <el-tabs v-model="activeType" @tab-change="handleTabChange">
      <el-tab-pane label="Skills" name="skill">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <Files />
            </el-icon>
            Skills
          </span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="Plugins" name="plugin">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <Connection />
            </el-icon>
            Plugins
          </span>
        </template>
      </el-tab-pane>
      <el-tab-pane label="Agents" name="agent">
        <template #label>
          <span class="tab-label">
            <el-icon>
              <User />
            </el-icon>
            Agents
          </span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- Featured Section -->
    <div v-if="!hasSearchResults && featuredResources.length > 0" class="featured-section">
      <div class="section-header">
        <h3>推荐资源</h3>
        <el-text type="info">精选的{{ activeType }}资源</el-text>
      </div>
      <el-row :gutter="16">
        <el-col v-for="resource in featuredResources" :key="resource.id" :span="8">
          <ResourceCard :resource="resource" :installing="isInstalling(resource.name)"
            :installed="isResourceInstalled(resource)" @install="handleInstall" @view-details="handleViewDetails" />
        </el-col>
      </el-row>
    </div>

    <!-- Search Results -->
    <div v-if="hasSearchResults" class="results-section">
      <div class="section-header">
        <h3>搜索结果</h3>
        <el-text type="info">
          找到 {{ searchResults.length }} 个结果
        </el-text>
      </div>

      <el-row :gutter="16" v-loading="isSearching(activeType)">
        <el-col v-for="resource in searchResults" :key="resource.id" :span="8">
          <ResourceCard :resource="resource" :installing="isInstalling(resource.name)"
            :installed="isResourceInstalled(resource)" @install="handleInstall" @view-details="handleViewDetails" />
        </el-col>
      </el-row>

      <!-- Empty State -->
      <el-empty v-if="!isSearching(activeType) && searchResults.length === 0" description="未找到相关资源" />
    </div>

    <!-- Initial State -->
    <div v-if="!hasSearchResults && featuredResources.length === 0" class="empty-state">
      <el-empty description="搜索集市资源">
        <el-button type="primary" @click="handleLoadFeatured">
          加载推荐资源
        </el-button>
      </el-empty>
    </div>

    <!-- Resource Detail Dialog -->
    <ResourceDetailDialog v-model="detailDialogVisible" :resource="selectedResource" @install="handleInstall" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { Search, Files, Connection, User, InfoFilled, TopRight } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { useMarketStore } from '@/stores/market';
import ResourceCard from './ResourceCard.vue';
import ResourceDetailDialog from './ResourceDetailDialog.vue';
import type { SearchResult, ResourceType } from '@/services/api/services/market';

// Market URL
const marketUrl = 'http://www.davybot.com/market/';

interface Props {
  workspaceId: string;
  initialType?: ResourceType;
}

const props = withDefaults(defineProps<Props>(), {
  initialType: 'skill'
});

const marketStore = useMarketStore();

const activeType = ref<ResourceType>(props.initialType);
const searchQuery = ref('');

// Watch for initialType changes
watch(() => props.initialType, (newType) => {
  if (newType) {
    activeType.value = newType;
  }
});
const detailDialogVisible = ref(false);
const selectedResource = ref<SearchResult | null>(null);

// Computed
const searchResults = computed(() => marketStore.searchResults[activeType.value]);
const featuredResources = computed(() => marketStore.featuredResources[activeType.value]);
const hasSearchResults = computed(() => searchResults.value.length > 0);

// Methods
const isSearching = (type: ResourceType) => marketStore.isSearching(type);
const isInstalling = (name: string) => marketStore.isInstalling(name);
const isResourceInstalled = (resource: SearchResult) =>
  marketStore.isResourceInstalled(resource.type, resource.name);

const handleSearch = async () => {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词');
    return;
  }

  await marketStore.searchResources(activeType.value, searchQuery.value, 20);
};

const handleTabChange = async () => {
  // Clear previous search when switching tabs
  marketStore.clearSearchResults(activeType.value);
  searchQuery.value = '';

  // Load featured resources for the new tab
  await handleLoadFeatured();
};

const handleLoadFeatured = async () => {
  await marketStore.loadFeaturedResources(activeType.value, 9);
};

const handleInstall = async (resource: SearchResult) => {
  const result = await marketStore.installResource(resource.type, resource.name);

  if (result) {
    ElMessage.success(`安装 ${resource.name} 成功`);
  }
};

const handleViewDetails = (resource: SearchResult) => {
  selectedResource.value = resource;
  detailDialogVisible.value = true;
};

// Lifecycle
onMounted(async () => {
  marketStore.setWorkspaceId(props.workspaceId);
  await marketStore.loadAllInstalledResources();
  await handleLoadFeatured();
});
</script>

<style scoped>
.market-browse-panel {
  padding: 20px;
}

.market-info-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #e7f3ff 0%, #f0f5ff 100%);
  border: 1px solid #b3d8ff;
  border-radius: 8px;
  font-size: 14px;
}

.market-info-banner .info-text {
  color: var(--el-text-color-regular);
}

.market-info-banner .el-link {
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.market-info-banner .link-icon {
  font-size: 14px;
  transition: transform 0.2s;
}

.market-info-banner .el-link:hover .link-icon {
  transform: translate(2px, -2px);
}

.search-section {
  margin-bottom: 20px;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.featured-section,
.results-section {
  margin-top: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.empty-state {
  margin-top: 60px;
}

:deep(.el-tabs__content) {
  padding-top: 20px;
}

:deep(.el-col) {
  margin-bottom: 16px;
}
</style>
