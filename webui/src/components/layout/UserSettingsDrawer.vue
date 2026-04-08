/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-drawer v-model="visible" :title="t('userSettings.title')" direction="rtl" :size="'80%'"
    class="user-settings-drawer" @close="handleClose">
    <template #header>
      <div class="drawer-header">
        <el-icon :size="20">
          <User />
        </el-icon>
        <span class="drawer-title">{{ t('userSettings.title') }}</span>
      </div>
    </template>

    <div class="drawer-content">
      <el-tabs v-model="activeTab" type="border-card">
        <!-- 个人信息 Tab -->
        <el-tab-pane :label="t('userSettings.tabs.profile')" name="profile">
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
        </el-tab-pane>

        <!-- 偏好设置 Tab -->
        <el-tab-pane :label="t('userSettings.tabs.preferences')" name="preferences">
          <el-form :model="preferences" label-width="140px" class="settings-form">
            <el-form-item :label="t('userSettings.preferences.theme')">
              <el-radio-group v-model="preferences.theme">
                <el-radio value="light">{{ t('userSettings.preferences.themeLight') }}</el-radio>
                <el-radio value="dark">{{ t('userSettings.preferences.themeDark') }}</el-radio>
                <el-radio value="auto">{{ t('userSettings.preferences.themeAuto') }}</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('userSettings.preferences.fontSize')">
              <el-slider v-model="preferences.fontSize" :min="12" :max="20" :marks="fontMarks" />
            </el-form-item>
            <el-form-item :label="t('userSettings.preferences.messageDensity')">
              <el-radio-group v-model="preferences.messageDensity">
                <el-radio value="comfortable">{{ t('userSettings.preferences.densityComfortable') }}</el-radio>
                <el-radio value="compact">{{ t('userSettings.preferences.densityCompact') }}</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('userSettings.preferences.codeTheme')">
              <el-select v-model="preferences.codeTheme" :placeholder="t('userSettings.preferences.codeTheme')">
                <el-option label="GitHub Light" value="github-light" />
                <el-option label="GitHub Dark" value="github-dark" />
                <el-option label="Monokai" value="monokai" />
                <el-option label="VS Code Dark" value="vscode-dark" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('userSettings.preferences.notifications')">
              <el-switch v-model="preferences.notificationsEnabled" />
            </el-form-item>
            <el-form-item :label="t('userSettings.preferences.autoSave')">
              <el-switch v-model="preferences.autoSave" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="savePreferences" :loading="saving">
                {{ t('userSettings.preferences.save') }}
              </el-button>
              <el-button @click="loadPreferences">{{ t('userSettings.preferences.refresh') }}</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 快捷键 Tab -->
        <el-tab-pane :label="t('userSettings.tabs.shortcuts')" name="shortcuts">
          <div class="shortcuts-list">
            <div v-for="(shortcut, key) in defaultShortcuts" :key="key" class="shortcut-item">
              <div class="shortcut-label">{{ shortcut.label }}</div>
              <div class="shortcut-keys">
                <kbd v-for="k in shortcut.keys" :key="k">{{ k }}</kbd>
              </div>
            </div>
          </div>
          <el-divider />
          <el-form-item :label="t('userSettings.shortcuts.customShortcut')">
            <el-button @click="resetShortcuts">{{ t('userSettings.shortcuts.reset') }}</el-button>
          </el-form-item>
        </el-tab-pane>

        <!-- 安全设置 Tab -->
        <el-tab-pane :label="t('userSettings.tabs.security')" name="security">
          <SecuritySettingsTab v-model="securitySettings" @update:model-value="handleSecuritySettingsUpdate" />
        </el-tab-pane>

        <!-- 关于 Tab -->
        <el-tab-pane :label="t('userSettings.tabs.about')" name="about">
          <div class="about-section">
            <el-result icon="success" :title="t('userSettings.about.title')"
              :sub-title="t('userSettings.about.subtitle')">
              <template #extra>
                <el-descriptions :column="1" border>
                  <el-descriptions-item :label="t('userSettings.about.version')">v{{ appVersion
                    }}</el-descriptions-item>
                  <el-descriptions-item :label="t('userSettings.about.buildTime')">{{ buildTime
                    }}</el-descriptions-item>
                  <el-descriptions-item :label="t('userSettings.about.vueVersion')">{{ vueVersion
                    }}</el-descriptions-item>
                  <el-descriptions-item :label="t('userSettings.about.elementVersion')">{{ elementVersion
                    }}</el-descriptions-item>
                  <el-descriptions-item :label="t('userSettings.about.homepage')">
                    <a href="https://github.com/geluzhiwei1/davybot" target="_blank" class="github-link">
                      https://github.com/geluzhiwei1/davybot
                      <el-icon>
                        <Link />
                      </el-icon>
                    </a>
                  </el-descriptions-item>
                </el-descriptions>
              </template>
            </el-result>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, version as vueVersion, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, Link, Lock } from '@element-plus/icons-vue';
