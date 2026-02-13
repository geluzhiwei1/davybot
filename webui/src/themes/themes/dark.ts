/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Dark主题配置 - 深色主题
 */

import type { ThemeConfig } from '../types'

export const darkTheme: ThemeConfig = {
  id: 'dark',
  name: 'Dark',
  description: '深色主题 - 护眼舒适',

  // 深色配色方案 - Premium Tech Dark
  colors: {
    primary: '#14B8A6',        // Luminous teal
    secondary: '#2DD4BF',      // Lighter teal
    accent: '#F59E0B',         // Warm amber accent
    success: '#10B981',        // Green optimized for dark
    warning: '#F59E0B',        // Amber
    error: '#EF4444',          // Red optimized for dark
    info: '#3B82F6',           // Blue optimized for dark

    // 背景色 - Rich layered darks
    bgPrimary: '#0A0E1A',      // Deepest background
    bgSecondary: '#111827',    // Main surfaces
    bgTertiary: '#1F2937',     // Elevated panels
    bgTerminal: '#0D1117',     // Terminal/code background

    // 文本色 - Luminous, high contrast
    textPrimary: '#F3F4F6',    // Bright white-gray
    textSecondary: '#D1D5DB',  // Medium gray
    textTertiary: '#9CA3AF',   // Muted gray
    textTerminal: '#E5E7EB',   // Code text

    // 边框色 - Crisp separation
    border: '#1F2937',         // Default border
    borderLight: '#374151',    // Light border
    borderDark: '#4B5563',     // Dark border

    // 其他
    overlay: 'rgba(0, 0, 0, 0.75)',
    divider: '#1F2937',
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

  // 阴影配置 - 深色模式用更强的阴影增强层次
  shadow: {
    none: 'none',
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.4)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.5), 0 2px 4px -1px rgba(0, 0, 0, 0.3)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -2px rgba(0, 0, 0, 0.4)',
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

  // Dark特定样式 - Premium aesthetic
  styles: {
    messageBubble: {
      background: '#1F2937',
      border: '1px solid #374151',
      borderRadius: '12px',
      padding: '14px 18px',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.05)',
    },
    button: {
      borderRadius: '8px',
      padding: '10px 18px',
      fontWeight: 500,
    },
    input: {
      borderRadius: '8px',
      padding: '10px 14px',
      fontSize: '14px',
    },
  },
}
