<template>
  <div class="resource-limits-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 最大并发任务数 -->
      <el-form-item :label="t('workspace.settings.security.resource.maxConcurrentTasks')">
        <el-input-number
          v-model="localValue.maxConcurrentTasks"
          :min="1"
          :max="50"
          @change="handleUpdate"
        />
        <span class="unit">个</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.maxConcurrentTasksHelp') }}
        </span>
      </el-form-item>

      <!-- 最大内存使用 -->
      <el-form-item :label="t('workspace.settings.security.resource.maxMemoryUsage')">
        <el-input-number
          v-model="localValue.maxMemoryUsageMb"
          :min="128"
          :max="16384"
          :step="128"
          @change="handleUpdate"
        />
        <span class="unit">MB</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.maxMemoryUsageHelp') }}
        </span>
      </el-form-item>

      <!-- 最大执行时间 -->
      <el-form-item :label="t('workspace.settings.security.resource.maxExecutionTime')">
        <el-input-number
          v-model="localValue.maxTaskExecutionTime"
          :min="60"
          :max="7200"
          :step="60"
          @change="handleUpdate"
        />
        <span class="unit">秒</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.maxExecutionTimeHelp') }}
        </span>
      </el-form-item>

      <!-- CPU 使用率限制 -->
      <el-form-item :label="t('workspace.settings.security.resource.cpuLimit')">
        <el-slider
          v-model="cpuLimitPercent"
          :min="10"
          :max="100"
          :step="10"
          :marks="cpuMarks"
          @change="handleCpuLimitUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.cpuLimitHelp') }}
        </span>
      </el-form-item>

      <!-- 最大文件操作数 -->
      <el-form-item :label="t('workspace.settings.security.resource.maxFileOperations')">
        <el-input-number
          v-model="localValue.maxFileOperations"
          :min="10"
          :max="10000"
          :step="10"
          @change="handleUpdate"
        />
        <span class="unit">次/分钟</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.maxFileOperationsHelp') }}
        </span>
      </el-form-item>

      <!-- 最大网络请求数 -->
      <el-form-item :label="t('workspace.settings.security.resource.maxNetworkRequests')">
        <el-input-number
          v-model="localValue.maxNetworkRequests"
          :min="1"
          :max="1000"
          @change="handleUpdate"
        />
        <span class="unit">次/分钟</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.maxNetworkRequestsHelp') }}
        </span>
      </el-form-item>

      <!-- 启用资源监控 -->
      <el-form-item :label="t('workspace.settings.security.resource.enableMonitoring')">
        <el-switch
          v-model="localValue.enableResourceMonitoring"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.resource.enableMonitoringHelp') }}
        </span>
      </el-form-item>

      <!-- 资源超限行为 -->
      <el-form-item :label="t('workspace.settings.security.resource.limitExceededAction')">
        <el-radio-group
          v-model="localValue.resourceLimitExceededAction"
          @change="handleUpdate"
        >
          <el-radio value="warn">{{ t('workspace.settings.security.resource.actionWarn') }}</el-radio>
          <el-radio value="terminate">{{ t('workspace.settings.security.resource.actionTerminate') }}</el-radio>
          <el-radio value="pause">{{ t('workspace.settings.security.resource.actionPause') }}</el-radio>
        </el-radio-group>
        <div class="form-item-help">
          <p><strong>{{ t('workspace.settings.security.resource.actionWarn') }}：</strong>{{ t('workspace.settings.security.resource.actionWarnHelp') }}</p>
          <p><strong>{{ t('workspace.settings.security.resource.actionTerminate') }}：</strong>{{ t('workspace.settings.security.resource.actionTerminateHelp') }}</p>
          <p><strong>{{ t('workspace.settings.security.resource.actionPause') }}：</strong>{{ t('workspace.settings.security.resource.actionPauseHelp') }}</p>
        </div>
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

// CPU 限制滑块
const cpuLimitPercent = computed({
  get: () => Math.round((localValue.value as any).cpuLimitPercent || 80),
  set: (val: number) => {
    (localValue.value as any).cpuLimitPercent = val;
  }
});

const cpuMarks = {
  10: '10%',
  25: '25%',
  50: '50%',
  75: '75%',
  100: '100%'
};

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

const handleCpuLimitUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.resource-limits-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;

    p {
      margin: 2px 0;
    }

    strong {
      color: var(--el-text-color-regular);
    }
  }

  .unit {
    margin-left: 5px;
    color: var(--el-text-color-regular);
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }

  :deep(.el-slider) {
    width: 80%;
  }
}
</style>
