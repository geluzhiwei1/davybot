/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { appConfig } from '@/config/app.config'

/**
 * 统一的日志管理器
 *
 * 设计原则：
 * 1. 代码完全一致 - 不使用 import.meta.env.DEV/PROD 控制逻辑
 * 2. 配置驱动行为 - 所有差异通过环境变量配置
 * 3. 始终存储日志 - 即使控制台输出被 tree-sharing，日志仍保存在内存
 *
 * 日志级别优先级：debug < info < warn < error
 * 例如：level='warn' 时，只输出 warn 和 error，忽略 debug 和 info
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  level: LogLevel
  timestamp: string
  message: string
  data?: unknown[]
}

// 日志级别优先级映射（数字越大优先级越高）
const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
}

class Logger {
  private logs: LogEntry[] = []
  private maxLogs: number

  constructor() {
    this.maxLogs = appConfig.logging.maxLogs
  }

  private addLog(level: LogLevel, message: string, data?: unknown[]): void {
    if (!appConfig.logging.enabled) {
      return
    }

    const entry: LogEntry = {
      level,
      timestamp: new Date().toISOString(),
      message,
      data
    }

    // 保留最近的日志
    this.logs.push(entry)
    if (this.logs.length > this.maxLogs) {
      this.logs.shift()
    }
  }

  /**
   * 判断是否应该输出日志
   */
  private shouldLog(level: LogLevel): boolean {
    const currentPriority = LOG_LEVEL_PRIORITY[level]
    const configPriority = LOG_LEVEL_PRIORITY[appConfig.logging.level]
    return currentPriority >= configPriority
  }

  /**
   * 输出到控制台（可能被 tree-sharing 删除，但日志仍存储在内存）
   */
  private logToConsole(level: LogLevel, args: unknown[]): void {
    if (!appConfig.logging.includeConsole) {
      return
    }

    // 尝试输出到 console（可能被 tree-sharing 删除）
    try {
      switch (level) {
        case 'debug':
          console.log('[DEBUG]', ...args)
          break
        case 'info':
          console.log('[INFO]', ...args)
          break
        case 'warn':
          console.warn('[WARN]', ...args)
          break
        case 'error':
          console.error('[ERROR]', ...args)
          break
      }
    } catch {
      // console 可能不可用（如某些受限环境），忽略错误
    }
  }

  /**
   * 调试级别日志
   * 用于详细的调试信息，通常仅在开发环境使用
   */
  debug(...args: unknown[]): void {
    if (this.shouldLog('debug')) {
      this.addLog('debug', args.join(' '), args)
      this.logToConsole('debug', args)
    }
  }

  /**
   * 信息级别日志
   * 用于一般的信息输出
   */
  info(...args: unknown[]): void {
    if (this.shouldLog('info')) {
      this.addLog('info', args.join(' '), args)
      this.logToConsole('info', args)
    }
  }

  /**
   * 警告级别日志
   * 用于警告信息，生产环境默认启用
   */
  warn(...args: unknown[]): void {
    if (this.shouldLog('warn')) {
      const message = '[WARN] ' + args.map(arg =>
        typeof arg === 'string' ? arg : JSON.stringify(arg)
      ).join(' ')
      this.addLog('warn', message, args)
      this.logToConsole('warn', args)
    }
  }

  /**
   * 错误级别日志
   * 用于错误信息，所有环境默认启用
   */
  error(...args: unknown[]): void {
    if (this.shouldLog('error')) {
      const message = '[ERROR] ' + args.map(arg =>
        typeof arg === 'string' ? arg : JSON.stringify(arg)
      ).join(' ')
      this.addLog('error', message, args)
      this.logToConsole('error', args)
    }
  }

  /**
   * 成功日志
   * 用于操作成功的提示
   */
  success(...args: unknown[]): void {
    if (this.shouldLog('info')) {
      this.addLog('info', `[SUCCESS] ${args.join(' ')}`, args)

      if (appConfig.logging.includeConsole) {
        try {
          console.log('%c[SUCCESS]', 'color: green; font-weight: bold', ...args)
        } catch {
          // console 可能不可用
        }
      }
    }
  }

  /**
   * 获取所有日志记录
   */
  getLogs(): LogEntry[] {
    return [...this.logs]
  }

  /**
   * 清空日志记录
   */
  clearLogs(): void {
    this.logs = []
  }

  /**
   * 导出日志为 JSON
   */
  exportLogs(): string {
    return JSON.stringify(this.logs, null, 2)
  }

  /**
   * 分组日志
   */
  group(label: string): void {
    if (this.isDev) {
      console.group(label)
    }
  }

  /**
   * 分组结束
   */
  groupEnd(): void {
    if (this.isDev) {
      console.groupEnd()
    }
  }

  /**
   * 表格形式显示日志
   */
  table(data: unknown): void {
    if (this.isDev) {
      console.table(data)
    }
  }

  /**
   * 性能测量开始
   */
  time(label: string): void {
    if (this.isDev) {
      console.time(label)
    }
  }

  /**
   * 性能测量结束
   */
  timeEnd(label: string): void {
    if (this.isDev) {
      console.timeEnd(label)
    }
  }
}

// 导出单例
export const logger = new Logger()

// 导出类型
export type { LogLevel, LogEntry }
