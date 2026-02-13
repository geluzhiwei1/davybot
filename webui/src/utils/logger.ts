/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 统一的日志管理器
 * 在开发环境显示所有日志，在生产环境只显示警告和错误
 * 开发环境默认禁用DEBUG日志以提升性能，可通过 VITE_DEBUG=true 启用
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  level: LogLevel
  timestamp: string
  message: string
  data?: unknown[]
}

class Logger {
  private isDev = import.meta.env.DEV
  private debugEnabled = import.meta.env.VITE_DEBUG === 'true'
  private logs: LogEntry[] = []
  private maxLogs = 100  // 减少内存占用

  private addLog(level: LogLevel, message: string, data?: unknown[]): void {
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
   * 调试级别日志 - 仅在 VITE_DEBUG=true 时显示
   */
  debug(...args: unknown[]): void {
    if (this.isDev && this.debugEnabled) {
      console.log('[DEBUG]', ...args)
      this.addLog('debug', args.join(' '), args)
    }
  }

  /**
   * 信息级别日志 - 只在 VITE_DEBUG=true 时显示
   */
  info(...args: unknown[]): void {
    if (this.debugEnabled) {
      console.log('[INFO]', ...args)
      this.addLog('info', args.join(' '), args)
    }
  }

  /**
   * 警告级别日志 - 始终显示
   */
  warn(...args: unknown[]): void {
    console.warn('[WARN]', ...args)
    this.addLog('warn', args.join(' '), args)
  }

  /**
   * 错误级别日志 - 始终显示
   */
  error(...args: unknown[]): void {
    console.error('[ERROR]', ...args)
    this.addLog('error', args.join(' '), args)
  }

  /**
   * 成功日志 - 只在 VITE_DEBUG=true 时显示
   */
  success(...args: unknown[]): void {
    if (this.isDev && this.debugEnabled) {
      console.log('%c[SUCCESS]', 'color: green; font-weight: bold', ...args)
      this.addLog('info', `[SUCCESS] ${args.join(' ')}`, args)
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
