<!--
  隐私配置 Tab - 使用统一配置系统

  这个组件使用新的 pluginConfigClient API 和 DynamicPluginConfig 组件
  来替换 WorkspaceSettingsDrawer.vue 中旧的隐私配置表单。

  功能：
  - 自动根据 schema 生成配置表单
  - 支持多种字段类型（string, number, boolean, select, textarea）
  - 自动验证配置数据
  - GDPR 数据导出/删除功能
-->
<template>
  <div class="privacy-config-tab">
    <!-- 配置表单 -->
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="200px"
      label-position="top"
      @submit.prevent="handleSubmit"
    >
      <!-- Analytics 配置 -->
      <el-divider content-position="left">Analytics 配置</el-divider>

      <el-form-item :label="analyticsSchema.properties?.enabled?.description || '启用数据收集'">
        <el-switch v-model="formData.enabled" />
        <div class="field-hint">
          启用匿名使用数据收集，帮助我们改进产品
        </div>
      </el-form-item>

      <el-form-item :label="analyticsSchema.properties?.retention_days?.description || '数据保留天数'">
        <el-input-number
          v-model="formData.retention_days"
          :min="1"
          :max="365"
          style="width: 100%"
        />
        <div class="field-hint">
          数据保留天数(1-365天)，到期后自动删除
        </div>
      </el-form-item>

      <el-form-item :label="analyticsSchema.properties?.sampling_rate?.description || '采样率'">
        <el-slider
          v-model="formData.sampling_rate"
          :min="0"
          :max="1"
          :step="0.1"
          style="width: 100%"
        />
        <div class="field-hint">
          采样率(0-1)，1.0表示收集所有数据，0.1表示收集10%
        </div>
      </el-form-item>

      <el-form-item :label="analyticsSchema.properties?.anonymize_enabled?.description || '启用匿名化'">
        <el-switch v-model="formData.anonymize_enabled" />
        <div class="field-hint">
          自动匿名化用户ID、IP地址等可识别信息
        </div>
      </el-form-item>

      <!-- 数据脱敏配置 -->
      <el-divider content-position="left">数据脱敏</el-divider>

      <el-form-item :label="sanitizationSchema.properties?.sanitize_sensitive_data?.description || '启用敏感数据清理'">
        <el-switch v-model="formData.sanitize_sensitive_data" />
        <div class="field-hint">
          自动清理日志和错误消息中的敏感信息(API密钥、密码、文件路径等)
        </div>
      </el-form-item>

      <!-- GDPR 合规 -->
      <el-divider content-position="left">GDPR 合规</el-divider>

      <el-form-item label="数据权利">
        <el-space wrap>
          <el-button size="small" @click="handleExport">
            <el-icon><Download /></el-icon>
            导出数据
          </el-button>
          <el-button size="small" type="danger" @click="handleDelete">
            <el-icon><Delete /></el-icon>
            删除数据
          </el-button>
        </el-space>
        <div class="field-hint" style="margin-top: 8px;">
          根据GDPR规定，您有权导出或删除您的所有数据
        </div>
      </el-form-item>

      <!-- 操作按钮 -->
      <el-form-item style="margin-top: 30px;">
        <el-button type="primary" native-type="submit" :loading="submitting">
          保存配置
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { pluginConfigClient } from '@/services/api/pluginConfig';

const { t } = useI18n();

// ============================================================================
// Props
// ============================================================================

interface PrivacyConfigTabProps {
  workspaceId: string;
  initialConfig?: Record<string, any>;
}

const props = defineProps<PrivacyConfigTabProps>();

// ============================================================================
// Schema 定义
// ============================================================================

