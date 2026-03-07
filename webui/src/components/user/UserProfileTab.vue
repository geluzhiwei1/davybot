/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="user-profile-tab">
    <!-- 登录状态区域 -->
    <div class="auth-section">
      <div v-if="authenticated && authenticatedUser" class="user-info-card">
        <el-avatar :size="64" :src="authenticatedUser.avatar">
          {{ authenticatedUser.nickname?.charAt(0)?.toUpperCase() || 'U' }}
        </el-avatar>
        <div class="user-details">
          <h3 class="user-name">{{ authenticatedUser.nickname || t('userSettings.profile.unknownUser') }}</h3>
          <p class="user-email">{{ authenticatedUser.email }}</p>
          <div class="token-stats">
            <el-tag size="small" type="info">
              Token: {{ authenticatedUser.token_used || 0 }} / {{ authenticatedUser.token_quota || 0 }}
            </el-tag>
          </div>
        </div>
        <el-button type="danger" @click="handleLogout" :loading="loggingOut">
          {{ t('userSettings.profile.logout') }}
        </el-button>
      </div>
      <div v-else class="login-prompt">
        <el-icon :size="48" color="#909399"><Lock /></el-icon>
        <h3>{{ t('userSettings.profile.notLoggedIn') }}</h3>
        <p>{{ t('userSettings.profile.loginHint') }}</p>
        <el-button type="primary" @click="handleLogin" :loading="loggingIn">
          {{ t('userSettings.profile.login') }}
        </el-button>
      </div>
    </div>

    <el-divider />

    <!-- 本地个人信息表单 -->
    <el-form :model="userProfile" label-width="120px" class="settings-form">
      <el-form-item :label="t('userSettings.profile.username')">
        <el-input v-model="userProfile.username" :placeholder="t('userSettings.profile.usernamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('userSettings.profile.email')">
        <el-input v-model="userProfile.email" :placeholder="t('userSettings.profile.emailPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('userSettings.profile.bio')">
        <el-input v-model="userProfile.bio" type="textarea" :rows="3"
          :placeholder="t('userSettings.profile.bioPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('userSettings.profile.timezone')">
        <el-select v-model="userProfile.timezone" :placeholder="t('userSettings.profile.timezone')" filterable>
          <el-option v-for="tz in timezones" :key="tz.value" :label="tz.label" :value="tz.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('userSettings.profile.language')">
        <el-select v-model="userProfile.language" :placeholder="t('userSettings.profile.language')">
          <el-option label="简体中文" value="zh-CN" />
          <el-option label="English" value="en-US" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveUserProfile" :loading="saving">
          {{ t('userSettings.profile.save') }}
        </el-button>
        <el-button @click="loadUserProfile">{{ t('userSettings.profile.refresh') }}</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Lock } from '@element-plus/icons-vue';
import { authService, type UserInfo } from '@/services/auth';

const { t } = useI18n();

// 认证状态
const authenticated = ref(false);
const authenticatedUser = ref<UserInfo | null>(null);
const loggingIn = ref(false);
const loggingOut = ref(false);

const userProfile = ref({
  username: '',
  email: '',
  bio: '',
  timezone: 'Asia/Shanghai',
  language: 'zh-CN'
});

const saving = ref(false);

const timezones = [
  { label: '亚洲/上海 (GMT+8)', value: 'Asia/Shanghai' },
  { label: '亚洲/东京 (GMT+9)', value: 'Asia/Tokyo' },
  { label: '欧洲/伦敦 (GMT+0)', value: 'Europe/London' },
  { label: '美国/纽约 (GMT-5)', value: 'America/New_York' },
  { label: '美国/洛杉矶 (GMT-8)', value: 'America/Los_Angeles' }
];

// 组件挂载和卸载时检查认证状态
onMounted(async () => {
  await loadUserProfile();
  await checkAuthStatus();

  // 监听来自OAuth回调窗口的消息
  window.addEventListener('message', handleOAuthMessage);
});

