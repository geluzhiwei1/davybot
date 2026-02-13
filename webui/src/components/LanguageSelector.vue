/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="language-selector-wrapper">
    <el-dropdown trigger="click" @command="selectLanguage" @visible-change="handleDropdownVisible">
      <el-button
        class="language-selector-btn"
        :title="`当前语言: ${currentLanguageLabel} - 点击切换`"
        :icon="ChatDotRound"
        text
        circle
      />
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="lang in languages"
            :key="lang.value"
            :command="lang.value"
            :class="{ 'is-selected': currentLanguage === lang.value }"
          >
            <div class="lang-item-content">
              <span class="lang-label">{{ lang.label }}</span>
              <el-icon v-if="currentLanguage === lang.value" class="check-icon">
                <Check />
              </el-icon>
            </div>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ChatDotRound, Check } from '@element-plus/icons-vue'

interface Language {
  value: string;
  label: string;
}

// 支持的语言列表
const languages: Language[] = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'en-US', label: 'English' },
];

const currentLanguage = ref('zh-CN');

// 当前语言的标签
const currentLanguageLabel = computed(() => {
  const lang = languages.find(l => l.value === currentLanguage.value);
  return lang?.label || 'Language';
});

// 加载保存的语言设置
onMounted(() => {
  const savedLang = localStorage.getItem('user-language') || 'zh-CN';
  currentLanguage.value = savedLang;
});

// 监听语言变化
watch(currentLanguage, (newLang) => {
  localStorage.setItem('user-language', newLang);

  // 触发语言变化事件（可以在这里添加i18n逻辑）
  console.log('Language changed to:', newLang);
});

// 选择语言
const selectLanguage = (langValue: string) => {
  currentLanguage.value = langValue;
};

// 处理下拉菜单显示/隐藏
const handleDropdownVisible = (visible: boolean) => {
  console.log('Dropdown visible:', visible);
};

// 暴露方法给父组件
defineExpose({
  currentLanguage,
  selectLanguage,
});
</script>

<style scoped>
.language-selector-wrapper {
  display: inline-block;
}

.language-selector-btn {
  font-size: 18px;
}

/* 下拉菜单项样式 */
.lang-item-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.lang-label {
  flex: 1;
  font-size: 14px;
}

.check-icon {
  margin-left: 8px;
  font-size: 16px;
  color: var(--el-color-primary);
}

/* 选中状态 */
.el-dropdown-item.is-selected {
  color: var(--el-color-primary);
  font-weight: 500;
}
</style>
