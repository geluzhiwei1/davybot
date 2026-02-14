<!--
Copyright (c) 2025 格律至微
SPDX-License-Identifier: AGPL-3.0-only
-->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="800px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    @close="handleClose"
    destroy-on-close
  >
    <!-- Loading state -->
    <div v-if="loadingSchema" class="loading-container">
      <el-skeleton :rows="5" animated />
    </div>

    <!-- Schema error state -->
    <div v-else-if="!configSchema" class="error-container">
      <el-alert type="warning" :closable="false">
        <template #title>
          {{ $t('workspaceSettings.plugins.pluginConfig.schemaNotLoaded') }}
        </template>
        <p>{{ $t('workspaceSettings.plugins.pluginConfig.schemaNotLoadedHint') }}</p>
      </el-alert>
    </div>

    <!-- Empty schema state -->
    <div v-else-if="!configSchema.schema || !configSchema.schema.properties || Object.keys(configSchema.schema.properties).length === 0" class="empty-container">
      <el-alert type="info" :closable="false">
        <template #title>
          {{ $t('workspaceSettings.plugins.pluginConfig.noCustomSettings') }}
        </template>
        <p>{{ $t('workspaceSettings.plugins.pluginConfig.noCustomSettingsHint') }}</p>
      </el-alert>
    </div>

    <!-- Main configuration form -->
    <div v-else class="plugin-config-form">
      <!-- Plugin ID (read-only) -->
      <el-form label-width="200px" class="basic-settings">
        <el-form-item :label="$t('workspaceSettings.plugins.pluginConfig.pluginId')">
          <el-input :model-value="pluginId" disabled />
        </el-form-item>
      </el-form>

      <el-divider>{{ $t('workspaceSettings.plugins.pluginConfig.customSettings') }}</el-divider>

      <!-- JSON Schema Form -->
      <json-schema-form
        v-model="formData.settings"
        :schema="configSchema.schema"
        :ui-schema="configSchema.ui_schema"
        :form-props="formProps"
        :fallback-label="true"
        :form-footer="{ show: false }"
      />

      <!-- Validation errors -->
      <div v-if="validationErrors.length > 0" class="validation-errors">
        <el-alert
          v-for="(error, index) in validationErrors"
          :key="index"
          type="error"
          :closable="false"
          :title="error"
        />
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="saving">
          {{ $t('common.save') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElAlert, ElDivider, ElForm, ElFormItem } from 'element-plus';
import JsonSchemaForm from '@lljj/vue3-form-element';
import { pluginsApi, type PluginConfigSchema } from '@/services/api/plugins';

const { t } = useI18n();

// Props
interface Props {
  visible: boolean;
  workspaceId: string;
  pluginId: string | null;
  pluginConfig?: unknown;
}

const props = defineProps<Props>();

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean];
  save: [pluginId: string, settings: unknown];
}>();

// State
const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value)
});

const dialogTitle = computed(() => {
  return props.pluginId
    ? `${t('workspaceSettings.plugins.pluginConfig.settingsFor')} ${props.pluginId}`
    : t('workspaceSettings.plugins.pluginConfig.pluginSettings');
});

const saving = ref(false);
const loadingSchema = ref(false);
const pluginId = computed(() => props.pluginId || '');
const configSchema = ref<PluginConfigSchema | null>(null);
const validationErrors = ref<string[]>([]);

// Form data - use reactive for reactivity
const formData = reactive({
  settings: {} as Record<string, unknown>
});

// Form props for json-schema-form
const formProps = computed(() => ({
  labelWidth: '200px',
  labelPosition: 'right',
  size: 'default'
}));