onUnmounted(() => {
  window.removeEventListener('message', handleOAuthMessage);
});

/**
 * 检查认证状态
 */
const checkAuthStatus = async () => {
  try {
    const authState = await authService.checkAuthStatus();
    authenticated.value = authState.authenticated;
    authenticatedUser.value = authState.user;
  } catch (error) {
    console.error('Failed to check auth status:', error);
  }
};

/**
 * 处理登录
 */
const handleLogin = async () => {
  loggingIn.value = true;
  try {
    // 发起OAuth登录
    await authService.login();

    // 开始轮询检查登录状态
    ElMessage.info(t('userSettings.profile.loginInProgress'));

    authService.startPolling((user) => {
      // 登录成功回调
      authenticated.value = true;
      authenticatedUser.value = user;
      loggingIn.value = false;

      ElMessage.success(t('userSettings.profile.loginSuccess'));
    });
  } catch (error) {
    loggingIn.value = false;
    ElMessage.error(t('userSettings.profile.loginFailed'));
    console.error('Login failed:', error);
  }
};

/**
 * 处理登出
 */
const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(
      t('userSettings.profile.logoutConfirm'),
      t('common.confirm'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning',
      }
    );

    loggingOut.value = true;
    await authService.logout();

    authenticated.value = false;
    authenticatedUser.value = null;
    loggingOut.value = false;

    ElMessage.success(t('userSettings.profile.logoutSuccess'));
  } catch (error) {
    if (error !== 'cancel') {
      loggingOut.value = false;
      ElMessage.error(t('userSettings.profile.logoutFailed'));
      console.error('Logout failed:', error);
    }
  }
};

/**
 * 处理来自OAuth回调窗口的消息
 */
const handleOAuthMessage = (event: MessageEvent) => {
  // 验证消息来源（安全检查）
  if (event.origin !== window.location.origin) {
    return;
  }

  const { type, data, error } = event.data;

  if (type === 'oauth_login_success') {
    // 登录成功，刷新用户信息
    checkAuthStatus();
    ElMessage.success(t('userSettings.profile.loginSuccess'));
  } else if (type === 'oauth_login_error') {
    // 登录失败
    loggingIn.value = false;
    authService.stopPolling();
    ElMessage.error(error || t('userSettings.profile.loginFailed'));
  }
};

const loadUserProfile = async () => {
  try {
    const saved = localStorage.getItem('user-profile');
    if (saved) {
      userProfile.value = JSON.parse(saved);
    }
  } catch (error) {
    console.error('Failed to load user profile:', error);
  }
};

const saveUserProfile = async () => {
  saving.value = true;
  try {
    localStorage.setItem('user-profile', JSON.stringify(userProfile.value));
    ElMessage.success(t('userSettings.profile.saveSuccess'));
  } catch (error) {
    ElMessage.error(t('common.saveFailed'));
    console.error('Failed to save user profile:', error);
  } finally {
    saving.value = false;
  }
};
</script>

<style scoped lang="scss">
.user-profile-tab {
  /* 认证区域样式 */
  .auth-section {
    padding: 20px;
    margin-bottom: 20px;
  }

  .user-info-card {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 24px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    color: white;
  }

  .user-details {
    flex: 1;
  }

  .user-name {
    margin: 0 0 8px 0;
    font-size: 20px;
    font-weight: 600;
  }

  .user-email {
    margin: 0 0 12px 0;
    font-size: 14px;
    opacity: 0.9;
  }

  .token-stats {
    display: inline-block;
  }

  .login-prompt {
    text-align: center;
    padding: 40px 20px;
    background: var(--el-fill-color-light);
    border-radius: 12px;
  }

  .login-prompt h3 {
    margin: 16px 0 8px 0;
    font-size: 18px;
    color: var(--el-text-color-primary);
  }

  .login-prompt p {
    margin: 0 0 20px 0;
    color: var(--el-text-color-regular);
    font-size: 14px;
  }

  .settings-form {
    padding: 16px;
  }
}
</style>
