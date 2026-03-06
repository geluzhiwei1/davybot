<template>
  <div class="command-security-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 启用命令白名单 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.enableWhitelist')">
        <el-switch
          v-model="localValue.enableCommandWhitelist"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.commandSecurity.enableWhitelistHelp') }}
        </span>
      </el-form-item>

      <!-- 使用系统默认白名单 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.useSystemWhitelist')">
        <el-switch
          v-model="localValue.useSystemCommandWhitelist"
          @change="handleUpdate"
          :disabled="!localValue.enableCommandWhitelist"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.commandSecurity.useSystemWhitelistHelp') }}
        </span>
      </el-form-item>

      <!-- 自定义允许的命令（用户级）或自定义允许的命令（工作区级） -->
      <el-form-item :label="isUserLevel ? t('workspace.settings.security.commandSecurity.baseAllowedCommands') : t('workspace.settings.security.commandSecurity.customAllowedCommands')">
        <el-select
          v-model="commandsAllowed"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.commandSecurity.commandsPlaceholder')"
          @change="handleCommandsUpdate"
        >
          <el-option
            v-for="cmd in commonSafeCommands"
            :key="cmd"
            :label="cmd"
            :value="cmd"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.commandSecurity.allowedCommandsHelp') }}
        </span>
      </el-form-item>

      <!-- 自定义拒绝的命令 -->
      <el-form-item :label="isUserLevel ? t('workspace.settings.security.commandSecurity.baseDeniedCommands') : t('workspace.settings.security.commandSecurity.customDeniedCommands')">
        <el-select
          v-model="commandsDenied"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.commandSecurity.commandsPlaceholder')"
          @change="handleCommandsUpdate"
        >
          <el-option
            v-for="cmd in dangerousCommands"
            :key="cmd"
            :label="cmd"
            :value="cmd"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.commandSecurity.deniedCommandsHelp') }}
        </span>
      </el-form-item>

      <!-- 允许 Shell 命令 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.allowShellCommands')">
        <el-switch
          v-model="localValue.allowShellCommands"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.commandSecurity.allowShellCommandsHelp') }}
        </span>
      </el-form-item>

      <!-- 允许后台执行 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.allowBackgroundCommands')">
        <el-switch
          v-model="localValue.allowBackgroundCommands"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.commandSecurity.allowBackgroundCommandsHelp') }}
        </span>
      </el-form-item>

      <!-- 允许管道命令 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.allowPipeCommands')">
        <el-switch
          v-model="localValue.allowPipeCommands"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.commandSecurity.allowPipeCommandsHelp') }}
        </span>
      </el-form-item>

      <!-- 命令执行超时 -->
      <el-form-item :label="t('workspace.settings.security.commandSecurity.commandTimeout')">
        <el-input-number
          v-model="localValue.commandExecutionTimeout"
          :min="1"
          :max="300"
          @change="handleUpdate"
        />
        <span class="unit">秒</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.commandSecurity.commandTimeoutHelp') }}
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

// 常见安全命令
const commonSafeCommands = [
  'ls', 'pwd', 'cat', 'head', 'tail', 'grep', 'find', 'wc',
  'sort', 'uniq', 'diff', 'date', 'echo', 'git', 'python', 'node'
];

// 危险命令
const dangerousCommands = [
  'rm -rf', 'dd', 'mkfs', 'fdisk', 'sudo', 'su', 'chmod 777',
  'reboot', 'shutdown', 'killall'
];

// 根据用户级或工作区级选择不同的字段
const commandsAllowed = computed({
  get: () => props.isUserLevel
    ? (localValue.value as UserSecuritySettings).baseAllowedCommands
    : (localValue.value as WorkspaceSecuritySettings).customAllowedCommands,
  set: (val: string[]) => {
    if (props.isUserLevel) {
      (localValue.value as UserSecuritySettings).baseAllowedCommands = val;
    } else {
      (localValue.value as WorkspaceSecuritySettings).customAllowedCommands = val;
    }
  }
});

const commandsDenied = computed({
  get: () => props.isUserLevel
    ? (localValue.value as UserSecuritySettings).baseDeniedCommands
    : (localValue.value as WorkspaceSecuritySettings).customDeniedCommands,
  set: (val: string[]) => {
    if (props.isUserLevel) {
      (localValue.value as UserSecuritySettings).baseDeniedCommands = val;
    } else {
      (localValue.value as WorkspaceSecuritySettings).customDeniedCommands = val;
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

const handleCommandsUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.command-security-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;

    &.warning {
      color: var(--el-color-warning);
      font-weight: 500;
    }
  }

  .unit {
    margin-left: 5px;
    color: var(--el-text-color-regular);
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }
}
</style>
