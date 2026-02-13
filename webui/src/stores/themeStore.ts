/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 主题管理Store
 * 使用Pinia进行状态管理
 */

import { defineStore } from 'pinia'
import { logger } from '@/utils/logger'

import { ref, computed } from 'vue'
import type { ThemeType, ThemeConfig } from '@/themes/types'
import { getThemeConfig, themes } from '@/themes/themes'

export const useThemeStore = defineStore('theme', () => {
  // ========== 状态 ==========

  /**
   * 当前主题ID
   */
  const currentTheme = ref<ThemeType>('light')

  /**
   * 主题切换历史
   */
  const themeHistory = ref<ThemeType[]>(['light'])

  /**
   * 主题切换次数
   */
  const switchCount = ref(0)

  /**
   * 最后切换时间
   */
  const lastSwitchTime = ref<Date | null>(null)

  // ========== 计算属性 ==========

  /**
   * 当前主题配置
   */
  const currentThemeConfig = computed<ThemeConfig>(() => {
    const config = getThemeConfig(currentTheme.value)
    return config || themes.light // 默认返回 light 主题
  })

  /**
   * 是否为浅色主题
   */
  const isLight = computed(() => currentTheme.value === 'light')

  /**
   * 是否为深色主题
   */
  const isDark = computed(() => currentTheme.value === 'dark')

  /**
   * 可用的主题列表
   */
  const availableThemes = computed(() => {
    return Object.entries(themes).map(([id, config]) => ({
      id: id as ThemeType,
      name: config.name,
      description: config.description,
    }))
  })

  // ========== 方法 ==========

  /**
   * 设置主题
   * @param themeId 主题ID
   * @param saveToStorage 是否保存到LocalStorage（默认true）
   */
  function setTheme(themeId: ThemeType, saveToStorage = true): void {
    // 验证主题是否存在
    if (!themes[themeId]) {
      logger.error(`[ThemeStore] Unknown theme: ${themeId}`)
      return
    }

    const previousTheme = currentTheme.value

    // 更新当前主题
    currentTheme.value = themeId

    // 更新历史记录
    if (themeHistory.value[themeHistory.value.length - 1] !== themeId) {
      themeHistory.value.push(themeId)
      // 只保留最近10条记录
      if (themeHistory.value.length > 10) {
        themeHistory.value.shift()
      }
    }

    // 更新切换统计
    if (previousTheme !== themeId) {
      switchCount.value++
      lastSwitchTime.value = new Date()
    }

    // 保存到LocalStorage
    if (saveToStorage) {
      try {
        localStorage.setItem('app-theme', themeId)
      } catch (error) {
        logger.error('[ThemeStore] Failed to save theme to localStorage:', error)
      }
    }

    // 触发主题切换事件
    window.dispatchEvent(new CustomEvent('theme-change', {
      detail: {
        from: previousTheme,
        to: themeId,
        timestamp: Date.now(),
      },
    }))
  }

  /**
   * 切换主题（Light ↔ Dark）
   */
  function toggleTheme(): void {
    const newTheme: ThemeType = isLight.value ? 'dark' : 'light'
    setTheme(newTheme)
  }

  /**
   * 初始化主题
   * 从LocalStorage读取保存的主题设置
   */
  function initializeTheme(): void {
    try {
      const savedTheme = localStorage.getItem('app-theme') as ThemeType | null
      const validThemes: ThemeType[] = ['light', 'dark']

      if (savedTheme && validThemes.includes(savedTheme)) {
        currentTheme.value = savedTheme
        themeHistory.value = [savedTheme]
      }
    } catch (error) {
      logger.error('[ThemeStore] Failed to load theme from localStorage:', error)
      // 保持默认主题
    }
  }

  /**
   * 重置主题为默认值
   */
  function resetTheme(): void {
    setTheme('light')
  }

  /**
   * 获取主题切换统计
   */
  function getSwitchStats() {
    return {
      count: switchCount.value,
      lastSwitch: lastSwitchTime.value,
      history: [...themeHistory.value],
    }
  }

  /**
   * 清除主题历史
   */
  function clearHistory(): void {
    themeHistory.value = [currentTheme.value]
    switchCount.value = 0
    lastSwitchTime.value = null
  }

  // ========== 返回 ==========

  return {
    // 状态
    currentTheme,
    themeHistory,
    switchCount,
    lastSwitchTime,

    // 计算属性
    currentThemeConfig,
    isLight,
    isDark,
    availableThemes,

    // 方法
    setTheme,
    toggleTheme,
    initializeTheme,
    resetTheme,
    getSwitchStats,
    clearHistory,
  }
})