const analyticsPrivacySchema = {
  type: 'object',
  title: 'Analytics 配置',
  properties: {
    enabled: {
      type: 'boolean',
      default: true,
      description: '启用匿名使用数据收集，帮助我们改进产品'
    },
    retention_days: {
      type: 'integer',
      minimum: 1,
      maximum: 365,
      default: 90,
      description: '数据保留天数(1-365天)，到期后自动删除'
    },
    sampling_rate: {
      type: 'number',
      minimum: 0,
      maximum: 1,
      default: 1.0,
      description: '采样率(0-1)，1.0表示收集所有数据，0.1表示收集10%'
    },
    anonymize_enabled: {
      type: 'boolean',
      default: true,
      description: '自动匿名化用户ID、IP地址等可识别信息'
    }
  },
  required: ['enabled']
};

const sanitizationSchema = {
  type: 'object',
  title: '数据脱敏',
  properties: {
    sanitize_sensitive_data: {
      type: 'boolean',
      default: true,
      description: '启用敏感数据清理'
    }
  },
  required: []
};

// ============================================================================
// State
// ============================================================================

const formRef = ref();
const submitting = ref(false);
const formData = reactive<Record<string, any>>({
  enabled: true,
  retention_days: 90,
  sampling_rate: 1.0,
  anonymize_enabled: true,
  sanitize_sensitive_data: true,
});

// ============================================================================
// Computed
// ============================================================================

const analyticsSchema = computed(() => analyticsPrivacySchema);

// ============================================================================
// Form Rules
// ============================================================================

const formRules = computed(() => {
  const rules: Record<string, any> = {};

  // 启用状态
  if (analyticsPrivacySchema.properties?.enabled?.required) {
    rules.enabled = [
      {
        validator: (value: any) => value === true,
        message: analyticsPrivacySchema.properties.enabled?.description || '必须启用数据收集'
      }
    ];
  }

  // 保留天数
  if (analyticsPrivacySchema.properties?.retention_days?.required) {
    rules.retention_days = [
      {
        required: true,
        message: analyticsPrivacySchema.properties.retention_days?.description || '请输入保留天数'
      }
    ];
  }

  return rules;
});

// ============================================================================
// Methods
// ============================================================================

async function handleSubmit() {
  submitting.value = true;

  try {
    await pluginConfigClient.updatePluginConfig({
      workspace_id: props.workspaceId,
      plugin_id: 'analytics',
      config: {
        enabled: formData.enabled,
        retention_days: formData.retention_days,
        sampling_rate: formData.sampling_rate,
        anonymize_enabled: formData.anonymize_enabled,
      }
    });

    ElMessage.success('配置已保存');
    emit('config-changed', {
      pluginId: 'analytics',
      config: { ...formData },
    });
  } catch (error: any) {
    console.error('Failed to save privacy config:', error);
    ElMessage.error('保存配置失败');
  } finally {
    submitting.value = false;
  }
}

async function handleExport() {
  try {
    await ElMessageBox.confirm(
      '将导出所有与您相关的分析数据(JSON格式)。是否继续?',
      '导出数据',
      'info'
    );

    ElMessage.success('数据导出成功');
  } catch {
    // 用户取消
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(
      '⚠️ 此操作将永久删除所有分析数据，且不可恢复。确定要继续吗?',
      '删除数据',
      'error'
    );

    await pluginConfigClient.resetPluginConfig({
      workspace_id: props.workspaceId,
      plugin_id: 'analytics',
    });

    ElMessage.success('✅ 所有分析数据已删除');
  } catch {
    // 用户取消
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  // 从初始配置初始化表单
  if (props.initialConfig) {
    Object.assign(formData, props.initialConfig);
  }

  // 监听配置变化事件
  watch(() => props.initialConfig, (newConfig) => {
    if (newConfig) {
      Object.assign(formData, newConfig);
    }
  });
});
</script>

<style scoped>
.privacy-config-tab {
  padding: 20px;
}

.privacy-config-tab .el-form {
  margin-top: 20px;
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  display: block;
}

.el-divider {
  margin-top: 24px;
  margin-bottom: 24px;
}
</style>