// Load plugin config schema
const loadConfigSchema = async () => {
  if (!props.pluginId || !props.workspaceId) {
    return;
  }

  loadingSchema.value = true;
  validationErrors.value = [];
  try {
    const response = await pluginsApi.getConfigSchema(props.workspaceId, props.pluginId);

    // API returns: {success, schema, config, existing_config, form_config, message}
    configSchema.value = response;

    // Initialize form data with defaults and existing config
    if (configSchema.value?.schema?.properties) {
      const defaultSettings: Record<string, unknown> = {};
      const { properties } = configSchema.value.schema;

      // Extract defaults from schema
      for (const [fieldName, fieldSchema] of Object.entries(properties)) {
        if ((fieldSchema as { default?: unknown }).default !== undefined) {
          defaultSettings[fieldName] = (fieldSchema as { default?: unknown }).default;
        }
      }

      // Merge with existing config (existing config takes precedence)
      // existing_config may be full config object or pure config values
      let existingConfigValues: Record<string, unknown> = {};
      if (response.existing_config) {
        const { enabled, activated, version, install_path, ...pureConfig } = response.existing_config as any;
        existingConfigValues = pureConfig || {};
      }

      const finalSettings = {
        ...defaultSettings,
        ...existingConfigValues
      };

      formData.settings = finalSettings;
    }
  } catch (error: unknown) {
    ElMessage.warning(t('workspaceSettings.plugins.pluginConfig.loadSchemaError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    loadingSchema.value = false;
  }
};

// Validate form data against schema
const validateForm = (): boolean => {
  if (!configSchema.value?.schema) {
    return true;
  }

  validationErrors.value = [];
  const { schema } = configSchema.value;

  // Check required fields
  if (schema.required) {
    for (const fieldName of schema.required) {
      const value = formData.settings[fieldName];
      if (value === undefined || value === null || value === '') {
        validationErrors.value.push(
          t('workspaceSettings.plugins.pluginConfig.requiredFieldMissing', { field: fieldName })
        );
      }
    }
  }

  // TODO: Add more validation logic (pattern, min/max, etc.)

  return validationErrors.value.length === 0;
};

// Submit form
const handleSubmit = async () => {
  if (!props.pluginId) return;

  // Validate form
  if (!validateForm()) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.validationError'));
    return;
  }

  saving.value = true;
  try {
    // 🔧 修复：提取纯数据，避免发送 Proxy 对象
    const plainData = JSON.parse(JSON.stringify(formData.settings));
    emit('save', props.pluginId, plainData);
  } catch (error: unknown) {
    ElMessage.error(t('workspaceSettings.plugins.pluginConfig.saveError') + ': ' + (error instanceof Error ? error.message : 'Unknown error'));
  } finally {
    saving.value = false;
  }
};

// Close dialog
const handleClose = () => {
  dialogVisible.value = false;
};

// Watch for dialog open to load schema
watch(() => props.visible, (visible) => {
  if (visible && props.pluginId) {
    loadConfigSchema();
  }
});

// Watch pluginConfig changes
watch(
  () => props.pluginConfig,
  (newConfig) => {
    if (newConfig) {
      // 提取纯配置值（排除 enabled, activated 等元数据）
      const { enabled, activated, version, install_path, ...pureConfig } = newConfig as any;
      // 使用 Object.assign 更新 reactive 对象，而不是替换整个对象
      Object.assign(formData, {
        settings: { ...(pureConfig || {}) }
      });
    }
  },
  { immediate: false, deep: true }
);
</script>

<style scoped lang="scss">
.loading-container,
.error-container,
.empty-container {
  padding: 20px;
  min-height: 200px;
}

.plugin-config-form {
  .basic-settings {
    margin-bottom: 20px;
  }

  :deep(.json-schema-form) {
    .el-form-item {
      margin-bottom: 18px;
    }

    // Ensure labels wrap properly
    .el-form-item__label {
      white-space: normal !important;
      word-break: break-word;
      line-height: 1.5;
      padding-right: 12px;
      color: var(--el-text-color-primary) !important;
      font-weight: 500;
    }

    // Radio group vertical layout
    .el-radio-group {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .el-radio {
        margin-right: 0;
        white-space: normal;
        height: auto;
        line-height: 1.5;

        .el-radio__label {
          white-space: normal;
          line-height: 1.5;
          padding-left: 8px;
        }
      }
    }
  }

  .validation-errors {
    margin-top: 20px;

    .el-alert {
      margin-bottom: 8px;

      &:last-child {
        margin-bottom: 0;
      }
    }
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
