/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 时区管理 Composable
 *
 * 提供用户时区检测、设置和管理功能
 * 支持在 WebSocket 连接时自动发送时区信息到后端
 */

import { computed, watch } from 'vue'
import i18nDefault from '@/i18n'
import { TimezoneManager, initDayjsLocale } from '@/utils/dateFormatter'

/**
 * 时区管理 Hook
 *
 * @returns 时区相关的状态和方法
 *
 * @example
 * const { userTimezone, setUserTimezone, resetTimezone, getTimezoneInfo, sendTimezoneToBackend } = useTimezone()
 *
 * // 获取当前时区
 *
 * // 设置时区
 * setUserTimezone('America/New_York')
 *
 * // 发送时区信息到后端
 * const timezoneInfo = sendTimezoneToBackend()
 */
export function useTimezone() {
  /**
   * 当前用户时区（响应式）
   */
  const userTimezone = computed(() => TimezoneManager.getUserTimezone())

  /**
   * 时区偏移量（响应式）
   */
  const timezoneOffset = computed(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone
    } catch {
      return 'UTC'
    }
  })

  /**
   * 获取时区详细信息
   */
  const getTimezoneInfo = () => {
    const tz = userTimezone.value
    const now = new Date()

    // 获取时区偏移
    const offset = -now.getTimezoneOffset() / 60
    const offsetSign = offset >= 0 ? '+' : '-'
    const offsetHours = Math.abs(Math.floor(offset))
    const offsetMinutes = Math.abs((offset % 1) * 60)
    const offsetString = `UTC${offsetSign}${String(offsetHours).padStart(2, '0')}:${String(offsetMinutes).padStart(2, '0')}`

    return {
      timezone: tz,
      offset: offsetString,
      locale: i18nDefault?.global?.locale?.value || 'zh-CN',
    }
  }

  /**
   * 设置用户时区
   *
   * @param timezone IANA 时区标识符（如 'Asia/Shanghai'）
   */
  const setUserTimezone = (timezone: string) => {
    TimezoneManager.setUserTimezone(timezone)
    // 重新初始化 dayjs locale 确保语言正确
    initDayjsLocale()
  }

  /**
   * 重置时区为自动检测
   */
  const resetTimezone = () => {
    TimezoneManager.resetTimezone()
    initDayjsLocale()
  }

  /**
   * 获取常用时区列表
   */
  const getCommonTimezones = () => {
    return TimezoneManager.getCommonTimezones()
  }

  /**
   * 发送时区信息到后端
   * 用于 WebSocket 连接时携带用户时区信息
   *
   * @returns 时区信息对象
   */
  const sendTimezoneToBackend = () => {
    const info = getTimezoneInfo()

    return {
      user_timezone: info.timezone,
      user_locale: info.locale,
      timezone_offset: info.offset,
    }
  }

  /**
   * 监听语言变化，自动更新 dayjs locale
   */
  if (i18nDefault?.global?.locale) {
    watch(
      () => i18nDefault.global.locale.value,
      () => {
        initDayjsLocale()
      }
    )
  }

  return {
    // 状态
    userTimezone,
    timezoneOffset,

    // 方法
    getTimezoneInfo,
    setUserTimezone,
    resetTimezone,
    getCommonTimezones,
    sendTimezoneToBackend,
  }
}

/**
 * 导出类型
 */
export type TimezoneInfo = ReturnType<typeof useTimezone>['getTimezoneInfo']

export default useTimezone
