/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-drawer v-model="visible" :title="t('sidePanel.memory')" direction="rtl" :size="'80%'" class="memory-drawer"
    @close="handleClose">
    <template #header>
      <div class="drawer-header">
        <el-icon :size="20">
          <Connection />
        </el-icon>
        <span class="drawer-title">{{ t('sidePanel.memory') }}</span>
      </div>
    </template>

    <div class="drawer-content">
      <!-- Show warning if no workspace ID -->
      <el-empty v-if="!props.workspaceId" description="未选择工作区" />

      <!-- Memory Browser Component -->
      <MemoryBrowser v-else :workspace-id="props.workspaceId" @select-memory="handleSelectMemory" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { Connection } from '@element-plus/icons-vue';
import MemoryBrowser from './MemoryBrowser.vue';

interface Props {
  modelValue: boolean;
  workspaceId?: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val)
});

const handleClose = () => {
  visible.value = false;
};

const handleSelectMemory = (_memoryId: string) => {
  // Future: Could open memory details or use memory in chat
};
</script>

<style scoped>
.memory-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drawer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.memory-drawer :deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.drawer-content {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
}
</style>
