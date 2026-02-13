/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 主题系统类型定义
 */

/**
 * 主题类型
 */
export type ThemeType = 'light' | 'dark'

/**
 * 颜色方案
 */
export interface ColorScheme {
  primary: string
  secondary: string
  accent: string
  success: string
  warning: string
  error: string
  info: string

  // 背景色
  bgPrimary: string
  bgSecondary: string
  bgTertiary: string
  bgTerminal: string

  // 文本色
  textPrimary: string
  textSecondary: string
  textTertiary: string
  textTerminal: string

  // 边框色
  border: string
  borderLight: string
  borderDark: string

  // 其他
  overlay: string
  divider: string
}

/**
 * 字体配置
 */
export interface FontConfig {
  family: string
  familyMono: string
  size: {
    xs: string
    sm: string
    md: string
    lg: string
    xl: string
  }
  weight: {
    normal: number
    medium: number
    bold: number
  }
}

/**
 * 间距配置
 */
export interface SpacingConfig {
  xs: string
  sm: string
  md: string
  lg: string
  xl: string
}

/**
 * 圆角配置
 */
export interface BorderRadiusConfig {
  none: string
  sm: string
  md: string
  lg: string
  full: string
}

/**
 * 阴影配置
 */
export interface ShadowConfig {
  none: string
  sm: string
  md: string
  lg: string
}

/**
 * 动画配置
 */
export interface AnimationConfig {
  enabled: boolean
  duration: {
    fast: string
    normal: string
    slow: string
  }
  easing: {
    linear: string
    ease: string
    'ease-in': string
    'ease-out': string
    'ease-in-out': string
  }
}

/**
 * 主题配置接口
 */
export interface ThemeConfig {
  id: ThemeType
  name: string
  description: string
  colors: ColorScheme
  fonts: FontConfig
  spacing: SpacingConfig
  borderRadius: BorderRadiusConfig
  shadow: ShadowConfig
  animation: AnimationConfig
  // 主题特定样式
  styles?: {
    // 消息气泡样式
    messageBubble?: {
      background?: string
      border?: string
      borderRadius?: string
      padding?: string
      boxShadow?: string
    }
    // 按钮样式
    button?: {
      borderRadius?: string
      padding?: string
      fontWeight?: number
    }
    // 输入框样式
    input?: {
      borderRadius?: string
      padding?: string
      fontSize?: string
    }
  }
}

/**
 * 主题元数据
 */
export interface ThemeMetadata {
  id: ThemeType
  name: string
  description: string
  icon: string
  preview?: string
  tags?: string[]
}

/**
 * 主题上下文值（用于依赖注入）
 */
export interface ThemeContextValue {
  theme: ThemeType
  themeConfig: ThemeConfig
  setTheme: (theme: ThemeType) => void
  toggleTheme: () => void
}

/**
 * CSS变量映射
 */
export type CSSVariableMap = Record<string, string>

/**
 * 主题切换事件
 */
export interface ThemeChangeEvent {
  from: ThemeType
  to: ThemeType
  timestamp: number
}
