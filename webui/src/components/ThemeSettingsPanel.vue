/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="theme-settings-panel">
    <div class="panel-header">
      <h3>主题设置</h3>
      <p class="panel-desc">选择界面主题风格</p>
    </div>

    <div class="theme-grid">
      <div
        v-for="theme in availableThemes"
        :key="theme.id"
        class="theme-card"
        :class="{ active: theme.id === currentTheme }"
        @click="selectTheme(theme.id)"
      >
        <div class="theme-card-header">
          <span class="theme-icon">{{ theme.icon }}</span>
          <span v-if="theme.id === currentTheme" class="theme-badge">当前</span>
        </div>

        <div class="theme-card-body">
          <h4 class="theme-name">{{ theme.name }}</h4>
          <p class="theme-description">{{ theme.description }}</p>

          <!-- 主题预览色板 -->
          <div class="theme-preview">
            <div
              v-for="(color, index) in getThemePreviewColors(theme.id)"
              :key="index"
              class="color-swatch"
              :style="{ backgroundColor: color }"
              :title="color"
            ></div>
          </div>

          <!-- 主题标签 -->
          <div v-if="theme.tags && theme.tags.length" class="theme-tags">
            <span v-for="tag in theme.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>

        <div class="theme-card-footer">
          <button
            class="select-btn"
            :class="{ primary: theme.id !== currentTheme }"
            @click.stop="selectTheme(theme.id)"
          >
            {{ theme.id === currentTheme ? '已应用' : '应用主题' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 主题切换统计 -->
    <div v-if="showStats" class="theme-stats">
      <div class="stats-header">
        <h4>主题切换统计</h4>
        <button @click="clearHistory" class="clear-btn">清除历史</button>
      </div>
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">切换次数</span>
          <span class="stat-value">{{ stats.count }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">当前主题</span>
          <span class="stat-value">{{ currentTheme.toUpperCase() }}</span>
        </div>
        <div class="stat-item" v-if="stats.lastSwitch">
          <span class="stat-label">上次切换</span>
          <span class="stat-value">{{ formatTime(stats.lastSwitch) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useTheme } from '@/themes/composables/useTheme'
import { useThemeStore } from '@/stores/themeStore'
import { themeMetadata, getThemeConfig } from '@/themes/themes'
import type { ThemeType } from '@/themes/types'

// Props
interface Props {
  showStats?: boolean
}

withDefaults(defineProps<Props>(), {
  showStats: false,
})

// 使用主题系统
const { currentTheme, setTheme } = useTheme()
const themeStore = useThemeStore()

// 获取可用主题列表
const availableThemes = computed(() => {
  return themeMetadata
})

// 获取主题切换统计
const stats = computed(() => {
  return themeStore.getSwitchStats()
})

/**
 * 选择主题
 */
function selectTheme(themeId: ThemeType): void {
  if (themeId !== currentTheme.value) {
    setTheme(themeId)
  }
}

/**
 * 获取主题预览颜色
 */
function getThemePreviewColors(themeId: ThemeType): string[] {
  const config = getThemeConfig(themeId)
  if (!config) return []

  return [
    config.colors.primary,
    config.colors.success,
    config.colors.warning,
    config.colors.error,
    config.colors.bgPrimary,
    config.colors.bgSecondary,
  ]
}

/**
 * 清除历史记录
 */
function clearHistory(): void {
  themeStore.clearHistory()
}

/**
 * 格式化时间
 */
function formatTime(date: Date): string {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  return date.toLocaleDateString()
}

onMounted(() => {
  // 初始化主题统计
  themeStore.getSwitchStats()
})
</script>

<style scoped>
.theme-settings-panel {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.panel-header {
  margin-bottom: 24px;
}

.panel-header h3 {
  margin: 0 0 8px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--theme-text-primary);
}

.panel-desc {
  margin: 0;
  font-size: 14px;
  color: var(--theme-text-secondary);
}

/* 主题网格 */
.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.theme-card {
  border: 2px solid var(--theme-border);
  background: var(--theme-bg-primary);
  border-radius: var(--theme-radius-lg);
  padding: 16px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.theme-card:hover {
  border-color: var(--theme-accent);
  box-shadow: var(--theme-shadow-md);
  transform: translateY(-2px);
}

.theme-card.active {
  border-color: var(--theme-accent);
  background: var(--theme-bg-secondary);
  box-shadow: var(--theme-shadow-md);
}

.theme-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.theme-icon {
  font-size: 32px;
  line-height: 1;
}

.theme-badge {
  padding: 4px 8px;
  background: var(--theme-success);
  color: #ffffff;
  font-size: 11px;
  font-weight: 600;
  border-radius: var(--theme-radius-sm);
}

.theme-card-body {
  margin-bottom: 16px;
}

.theme-name {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--theme-text-primary);
}

.theme-description {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--theme-text-secondary);
  line-height: 1.5;
}

/* 颜色预览 */
.theme-preview {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.color-swatch {
  width: 32px;
  height: 32px;
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  transition: transform 0.2s;
}

.color-swatch:hover {
  transform: scale(1.1);
}

/* 标签 */
.theme-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 3px 8px;
  background: var(--theme-bg-tertiary);
  color: var(--theme-text-secondary);
  font-size: 11px;
  border-radius: var(--theme-radius-sm);
  border: 1px solid var(--theme-border);
}

.theme-card-footer {
  display: flex;
  justify-content: flex-end;
}

.select-btn {
  padding: 6px 16px;
  border: 1px solid var(--theme-border);
  background: var(--theme-bg-primary);
  color: var(--theme-text-primary);
  font-size: 13px;
  border-radius: var(--theme-radius-md);
  cursor: pointer;
  transition: all 0.2s;
}

.select-btn:hover {
  background: var(--theme-bg-secondary);
  border-color: var(--theme-accent);
}

.select-btn.primary {
  background: var(--theme-accent);
  color: #ffffff;
  border-color: var(--theme-accent);
}

.select-btn.primary:hover {
  opacity: 0.9;
}

/* 统计信息 */
.theme-stats {
  padding: 16px;
  background: var(--theme-bg-secondary);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-md);
}

.stats-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stats-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--theme-text-primary);
}

.clear-btn {
  padding: 4px 8px;
  background: transparent;
  color: var(--theme-text-secondary);
  border: 1px solid var(--theme-border);
  border-radius: var(--theme-radius-sm);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: var(--theme-bg-tertiary);
  color: var(--theme-error);
  border-color: var(--theme-error);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 11px;
  color: var(--theme-text-secondary);
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--theme-text-primary);
}
</style>
