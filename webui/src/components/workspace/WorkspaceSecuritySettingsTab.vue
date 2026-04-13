<template>
  <div class="workspace-security-settings-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
    >
      <template #title>
        {{ t('workspace.settings.security.title') }}
      </template>
      <p>{{ t('workspace.settings.security.description') }}</p>
    </el-alert>

    <el-collapse v-model="activeSections" class="security-sections">
      <!-- 命令执行安全配置 -->
      <el-collapse-item
        name="command-security"
        :title="t('workspace.settings.security.commandSecurity.title')"
      >
        <CommandSecuritySection
          v-model="localSettings"
          :is-user-level="false"
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
          :is-user-level="false"
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
import { ref, watch } from 'vue';
import type { InstanceType } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { WorkspaceSecurityApiService } from '@/services/api/security';
import CommandSecuritySection from '@/components/workspace/security/CommandSecuritySection.vue';
import SandboxConfigSection from '@/components/workspace/security/SandboxConfigSection.vue';
import type { WorkspaceSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();
const defaultWorkspaceSecurity: WorkspaceSecuritySettings = {
  enableCommandWhitelist: true,
  useSystemCommandWhitelist: true,
  customAllowedCommands: [],
  customDeniedCommands: [],
  allowShellCommands: false,
  allowBackgroundCommands: false,
  allowPipeCommands: false,
  commandExecutionTimeout: 30,
  enableSandbox: false,
  containerRuntime: 'auto',
  dropAllCapabilities: true,
  noNewPrivileges: true,
  sandboxDisableNetwork: true,
};

const localSettings = ref<WorkspaceSecuritySettings>({ ...defaultWorkspaceSecurity });
const saving = ref(false);
const activeSections = ref(['command-security']);

const handleUpdate = (value: WorkspaceSecuritySettings) => {
  localSettings.value = value;
};

const sandboxConfigRef = ref<InstanceType<typeof SandboxConfigSection>>();

const handleSave = async () => {
  if (!props.workspaceId) {
    ElMessage.error('Workspace ID is required');
    return;
  }

  saving.value = true;
  try {
    // 保存前校验沙箱运行时
    if (sandboxConfigRef.value) {
      const valid = await sandboxConfigRef.value.validateBeforeSave();
      if (!valid) return;
    }
    const api = new WorkspaceSecurityApiService(props.workspaceId);
    const response = await api.updateWorkspaceSecuritySettings(
      localSettings.value
    );
    if (response.success) {
      ElMessage.success(t('workspace.settings.security.saveSuccess'));
    }
  } catch (error) {
    ElMessage.error(t('workspace.settings.security.saveError'));
    console.error('Failed to save workspace security settings:', error);
  } finally {
    saving.value = false;
  }
};

const handleReset = async () => {
  if (!props.workspaceId) {
    ElMessage.error('Workspace ID is required');
    return;
  }

  try {
    const api = new WorkspaceSecurityApiService(props.workspaceId);
    const response = await api.resetWorkspaceSecuritySettings();
    if (response.success) {
      ElMessage.success(t('workspace.settings.security.resetSuccess'));
      if (response.settings) {
        localSettings.value = response.settings as WorkspaceSecuritySettings;
      }
    }
  } catch (error) {
    ElMessage.error(t('workspace.settings.security.resetError'));
    console.error('Failed to reset workspace security settings:', error);
  }
};

const loadSettings = async () => {
  if (!props.workspaceId) {
    return;
  }

  try {
    const api = new WorkspaceSecurityApiService(props.workspaceId);
    const response = await api.getWorkspaceSecuritySettings();
    if (response.success && response.settings) {
      localSettings.value = { ...defaultWorkspaceSecurity, ...response.settings } as WorkspaceSecuritySettings;
    }
  } catch (error) {
    console.error('Failed to load workspace security settings:', error);
  }
};

// Watch workspaceId changes
watch(
  () => props.workspaceId,
  () => {
    if (props.workspaceId) {
      loadSettings();
    }
  },
  { immediate: true }
);
</script>

<style scoped lang="scss">
.workspace-security-settings-tab {
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
