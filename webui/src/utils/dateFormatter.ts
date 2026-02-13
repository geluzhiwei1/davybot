/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 国际化日期格式化工具
 *
 * 基于 dayjs 实现完整的时区和多语言支持
 * 解决原有硬编码中文 locale 的问题
 */

import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import relativeTime from 'dayjs/plugin/relativeTime'
import type { Dayjs } from 'dayjs'

// 导入语言包
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'
import 'dayjs/locale/ko'
import 'dayjs/locale/de'
import 'dayjs/locale/fr'
import 'dayjs/locale/es'

import i18nDefault from '@/i18n'

// 扩展 dayjs 插件
dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)

/**
 * 语言映射表
 * 将 i18n locale 映射到 dayjs locale
 */
const LOCALE_MAP: Record<string, string> = {
  'zh-CN': 'zh-cn',
  'en': 'en',
  'ko': 'ko',
  'de': 'de',
  'fr': 'fr',
  'es': 'es',
}

/**
 * 获取当前 dayjs locale
 */
function getDayjsLocale(): string {
  const currentLocale = i18nDefault?.global?.locale?.value || 'zh-CN'
  return LOCALE_MAP[currentLocale] || 'en'
}

/**
 * 初始化 dayjs locale
 * 在 i18n locale 改变时自动更新
 */
export function initDayjsLocale() {
  const locale = getDayjsLocale()
  dayjs.locale(locale)

  // 配置相对时间文本（中文需要手动配置）
  if (locale === 'zh-cn') {
    dayjs.locale('zh-cn', {
      relativeTime: {
        future: '%s后',
        past: '%s前',
        s: '几秒',
        m: '1分钟',
        mm: '%d分钟',
        h: '1小时',
        hh: '%d小时',
        d: '1天',
        dd: '%d天',
        M: '1个月',
        MM: '%d个月',
        y: '1年',
        yy: '%d年',
      },
    })
  }
}

// 初始化时设置一次
initDayjsLocale()

/**
 * 时区管理
 */
export class TimezoneManager {
  private static userTimezone: string | null = null

  /**
   * 获取用户时区
   * 优先级：用户设置 > 自动检测 > UTC
   */
  static getUserTimezone(): string {
    if (this.userTimezone) {
      return this.userTimezone
    }

    // 从 localStorage 读取用户设置的时区
    const savedTimezone = localStorage.getItem('user_timezone')
    if (savedTimezone) {
      this.userTimezone = savedTimezone
      return savedTimezone
    }

    // 自动检测时区
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
      if (detected) {
        this.userTimezone = detected
        return detected
      }
    } catch (error) {
      console.warn('Failed to detect timezone:', error)
    }

    // 默认 UTC
    return 'UTC'
  }

  /**
   * 设置用户时区
   */
  static setUserTimezone(timezone: string): void {
    this.userTimezone = timezone
    localStorage.setItem('user_timezone', timezone)
  }

  /**
   * 重置时区为自动检测
   */
  static resetTimezone(): void {
    this.userTimezone = null
    localStorage.removeItem('user_timezone')
  }

  /**
   * 获取所有可用时区列表（常用）
   */
  static getCommonTimezones(): Array<{ value: string; label: string; offset: string }> {
    const commonTimezones = [
      'UTC',
      'Asia/Shanghai',
      'Asia/Seoul',
      'Europe/London',
      'Europe/Paris',
      'Europe/Berlin',
      'America/New_York',
      'America/Los_Angeles',
      'America/Chicago',
      'Australia/Sydney',
    ]

    return commonTimezones.map(tz => {
      const offset = dayjs().tz(tz).format('Z')
      return {
        value: tz,
        label: tz.replace('_', ' '),
        offset: `UTC${offset}`,
      }
    })
  }
}

