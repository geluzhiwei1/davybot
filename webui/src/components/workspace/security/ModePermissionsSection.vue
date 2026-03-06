<template>
  <div class="mode-permissions-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- Plan 模式写操作限制 -->
      <el-form-item :label="t('workspace.settings.security.modePermissions.restrictPlanWrite')">
        <el-switch
          v-model="localValue.restrictPlanModeWriteOperations"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.modePermissions.restrictPlanWriteHelp') }}
        </span>
      </el-form-item>

      <!-- Plan 模式允许的工具 -->
      <el-form-item :label="t('workspace.settings.security.modePermissions.planModeTools')">
        <el-select
          v-model="planModeTools"
          multiple
          :placeholder="t('workspace.settings.security.modePermissions.planModeToolsPlaceholder')"
          @change="handleToolsUpdate"
        >
          <el-option
            v-for="tool in readOnlyTools"
            :key="tool"
            :label="tool"
            :value="tool"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.modePermissions.planModeToolsHelp') }}
        </span>
      </el-form-item>

      <!-- 禁用的模式 -->
      <el-form-item :label="t('workspace.settings.security.modePermissions.disabledModes')">
        <el-checkbox-group
          v-model="disabledModes"
          @change="handleModesUpdate"
        >
          <el-checkbox value="orchestrator">🪃 {{ t('mode.orchestrator') }}</el-checkbox>
          <el-checkbox value="plan">📋 {{ t('mode.plan') }}</el-checkbox>
          <el-checkbox value="do">⚙️ {{ t('mode.do') }}</el-checkbox>
          <el-checkbox value="check">✓ {{ t('mode.check') }}</el-checkbox>
          <el-checkbox value="act">🚀 {{ t('mode.act') }}</el-checkbox>
        </el-checkbox-group>
        <div class="form-item-help">
          <p>⚠️ {{ t('workspace.settings.security.modePermissions.disabledModesHelp') }}</p>
        </div>
      </el-form-item>

      <!-- 模式切换确认 -->
      <el-form-item :label="t('workspace.settings.security.modePermissions.confirmModeSwitch')">
        <el-switch
          v-model="localValue.requireConfirmationForModeSwitch"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.modePermissions.confirmModeSwitchHelp') }}
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { UserSecuritySettings, WorkspaceSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  modelValue: UserSecuritySettings | WorkspaceSecuritySettings;
  isUserLevel?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: UserSecuritySettings | WorkspaceSecuritySettings];
}>();

const { t } = useI18n();
const localValue = ref<UserSecuritySettings | WorkspaceSecuritySettings>({ ...props.modelValue });

// 只读工具列表（Plan 模式可用）
const readOnlyTools = [
  'read_file',
  'list_files',
  'search_files',
  'directory_tree',
  'ask_followup_question',
  'switch_mode',
  'browser_search',
  'browser_open',
  'run_slash_command'
];

// Plan 模式工具
const planModeTools = computed({
  get: () => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    return 'planModeAllowedTools' in settings
      ? (settings as UserSecuritySettings).planModeAllowedTools
      : (settings as WorkspaceSecuritySettings).planModeAllowedTools || [];
  },
  set: (val: string[]) => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    if ('planModeAllowedTools' in settings) {
      (settings as UserSecuritySettings).planModeAllowedTools = val;
    } else {
      (settings as WorkspaceSecuritySettings).planModeAllowedTools = val;
    }
  }
});

// 禁用的模式
const disabledModes = computed({
  get: () => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    return 'disabledModes' in settings
      ? (settings as UserSecuritySettings).disabledModes
      : (settings as WorkspaceSecuritySettings).disabledModes || [];
  },
  set: (val: string[]) => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    if ('disabledModes' in settings) {
      (settings as UserSecuritySettings).disabledModes = val;
    } else {
      (settings as WorkspaceSecuritySettings).disabledModes = val;
    }
  }
});

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

const handleToolsUpdate = () => {
  handleUpdate();
};

const handleModesUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.mode-permissions-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;

    p {
      margin: 2px 0;
    }
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }

  :deep(.el-checkbox-group) {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
