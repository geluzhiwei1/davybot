/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-drawer v-model="visible" :title="t('knowledge.title')" direction="rtl" :size="'80%'" class="knowledge-drawer"
    @close="handleClose">
    <template #header>
      <div class="drawer-header">
        <el-icon :size="20">
          <Grid />
        </el-icon>
        <span class="drawer-title">{{ t('knowledge.title') }}</span>
      </div>
    </template>

    <div class="drawer-content">
      <!-- Show warning if no workspace ID -->
      <el-empty v-if="!props.workspaceId" description="未选择工作区" />

      <!-- Knowledge Settings Component -->
      <KnowledgeSettings v-else :workspace-id="props.workspaceId" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { Grid } from '@element-plus/icons-vue';
import KnowledgeSettings from '@/components/knowledge/KnowledgeSettings.vue';

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
</script>

<style scoped>
.knowledge-drawer :deep(.el-drawer__header) {
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

.knowledge-drawer :deep(.el-drawer__body) {
  padding: 0;
  overflow: hidden;
}

.drawer-content {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
}
</style>
