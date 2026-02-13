<!--
  动态插件配置组件 - 基于 JSON Schema 自动生成表单

  功能：
  - 根据 JSON Schema 动态生成配置表单
  - 支持多种字段类型（text, number, boolean, select, textarea等）
  - 自动验证输入
  - 提交和重置功能
-->
<template>
  <div class="dynamic-plugin-config">
    <!-- 配置加载状态 -->
    <el-skeleton v-if="loading" :rows="5" animated />

    <!-- 配置错误提示 -->
    <el-alert
      v-if="error"
      type="error"
      :title="$t('common.error')"
      :description="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <el-icon><Warning /></el-icon>
        {{ error }}
      </template>
    </el-alert>

    <!-- 成功提示 -->
    <el-alert
      v-if="success"
      type="success"
      :title="$t('common.success')"
      :description="success"
      :closable="true"
      show-icon
    >
      <template #default>
        <el-icon><Success /></el-icon>
        {{ success }}
      </template>
    </el-alert>

    <!-- 配置表单 -->
    <el-form
      v-if="formConfig && !loading"
      :model="formData"
      :rules="formRules"
      label-width="180px"
      label-position="top"
      @submit.prevent="handleSubmit"
    >
      <!-- 表单标题 -->
      <template #header>
        <div class="form-header">
          <h3>{{ formConfig.title || 'Plugin Configuration' }}</h3>
          <p v-if="formConfig.description" class="form-description">
            {{ formConfig.description }}
          </p>
        </div>
      </template>

      <!-- 动态生成表单字段 -->
      <template v-for="field in schema.properties" :key="field.name">
        <!-- 文本输入 -->
        <el-form-item
          v-if="isTextField(field)"
          :label="field.description || field.name"
          :prop="field.name"
          :required="isFieldRequired(field)"
        >
          <el-input
            v-model="formData[field.name]"
            :type="getTextInputType(field)"
            :placeholder="getPlaceholder(field)"
            :rows="getFieldRows(field)"
            :disabled="!isEnabled(field)"
            clearable
          >
            <!-- 字段提示 -->
            <template #suffix>
              <el-tooltip
                v-if="field.hint || field.description"
                :content="field.hint || field.description"
                placement="top"
              >
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
          </el-input>
        </el-form-item>

        <!-- 数字输入 -->
        <el-form-item
          v-else-if="isNumberField(field)"
          :label="field.description || field.name"
          :prop="field.name"
          :required="isFieldRequired(field)"
        >
          <el-input-number
            v-model="formData[field.name]"
            :min="field.minimum"
            :max="field.maximum"
            :step="getNumberStep(field)"
            :disabled="!isEnabled(field)"
            :placeholder="getPlaceholder(field)"
            controls-position="right"
          />
          <!-- 单位提示 -->
          <template #suffix>
            <span v-if="field.unit" class="unit-hint">{{ field.unit }}</span>
          </template>
        </el-form-item>

        <!-- 布尔开关 -->
        <el-form-item
          v-else-if="isBooleanField(field)"
          :label="field.description || field.name"
          :prop="field.name"
        >
          <el-switch
            v-model="formData[field.name]"
            :disabled="!isEnabled(field)"
            :active-text="getActiveText(field)"
            :inactive-text="getInactiveText(field)"
          />
          <!-- 字段说明 -->
          <div v-if="field.hint" class="field-hint">
            {{ field.hint }}
          </div>
        </el-form-item>

        <!-- 选择器 -->
        <el-form-item
          v-else-if="isSelectField(field)"
          :label="field.description || field.name"
          :prop="field.name"
          :required="isFieldRequired(field)"
        >
          <el-select
            v-model="formData[field.name]"
            :disabled="!isEnabled(field)"
            :placeholder="getPlaceholder(field)"
            clearable
          >
            <el-option
              v-for="option in getFieldOptions(field)"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            >
              {{ option.label }}
            </el-option>
          </el-select>
        </el-form-item>

        <!-- 文本域 -->
        <el-form-item
          v-else-if="isTextAreaField(field)"
          :label="field.description || field.name"
          :prop="field.name"
          :required="isFieldRequired(field)"
        >
          <el-input
            v-model="formData[field.name]"
            type="textarea"
            :rows="field.rows || 4"
            :placeholder="getPlaceholder(field)"
            :disabled="!isEnabled(field)"
          />
        </el-form-item>
      </template>

      <!-- 操作按钮 -->
      <template #footer>
        <div class="form-actions">
          <el-button
            type="primary"
            native-type="submit"
            :loading="submitting"
            :disabled="!isFormDirty || submitting"
          >
            {{ formConfig.submitLabel || $t('common.save') }}
          </el-button>

          <el-button
            v-if="canReset"
            @click="handleReset"
            :disabled="submitting"
          >
            {{ formConfig.resetLabel || $t('workspaceSettings.workspace.actions.reset') }}
          </el-button>

          <el-button @click="handleCancel">
            {{ $t('common.cancel') }}
          </el-button>
        </div>
      </template>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

