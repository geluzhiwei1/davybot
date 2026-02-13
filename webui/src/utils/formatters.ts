/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 统一的格式化工具集
 *
 * 消除代码库中重复的格式化逻辑，提供统一的API接口
 *
 * 注意：时间相关格式化已迁移到 @/utils/dateFormatter
 * 保留此文件是为了向后兼容，内部会调用新的 dayjs 实现
 */

import {
  formatTimestamp as formatDateTimestamp,
  formatDuration as formatDurationMs,
  formatRelativeTime as formatRelativeTimeMs,
} from './dateFormatter'
import i18nDefault from '@/i18n'

/**
 * 格式化时间戳为本地时间字符串
 *
 * @param timestamp ISO时间字符串或Date对象
 * @param format 格式化模式: 'full' | 'date' | 'time' | 'compact'
 * @returns 格式化后的时间字符串
 *
 * @deprecated 请直接使用 @/utils/dateFormatter 中的函数
 */
export function formatTimestamp(
  timestamp: string | Date,
  format: 'full' | 'date' | 'time' | 'compact' = 'full'
): string {
  try {
    // 映射到 dayjs 格式
    const formatMap: Record<string, string> = {
      'full': 'YYYY-MM-DD HH:mm:ss',
      'date': 'YYYY-MM-DD',
      'time': 'HH:mm:ss',
      'compact': 'HH:mm'
    }

    return formatDateTimestamp(timestamp, formatMap[format] || formatMap['full'])
  } catch (error) {
    console.warn('formatTimestamp error:', error)
    return String(timestamp)
  }
}

/**
 * 格式化时间间隔（毫秒）为可读字符串
 *
 * @param ms 时间间隔（毫秒）
 * @param precision 精度: 'standard' | 'detailed'
 * @returns 格式化后的时间间隔字符串
 *
 * @example
 * formatDuration(500) // '500ms'
 * formatDuration(1500) // '1.50s'
 * formatDuration(65000) // '1.08m'
 * formatDuration(65000, 'detailed') // '1m 5s'
 */
export function formatDuration(
  ms: number,
  precision: 'standard' | 'detailed' = 'standard'
): string {
  return formatDurationMs(ms, precision)
}

/**
 * 计算两个时间点之间的时间差（毫秒）
 *
 * @param startTime 开始时间
 * @param endTime 结束时间（默认为当前时间）
 * @returns 时间差（毫秒）
 *
 * @deprecated 请直接使用 @/utils/dateFormatter 中的 getTimeDifference
 */
export function getTimeDifference(
  startTime: string | Date,
  endTime?: string | Date
): number {
  try {
    const start = typeof startTime === 'string' ? new Date(startTime) : startTime
    const end = endTime
      ? (typeof endTime === 'string' ? new Date(endTime) : endTime)
      : new Date()

    return end.getTime() - start.getTime()
  } catch (error) {
    console.warn('getTimeDifference error:', error)
    return 0
  }
}

/**
 * 格式化文件大小
 *
 * @param bytes 文件大小（字节）
 * @returns 格式化后的文件大小字符串
 *
 * @example
 * formatFileSize(1024) // '1.00 KB'
 * formatFileSize(1048576) // '1.00 MB'
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes'

  try {
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))

    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
  } catch (error) {
    console.warn('formatFileSize error:', error)
    return `${bytes} Bytes`
  }
}

/**
 * 格式化数字（添加千分位分隔符）
 *
 * @param num 数字
 * @param decimals 小数位数
 * @returns 格式化后的数字字符串
 *
 * @example
 * formatNumber(1234567) // '1,234,567'
 * formatNumber(1234.5678, 2) // '1,234.57'
 */
export function formatNumber(num: number, decimals: number = 0): string {
  try {
    // 使用 i18n locale 而不是硬编码 'zh-CN'
    const locale = i18nDefault?.global?.locale?.value || 'zh-CN'
    return num.toLocaleString(locale, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    })
  } catch (error) {
    console.warn('formatNumber error:', error)
    return String(num)
  }
}

/**
 * 格式化百分比
 *
 * @param value 数值
 * @param total 总数
 * @param decimals 小数位数
 * @returns 格式化后的百分比字符串
 *
 * @example
 * formatPercentage(75, 100) // '75%'
 * formatPercentage(75, 100, 2) // '75.00%'
 */
export function formatPercentage(
  value: number,
  total: number,
  decimals: number = 0
): string {
  try {
    if (total === 0) return '0%'
    const percentage = (value / total) * 100
    return `${percentage.toFixed(decimals)}%`
  } catch (error) {
    console.warn('formatPercentage error:', error)
    return '0%'
  }
}

/**
 * 截断文本并添加省略号
 *
 * @param text 原文本
 * @param maxLength 最大长度
 * @returns 截断后的文本
 *
 * @example
 * truncateText('Hello World', 5) // 'Hello...'
 */
export function truncateText(text: string, maxLength: number): string {
  if (!text || text.length <= maxLength) return text
  return `${text.substring(0, maxLength)}...`
}

/**
 * 格式化相对时间（多久前）
 *
 * @param timestamp 时间戳
 * @returns 相对时间字符串
 *
 * @example
 * formatRelativeTime('2025-01-19T10:00:00') // '2小时前'（假设当前是12点）
 *
 * @deprecated 请直接使用 @/utils/dateFormatter 中的 formatRelativeTime
 */
export function formatRelativeTime(timestamp: string | Date): string {
  return formatRelativeTimeMs(timestamp)
}

/**
 * 格式化JSON字符串（美化输出）
 *
 * @param obj 对象或JSON字符串
 * @param space 缩进空格数
 * @returns 格式化后的JSON字符串
 */
export function formatJSON(obj: unknown, space: number = 2): string {
  try {
    if (typeof obj === 'string') {
      obj = JSON.parse(obj)
    }
    return JSON.stringify(obj, null, space)
  } catch (error) {
    console.warn('formatJSON error:', error)
    return String(obj)
  }
}

/**
 * 导出所有格式化函数
 */
export default {
  formatTimestamp,
  formatDuration,
  getTimeDifference,
  formatFileSize,
  formatNumber,
  formatPercentage,
  truncateText,
  formatRelativeTime,
  formatJSON,
}
