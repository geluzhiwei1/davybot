/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 主题列表导出
 */

import type { ThemeConfig, ThemeMetadata } from '../types'
import { lightTheme } from './light'
import { darkTheme } from './dark'

/**
 * 所有可用主题配置
 */
export const themes: Record<string, ThemeConfig> = {
  light: lightTheme,
  dark: darkTheme,
}

/**
 * 所有主题元数据
 */
export const themeMetadata: ThemeMetadata[] = [
  {
    id: 'light',
    name: 'Light',
    description: '明亮主题 - 清爽明亮',
    icon: '☀️',
    tags: ['light', 'bright', 'clean'],
  },
  {
    id: 'dark',
    name: 'Dark',
    description: '深色主题 - 护眼舒适',
    icon: '🌙',
    tags: ['dark', 'comfortable', 'eye-care'],
  },
]

/**
 * 获取主题配置
 */
export function getThemeConfig(themeId: string): ThemeConfig | undefined {
  return themes[themeId]
}

/**
 * 获取所有可用的主题ID
 */
export function getAvailableThemeIds(): string[] {
  return Object.keys(themes)
}

/**
 * 获取默认主题
 */
export function getDefaultTheme(): string {
  return 'light' // 默认使用浅色主题
}
