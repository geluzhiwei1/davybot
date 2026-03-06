<template>
  <div class="network-security-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 启用网络安全限制 -->
      <el-form-item :label="t('workspace.settings.security.network.enableRestrictions')">
        <el-switch
          v-model="localValue.enableNetworkRestrictions"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.enableRestrictionsHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：基础允许的域名 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.network.baseAllowedDomains')"
      >
        <el-select
          v-model="baseAllowedDomains"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.network.domainsPlaceholder')"
          @change="handleDomainsUpdate"
        >
          <el-option
            v-for="domain in commonDomains"
            :key="domain"
            :label="domain"
            :value="domain"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.baseAllowedDomainsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：允许的域名 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.network.allowedDomains')"
      >
        <el-select
          v-model="allowedDomains"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.network.domainsPlaceholder')"
          @change="handleDomainsUpdate"
        >
          <el-option
            v-for="domain in commonDomains"
            :key="domain"
            :label="domain"
            :value="domain"
          />
        </el-select>
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.allowedDomainsHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：基础拒绝的域名 -->
      <el-form-item
        v-if="isUserLevel"
        :label="t('workspace.settings.security.network.baseDeniedDomains')"
      >
        <el-select
          v-model="baseDeniedDomains"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.network.domainsPlaceholder')"
          @change="handleDomainsUpdate"
        >
          <el-option
            v-for="domain in dangerousDomains"
            :key="domain"
            :label="domain"
            :value="domain"
          />
        </el-select>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.network.baseDeniedDomainsHelp') }}
        </span>
      </el-form-item>

      <!-- 工作区级：拒绝的域名 -->
      <el-form-item
        v-else
        :label="t('workspace.settings.security.network.deniedDomains')"
      >
        <el-select
          v-model="deniedDomains"
          multiple
          filterable
          allow-create
          :placeholder="t('workspace.settings.security.network.domainsPlaceholder')"
          @change="handleDomainsUpdate"
        >
          <el-option
            v-for="domain in dangerousDomains"
            :key="domain"
            :label="domain"
            :value="domain"
          />
        </el-select>
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.network.deniedDomainsHelp') }}
        </span>
      </el-form-item>

      <!-- 网络请求超时 -->
      <el-form-item :label="t('workspace.settings.security.network.requestTimeout')">
        <el-input-number
          v-model="localValue.networkRequestTimeout"
          :min="1"
          :max="300"
          @change="handleUpdate"
        />
        <span class="unit">秒</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.requestTimeoutHelp') }}
        </span>
      </el-form-item>

      <!-- 最大下载大小 -->
      <el-form-item :label="t('workspace.settings.security.network.maxDownloadSize')">
        <el-input-number
          v-model="localValue.maxDownloadSizeMb"
          :min="1"
          :max="1024"
          @change="handleUpdate"
        />
        <span class="unit">MB</span>
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.maxDownloadSizeHelp') }}
        </span>
      </el-form-item>

      <!-- 允许浏览器访问 -->
      <el-form-item :label="t('workspace.settings.security.network.allowBrowser')">
        <el-switch
          v-model="localValue.enableBrowserAccess"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.network.allowBrowserHelp') }}
        </span>
      </el-form-item>

      <!-- 允许外部 API 调用 -->
      <el-form-item :label="t('workspace.settings.security.network.allowExternalApi')">
        <el-switch
          v-model="localValue.allowExternalApiCalls"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ {{ t('workspace.settings.security.network.allowExternalApiHelp') }}
        </span>
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

// 常见安全域名
const commonDomains = [
  'github.com',
  'api.openai.com',
  'api.anthropic.com',
  'pypi.org',
  'npmjs.com',
  'stackoverflow.com'
];

// 危险域名
const dangerousDomains = [
  'malicious-example.com',
  'suspicious-site.net',
  'test-phishing.org'
];

// 用户级：基础允许的域名
const baseAllowedDomains = computed({
  get: () => (localValue.value as UserSecuritySettings).baseAllowedDomains,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseAllowedDomains = val;
  }
});

// 用户级：基础拒绝的域名
const baseDeniedDomains = computed({
  get: () => (localValue.value as UserSecuritySettings).baseDeniedDomains,
  set: (val: string[]) => {
    (localValue.value as UserSecuritySettings).baseDeniedDomains = val;
  }
});

// 工作区级：允许的域名
const allowedDomains = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).allowedDomains || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).allowedDomains = val;
  }
});

// 工作区级：拒绝的域名
const deniedDomains = computed({
  get: () => (localValue.value as WorkspaceSecuritySettings).deniedDomains || [],
  set: (val: string[]) => {
    (localValue.value as WorkspaceSecuritySettings).deniedDomains = val;
  }
});

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

const handleDomainsUpdate = () => {
  handleUpdate();
};
</script>

<style scoped lang="scss">
.network-security-section {
  padding: 10px;

  .form-item-help {
    margin-left: 10px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;

    &.warning {
      color: var(--el-color-warning);
      font-weight: 500;
    }
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