/**
 * 格式化时间戳为本地时间字符串
 *
 * @param timestamp ISO时间字符串或Date对象
 * @param format 格式化模板（dayjs 格式）
 * @param timezone 指定时区（可选，默认使用用户时区）
 * @returns 格式化后的时间字符串
 *
 * @example
 * formatTimestamp('2025-02-12T10:00:00Z') // '2025-02-12 18:00:00' (北京时间)
 * formatTimestamp('2025-02-12T10:00:00Z', 'YYYY-MM-DD') // '2025-02-12'
 * formatTimestamp('2025-02-12T10:00:00Z', 'HH:mm', 'America/New_York')
 */
export function formatTimestamp(
  timestamp: string | Date | Dayjs,
  format: string = 'YYYY-MM-DD HH:mm:ss',
  timezone?: string
): string {
  try {
    const userTimezone = timezone || TimezoneManager.getUserTimezone()
    const date = dayjs(timestamp)

    // 确保使用当前 locale
    initDayjsLocale()

    return date.tz(userTimezone).format(format)
  } catch (error) {
    console.warn('formatTimestamp error:', error)
    return String(timestamp)
  }
}

/**
 * 格式化时间戳为简短格式
 *
 * @param timestamp 时间戳
 * @param timezone 时区（可选）
 * @returns 格式化后的时间字符串
 */
export function formatTime(timestamp: string | Date, timezone?: string): string {
  return formatTimestamp(timestamp, 'HH:mm:ss', timezone)
}

/**
 * 格式化日期
 *
 * @param timestamp 时间戳
 * @param timezone 时区（可选）
 * @returns 格式化后的日期字符串
 */
export function formatDate(timestamp: string | Date, timezone?: string): string {
  return formatTimestamp(timestamp, 'YYYY-MM-DD', timezone)
}

/**
 * 格式化紧凑时间（只有小时和分钟）
 *
 * @param timestamp 时间戳
 * @param timezone 时区（可选）
 * @returns 格式化后的时间字符串
 */
export function formatCompactTime(timestamp: string | Date, timezone?: string): string {
  return formatTimestamp(timestamp, 'HH:mm', timezone)
}

/**
 * 格式化完整日期时间
 *
 * @param timestamp 时间戳
 * @param timezone 时区（可选）
 * @returns 格式化后的日期时间字符串
 */
export function formatFullDateTime(timestamp: string | Date, timezone?: string): string {
  return formatTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss', timezone)
}

/**
 * 格式化相对时间（多久前/多久后）
 *
 * @param timestamp 时间戳
 * @returns 相对时间字符串
 *
 * @example
 * formatRelativeTime('2025-02-12T10:00:00Z') // '2小时前'
 * formatRelativeTime(Date.now() - 3600000) // '1小时前'
 */
export function formatRelativeTime(timestamp: string | Date): string {
  try {
    // 确保使用当前 locale
    initDayjsLocale()

    return dayjs(timestamp).fromNow()
  } catch (error) {
    console.warn('formatRelativeTime error:', error)
    return String(timestamp)
  }
}

/**
 * 格式化日历时间（今天/昨天/具体日期）
 *
 * @param timestamp 时间戳
 * @param timezone 时区（可选）
 * @returns 格式化后的时间字符串
 *
 * @example
 * formatCalendarTime(new Date()) // '今天 14:30'
 * formatCalendarTime(new Date() - 86400000) // '昨天 14:30'
 */
export function formatCalendarTime(timestamp: string | Date, timezone?: string): string {
  try {
    const userTimezone = timezone || TimezoneManager.getUserTimezone()
    const date = dayjs(timestamp).tz(userTimezone)
    const now = dayjs().tz(userTimezone)

    // 确保使用当前 locale
    initDayjsLocale()

    const locale = getDayjsLocale()

    if (date.isSame(now, 'day')) {
      // 今天
      if (locale === 'zh-cn') {
        return `今天 ${date.format('HH:mm')}`
      }
      return `Today ${date.format('HH:mm')}`
    } else if (date.isSame(now.subtract(1, 'day'), 'day')) {
      // 昨天
      if (locale === 'zh-cn') {
        return `昨天 ${date.format('HH:mm')}`
      }
      return `Yesterday ${date.format('HH:mm')}`
    } else {
      // 更早的日期
      return date.format('YYYY-MM-DD HH:mm')
    }
  } catch (error) {
    console.warn('formatCalendarTime error:', error)
    return String(timestamp)
  }
}

