/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * useThemeCssVars composable
 * 提供CSS变量的响应式访问
 */

import { computed } from 'vue'
import { useTheme } from './useTheme'

/**
 * CSS变量访问Composable
 */
export function useThemeCssVars() {
  const { currentThemeConfig } = useTheme()

  // 颜色变量
  const colors = computed(() => currentThemeConfig.value.colors)

  // 字体变量
  const fonts = computed(() => currentThemeConfig.value.fonts)

  // 间距变量
  const spacing = computed(() => currentThemeConfig.value.spacing)

  // 圆角变量
  const borderRadius = computed(() => currentThemeConfig.value.borderRadius)

  // 阴影变量
  const shadow = computed(() => currentThemeConfig.value.shadow)

  // 动画变量
  const animation = computed(() => currentThemeConfig.value.animation)

  /**
   * 获取CSS变量值（用于内联样式）
   */
  function getCssVar(name: keyof ReturnType<typeof colors>): string {
    return `var(--theme-${kebabCase(name)})`
  }

  /**
   * 获取颜色CSS变量
   */
  const colorVars = computed(() => {
    const vars: Record<string, string> = {}
    Object.entries(colors.value).forEach(([key]) => {
      vars[key] = `var(--theme-${kebabCase(key)})`
    })
    return vars
  })

  /**
   * 获取字体CSS变量
   */
  const fontVars = computed(() => {
    const vars: Record<string, string> = {}
    vars.family = `var(--theme-font-family)`
    vars.familyMono = `var(--theme-font-family-mono)`
    Object.entries(fonts.value.size).forEach(([key]) => {
      vars[`fontSize-${key}`] = `var(--theme-font-size-${kebabCase(key)})`
    })
    Object.entries(fonts.value.weight).forEach(([key]) => {
      vars[`fontWeight-${key}`] = `var(--theme-font-weight-${kebabCase(key)})`
    })
    return vars
  })

  /**
   * 获取间距CSS变量
   */
  const spacingVars = computed(() => {
    const vars: Record<string, string> = {}
    Object.entries(spacing.value).forEach(([key]) => {
      vars[key] = `var(--theme-spacing-${kebabCase(key)})`
    })
    return vars
  })

  /**
   * 获取圆角CSS变量
   */
  const radiusVars = computed(() => {
    const vars: Record<string, string> = {}
    Object.entries(borderRadius.value).forEach(([key]) => {
      vars[key] = `var(--theme-radius-${kebabCase(key)})`
    })
    return vars
  })

  /**
   * 获取阴影CSS变量
   */
  const shadowVars = computed(() => {
    const vars: Record<string, string> = {}
    Object.entries(shadow.value).forEach(([key]) => {
      vars[key] = `var(--theme-shadow-${kebabCase(key)})`
    })
    return vars
  })

  /**
   * 驼峰命名转短横线命名
   */
  function kebabCase(str: string): string {
    return str.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '')
  }

  return {
    // 原始配置
    colors,
    fonts,
    spacing,
    borderRadius,
    shadow,
    animation,

    // CSS变量
    colorVars,
    fontVars,
    spacingVars,
    radiusVars,
    shadowVars,

    // 工具方法
    getCssVar,
  }
}

export default useThemeCssVars
