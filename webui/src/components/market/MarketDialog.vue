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
      <MarketBrowsePanel v-if="visible" :workspace-id="workspaceId" :initial-type="activeType" @installed="handleInstalled" />
    </div>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
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
  (e: 'installed', type: ResourceType): void;
}>();

const visible = ref(props.modelValue);
const activeType = ref<ResourceType>(props.initialType);

const title = computed(() => {
  const typeNames = {
    skill: 'Skills 集市',
    agent: 'Agents 集市',
    plugin: 'Plugins 集市'
  };
  return typeNames[activeType.value];
});

const handleClose = () => {
  visible.value = false;
};

const handleClosed = () => {
  emit('closed');
};

const handleInstalled = (type: ResourceType) => {
  emit('installed', type);
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

/* 确保弹窗有最小宽度 */
:deep(.el-dialog) {
  min-width: 900px;
  max-width: 1400px;
}

@media (max-width: 768px) {
  :deep(.el-dialog) {
    min-width: 95vw;
    width: 95vw !important;
  }
}
</style>
