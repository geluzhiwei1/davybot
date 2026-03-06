<template>
  <div class="sandbox-config-section">
    <el-form :model="localValue" label-width="250px" label-position="left">
      <!-- 启用沙箱隔离 -->
      <el-form-item :label="t('workspace.settings.security.sandbox.enableSandbox')">
        <el-switch
          v-model="localValue.enableSandbox"
          @change="handleUpdate"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.sandbox.enableSandboxHelp') }}
        </span>
      </el-form-item>

      <!-- 沙箱模式 -->
      <el-form-item :label="t('userSettings.security.sandbox.sandboxMode')">
        <el-radio-group
          v-model="localValue.sandboxMode"
          @change="handleUpdate"
          :disabled="!localValue.enableSandbox"
        >
          <el-radio value="docker">Docker/Podman 沙箱</el-radio>
          <el-radio value="lightweight">轻量级沙箱</el-radio>
          <el-radio value="disabled">禁用</el-radio>
        </el-radio-group>
        <div class="form-item-help">
          <p><strong>Docker/Podman 沙箱：</strong>完整的容器隔离，最安全但需要容器运行时</p>
          <p><strong>轻量级沙箱：</strong>使用 firejail 或 chroot，无需容器运行时</p>
          <p><strong>禁用：</strong>直接在主机执行，不推荐</p>
        </div>
      </el-form-item>

      <!-- 容器运行时选择 -->
      <el-form-item
        v-if="localValue.sandboxMode === 'docker'"
        :label="t('userSettings.security.sandbox.containerRuntime')"
      >
        <div class="runtime-selection-wrapper">
          <el-radio-group
            v-model="localValue.containerRuntime"
            @change="handleUpdate"
            :disabled="!localValue.enableSandbox"
          >
            <el-radio value="auto">自动检测</el-radio>
            <el-radio value="docker">Docker</el-radio>
            <el-radio value="podman">Podman</el-radio>
          </el-radio-group>
          <el-button
            type="primary"
            size="small"
            @click="detectContainerRuntime"
            :loading="detecting"
            :disabled="!localValue.enableSandbox"
            style="margin-left: 12px;"
          >
            {{ t('userSettings.security.sandbox.detectButton') }}
          </el-button>
        </div>
        <div class="form-item-help">
          <p><strong>自动检测：</strong>优先使用 Podman（更安全），不可用时降级到 Docker</p>
          <p><strong>Docker：</strong>使用 Docker 守护进程（需要 root 或 docker 组权限）</p>
          <p><strong>Podman：</strong>使用 Podman（无守护进程，更安全，支持 rootless 模式）</p>
        </div>

        <!-- 检测结果显示 -->
        <el-alert
          v-if="detectionResult"
          :type="detectionResult.success ? 'success' : 'warning'"
          :closable="false"
          style="margin-top: 12px;"
        >
          <template #title>
            <div v-html="detectionResult.message"></div>
          </template>
        </el-alert>
      </el-form-item>

      <!-- 允许降级 -->
      <el-form-item :label="t('workspace.settings.security.sandbox.allowFallback')">
        <el-switch
          v-model="localValue.allowSandboxFallback"
          @change="handleUpdate"
          :disabled="!localValue.enableSandbox"
        />
        <span class="form-item-help">
          {{ t('workspace.settings.security.sandbox.allowFallbackHelp') }}
        </span>
      </el-form-item>

      <!-- 用户级：强制使用沙箱 -->
      <el-form-item
        v-if="isUserLevel"
        label="强制所有工作区使用沙箱"
      >
        <el-switch
          v-model="localValue.enforceSandbox"
          @change="handleUpdate"
        />
        <span class="form-item-help warning">
          ⚠️ 启用后，所有工作区都无法禁用沙箱
        </span>
      </el-form-item>

      <!-- Docker沙箱细粒度安全控制 -->
      <el-divider v-if="localValue.sandboxMode === 'docker'" content-position="left">
        Docker 沙箱细粒度安全控制
      </el-divider>

      <!-- 移除所有capabilities -->
      <el-form-item
        v-if="localValue.sandboxMode === 'docker'"
        :label="t('userSettings.security.sandbox.dropAllCapabilities')"
      >
        <el-switch
          v-model="localValue.dropAllCapabilities"
          @change="handleUpdate"
          :disabled="!localValue.enableSandbox"
        />
        <span class="form-item-help">
          {{ t('userSettings.security.sandbox.dropAllCapabilitiesHelp') }}
        </span>
      </el-form-item>

      <!-- 禁止获得新权限 -->
      <el-form-item
        v-if="localValue.sandboxMode === 'docker'"
        :label="t('userSettings.security.sandbox.noNewPrivileges')"
      >
        <el-switch
          v-model="localValue.noNewPrivileges"
          @change="handleUpdate"
          :disabled="!localValue.enableSandbox"
        />
        <span class="form-item-help">
          {{ t('userSettings.security.sandbox.noNewPrivilegesHelp') }}
        </span>
      </el-form-item>

      <!-- 网络禁用 -->
      <el-form-item
        v-if="localValue.sandboxMode === 'docker'"
        :label="t('userSettings.security.sandbox.sandboxDisableNetwork')"
      >
        <el-switch
          v-model="localValue.sandboxDisableNetwork"
          @change="handleUpdate"
          :disabled="!localValue.enableSandbox"
        />
        <span class="form-item-help">
          {{ t('userSettings.security.sandbox.sandboxDisableNetworkHelp') }}
        </span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
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