/**
 * 计算两个时间点之间的时间差（毫秒）
 *
 * @param startTime 开始时间
 * @param endTime 结束时间（默认为当前时间）
 * @returns 时间差（毫秒）
 */
export function getTimeDifference(
  startTime: string | Date,
  endTime?: string | Date
): number {
  try {
    const start = dayjs(startTime)
    const end = endTime ? dayjs(endTime) : dayjs()
    return end.diff(start)
  } catch (error) {
    console.warn('getTimeDifference error:', error)
    return 0
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
export function formatDuration(ms: number, precision: 'standard' | 'detailed' = 'standard'): string {
  if (ms === 0 || isNaN(ms)) return '0ms'

  try {
    if (ms < 1000) {
      return precision === 'detailed' ? `${ms.toFixed(0)}ms` : `${ms}ms`
    }

    if (ms < 60000) {
      const seconds = ms / 1000
      return precision === 'detailed' ? `${seconds.toFixed(2)}s` : `${seconds.toFixed(1)}s`
    }

    if (ms < 3600000) {
      const minutes = Math.floor(ms / 60000)
      const seconds = Math.floor((ms % 60000) / 1000)

      if (precision === 'detailed' && seconds > 0) {
        return `${minutes}m ${seconds}s`
      }
      return `${minutes}m`
    }

    const hours = Math.floor(ms / 3600000)
    const minutes = Math.floor((ms % 3600000) / 60000)

    if (precision === 'detailed' && minutes > 0) {
      return `${hours}h ${minutes}m`
    }
    return `${hours}h`
  } catch (error) {
    console.warn('formatDuration error:', error)
    return `${ms}ms`
  }
}

/**
 * 转换 UTC 时间到用户时区
 *
 * @param utcTimestamp UTC时间戳
 * @param timezone 用户时区（可选）
 * @returns 转换后的 Date 对象
 */
export function toUserTimezone(utcTimestamp: string, timezone?: string): Date {
  const userTimezone = timezone || TimezoneManager.getUserTimezone()
  return dayjs.utc(utcTimestamp).tz(userTimezone).toDate()
}

/**
 * 转换本地时间到 UTC
 *
 * @param localTime 本地时间
 * @param timezone 时区（可选，默认用户时区）
 * @returns UTC 时间的 ISO 字符串
 */
export function toUTC(localTime: string | Date, timezone?: string): string {
  const userTimezone = timezone || TimezoneManager.getUserTimezone()
  return dayjs.tz(localTime, userTimezone).utc().toISOString()
}

/**
 * 检查日期是否有效
 *
 * @param date 日期对象或字符串
 * @returns 是否有效
 */
export function isValidDate(date: string | Date | Dayjs): boolean {
  return dayjs(date).isValid()
}

/**
 * 获取时区偏移量
 *
 * @param timezone 时区
 * @returns 时区偏移字符串（如 '+08:00'）
 */
export function getTimezoneOffset(timezone?: string): string {
  const tz = timezone || TimezoneManager.getUserTimezone()
  return dayjs().tz(tz).format('Z')
}

/**
 * 默认导出 - 可以直接使用所有函数
 */
export default {
  formatTimestamp,
  formatTime,
  formatDate,
  formatCompactTime,
  formatFullDateTime,
  formatRelativeTime,
  formatCalendarTime,
  getTimeDifference,
  formatDuration,
  toUserTimezone,
  toUTC,
  isValidDate,
  getTimezoneOffset,
  TimezoneManager,
  initDayjsLocale,
}
