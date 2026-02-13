<!--
  Simplified Privacy Configuration Component - Progressive Privacy Configuration

  Core improvements:
  1. Three-level privacy presets - Most users only need to select a level
  2. Simplified terminology - Replace technical terms with user-friendly descriptions
  3. Advanced options collapsed - Hidden by default to reduce cognitive burden
  4. Visual feedback - Card-style selector, clear and intuitive
-->
<template>
  <div class="privacy-config-simplified">
    <!-- Compliance Standards -->
    <el-alert type="info" :closable="false" show-icon class="compliance-banner">
      <template #title>
        <div class="compliance-title">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ t('privacy.complianceStandards.title') }}</span>
        </div>
      </template>
      <div class="compliance-description">
        {{ t('privacy.complianceStandards.description') }}
      </div>
      <div class="compliance-standards">
        <div class="standard-item">
          <div class="standard-header">
            <el-icon class="standard-icon"><Document /></el-icon>
            <span class="standard-title">{{ t('privacy.complianceStandards.chinaLaw.title') }}</span>
          </div>
          <p class="standard-desc">{{ t('privacy.complianceStandards.chinaLaw.description') }}</p>
        </div>
        <div class="standard-item">
          <div class="standard-header">
            <el-icon class="standard-icon"><Position /></el-icon>
            <span class="standard-title">{{ t('privacy.complianceStandards.gdpr.title') }}</span>
          </div>
          <p class="standard-desc">{{ t('privacy.complianceStandards.gdpr.description') }}</p>
        </div>
        <div class="standard-item">
          <div class="standard-header">
            <el-icon class="standard-icon"><Location /></el-icon>
            <span class="standard-title">{{ t('privacy.complianceStandards.usLaw.title') }}</span>
          </div>
          <p class="standard-desc">{{ t('privacy.complianceStandards.usLaw.description') }}</p>
        </div>
      </div>
    </el-alert>

    <!-- Privacy Level Selector -->
    <div class="privacy-levels">
      <h3 class="section-title">
        {{ t('privacy.selectLevel') }}
      </h3>

      <div class="level-cards">
        <div
          v-for="level in PRIVACY_LEVELS"
          :key="level.id"
          :class="['level-card', `level-${level.id}`, { active: selectedLevel === level.id }]"
          @click="selectLevel(level.id)"
        >
          <div class="level-header">
            <span class="level-icon">{{ level.icon }}</span>
            <span class="level-title">{{ level.title }}</span>
            <el-tag v-if="level.recommended" size="small" type="success">
              {{ t('privacy.recommended') }}
            </el-tag>
            <el-tag v-if="level.default" size="small" type="info">
              {{ t('privacy.default') }}
            </el-tag>
          </div>

          <p class="level-description">{{ level.description }}</p>

          <ul class="level-features">
            <li v-for="feature in level.features" :key="feature">
              <el-icon><Check /></el-icon>
              {{ feature }}
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Advanced Options (Collapsed) -->
    <el-collapse v-model="activePanels" class="advanced-options">
      <el-collapse-item name="advanced">
        <template #title>
          <div class="collapse-title">
            <span>{{ t('privacy.advancedOptions') }}</span>
            <el-tag v-if="isCustomConfig" size="small" type="warning">
              {{ t('privacy.customized') }}
            </el-tag>
          </div>
        </template>

        <el-form
          ref="formRef"
          :model="formData"
          label-width="200px"
          label-position="top"
          @submit.prevent="handleSave"
        >
          <!-- Data Collection -->
          <el-form-item :label="t('privacy.dataCollection')">
            <el-switch v-model="formData.enabled" @change="handleFieldChange" />
            <div class="field-hint">
              {{ t('privacy.dataCollectionHint') }}
            </div>
          </el-form-item>

          <!-- Protect Sensitive Information -->
          <el-form-item :label="t('privacy.protectSensitive')">
            <el-switch v-model="formData.sanitize_sensitive_data" @change="handleFieldChange" />
            <div class="field-hint">
              {{ t('privacy.protectSensitiveHint') }}
            </div>
          </el-form-item>

          <!-- Data Management -->
          <template v-if="formData.enabled">
            <el-divider content-position="left">{{ t('privacy.dataManagement') }}</el-divider>

            <el-form-item :label="t('privacy.dataRetention')">
              <el-input-number
                v-model="formData.retention_days"
                :min="1"
                :max="365"
                style="width: 100%"
                @change="handleFieldChange"
              />
              <div class="field-hint">
                {{ t('privacy.dataRetentionHint') }}
              </div>
            </el-form-item>

            <el-form-item :label="t('privacy.collectionFrequency')">
              <el-slider
                v-model="formData.sampling_rate"
                :min="0"
                :max="1"
                :step="0.1"
                :format-tooltip="formatSamplingRate"
                style="width: 100%"
                @change="handleFieldChange"
              />
              <div class="field-hint">
                {{ t('privacy.collectionFrequencyHint') }}
              </div>
            </el-form-item>
          </template>

          <!-- Data Rights -->
          <el-divider content-position="left">{{ t('privacy.dataRights') }}</el-divider>

          <el-form-item :label="t('privacy.gdprRights')">
            <el-space wrap>
              <el-button size="small" @click="handleExport">
                <el-icon><Download /></el-icon>
                {{ t('privacy.exportData') }}
              </el-button>
              <el-button size="small" type="danger" @click="handleDelete">
                <el-icon><Delete /></el-icon>
                {{ t('privacy.deleteData') }}
              </el-button>
            </el-space>
            <div class="field-hint" style="margin-top: 8px;">
              {{ t('privacy.gdprRightsHint') }}
            </div>
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <!-- 操作按钮 -->
    <div class="actions">
      <el-button @click="handleReset">
        {{ t('privacy.resetToDefault') }}
      </el-button>
      <el-button type="primary" :loading="submitting" @click="handleSave">
        {{ t('privacy.saveConfig') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Check, Download, Delete, InfoFilled, Document, Position, Location } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { pluginConfigClient } from '@/services/api/pluginConfig';

const { t } = useI18n();

// ============================================================================
// Types
// ============================================================================

interface PrivacyLevel {
  id: string;
  icon: string;
  title: string;
  description: string;
  features: string[];
  recommended?: boolean;
  default?: boolean;
  config: {
    enabled: boolean;
    anonymize_enabled: boolean;
    sanitize_sensitive_data: boolean;
    retention_days: number;
    sampling_rate: number;
  };
}

// ============================================================================
// 隐私级别配置
// ============================================================================

const PRIVACY_LEVELS: PrivacyLevel[] = [
  {
    id: 'basic',
    icon: '🟢',
    title: t('privacy.level.basic.title'),
    description: t('privacy.level.basic.description'),
    features: [
      t('privacy.level.basic.feature1'),
      t('privacy.level.basic.feature2'),
      t('privacy.level.basic.feature3'),
    ],
    recommended: true,
    config: {
      enabled: true,
      anonymize_enabled: true,
      sanitize_sensitive_data: true,
      retention_days: 90,
      sampling_rate: 1.0,
    },
  },
  {
    id: 'balanced',
    icon: '🟡',
    title: t('privacy.level.balanced.title'),
    description: t('privacy.level.balanced.description'),
    features: [
      t('privacy.level.balanced.feature1'),
      t('privacy.level.balanced.feature2'),
      t('privacy.level.balanced.feature3'),
      t('privacy.level.balanced.feature4'),
    ],
    default: true,
    config: {
      enabled: true,
      anonymize_enabled: true,
      sanitize_sensitive_data: true,
      retention_days: 30,
      sampling_rate: 0.5,
    },
  },
  {
    id: 'strict',
    icon: '🔴',
    title: t('privacy.level.strict.title'),
    description: t('privacy.level.strict.description'),
    features: [
      t('privacy.level.strict.feature1'),
      t('privacy.level.strict.feature2'),
    ],
    config: {
      enabled: false,
      anonymize_enabled: true,
      sanitize_sensitive_data: true,
      retention_days: 0,
      sampling_rate: 0,
    },
  },
];

// ============================================================================
// Props
// ============================================================================

interface PrivacyConfigSimplifiedProps {
  workspaceId: string;
  initialConfig?: Record<string, any>;
}

const props = defineProps<PrivacyConfigSimplifiedProps>();

// ============================================================================
// State
// ============================================================================

const formRef = ref();
const submitting = ref(false);
const activePanels = ref<string[]>([]);
const selectedLevel = ref<string>('balanced');

const formData = reactive({
  enabled: true,
  anonymize_enabled: true,
  sanitize_sensitive_data: true,
  retention_days: 30,
  sampling_rate: 0.5,
});

// ============================================================================
// Computed
// ============================================================================

// 检测是否为自定义配置
const isCustomConfig = computed(() => {
  const currentConfig = {
    enabled: formData.enabled,
    anonymize_enabled: formData.anonymize_enabled,
    sanitize_sensitive_data: formData.sanitize_sensitive_data,
    retention_days: formData.retention_days,
    sampling_rate: formData.sampling_rate,
  };

  return !PRIVACY_LEVELS.some(
    level => JSON.stringify(level.config) === JSON.stringify(currentConfig)
  );
});

// ============================================================================
// Methods
// ============================================================================

// 选择隐私级别
function selectLevel(levelId: string) {
  selectedLevel.value = levelId;
  const level = PRIVACY_LEVELS.find(l => l.id === levelId);
  if (level) {
    Object.assign(formData, level.config);
    ElMessage.success(t('privacy.levelSelected', { level: level.title }));
  }
}

// 处理字段变化 - 自动切换到自定义
function handleFieldChange() {
  if (selectedLevel.value !== 'custom') {
    selectedLevel.value = 'custom';
  }
}

// 格式化采样率显示
function formatSamplingRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}