// ============================================================================
// Props
// ============================================================================

interface PluginField {
  name: string;
  type: string;
  description?: string;
  default?: any;
  required?: boolean;
  enum?: Array<{ value: any; label: string }>;
  minimum?: number;
  maximum?: number;
  pattern?: string;
  format?: string;
  hint?: string;
  unit?: string;
  rows?: number;
}

interface FormConfig {
  schema: {
    title?: string;
    description?: string;
    submitLabel?: string;
    resetLabel?: string;
  };
}

const props = defineProps<{
  pluginId: string;
  workspaceId: string;
  schema?: PluginField[];
  initialConfig?: Record<string, any>;
  canReset?: boolean;
}>();

// ============================================================================
// State
// ============================================================================

const loading = ref(false);
const error = ref<string | null>(null);
const success = ref<string | null>(null);
const formData = reactive<Record<string, any>>({});
const submitting = ref(false);

// ============================================================================
// Computed
// ============================================================================

const formConfig = computed<FormConfig | undefined>(() => {
  if (!props.schema) return undefined;
  return {
    title: props.schema.find(f => f.name === 'title')?.description || t('common.settings'),
    description: props.schema.find(f => f.name === 'description')?.description || '',
    submitLabel: props.schema.find(f => f.name === 'submitLabel')?.description || t('common.save'),
    resetLabel: props.schema.find(f => f.name === 'resetLabel')?.description || t('workspaceSettings.workspace.actions.reset'),
  };
});

const isFormDirty = computed(() => {
  if (!props.initialConfig) return true;
  return Object.keys(formData).some(key => {
    const initialValue = props.initialConfig[key];
    const currentValue = formData[key];
    return JSON.stringify(initialValue) !== JSON.stringify(currentValue);
  });
});

// ============================================================================
// 表单规则
// ============================================================================

const formRules = computed<Record<string, any>>(() => {
  if (!props.schema) return {};

  const rules: Record<string, any> = {};

  for (const field of props.schema) {
    if (!isTextField(field) && !isNumberField(field) &&
        !isBooleanField(field) && !isSelectField(field) &&
        !isTextAreaField(field)) {
      continue;
    }

    // 必填验证
    if (field.required || isFieldRequired(field)) {
      rules[field.name] = [
        { required: true, message: `${field.description || field.name} is required` }
      ];
    }

    // 类型验证
    if (field.type === 'number') {
      if (field.minimum !== undefined) {
        rules[field.name] = rules[field.name] || [];
        rules[field.name].push({
          type: 'number',
          min: field.minimum,
          message: `Must be at least ${field.minimum}`
        });
      }
      if (field.maximum !== undefined) {
        rules[field.name] = rules[field.name] || [];
        rules[field.name].push({
          type: 'number',
          max: field.maximum,
          message: `Must be at most ${field.maximum}`
        });
      }
    }

    // 正则验证
    if (field.pattern) {
      rules[field.name] = rules[field.name] || [];
      rules[field.name].push({
        pattern: new RegExp(field.pattern),
        message: `Invalid format for ${field.description || field.name}`
      });
    }
  }

  return rules;
});

// ============================================================================
// 字段类型判断
// ============================================================================

