/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-dialog
    v-model="visible"
    :title="resourceInfo?.result?.name || 'Resource Details'"
    width="700px"
    @close="handleClose"
  >
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else-if="resourceInfo" class="resource-detail">
      <!-- Header -->
      <div class="detail-header">
        <div class="header-left">
          <el-icon class="resource-type-icon" :size="32">
            <component :is="getTypeIcon(resourceInfo.result.type)" />
          </el-icon>
          <div>
            <h2 class="resource-name">{{ resourceInfo.result.name }}</h2>
            <div class="resource-meta">
              <el-tag :type="getTypeTagType(resourceInfo.result.type)">
                {{ resourceInfo.result.type }}
              </el-tag>
              <el-tag v-if="resourceInfo.result.version" type="info">
                v{{ resourceInfo.result.version }}
              </el-tag>
              <span class="meta-item">
                <el-icon><Download /></el-icon>
                {{ formatNumber(resourceInfo.result.downloads) }} 下载
              </span>
              <span v-if="resourceInfo.result.rating" class="meta-item">
                <el-icon><Star /></el-icon>
                {{ resourceInfo.result.rating.toFixed(1) }} 评分
              </span>
            </div>
          </div>
        </div>
      </div>

      <el-divider />

      <!-- Description -->
      <div class="detail-section">
        <h3>描述</h3>
        <p>{{ resourceInfo.result.description }}</p>
      </div>

      <!-- Tags -->
      <div v-if="resourceInfo.result.tags && resourceInfo.result.tags.length > 0" class="detail-section">
        <h3>标签</h3>
        <div class="tags-container">
          <el-tag
            v-for="tag in resourceInfo.result.tags"
            :key="tag"
            class="tag-item"
          >
            {{ tag }}
          </el-tag>
        </div>
      </div>

      <!-- Author -->
      <div v-if="resourceInfo.result.author" class="detail-section">
        <h3>作者</h3>
        <span>{{ resourceInfo.result.author }}</span>
      </div>

      <!-- Readme -->
      <div v-if="resourceInfo.readme" class="detail-section">
        <h3>详细说明</h3>
        <div class="readme-content" v-html="renderMarkdown(resourceInfo.readme)"></div>
      </div>

      <!-- Dependencies -->
      <div v-if="resourceInfo.dependencies && resourceInfo.dependencies.length > 0" class="detail-section">
        <h3>依赖</h3>
        <el-tag
          v-for="dep in resourceInfo.dependencies"
          :key="dep"
          type="warning"
          class="dep-item"
        >
          {{ dep }}
        </el-tag>
      </div>

      <!-- Installation Path -->
      <div v-if="resourceInfo.install_path" class="detail-section">
        <h3>安装路径</h3>
        <el-text type="info" size="small">{{ resourceInfo.install_path }}</el-text>
      </div>

      <!-- Python Version -->
      <div v-if="resourceInfo.python_version" class="detail-section">
        <h3>Python 版本</h3>
        <el-tag type="success">{{ resourceInfo.python_version }}</el-tag>
      </div>

      <!-- License -->
      <div v-if="resourceInfo.license" class="detail-section">
        <h3>许可证</h3>
        <el-text>{{ resourceInfo.license }}</el-text>
      </div>
    </div>

    <el-empty v-else description="无法加载资源详情" />

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
      <el-button
        type="primary"
        :loading="installing"
        @click="handleInstall"
      >
        安装到工作区
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { Download, Star, Files, User, Connection } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { useMarketStore } from '@/stores/market';
import type { SearchResult, ResourceInfo } from '@/services/api/services/market';

interface Props {
  modelValue: boolean;
  resource: SearchResult | null;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'install', resource: SearchResult): void;
}>();

const marketStore = useMarketStore();

const visible = ref(props.modelValue);
const loading = ref(false);
const installing = ref(false);
const resourceInfo = ref<ResourceInfo | null>(null);

watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal && props.resource) {
    loadResourceDetails();
  } else {
    resourceInfo.value = null;
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});

const loadResourceDetails = async () => {
  if (!props.resource) return;

  loading.value = true;
  try {
    const info = await marketStore.getResourceInfo(
      props.resource.type,
      props.resource.name
    );
    resourceInfo.value = info;
  } catch (err: unknown) {
    ElMessage.error(`加载资源详情失败: ${err.message}`);
  } finally {
    loading.value = false;
  }
};

const getTypeIcon = (type: string) => {
  const icons: Record<string, unknown> = {
    skill: Files,
    agent: User,
    plugin: Connection
  };
  return icons[type] || Files;
};

const getTypeTagType = (type: string) => {
  const types: Record<string, unknown> = {
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

const renderMarkdown = (content: string) => {
  // Simple markdown rendering - replace with proper library if needed
  return content
    .replace(/### (.*)/g, '<h4>$1</h4>')
    .replace(/## (.*)/g, '<h3>$1</h3>')
    .replace(/\n/g, '<br>');
};

const handleInstall = () => {
  if (props.resource) {
    emit('install', props.resource);
  }
};

const handleClose = () => {
  visible.value = false;
};
</script>

<style scoped>
.loading-container {
  padding: 20px;
}

.resource-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  flex: 1;
}

.resource-type-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.resource-name {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
}

.resource-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-section h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.detail-section p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.tags-container {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tag-item {
  cursor: pointer;
}

.dep-item {
  margin-right: 8px;
  margin-bottom: 8px;
}

.readme-content {
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
}

.readme-content :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
}

.readme-content :deep(h4) {
  margin-top: 12px;
  margin-bottom: 6px;
}
</style>
