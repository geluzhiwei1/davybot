/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-card
    class="resource-card"
    :class="{ 'is-installed': isInstalled }"
    shadow="hover"
  >
    <!-- Header -->
    <template #header>
      <div class="resource-header">
        <div class="resource-info">
          <el-icon class="resource-icon" :size="24">
            <component :is="getTypeIcon(resource.type)" />
          </el-icon>
          <div class="resource-title">
            <span class="resource-name">{{ resource.name }}</span>
            <el-tag
              v-if="resource.version"
              size="small"
              type="info"
            >
              {{ resource.version }}
            </el-tag>
          </div>
        </div>
        <el-tag
          :type="getTypeTagType(resource.type)"
          size="small"
        >
          {{ resource.type }}
        </el-tag>
      </div>
    </template>

    <!-- Body -->
    <div class="resource-body">
      <p class="resource-description">{{ resource.description }}</p>

      <!-- Tags -->
      <div v-if="resource.tags && resource.tags.length > 0" class="resource-tags">
        <el-tag
          v-for="tag in resource.tags.slice(0, 3)"
          :key="tag"
          size="small"
          class="tag-item"
        >
          {{ tag }}
        </el-tag>
        <el-tag
          v-if="resource.tags.length > 3"
          size="small"
          type="info"
        >
          +{{ resource.tags.length - 3 }}
        </el-tag>
      </div>

      <!-- Meta info -->
      <div class="resource-meta">
        <div class="meta-item">
          <el-icon><Download /></el-icon>
          <span>{{ formatNumber(resource.downloads) }}</span>
        </div>
        <div v-if="resource.rating" class="meta-item">
          <el-icon><Star /></el-icon>
          <span>{{ resource.rating.toFixed(1) }}</span>
        </div>
        <div v-if="resource.author" class="meta-item">
          <el-icon><User /></el-icon>
          <span>{{ resource.author }}</span>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <div class="resource-footer">
        <el-button
          v-if="!isInstalled"
          type="primary"
          size="small"
          :loading="installing"
          @click="handleInstall"
        >
          <el-icon><Plus /></el-icon>
          安装
        </el-button>
        <template v-else>
          <el-button
            type="success"
            size="small"
            @click="handleInstall"
          >
            <el-icon><Refresh /></el-icon>
            更新
          </el-button>
          <el-button
            size="small"
            @click="handleForceInstall"
          >
            <el-icon><RefreshRight /></el-icon>
            强制重装
          </el-button>
        </template>
        <el-button
          size="small"
          @click="handleViewDetails"
        >
          详情
        </el-button>
      </div>
    </template>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Plus, Refresh, RefreshRight, Download, Star, User } from '@element-plus/icons-vue';
import type { SearchResult, ResourceType } from '@/services/api/services/market';

interface Props {
  resource: SearchResult;
  installing?: boolean;
  installed?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  installing: false,
  installed: false
});

const emit = defineEmits<{
  (e: 'install', resource: SearchResult): void;
  (e: 'install-force', resource: SearchResult): void;
  (e: 'view-details', resource: SearchResult): void;
}>();

const isInstalled = computed(() => props.installed);

const getTypeIcon = (type: ResourceType) => {
  const icons: Record<ResourceType, unknown> = {
    skill: 'Files',
    agent: 'User',
    plugin: 'Connection'
  };
  return icons[type] || 'Document';
};

const getTypeTagType = (type: ResourceType) => {
  const types: Record<ResourceType, unknown> = {
    skill: 'success',
    agent: 'primary',
    plugin: 'warning'
  };
  return types[type] || 'info';
};

const formatNumber = (num: number) => {
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}k`;
  }
  return num.toString();
};

const handleInstall = () => {
  emit('install', props.resource);
};

const handleForceInstall = () => {
  emit('install-force', props.resource);
};

const handleViewDetails = () => {
  emit('view-details', props.resource);
};
</script>

<style scoped>
.resource-card {
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.resource-card.is-installed {
  border-left: 3px solid var(--el-color-success);
}

.resource-card:hover {
  transform: translateY(-2px);
}

.resource-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.resource-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.resource-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.resource-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.resource-name {
  font-weight: 600;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.resource-description {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resource-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.tag-item {
  cursor: pointer;
}

.resource-meta {
  display: flex;
  gap: 16px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.resource-footer {
  display: flex;
  gap: 8px;
}

.resource-footer .el-button {
  flex: 1;
}
</style>
