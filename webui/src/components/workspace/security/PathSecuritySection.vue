<template>
  <div class="path-security-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 启用路径遍历保护 -->
      <el-form-item :label="t('workspace.settings.security.pathSecurity.enableProtection')">
        <el-switch
          v-model="localValue.enablePathTraversalProtection"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.pathSecurity.enableProtectionHelp') }}
        </span>
      </el-form-item>

      <!-- 允许绝对路径 -->
      <el-form-item :label="t('workspace.settings.security.pathSecurity.allowAbsolutePaths')">
        <el-switch
          v-model="localValue.allowAbsolutePaths"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.pathSecurity.allowAbsolutePathsHelp') }}
        </span>
      </el-form-item>

      <!-- 允许的文件扩展名 -->
      <el-form-item :label="t('workspace.settings.security.pathSecurity.allowedExtensions')">
        <el-select
          v-model="localValue.allowedFileExtensions"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.pathSecurity.allowedExtensionsPlaceholder')"
          @change="handleUpdate"
        >
          <el-option
            v-for="ext in commonExtensions"
            :key="ext"
            :label="ext"
            :value="ext"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.pathSecurity.allowedExtensionsHelp') }}
        </span>
      </el-form-item>

      <!-- 拒绝的文件扩展名 -->
      <el-form-item :label="t('workspace.settings.security.pathSecurity.deniedExtensions')">
        <el-select
          v-model="localValue.deniedFileExtensions"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.pathSecurity.deniedExtensionsPlaceholder')"
          @change="handleUpdate"
        >
          <el-option
            v-for="ext in dangerousExtensions"
            :key="ext"
            :label="ext"
            :value="ext"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.pathSecurity.deniedExtensionsHelp') }}
        </span>
      </el-form-item>

      <!-- 最大文件大小 -->
      <el-form-item :label="t('workspace.settings.security.pathSecurity.maxFileSize')">
        <el-input-number
          v-model="localValue.maxFileSizeMb"
          :min="1"
          :max="1000"
          @change="handleUpdate"
        />
        <span class="unit">MB</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.pathSecurity.maxFileSizeHelp') }}
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
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

const commonExtensions = [
  '.py', '.txt', '.md', '.json', '.yaml', '.yml', '.toml',
  '.html', '.css', '.js', '.ts', '.vue', '.jsx', '.tsx',
  '.xml', '.csv', '.sql', '.sh', '.bat'
];

const dangerousExtensions = [
  '.exe', '.dll', '.so', '.dylib', '.app', '.deb', '.rpm',
  '.scr', '.vbs', '.js', '.jar', '.com', '.pif'
];

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
.path-security-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
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
