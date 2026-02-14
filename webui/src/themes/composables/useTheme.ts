/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * useTheme composable
 * 提供主题切换和管理的核心功能
 */

import { computed, watch } from 'vue'
import { useThemeStore } from '@/stores/themeStore'
import type { ThemeType, ThemeConfig } from '../types'
import { applyCSSVariables } from '../generator'

const STORAGE_KEY = 'app-theme'

/**
 * 主题管理Composable
 */
export function useTheme() {
  const themeStore = useThemeStore()

  // 当前主题ID
  const currentTheme = computed<ThemeType>(() => themeStore.currentTheme)

  // 当前主题配置
  const currentThemeConfig = computed<ThemeConfig>(() => themeStore.currentThemeConfig)

  // 是否为浅色主题
  const isLight = computed(() => currentTheme.value === 'light')

  // 是否为深色主题
  const isDark = computed(() => currentTheme.value === 'dark')

  /**
   * 设置主题
   */
  function setTheme(themeId: ThemeType): void {
    themeStore.setTheme(themeId)
  }

  /**
   * 切换主题（Light ↔ Dark）
   */
  function toggleTheme(): void {
    const newTheme: ThemeType = currentTheme.value === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
  }

  /**
   * 应用主题CSS变量到DOM
   */
  function applyThemeToDOM(): void {
    applyCSSVariables(currentThemeConfig.value)
  }

  /**
   * 初始化主题
   * - 从LocalStorage读取保存的主题
   * - 应用CSS变量到DOM
   * - 添加主题class到body
   */
  function initTheme(): void {
    // 从LocalStorage读取
    const savedTheme = localStorage.getItem(STORAGE_KEY) as ThemeType | null
    const validThemes: ThemeType[] = ['light', 'dark']

    if (savedTheme && validThemes.includes(savedTheme)) {
      themeStore.setTheme(savedTheme, false) // false = 不重复保存
    } else {
      // 使用默认主题
      themeStore.setTheme('light', false)
    }

    // 应用主题到DOM
    applyThemeToDOM()

    // 添加主题class到body
    updateBodyClass()

    // 监听主题变化
    watch(
      () => themeStore.currentTheme,
      (newTheme, oldTheme) => {
        applyThemeToDOM()
        updateBodyClass()
        localStorage.setItem(STORAGE_KEY, newTheme)
      },
      { immediate: false }
    )
  }

  /**
   * 更新body的class和data属性
   */
  function updateBodyClass(): void {
    const body = document.body
    const html = document.documentElement

    // 移除所有主题class
    body.classList.remove('theme-light', 'theme-dark')

    // 添加当前主题class到body
    body.classList.add(`theme-${currentTheme.value}`)

    // 同时更新html元素的class（用于Element Plus暗色模式）
    if (currentTheme.value === 'dark') {
      html.classList.add('dark')
      html.setAttribute('data-theme', 'dark')
    } else {
      html.classList.remove('dark')
      html.setAttribute('data-theme', 'light')
    }
  }

  return {
    // 状态
    currentTheme,
    currentThemeConfig,
    isLight,
    isDark,

    // 方法
    setTheme,
    toggleTheme,
    applyThemeToDOM,
    initTheme,
    updateBodyClass,
  }
}

export default useTheme