import elementPlusVersion from 'element-plus/package.json';
import SecuritySettingsTab from '@/components/user/SecuritySettingsTab.vue';
import type { UserSecuritySettings } from '@/services/api/types';
import { authService, type UserInfo } from '@/services/auth';

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const visible = ref(props.modelValue);
const activeTab = ref('profile');
const saving = ref(false);

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

const preferences = ref({
  theme: 'auto',
  fontSize: 14,
  messageDensity: 'comfortable',
  codeTheme: 'github-light',
  notificationsEnabled: true,
  autoSave: true
});

// 安全配置
const securitySettings = ref<UserSecuritySettings>({} as UserSecuritySettings);

const fontMarks = {
  12: '小',
  14: '中',
  16: '大',
  18: '超大',
  20: '特大'
};

const timezones = [
  { label: '亚洲/上海 (GMT+8)', value: 'Asia/Shanghai' },
  { label: '亚洲/东京 (GMT+9)', value: 'Asia/Tokyo' },
  { label: '欧洲/伦敦 (GMT+0)', value: 'Europe/London' },
  { label: '美国/纽约 (GMT-5)', value: 'America/New_York' },
  { label: '美国/洛杉矶 (GMT-8)', value: 'America/Los_Angeles' }
];

const defaultShortcuts = {
  'ctrl+k': { label: t('userSettings.shortcuts.quickSearch'), keys: ['Ctrl', 'K'] },
  'ctrl+n': { label: t('userSettings.shortcuts.newConversation'), keys: ['Ctrl', 'N'] },
  'ctrl+b': { label: t('userSettings.shortcuts.toggleSidePanel'), keys: ['Ctrl', 'B'] },
  'ctrl+shift+s': { label: t('userSettings.shortcuts.save'), keys: ['Ctrl', 'Shift', 'S'] },
  'ctrl+,': { label: t('userSettings.shortcuts.openSettings'), keys: ['Ctrl', ','] }
};

const buildTime = import.meta.env.VITE_BUILD_TIME || new Date().toISOString();
const elementVersion = elementPlusVersion.version;
const appVersion = import.meta.env.VITE_APP_VERSION || '0.0.0';

watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal) {
    loadSettings();
    checkAuthStatus(); // 打开时检查认证状态
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});

// 组件挂载和卸载时检查认证状态
onMounted(async () => {
  await checkAuthStatus();

  // 监听来自OAuth回调窗口的消息
  window.addEventListener('message', handleOAuthMessage);
});

onUnmounted(() => {
  authService.stopPolling();
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

const loadSettings = async () => {
  await Promise.all([
    loadUserProfile(),
    loadPreferences()
  ]);
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

const loadPreferences = async () => {
  try {
    const saved = localStorage.getItem('user-preferences');
    if (saved) {
      preferences.value = JSON.parse(saved);
    }
  } catch (error) {
    console.error('Failed to load preferences:', error);
  }
};

const savePreferences = async () => {
  saving.value = true;
  try {
    localStorage.setItem('user-preferences', JSON.stringify(preferences.value));
    ElMessage.success(t('userSettings.preferences.saveSuccess'));
    // 应用主题
    applyTheme();
  } catch (error) {
    ElMessage.error(t('common.saveFailed'));
    console.error('Failed to save preferences:', error);
  } finally {
    saving.value = false;
  }
};

const applyTheme = () => {
  const theme = preferences.value.theme;
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else if (theme === 'light') {
    document.documentElement.classList.remove('dark');
  } else {
    // auto - 跟随系统
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }
};

const resetShortcuts = () => {
  ElMessage.info(t('userSettings.shortcuts.resetSuccess'));
};

const handleSecuritySettingsUpdate = (value: UserSecuritySettings) => {
  securitySettings.value = value;
};

const handleClose = () => {
  visible.value = false;
};
</script>

<style scoped>
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

.user-settings-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.user-settings-drawer :deep(.el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.drawer-title {
  font-size: 18px;
  font-weight: 600;
}

.drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.settings-form {
  padding: 16px;
}

.shortcuts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.shortcut-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background-color: var(--el-fill-color-blank);
  border-radius: 6px;
}

.shortcut-label {
  font-weight: 500;
}

.shortcut-keys {
  display: flex;
  gap: 4px;
}

.shortcut-keys kbd {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  font-family: monospace;
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.1);
}

.about-section {
  padding: 16px;
}

.github-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--el-color-primary);
  text-decoration: none;
  word-break: break-all;
}

.github-link:hover {
  text-decoration: underline;
}
</style>
