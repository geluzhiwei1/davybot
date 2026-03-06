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
      <!-- 路径安全配置 -->
      <el-collapse-item
        name="path-security"
        :title="t('workspace.settings.security.pathSecurity.title')"
      >
        <PathSecuritySection
          v-model="localSettings"
          :is-user-level="false"
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
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 沙箱配置 -->
      <el-collapse-item
        name="sandbox-config"
        :title="t('workspace.settings.security.sandbox.title')"
      >
        <SandboxConfigSection
          v-model="localSettings"
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 模式权限配置 -->
      <el-collapse-item
        name="mode-permissions"
        :title="t('workspace.settings.security.modePermissions.title')"
      >
        <ModePermissionsSection
          v-model="localSettings"
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 工具权限配置 -->
      <el-collapse-item
        name="tool-permissions"
        :title="t('workspace.settings.security.toolPermissions.title')"
      >
        <ToolPermissionsSection
          v-model="localSettings"
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 网络安全配置 -->
      <el-collapse-item
        name="network-security"
        :title="t('workspace.settings.security.network.title')"
      >
        <NetworkSecuritySection
          v-model="localSettings"
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 资源限制配置 -->
      <el-collapse-item
        name="resource-limits"
        :title="t('workspace.settings.security.resource.title')"
      >
        <ResourceLimitsSection
          v-model="localSettings"
          :is-user-level="false"
          @update:model-value="handleUpdate"
        />
      </el-collapse-item>

      <!-- 高级安全选项 -->
      <el-collapse-item
        name="advanced-security"
        :title="t('workspace.settings.security.advanced.title')"
      >
        <AdvancedSecuritySection
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
import { ref, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { WorkspaceSecurityApiService } from '@/services/api/security';
import PathSecuritySection from '@/components/workspace/security/PathSecuritySection.vue';
import CommandSecuritySection from '@/components/workspace/security/CommandSecuritySection.vue';
import SandboxConfigSection from '@/components/workspace/security/SandboxConfigSection.vue';
import ModePermissionsSection from '@/components/workspace/security/ModePermissionsSection.vue';
import ToolPermissionsSection from '@/components/workspace/security/ToolPermissionsSection.vue';
import NetworkSecuritySection from '@/components/workspace/security/NetworkSecuritySection.vue';
import ResourceLimitsSection from '@/components/workspace/security/ResourceLimitsSection.vue';
import AdvancedSecuritySection from '@/components/workspace/security/AdvancedSecuritySection.vue';
import type { WorkspaceSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  workspaceId: string;
}>();

const { t } = useI18n();
const localSettings = ref<WorkspaceSecuritySettings>({
  enablePathTraversalProtection: true,
  allowAbsolutePaths: false,
  allowedFileExtensions: [],
  deniedFileExtensions: [],
  maxFileSizeMb: 100,
  // ... 其他默认值
});
const saving = ref(false);
const activeSections = ref(['path-security']);

const handleUpdate = (value: WorkspaceSecuritySettings) => {
  localSettings.value = value;
};

const handleSave = async () => {
  if (!props.workspaceId) {
    ElMessage.error('Workspace ID is required');
    return;
  }

  saving.value = true;
  try {
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
      localSettings.value = response.settings as WorkspaceSecuritySettings;
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