// 检测状态
const detecting = ref(false);
const detectionResult = ref<{ success: boolean; message: string } | null>(null);

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

// 检测容器运行时
const detectContainerRuntime = async () => {
  detecting.value = true;
  detectionResult.value = null;

  try {
    // 调用后端 API 进行检测
    const response = await fetch('/api/system/container-runtime/detect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`检测失败: ${response.statusText}`);
    }

    const result = await response.json();

    // 格式化检测结果
    let message = '<div style="line-height: 1.8;">';

    if (result.docker?.available) {
      message += `<p>✅ <strong>Docker</strong> 可用 (版本: ${result.docker.version || 'unknown'})</p>`;
    } else {
      message += `<p>❌ <strong>Docker</strong> 不可用 (${result.docker?.error || '未安装或未运行'})</p>`;
    }

    if (result.podman?.available) {
      message += `<p>✅ <strong>Podman</strong> 可用 (版本: ${result.podman.version || 'unknown'})</p>`;
      if (result.podman.socket) {
        message += `<p style="margin-left: 20px; color: var(--el-text-color-secondary);">Socket: ${result.podman.socket}</p>`;
      }
    } else {
      message += `<p>❌ <strong>Podman</strong> 不可用 (${result.podman?.error || '未安装或未运行'})</p>`;
    }

    message += '</div>';

    // 推荐配置
    if (result.podman?.available && !result.docker?.available) {
      message += `<p style="margin-top: 12px; padding: 8px; background: var(--el-color-success-light-9); border-radius: 4px;">💡 推荐使用 <strong>Podman</strong>（更安全，支持 rootless 模式）</p>`;
    } else if (result.docker?.available && !result.podman?.available) {
      message += `<p style="margin-top: 12px; padding: 8px; background: var(--el-color-warning-light-9); border-radius: 4px;">ℹ️ 检测到 <strong>Docker</strong>，建议考虑安装 Podman 以获得更好的安全性</p>`;
    } else if (result.docker?.available && result.podman?.available) {
      message += `<p style="margin-top: 12px; padding: 8px; background: var(--el-color-success-light-9); border-radius: 4px;">💡 <strong>两者都可用</strong>，推荐使用 Podman（默认优先）</p>`;
    } else {
      message += `<p style="margin-top: 12px; padding: 8px; background: var(--el-color-danger-light-9); border-radius: 4px;">⚠️ <strong>未检测到可用的容器运行时</strong>，请安装 Docker 或 Podman</p>`;
    }

    detectionResult.value = {
      success: result.docker?.available || result.podman?.available,
      message
    };

    ElMessage.success('容器运行时检测完成');
  } catch (error) {
    console.error('检测容器运行时失败:', error);
    detectionResult.value = {
      success: false,
      message: `<p style="color: var(--el-color-danger);">检测失败: ${error instanceof Error ? error.message : '未知错误'}</p>`
    };
    ElMessage.error('检测容器运行时失败');
  } finally {
    detecting.value = false;
  }
};
</script>

<style scoped lang="scss">
.sandbox-config-section {
  padding: 10px;

  .runtime-selection-wrapper {
    display: flex;
    align-items: center;
  }

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

    &.warning {
      color: var(--el-color-warning);
    }
  }

  :deep(.el-form-item) {
    margin-bottom: 20px;
  }

  :deep(.el-divider) {
    margin: 24px 0 16px;
    font-weight: 500;
  }

  :deep(.el-alert) {
    p {
      margin: 4px 0;
    }
  }
}
</style>
