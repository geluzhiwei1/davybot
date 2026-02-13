/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-dialog
    v-model="visible"
    :title="title"
    width="90%"
    :close-on-click-modal="false"
    destroy-on-close
    class="market-dialog-wrapper"
    @close="handleClose"
    @closed="handleClosed">
    <div class="market-dialog-content">
      <div class="market-layout">
        <!-- Left Sidebar - Resource Type Selector -->
        <div class="market-sidebar">
          <div class="sidebar-title">资源类型</div>
          <el-radio-group v-model="activeType" size="large" @change="handleTypeChange" direction="vertical">
            <el-radio-button value="skill">
              <el-icon>
                <Files />
              </el-icon>
              <span>Skills</span>
            </el-radio-button>
            <el-radio-button value="agent">
              <el-icon>
                <User />
              </el-icon>
              <span>Agents</span>
            </el-radio-button>
            <el-radio-button value="plugin">
              <el-icon>
                <Connection />
              </el-icon>
              <span>Plugins</span>
            </el-radio-button>
          </el-radio-group>
        </div>

        <!-- Right Content - Market Content -->
        <div class="market-content" v-loading="loading">
          <MarketBrowsePanel v-if="visible" :workspace-id="workspaceId" :initial-type="activeType" />
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Files, User, Connection } from '@element-plus/icons-vue';
import MarketBrowsePanel from './MarketBrowsePanel.vue';
import type { ResourceType } from '@/services/api/services/market';

interface Props {
  modelValue: boolean;
  workspaceId: string;
  initialType?: ResourceType;
}

const props = withDefaults(defineProps<Props>(), {
  initialType: 'skill'
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
  (e: 'closed'): void;
}>();

const visible = ref(props.modelValue);
const activeType = ref<ResourceType>(props.initialType);
const loading = ref(false);

const title = computed(() => {
  const typeNames = {
    skill: 'Skills 集市',
    agent: 'Agents 集市',
    plugin: 'Plugins 集市'
  };
  return typeNames[activeType.value];
});

const handleTypeChange = () => {
  // MarketBrowsePanel will handle the type change automatically
};

const handleClose = () => {
  visible.value = false;
};

const handleClosed = () => {
  emit('closed');
};

// Watch for external changes
watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal) {
    activeType.value = props.initialType;
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});
</script>

<style scoped>
.market-dialog-content {
  min-height: 60vh;
}

.market-layout {
  display: flex;
  gap: 20px;
  min-height: 60vh;
}

/* Left Sidebar */
.market-sidebar {
  width: 180px;
  flex-shrink: 0;
  border-right: 1px solid var(--el-border-color-light);
  padding-right: 20px;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  padding-left: 4px;
}

.market-sidebar :deep(.el-radio-group) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.market-sidebar :deep(.el-radio-button) {
  width: 100%;
  display: flex;
  margin-right: 0;
}

.market-sidebar :deep(.el-radio-button__inner) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  width: 100%;
  justify-content: flex-start;
  border-radius: 6px;
}

.market-sidebar :deep(.el-radio-button__inner .el-icon) {
  font-size: 18px;
}

/* Right Content */
.market-content {
  flex: 1;
  overflow: auto;
}

/* 确保弹窗有最小宽度 */
:deep(.el-dialog) {
  min-width: 900px;
  max-width: 1400px;
}

@media (max-width: 768px) {
  .market-layout {
    flex-direction: column;
  }

  .market-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--el-border-color-light);
    padding-right: 0;
    padding-bottom: 16px;
  }

  .market-sidebar :deep(.el-radio-group) {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .market-sidebar :deep(.el-radio-button) {
    width: auto;
    flex: 1;
  }

  :deep(.el-dialog) {
    min-width: 95vw;
    width: 95vw !important;
  }
}
</style>
