/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Theme management for CodeMirror editor
 */

import type { Extension } from '@codemirror/state'
import { oneDark } from '@codemirror/theme-one-dark'

export type ThemeType = 'light' | 'dark' | 'one-dark'

interface ThemeConfig {
  extension: Extension
  isDark: boolean
}

/**
 * Theme configurations with metadata
 */
const THEME_CONFIGS: Readonly<Record<ThemeType, ThemeConfig>> = Object.freeze({
  light: {
    extension: [],
    isDark: false,
  },
  dark: {
    extension: oneDark,
    isDark: true,
  },
  'one-dark': {
    extension: oneDark,
    isDark: true,
  },
})

/**
 * Get theme extension by type
 * @param theme - Theme identifier
 * @returns CodeMirror extension for the theme
 */
export function getTheme(theme: ThemeType = 'one-dark'): Extension {
  return THEME_CONFIGS[theme]?.extension ?? THEME_CONFIGS.light.extension
}

/**
 * Check if theme is dark
 * @param theme - Theme identifier
 */
export function isDarkTheme(theme: ThemeType): boolean {
  return THEME_CONFIGS[theme]?.isDark ?? false
}

/**
 * Get all available theme types
 */
export function getAvailableThemes(): ThemeType[] {
  return Object.keys(THEME_CONFIGS) as ThemeType[]
}

/**
 * Validate theme type
 */
export function isValidTheme(theme: string): theme is ThemeType {
  return theme in THEME_CONFIGS
}
