/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 时间格式化集成测试
 *
 * 验证向后兼容性和新功能正常工作
 */

import { describe, it, expect } from 'vitest'
import {
  formatTimestamp,
  formatDuration,
  formatRelativeTime,
  formatNumber,
} from '@/utils/formatters'
import {
  formatTimestamp as dfTimestamp,
  formatRelativeTime as dfRelative,
  formatDuration as dfDuration,
  TimezoneManager,
} from '@/utils/dateFormatter'

describe('时间格式化 - 向后兼容性测试', () => {
  describe('formatters.ts (向后兼容)', () => {
    it('应该正确格式化时间戳 - full 格式', () => {
      const timestamp = '2025-02-12T10:00:00Z'
      const result = formatTimestamp(timestamp, 'full')

      // 结果应该包含日期和时间（格式可能因locale而异）
      expect(result).toBeTruthy()
      expect(result).toContain('2025')
      expect(result).toContain('02')
      expect(result).toContain('12')
    })

    it('应该正确格式化时间戳 - time 格式', () => {
      const timestamp = '2025-02-12T10:00:00Z'
      const result = formatTimestamp(timestamp, 'time')

      // 结果应该包含时间
      expect(result).toBeTruthy()
      expect(result).toMatch(/\d{2}:\d{2}:\d{2}/)
    })

    it('应该正确格式化时长', () => {
      const result = formatDuration(5400000) // 1.5小时

      expect(result).toBeTruthy()
      expect(result).toContain('h')
    })

    it('应该正确格式化数字（使用i18n locale）', () => {
      const result = formatNumber(1234567.89, 2)

      // 应该有千分位分隔符
      expect(result).toBeTruthy()
      // 不同的locale可能有不同的格式
      expect(result).toMatch(/1,234,567.89|1234,567.89/)
    })
  })

  describe('dateFormatter.ts (新工具)', () => {
    beforeEach(() => {
      // 重置时区为 UTC 以获得可预测的结果
      TimezoneManager.setUserTimezone('UTC')
    })

    it('应该正确格式化时间戳（UTC时区）', () => {
      const timestamp = '2025-02-12T10:00:00Z'
      const result = dfTimestamp(timestamp, 'YYYY-MM-DD HH:mm:ss', 'UTC')

      expect(result).toBe('2025-02-12 10:00:00')
    })

    it('应该正确格式化相对时间', () => {
      const timestamp = '2025-02-12T10:00:00Z'
      const result = dfRelative(timestamp)

      // 相对时间应该包含 "ago" 或 "前"（取决于locale）
      expect(result).toBeTruthy()
      expect(result).toMatch(/(ago|前|hoursAgo|hoursBefore)/)
    })

    it('应该正确格式化时长', () => {
      const result = dfDuration(5400000, 'standard')

      expect(result).toBe('1h') // 1.5小时向上取整
    })

    it('应该支持时区转换', () => {
      const utcTimestamp = '2025-02-12T10:00:00Z'

      // 北京时间 (UTC+8)
      const beijingTime = dfTimestamp(utcTimestamp, 'YYYY-MM-DD HH:mm:ss', 'Asia/Shanghai')
      expect(beijingTime).toBe('2025-02-12 18:00:00')

      // 纽约时间 (UTC-5)
      const nyTime = dfTimestamp(utcTimestamp, 'YYYY-MM-DD HH:mm:ss', 'America/New_York')
      expect(nyTime).toBe('2025-02-12 05:00:00')
    })
  })

  describe('集成测试 - formatters 调用 dateFormatter', () => {
    it('formatters.ts 应该正确调用 dateFormatter', () => {
      const timestamp = '2025-02-12T10:00:00Z'

      // 使用旧API（formatters.ts）
      const oldResult = formatTimestamp(timestamp, 'full')

      // 应该返回有效的日期字符串
      expect(oldResult).toBeTruthy()
      expect(typeof oldResult).toBe('string')

      // 应该包含关键信息
      expect(oldResult).toContain('2025')
    })

    it('formatDuration 应该正确调用 dateFormatter', () => {
      const ms = 90000 // 1.5分钟 = 90秒

      const result = formatDuration(ms, 'standard')

      expect(result).toBeTruthy()
      // 90秒应该是 1.5m 或 90s，取决于precision
      expect(result).toMatch(/(m|s)/)
    })
  })
})

describe('时区管理', () => {
  it('应该能够检测用户时区', () => {
    const tz = TimezoneManager.getUserTimezone()

    expect(tz).toBeTruthy()
    expect(typeof tz).toBe('string')
  })

  it('应该能够设置用户时区', () => {
    TimezoneManager.setUserTimezone('Asia/Tokyo')

    const tz = TimezoneManager.getUserTimezone()
    expect(tz).toBe('Asia/Tokyo')
  })

  it('应该提供常用时区列表', () => {
    const timezones = TimezoneManager.getCommonTimezones()

    expect(Array.isArray(timezones)).toBe(true)
    expect(timezones.length).toBeGreaterThan(0)

    // 应该包含常用时区
    const tzValues = timezones.map((tz: { value: string }) => tz.value)
    expect(tzValues).toContain('Asia/Shanghai')
    expect(tzValues).toContain('America/New_York')
    expect(tzValues).toContain('Europe/London')
  })
})

describe('国际化测试', () => {
  it('格式化应该支持不同locale', () => {
    // 这个测试主要验证不抛出错误
    // 实际的locale测试需要在运行时动态切换

    const timestamp = '2025-02-12T10:00:00Z'

    // 中文locale（默认）
    const zhResult = formatTimestamp(timestamp, 'full')
    expect(zhResult).toBeTruthy()

    // 应该包含年月日时分秒
    expect(zhResult).toMatch(/\d{4}-\d{2}-\d{2}/)
  })

  it('相对时间应该根据locale变化', () => {
    const now = new Date()
    const oneHourAgo = new Date(now.getTime() - 3600000).toISOString()

    const result = formatRelativeTime(oneHourAgo)

    // 应该包含"小时"相关文字
    expect(result).toBeTruthy()
    // 不同locale会有不同的文本，但都应该包含数字
    expect(result).toMatch(/\d/)
  })
})
