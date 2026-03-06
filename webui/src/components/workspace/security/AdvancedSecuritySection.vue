<template>
  <div class="advanced-security-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 启用审计日志 -->
      <el-form-item :label="t('workspace.settings.security.advanced.enableAuditLog')">
        <el-switch
          v-model="localValue.enableAuditLogging"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.enableAuditLogHelp') }}
        </span>
      </el-form-item>

      <!-- 审计日志级别 -->
      <el-form-item :label="t('workspace.settings.security.advanced.auditLogLevel')">
        <el-radio-group
          v-model="localValue.auditLogLevel"
          @change="handleUpdate"
          :disabled="!localValue.enableAuditLogging"
        >
          <el-radio value="basic">{{ t('workspace.settings.security.advanced.logLevelBasic') }}</el-radio>
          <el-radio value="detailed">{{ t('workspace.settings.security.advanced.logLevelDetailed') }}</el-radio>
          <el-radio value="verbose">{{ t('workspace.settings.security.advanced.logLevelVerbose') }}</el-radio>
        </el-radio-group>
        <div class="form-item-help">
          <p><strong>{{ t('workspace.settings.security.advanced.logLevelBasic') }}：</strong>记录关键操作</p>
          <p><strong>{{ t('workspace.settings.security.advanced.logLevelDetailed') }}：</strong>记录所有操作及参数</p>
          <p><strong>{{ t('workspace.settings.security.advanced.logLevelVerbose') }}：</strong>记录完整上下文</p>
        </div>
      </el-form-item>

      <!-- 危险操作需要确认 -->
      <el-form-item :label="t('workspace.settings.security.advanced.requireConfirmation')">
        <el-switch
          v-model="localValue.requireConfirmationForDangerousOperations"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.requireConfirmationHelp') }}
        </span>
      </el-form-item>

      <!-- 危险操作列表 -->
      <el-form-item :label="t('workspace.settings.security.advanced.dangerousOperations')">
        <el-checkbox-group
          v-model="dangerousOperations"
          @change="handleOperationsUpdate"
          :disabled="!localValue.requireConfirmationForDangerousOperations"
        >
          <el-checkbox value="delete">{{ t('workspace.settings.security.advanced.opDelete') }}</el-checkbox>
          <el-checkbox value="execute">{{ t('workspace.settings.security.advanced.opExecute') }}</el-checkbox>
          <el-checkbox value="network">{{ t('workspace.settings.security.advanced.opNetwork') }}</el-checkbox>
          <el-checkbox value="sandbox">{{ t('workspace.settings.security.advanced.opSandbox') }}</el-checkbox>
          <el-checkbox value="mode">{{ t('workspace.settings.security.advanced.opMode') }}</el-checkbox>
        </el-checkbox-group>
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.dangerousOperationsHelp') }}
        </span>
      </el-form-item>

      <!-- 阻止可执行文件 -->
      <el-form-item :label="t('workspace.settings.security.advanced.blockExecutables')">
        <el-switch
          v-model="localValue.blockExecutableFiles"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.blockExecutablesHelp') }}
        </span>
      </el-form-item>

      <!-- 可执行文件扩展名 -->
      <el-form-item :label="t('workspace.settings.security.advanced.executableExtensions')">
        <el-select
          v-model="executableExtensions"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.advanced.extensionsPlaceholder')"
          @change="handleExtensionsUpdate"
          :disabled="!localValue.blockExecutableFiles"
        >
          <el-option
            v-for="ext in commonExecutableExtensions"
            :key="ext"
            :label="ext"
            :value="ext"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.executableExtensionsHelp') }}
        </span>
      </el-form-item>

      <!-- 符号链接策略 -->
      <el-form-item :label="t('workspace.settings.security.advanced.symlinkPolicy')">
        <el-radio-group
          v-model="localValue.symlinkPolicy"
          @change="handleUpdate"
        >
          <el-radio value="allow">{{ t('workspace.settings.security.advanced.symlinkAllow') }}</el-radio>
          <el-radio value="follow">{{ t('workspace.settings.security.advanced.symlinkFollow') }}</el-radio>
          <el-radio value="block">{{ t('workspace.settings.security.advanced.symlinkBlock') }}</el-radio>
        </el-radio-group>
        <div class="form-item-help">
          <p><strong>{{ t('workspace.settings.security.advanced.symlinkAllow') }}：</strong>允许创建和跟随符号链接</p>
          <p><strong>{{ t('workspace.settings.security.advanced.symlinkFollow') }}：</strong>只允许跟随，不允许创建</p>
          <p><strong>{{ t('workspace.settings.security.advanced.symlinkBlock') }}：</strong>完全禁止符号链接</p>
        </div>
      </el-form-item>

      <!-- 用户级：强制安全策略 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.advanced.enforcePolicy')"
      >
        <el-switch
          v-model="localValue.enforceSecurityPolicy"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.advanced.enforcePolicyHelp') }}
        </span>
      </el-form-item>

      <!-- 启用安全告警 -->
      <el-form-item :label="t('workspace.settings.security.advanced.enableAlerts')">
        <el-switch
          v-model="localValue.enableSecurityAlerts"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.advanced.enableAlertsHelp') }}
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

// 常见可执行文件扩展名
const commonExecutableExtensions = [
  '.exe',
  '.dll',
  '.so',
  '.dylib',
  '.app',
  '.bat',
  '.sh',
  '.command',
  '.msi',
  '.deb',
  '.rpm'
];

// 危险操作
const dangerousOperations = computed({
  get: () => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    return 'dangerousOperationsRequireConfirmation' in settings
      ? (settings as UserSecuritySettings).dangerousOperationsRequireConfirmation
      : (settings as WorkspaceSecuritySettings).dangerousOperationsRequireConfirmation || [];
  },
  set: (val: string[]) => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    if ('dangerousOperationsRequireConfirmation' in settings) {
      (settings as UserSecuritySettings).dangerousOperationsRequireConfirmation = val;
    } else {
      (settings as WorkspaceSecuritySettings).dangerousOperationsRequireConfirmation = val;
    }
  }
});

// 可执行文件扩展名
const executableExtensions = computed({
  get: () => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    return 'executableFileExtensions' in settings
      ? (settings as UserSecuritySettings).executableFileExtensions
      : (settings as WorkspaceSecuritySettings).executableFileExtensions || [];
  },
  set: (val: string[]) => {
    const settings = localValue.value as UserSecuritySettings | WorkspaceSecuritySettings;
    if ('executableFileExtensions' in settings) {
      (settings as UserSecuritySettings).executableFileExtensions = val;
    } else {
      (settings as WorkspaceSecuritySettings).executableFileExtensions = val;
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

const handleOperationsUpdate = () => {
  handleUpdate();
};

const handleExtensionsUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.advanced-security-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;

    &.warning {
      color: var(--el-color-warning);
      font-weight: 500;
    }

    p {
      margin: 2px 0;
    }

    strong {
      color: var(--el-text-color-regular);
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
