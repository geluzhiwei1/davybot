/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Light主题配置 - 浅色主题
 */

import type { ThemeConfig } from '../types'

export const lightTheme: ThemeConfig = {
  id: 'light',
  name: 'Light',
  description: '明亮主题 - 清爽明亮',

  // 浅色配色方案
  colors: {
    primary: '#409EFF',
    secondary: '#79bbff',
    accent: '#409EFF',
    success: '#67C23A',
    warning: '#E6A23C',
    error: '#F56C6C',
    info: '#909399',

    // 背景色 - 浅色
    bgPrimary: '#FFFFFF',
    bgSecondary: '#F5F7FA',
    bgTertiary: '#FAFAFA',
    bgTerminal: '#282C34',

    // 文本色 - 深色
    textPrimary: '#303133',
    textSecondary: '#606266',
    textTertiary: '#909399',
    textTerminal: '#ABB2BF',

    // 边框色
    border: '#DCDFE6',
    borderLight: '#E4E7ED',
    borderDark: '#D4D7DE',

    // 其他
    overlay: 'rgba(0, 0, 0, 0.5)',
    divider: '#DCDFE6',
  },

  // 字体配置
  fonts: {
    family: '"Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "微软雅黑", Arial, sans-serif',
    familyMono: '"Consolas", "Monaco", "Courier New", monospace',
    size: {
      xs: '12px',
      sm: '13px',
      md: '14px',
      lg: '16px',
      xl: '18px',
    },
    weight: {
      normal: 400,
      medium: 500,
      bold: 700,
    },
  },

  // 间距配置
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
  },

  // 圆角配置
  borderRadius: {
    none: '0',
    sm: '2px',
    md: '4px',
    lg: '8px',
    full: '9999px',
  },

  // 阴影配置
  shadow: {
    none: 'none',
    sm: '0 2px 4px rgba(0, 0, 0, 0.12)',
    md: '0 4px 8px rgba(0, 0, 0, 0.12)',
    lg: '0 8px 16px rgba(0, 0, 0, 0.12)',
  },

  // 动画配置
  animation: {
    enabled: true,
    duration: {
      fast: '150ms',
      normal: '300ms',
      slow: '500ms',
    },
    easing: {
      linear: 'linear',
      ease: 'ease',
      'ease-in': 'ease-in',
      'ease-out': 'ease-out',
      'ease-in-out': 'ease-in-out',
    },
  },

  // Light特定样式
  styles: {
    messageBubble: {
      background: '#FFFFFF',
      border: '1px solid #DCDFE6',
      borderRadius: '8px',
      padding: '12px 16px',
      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)',
    },
    button: {
      borderRadius: '4px',
      padding: '8px 16px',
      fontWeight: 500,
    },
    input: {
      borderRadius: '4px',
      padding: '8px 12px',
      fontSize: '14px',
    },
  },
}
