<template>
  <div class="override-controls-section">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 15px"
    >
      <template #title>
        {{ t('userSettings.security.overrideControls.warningTitle') }}
      </template>
      <p>{{ t('userSettings.security.overrideControls.warningMessage') }}</p>
    </el-alert>

    <el-form :model="localValue" label-width="280px" label-position="left">
      <!-- 命令执行覆盖控制 -->
      <el-form-item :label="t('userSettings.security.overrideControls.allowOverrideCommand')">
        <el-switch
          v-model="localValue.allowWorkspaceOverrideCommandSecurity"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('userSettings.security.overrideControls.allowOverrideCommandHelp') }}
        </span>
      </el-form-item>

      <!-- 沙箱覆盖控制 -->
      <el-form-item :label="t('userSettings.security.overrideControls.allowOverrideSandbox')">
        <div class="sandbox-controls">
          <el-switch
            v-model="localValue.allowWorkspaceOverrideSandbox"
            @change="handleUpdate"
          />
          <el-switch
            v-model="localValue.enforceSandbox"
            @change="handleUpdate"
            style="margin-left: 10px"
          />
          <span class="form-item-help" style="margin-left: 10px">
            {{ t('userSettings.security.overrideControls.enforceSandbox') }}
          </span>
        </div>
        <span class="form-item-help">
          {{ t('userSettings.security.overrideControls.allowOverrideSandboxHelp') }}
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { UserSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  modelValue: UserSecuritySettings;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: UserSecuritySettings];
}>();

const { t } = useI18n();
const localValue = ref<UserSecuritySettings>({ ...props.modelValue });

watch(
  () => props.modelValue,
  (newValue) => {
    localValue.value = { ...newValue };
  },
  { deep: true }
);

const handleUpdate = () => {
  emit('update:modelValue', localValue.value);
};
</script>

<style scoped lang="scss">
.override-controls-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .sandbox-controls {
    display: flex;
    align-items: center;
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }
}
</style>
