/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-drawer
    v-model="visible"
    title="用户设置"
    direction="rtl"
    :size="500"
    class="user-settings-drawer"
    @close="handleClose"
  >
    <template #header>
      <div class="drawer-header">
        <el-icon :size="20"><User /></el-icon>
        <span class="drawer-title">用户设置</span>
      </div>
    </template>

    <div class="drawer-content">
      <el-tabs v-model="activeTab" type="border-card">
        <!-- 个人信息 Tab -->
        <el-tab-pane label="个人信息" name="profile">
          <el-form :model="userProfile" label-width="120px" class="settings-form">
            <el-form-item label="用户名">
              <el-input v-model="userProfile.username" placeholder="请输入用户名" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="userProfile.email" placeholder="请输入邮箱" />
            </el-form-item>
            <el-form-item label="个人简介">
              <el-input
                v-model="userProfile.bio"
                type="textarea"
                :rows="3"
                placeholder="请输入个人简介"
              />
            </el-form-item>
            <el-form-item label="时区">
              <el-select v-model="userProfile.timezone" placeholder="选择时区" filterable>
                <el-option
                  v-for="tz in timezones"
                  :key="tz.value"
                  :label="tz.label"
                  :value="tz.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="语言">
              <el-select v-model="userProfile.language" placeholder="选择语言">
                <el-option label="简体中文" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveUserProfile" :loading="saving">
                保存个人信息
              </el-button>
              <el-button @click="loadUserProfile">刷新</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 偏好设置 Tab -->
        <el-tab-pane label="偏好设置" name="preferences">
          <el-form :model="preferences" label-width="140px" class="settings-form">
            <el-form-item label="主题">
              <el-radio-group v-model="preferences.theme">
                <el-radio value="light">浅色</el-radio>
                <el-radio value="dark">深色</el-radio>
                <el-radio value="auto">跟随系统</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="字体大小">
              <el-slider v-model="preferences.fontSize" :min="12" :max="20" :marks="fontMarks" />
            </el-form-item>
            <el-form-item label="消息显示密度">
              <el-radio-group v-model="preferences.messageDensity">
                <el-radio value="comfortable">舒适</el-radio>
                <el-radio value="compact">紧凑</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="代码主题">
              <el-select v-model="preferences.codeTheme" placeholder="选择代码主题">
                <el-option label="GitHub Light" value="github-light" />
                <el-option label="GitHub Dark" value="github-dark" />
                <el-option label="Monokai" value="monokai" />
                <el-option label="VS Code Dark" value="vscode-dark" />
              </el-select>
            </el-form-item>
            <el-form-item label="启用通知">
              <el-switch v-model="preferences.notificationsEnabled" />
            </el-form-item>
            <el-form-item label="自动保存">
              <el-switch v-model="preferences.autoSave" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="savePreferences" :loading="saving">
                保存偏好设置
              </el-button>
              <el-button @click="loadPreferences">刷新</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 快捷键 Tab -->
        <el-tab-pane label="快捷键" name="shortcuts">
          <div class="shortcuts-list">
            <div v-for="(shortcut, key) in defaultShortcuts" :key="key" class="shortcut-item">
              <div class="shortcut-label">{{ shortcut.label }}</div>
              <div class="shortcut-keys">
                <kbd v-for="k in shortcut.keys" :key="k">{{ k }}</kbd>
              </div>
            </div>
          </div>
          <el-divider />
          <el-form-item label="自定义快捷键">
            <el-button @click="resetShortcuts">恢复默认快捷键</el-button>
          </el-form-item>
        </el-tab-pane>

        <!-- 关于 Tab -->
        <el-tab-pane label="关于" name="about">
          <div class="about-section">
            <el-result icon="success" title="大微" sub-title="通用 AI 助手">
              <template #extra>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="版本">v1.0.0</el-descriptions-item>
                  <el-descriptions-item label="构建时间">{{ buildTime }}</el-descriptions-item>
                  <el-descriptions-item label="Vue版本">{{ vueVersion }}</el-descriptions-item>
                  <el-descriptions-item label="Element版本">{{ elementVersion }}</el-descriptions-item>
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
import { ref, watch, version as vueVersion } from 'vue';
import { ElMessage } from 'element-plus';
import { User } from '@element-plus/icons-vue';
import elementPlusVersion from 'element-plus/package.json';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

const visible = ref(props.modelValue);
const activeTab = ref('profile');
const saving = ref(false);

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
  'ctrl+k': { label: '快速搜索', keys: ['Ctrl', 'K'] },
  'ctrl+n': { label: '新建会话', keys: ['Ctrl', 'N'] },
  'ctrl+b': { label: '切换侧边栏', keys: ['Ctrl', 'B'] },
  'ctrl+shift+s': { label: '保存', keys: ['Ctrl', 'Shift', 'S'] },
  'ctrl+,': { label: '打开设置', keys: ['Ctrl', ','] }
};

const buildTime = import.meta.env.VITE_BUILD_TIME || new Date().toISOString();
const elementVersion = elementPlusVersion.version;

watch(() => props.modelValue, (newVal) => {
  visible.value = newVal;
  if (newVal) {
    loadSettings();
  }
});

watch(visible, (newVal) => {
  emit('update:modelValue', newVal);
});

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
    ElMessage.success('个人信息保存成功');
  } catch (error) {
    ElMessage.error('保存失败');
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
    ElMessage.success('偏好设置保存成功');
    // 应用主题
    applyTheme();
  } catch (error) {
    ElMessage.error('保存失败');
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
  ElMessage.info('快捷键已重置为默认值');
};

const handleClose = () => {
  visible.value = false;
};
</script>

<style scoped>
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
</style>
