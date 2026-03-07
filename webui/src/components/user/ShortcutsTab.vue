/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="shortcuts-tab">
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
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';

const { t } = useI18n();

const defaultShortcuts = ref({
  'ctrl+k': { label: t('userSettings.shortcuts.quickSearch'), keys: ['Ctrl', 'K'] },
  'ctrl+n': { label: t('userSettings.shortcuts.newConversation'), keys: ['Ctrl', 'N'] },
  'ctrl+b': { label: t('userSettings.shortcuts.toggleSidePanel'), keys: ['Ctrl', 'B'] },
  'ctrl+shift+s': { label: t('userSettings.shortcuts.save'), keys: ['Ctrl', 'Shift', 'S'] },
  'ctrl+,': { label: t('userSettings.shortcuts.openSettings'), keys: ['Ctrl', ','] }
});

const resetShortcuts = () => {
  ElMessage.info(t('userSettings.shortcuts.resetSuccess'));
};
</script>

<style scoped lang="scss">
.shortcuts-tab {
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
}
</style>
