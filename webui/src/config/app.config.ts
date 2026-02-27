/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 应用运行时配置
 *
 * 核心原则：
 * 1. 代码完全一致 - 不使用 import.meta.env.DEV/PROD 控制逻辑
 * 2. 配置驱动行为 - 所有差异通过环境变量配置
 * 3. 功能开关 - 使用运行时配置而非编译时检查
 *
 * 这样可以确保开发和生产环境使用完全相同的代码，
 * 仅通过环境变量配置实现不同的行为。
 */

export interface AppConfig {
  // 日志配置
  logging: {
    // 是否启用日志系统
    enabled: boolean
    // 日志级别: 'debug' | 'info' | 'warn' | 'error'
    level: 'debug' | 'info' | 'warn' | 'error'
    // 是否输出到浏览器控制台（即使被 tree-sharing，日志仍存储在内存）
    includeConsole: boolean
    // 内存中最大日志数量
    maxLogs: number
  }

  // API 配置
  api: {
    // 是否记录 HTTP 请求日志
    logRequests: boolean
    // 是否记录 HTTP 响应日志
    logResponses: boolean
    // 请求超时时间（毫秒）
    timeout: number
  }

  // 调试工具配置
  debug: {
    // 是否启用调试模式
    enabled: boolean
    // 是否暴露全局调试对象到 window
    exposeGlobal: boolean
  }

  // DevTools 配置
  devTools: {
    // 是否自动打开 DevTools（Tauri）
    autoOpen: boolean
  }

  // WebSocket 配置
  websocket: {
    // 是否启用 WebSocket 自动重连
    autoReconnect: boolean
    // 重连延迟（毫秒）
    reconnectDelay: number
    // 最大重连次数（0 = 无限）
    maxReconnectAttempts: number
  }
}

/**
 * 应用配置实例
 *
 * 所有环境变量配置在此集中管理，通过 VITE_ 前缀的环境变量注入。
 */
export const appConfig: AppConfig = {
  logging: {
    enabled: import.meta.env.VITE_LOGGING_ENABLED !== 'false',
    level: (import.meta.env.VITE_LOG_LEVEL as 'debug' | 'info' | 'warn' | 'error') || 'warn',
    includeConsole: import.meta.env.VITE_LOG_CONSOLE !== 'false',
    maxLogs: 100,
  },

  api: {
    logRequests: import.meta.env.VITE_API_LOG_REQUESTS === 'true',
    logResponses: import.meta.env.VITE_API_LOG_RESPONSES === 'true',
    timeout: 30000, // 30 秒
  },

  debug: {
    enabled: import.meta.env.VITE_DEBUG === 'true',
    exposeGlobal: import.meta.env.VITE_DEBUG_EXPOSE_GLOBAL === 'true',
  },

  devTools: {
    autoOpen: import.meta.env.VITE_DEVTOOLS_AUTO_OPEN === 'true',
  },

  websocket: {
    autoReconnect: import.meta.env.VITE_WS_AUTO_RECONNECT !== 'false',
    reconnectDelay: Number(import.meta.env.VITE_WS_RECONNECT_DELAY) || 3000,
    maxReconnectAttempts: Number(import.meta.env.VITE_WS_MAX_RECONNECT_ATTEMPTS) || 0,
  },
}

/**
 * 获取当前环境信息（只读，用于日志显示）
 */
export const environmentInfo = {
  mode: import.meta.env.MODE,
  isDev: import.meta.env.DEV,
  isProd: import.meta.env.PROD,
  baseUrl: import.meta.env.BASE_URL,
}

/**
 * 验证配置有效性
 */
export function validateConfig(): { valid: boolean; errors: string[] } {
  const errors: string[] = []

  // 验证日志级别
  const validLevels = ['debug', 'info', 'warn', 'error']
  if (!validLevels.includes(appConfig.logging.level)) {
    errors.push(`Invalid VITE_LOG_LEVEL: ${appConfig.logging.level}. Must be one of: ${validLevels.join(', ')}`)
  }

  // 验证超时时间
  if (appConfig.api.timeout < 1000) {
    errors.push(`VITE_API_TIMEOUT must be at least 1000ms, got: ${appConfig.api.timeout}`)
  }

  return {
    valid: errors.length === 0,
    errors,
  }
}

/**
 * 获取配置摘要（用于调试）
 */
export function getConfigSummary(): Record<string, unknown> {
  return {
    logging: {
      enabled: appConfig.logging.enabled,
      level: appConfig.logging.level,
      includeConsole: appConfig.logging.includeConsole,
    },
    api: {
      logRequests: appConfig.api.logRequests,
      logResponses: appConfig.api.logResponses,
    },
    debug: {
      enabled: appConfig.debug.enabled,
      exposeGlobal: appConfig.debug.exposeGlobal,
    },
    devTools: {
      autoOpen: appConfig.devTools.autoOpen,
    },
    environment: environmentInfo,
  }
}

// 开发环境：启动时验证配置
if (import.meta.env.DEV) {
  const validation = validateConfig()
  if (!validation.valid) {
    console.warn('[AppConfig] Configuration errors:', validation.errors)
  }

  // 开发环境：输出配置摘要
  console.log('[AppConfig] Configuration:', getConfigSummary())
}