function isTextField(field: PluginField): boolean {
  return field.type === 'string' && !field.enum;
}

function isNumberField(field: PluginField): boolean {
  return field.type === 'number' || field.type === 'integer';
}

function isBooleanField(field: PluginField): boolean {
  return field.type === 'boolean';
}

function isSelectField(field: PluginField): boolean {
  return field.enum && field.enum.length > 0;
}

function isTextAreaField(field: PluginField): boolean {
  return field.type === 'string' && (field.rows && field.rows > 2);
}

function isFieldRequired(field: PluginField): boolean {
  return field.required || (field.name && isFieldInSchema(field.name));
}

function isFieldInSchema(fieldName: string): boolean {
  return props.schema?.some(f => f.name === fieldName);
}

// ============================================================================
// 辅助函数
// ============================================================================

function getTextInputType(field: PluginField): 'text' | 'password' | 'email' | 'url' {
  if (field.format === 'password') return 'password';
  if (field.format === 'email') return 'email';
  if (field.format === 'uri') return 'url';
  return 'text';
}

function getFieldRows(field: PluginField): number {
  return field.rows || (field.type === 'string' && field.name === 'description' ? 4 : 1);
}

function getNumberStep(field: PluginField): number {
  if (field.type === 'integer') return 1;
  return 0.01;
}

function getPlaceholder(field: PluginField): string {
  if (field.placeholder) return field.placeholder;
  if (field.type === 'number') return 'Enter a number';
  if (field.type === 'boolean') return 'Enabled/Disabled';
  if (field.enum) return 'Select an option';
  return `Enter ${field.description || field.name}`;
}

function getFieldOptions(field: PluginField): Array<{ value: any; label: string }> {
  return field.enum || [];
}

function getActiveText(field: PluginField): string {
  return field.activeText || 'Enabled';
}

function getInactiveText(field: PluginField): string {
  return field.inactiveText || 'Disabled';
}

function isEnabled(field: PluginField): boolean {
  // 字段级别的禁用检查
  return field.disabled !== true;
}

// ============================================================================
// 初始化
// ============================================================================

onMounted(() => {
  initializeForm();
});

function initializeForm() {
  if (!props.schema) {
    error.value = 'No configuration schema available';
    return;
  }

  error.value = null;
  success.value = null;

  // 从初始配置或默认值初始化表单
  for (const field of props.schema) {
    const initialValue = props.initialConfig?.[field.name];
    const defaultValue = field.default;

    formData[field.name] = initialValue !== undefined ? initialValue : defaultValue;
  }
}

// ============================================================================
// 事件处理
// ============================================================================

async function handleSubmit() {
  submitting.value = true;
  error.value = null;
  success.value = null;

  try {
    emit('submit', formData);
    success.value = 'Configuration saved successfully';
  } catch (err: any) {
    error.value = err.message || 'Failed to save configuration';
    console.error('Failed to submit plugin config:', err);
  } finally {
    submitting.value = false;
  }
}

function handleReset() {
  emit('reset', props.pluginId);
  success.value = 'Configuration reset to defaults';
  error.value = null;
}

function handleCancel() {
  emit('cancel');
  error.value = null;
  success.value = null;
}

// 暴露方法给父组件
defineExpose({
  validate: () => {
    // 基本验证
    for (const field of props.schema || []) {
      const value = formData[field.name];
      const rules = formRules.value[field.name];

      if (!rules) continue;

      for (const rule of rules) {
        // Required 验证
        if (rule.required && !value) {
          return false;
        }

        // Pattern 验证
        if (rule.pattern && !rule.pattern.test(value)) {
          return false;
        }

        // Number 范围验证
        if (rule.min !== undefined && value < rule.min) {
          return false;
        }
        if (rule.max !== undefined && value > rule.max) {
          return false;
        }
      }
    }

    return true;
  },
});
</script>

<style scoped>
.dynamic-plugin-config {
  padding: 20px;
}

.form-header {
  margin-bottom: 24px;
}

.form-header h3 {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.form-description {
  margin: -8px 0 0 16px;
  font-size: 14px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  display: block;
}

.unit-hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.form-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color);
}
</style>