// 保存配置
async function handleSave() {
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

    ElMessage.success(t('privacy.configSaved'));
    emit('config-changed', {
      pluginId: 'analytics',
      config: { ...formData },
    });
  } catch (error: any) {
    console.error('Failed to save privacy config:', error);
    ElMessage.error(t('privacy.saveFailed'));
  } finally {
    submitting.value = false;
  }
}

function handleReset() {
  selectLevel('balanced');
}

async function handleExport() {
  try {
    await ElMessageBox.confirm(
      t('privacy.exportConfirm'),
      t('privacy.exportData'),
      { type: 'info' }
    );

    ElMessage.success(t('privacy.exportSuccess'));
  } catch {
    // 用户取消
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(
      t('privacy.deleteConfirm'),
      t('privacy.deleteData'),
      { type: 'error' }
    );

    await pluginConfigClient.resetPluginConfig({
      workspace_id: props.workspaceId,
      plugin_id: 'analytics',
    });

    ElMessage.success(t('privacy.deleteSuccess'));
  } catch {
    // 用户取消
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

const emit = defineEmits<{
  'config-changed': [payload: { pluginId: string; config: Record<string, any> }];
}>();

onMounted(() => {
  // 从初始配置初始化表单
  if (props.initialConfig) {
    Object.assign(formData, props.initialConfig);

    // 检测匹配的级别
    const matchedLevel = PRIVACY_LEVELS.find(
      level => JSON.stringify(level.config) === JSON.stringify(props.initialConfig)
    );
    if (matchedLevel) {
      selectedLevel.value = matchedLevel.id;
    } else {
      selectedLevel.value = 'custom';
    }
  }
});
</script>

<style scoped>
.privacy-config-simplified {
  padding: 20px;
}

/* 合规横幅样式 */
.compliance-banner :deep(.el-alert__title) {
  font-size: 16px;
  font-weight: 600;
  align-items: center;
}

.compliance-banner :deep(.el-alert__content) {
  padding: 16px 0;
}

.compliance-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  margin-bottom: 12px;
}

.compliance-description {
  margin-bottom: 20px;
  font-size: 14px;
  line-height: 1.6;
}

.compliance-standards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 16px;
}

.standard-item {
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color-page);
  transition: all 0.3s ease;
}

.standard-item:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
}

.standard-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 600;
}

.standard-icon {
  font-size: 20px;
  color: var(--el-color-primary);
}

.standard-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.standard-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--el-text-color-primary);
}

/* 隐私级别卡片 */
.level-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.level-card {
  border: 2px solid var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--el-bg-color);
}

.level-card:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.level-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.level-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.level-icon {
  font-size: 24px;
}

.level-title {
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}

.level-description {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.level-features {
  list-style: none;
  padding: 0;
  margin: 0;
}

.level-features li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}

.level-features li .el-icon {
  color: var(--el-color-success);
  font-size: 16px;
}

/* Advanced Options */
.advanced-options {
  margin-top: 24px;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
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

/* 操作按钮 */
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid var(--el-border-color);
}

/* 响应式调整 */
@media (max-width: 768px) {
  .level-cards {
    grid-template-columns: 1fr;
  }

  .actions {
    flex-direction: column;
  }

  .actions .el-button {
    width: 100%;
  }
}
</style>
