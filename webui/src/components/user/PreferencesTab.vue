/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="preferences-tab">
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';

const { t } = useI18n();

const preferences = ref({
  theme: 'auto',
  fontSize: 14,
  messageDensity: 'comfortable',
  codeTheme: 'github-light',
  notificationsEnabled: true,
  autoSave: true
});

const saving = ref(false);

const fontMarks = {
  12: '小',
  14: '中',
  16: '大',
  18: '超大',
  20: '特大'
};

onMounted(() => {
  loadPreferences();
  applyTheme();
});

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
</script>

<style scoped lang="scss">
.preferences-tab {
  .settings-form {
    padding: 16px;
  }
}
</style>
