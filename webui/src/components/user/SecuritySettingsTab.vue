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

      <!-- 路径安全配置 -->
      <el-collapse-item
        name="path-security"
        :title="t('workspace.settings.security.pathSecurity.title')"
      >
        <PathSecuritySection
          v-model="localSettings"
          is-user-level
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

      <!-- 沙箱配置 -->
      <el-collapse-item
        name="sandbox-config"
        :title="t('workspace.settings.security.sandbox.title')"
      >
        <SandboxConfigSection
          v-model="localSettings"
          is-user-level
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
          is-user-level
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
          is-user-level
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
          is-user-level
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
          is-user-level
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
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { usersSecurityApi } from '@/services/api/security';
import OverrideControlsSection from './security/OverrideControlsSection.vue';
import PathSecuritySection from '@/components/workspace/security/PathSecuritySection.vue';
import CommandSecuritySection from '@/components/workspace/security/CommandSecuritySection.vue';
import SandboxConfigSection from '@/components/workspace/security/SandboxConfigSection.vue';
import ResourceLimitsSection from '@/components/workspace/security/ResourceLimitsSection.vue';
import ModePermissionsSection from '@/components/workspace/security/ModePermissionsSection.vue';
import ToolPermissionsSection from '@/components/workspace/security/ToolPermissionsSection.vue';
import NetworkSecuritySection from '@/components/workspace/security/NetworkSecuritySection.vue';
import AdvancedSecuritySection from '@/components/workspace/security/AdvancedSecuritySection.vue';
import type { UserSecuritySettings } from '@/services/api/types';

const props = defineProps<{
  modelValue: UserSecuritySettings;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: UserSecuritySettings];
}>();

const { t } = useI18n();
const localSettings = ref<UserSecuritySettings>({ ...props.modelValue });
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

const handleSave = async () => {
  saving.value = true;
  try {
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
      localSettings.value = response.settings as UserSecuritySettings;
      emit('update:modelValue', response.settings as UserSecuritySettings);
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
