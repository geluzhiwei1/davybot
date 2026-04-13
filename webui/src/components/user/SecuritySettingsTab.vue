<template>
  <div class="user-security-settings-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
    >
      <template #title>
        {{ t('userSettings.security.title') }}
      </template>
      <p>{{ t('userSettings.security.description') }}</p>
    </el-alert>

    <el-collapse v-model="activeSections" class="security-sections">
      <!-- 覆盖控制配置 -->
      <el-collapse-item
        name="override-controls"
        :title="t('userSettings.security.overrideControls.title')"
      >
        <OverrideControlsSection
          v-model="localSettings"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 命令执行安全配置 -->
      <el-collapse-item
        name="command-security"
        :title="t('workspace.settings.security.commandSecurity.title')"
      >
        <CommandSecuritySection
          v-model="localSettings"
          is-user-level
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 容器沙箱配置 -->
      <el-collapse-item
        name="sandbox-config"
        :title="t('workspace.settings.security.sandbox.title')"
      >
        <SandboxConfigSection
          ref="sandboxConfigRef"
          v-model="localSettings"
          is-user-level
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>
    </el-collapse>

    <div class="security-actions">
      <el-button @click="handleReset">
        {{ t('common.reset') }}
      </el-button>
      <el-button
        type="primary"
        :loading="saving"
        @click="handleSave"
      >
        {{ t('common.save') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import type { InstanceType } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { usersSecurityApi } from '@/services/api/security';
import OverrideControlsSection from './security/OverrideControlsSection.vue';
import CommandSecuritySection from '@/components/workspace/security/CommandSecuritySection.vue';
import SandboxConfigSection from '@/components/workspace/security/SandboxConfigSection.vue';
import type { UserSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  modelValue: UserSecuritySettings;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: UserSecuritySettings];
}>();

const { t } = useI18n();

const defaultUserSecurity: UserSecuritySettings = {
  enableCommandWhitelist: true,
  useSystemCommandWhitelist: true,
  baseAllowedCommands: [],
  baseDeniedCommands: [],
  allowShellCommands: false,
  allowBackgroundCommands: false,
  allowPipeCommands: false,
  commandExecutionTimeout: 30,
  enableSandbox: false,
  containerRuntime: 'auto',
  dropAllCapabilities: true,
  noNewPrivileges: true,
  sandboxDisableNetwork: true,
  allowWorkspaceOverrideCommandSecurity: true,
  allowWorkspaceOverrideSandbox: true,
};

const localSettings = ref<UserSecuritySettings>({ ...defaultUserSecurity, ...props.modelValue });
const saving = ref(false);
const activeSections = ref(['override-controls']);

watch(
  () => props.modelValue,
  (newValue) => {
    localSettings.value = { ...newValue };
  },
  { deep: true }
);

const handleUpdate = (value: UserSecuritySettings) => {
  localSettings.value = value;
  emit('update:modelValue', value);
};

const sandboxConfigRef = ref<InstanceType<typeof SandboxConfigSection>>();

const handleSave = async () => {
  saving.value = true;
  try {
    // 保存前校验沙箱运行时
    if (sandboxConfigRef.value) {
      const valid = await sandboxConfigRef.value.validateBeforeSave();
      if (!valid) return;
    }
    const response = await usersSecurityApi.updateUserSecuritySettings(
      localSettings.value
    );
    if (response.success) {
      ElMessage.success(t('userSettings.security.saveSuccess'));
      emit('update:modelValue', response.settings as UserSecuritySettings);
    }
  } catch (error) {
    ElMessage.error(t('userSettings.security.saveError'));
    console.error('Failed to save user security settings:', error);
  } finally {
    saving.value = false;
  }
};

const handleReset = async () => {
  try {
    const response = await usersSecurityApi.resetUserSecuritySettings();
    if (response.success) {
      ElMessage.success(t('userSettings.security.resetSuccess'));
      emit('update:modelValue', response.settings as UserSecuritySettings);
    }
  } catch (error) {
    ElMessage.error(t('userSettings.security.resetError'));
    console.error('Failed to reset user security settings:', error);
  }
};

// 加载用户安全配置
const loadSettings = async () => {
  try {
    const response = await usersSecurityApi.getUserSecuritySettings();
    if (response.success && response.settings) {
      const settings = { ...defaultUserSecurity, ...response.settings } as UserSecuritySettings;
      localSettings.value = settings;
      emit('update:modelValue', settings);
    }
  } catch (error) {
    console.error('Failed to load user security settings:', error);
  }
};

onMounted(() => {
  loadSettings();
});
</script>

<style scoped lang="scss">
.user-security-settings-tab {
  padding: 20px;

  .security-sections {
    margin-bottom: 20px;
  }

  .security-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding-top: 20px;
    border-top: 1px solid var(--el-border-color);
  }
}
</style>
