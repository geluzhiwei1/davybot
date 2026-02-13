/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * CSS变量生成器
 * 将主题配置转换为CSS变量
 */

import type { ThemeConfig, CSSVariableMap } from './types'

/**
 * 生成CSS变量映射
 */
export function generateCSSVariables(theme: ThemeConfig): CSSVariableMap {
  const variables: CSSVariableMap = {}

  // 颜色变量
  Object.entries(theme.colors).forEach(([key, value]) => {
    const cssVarName = `--theme-${kebabCase(key)}`
    variables[cssVarName] = value
  })

  // 字体变量
  variables['--theme-font-family'] = theme.fonts.family
  variables['--theme-font-family-mono'] = theme.fonts.familyMono
  Object.entries(theme.fonts.size).forEach(([key, value]) => {
    variables[`--theme-font-size-${kebabCase(key)}`] = value
  })
  Object.entries(theme.fonts.weight).forEach(([key, value]) => {
    variables[`--theme-font-weight-${kebabCase(key)}`] = String(value)
  })

  // 间距变量
  Object.entries(theme.spacing).forEach(([key, value]) => {
    variables[`--theme-spacing-${kebabCase(key)}`] = value
  })

  // 圆角变量
  Object.entries(theme.borderRadius).forEach(([key, value]) => {
    variables[`--theme-radius-${kebabCase(key)}`] = value
  })

  // 阴影变量
  Object.entries(theme.shadow).forEach(([key, value]) => {
    variables[`--theme-shadow-${kebabCase(key)}`] = value
  })

  // 动画变量
  variables['--theme-animation-enabled'] = theme.animation.enabled ? '1' : '0'
  Object.entries(theme.animation.duration).forEach(([key, value]) => {
    variables[`--theme-duration-${kebabCase(key)}`] = value
  })
  Object.entries(theme.animation.easing).forEach(([key, value]) => {
    variables[`--theme-easing-${kebabCase(key)}`] = value
  })

  return variables
}

/**
 * 生成CSS变量字符串（用于style标签）
 */
export function generateCSSVariablesString(theme: ThemeConfig): string {
  const variables = generateCSSVariables(theme)
  const cssVars = Object.entries(variables)
    .map(([key, value]) => `  ${key}: ${value};`)
    .join('\n')

  return `:root {\n${cssVars}\n}`
}

/**
 * 将CSS变量应用到DOM
 */
export function applyCSSVariables(theme: ThemeConfig, target: HTMLElement = document.documentElement): void {
  const variables = generateCSSVariables(theme)
  Object.entries(variables).forEach(([key, value]) => {
    target.style.setProperty(key, value)
  })
}

/**
 * 移除所有主题CSS变量
 */
export function removeCSSVariables(target: HTMLElement = document.documentElement): void {
  const variables = generateCSSVariables({
    // 使用任意主题获取变量名
    id: 'gui' as unknown,
    name: '',
    description: '',
    colors: {} as unknown,
    fonts: {} as unknown,
    spacing: {} as unknown,
    borderRadius: {} as unknown,
    shadow: {} as unknown,
    animation: {} as unknown,
  })

  Object.keys(variables).forEach(key => {
    target.style.removeProperty(key)
  })
}

/**
 * 驼峰命名转短横线命名
 */
function kebabCase(str: string): string {
  return str.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '')
}

/**
 * 生成主题类名
 */
export function generateThemeClass(themeId: string): string {
  return `theme-${themeId}`
}

/**
 * 生成主题特定的CSS
 */
export function generateThemeSpecificCSS(theme: ThemeConfig): string {
  const themeClass = generateThemeClass(theme.id)
  let css = `/* Theme: ${theme.name} */\n`
  css += `.${themeClass} {\n`

  // 添加主题特定的样式覆盖
  if (theme.styles?.messageBubble) {
    const bubble = theme.styles.messageBubble
    css += `  --message-bubble-bg: ${bubble.background || 'transparent'};\n`
    css += `  --message-bubble-border: ${bubble.border || 'none'};\n`
    css += `  --message-bubble-radius: ${bubble.borderRadius || '0'};\n`
    css += `  --message-bubble-padding: ${bubble.padding || '0'};\n`
    css += `  --message-bubble-shadow: ${bubble.boxShadow || 'none'};\n`
  }

  if (theme.styles?.button) {
    const button = theme.styles.button
    css += `  --button-radius: ${button.borderRadius || '0'};\n`
    css += `  --button-padding: ${button.padding || '0'};\n`
    css += `  --button-font-weight: ${button.fontWeight || 400};\n`
  }

  if (theme.styles?.input) {
    const input = theme.styles.input
    css += `  --input-radius: ${input.borderRadius || '0'};\n`
    css += `  --input-padding: ${input.padding || '0'};\n`
    css += `  --input-font-size: ${input.fontSize || '14px'};\n`
  }

  css += `}\n\n`

  return css
}

/**
 * 生成完整的主题CSS文件内容
 */
export function generateCompleteThemeCSS(theme: ThemeConfig): string {
  let css = `/* ========================================\n`
  css += `   Theme: ${theme.name}\n`
  css += `   ${theme.description}\n`
  css += `   ======================================== */\n\n`

  // CSS变量
  css += generateCSSVariablesString(theme)
  css += `\n\n`

  // 主题特定样式
  css += generateThemeSpecificCSS(theme)

  return css
}
