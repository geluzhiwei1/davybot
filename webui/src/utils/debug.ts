/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 全局调试控制
 * 在开发环境可以通过环境变量 VITE_DEBUG 启用详细日志
 * 生产环境默认禁用所有DEBUG日志
 */

// 从环境变量读取调试开关，默认false（禁用）
const DEBUG_ENABLED = import.meta.env.VITE_DEBUG === 'true'

// 平台检测日志（高频调用）
export const DEBUG_PLATFORM = false

// HTTP请求日志（高频调用）
export const DEBUG_HTTP = false

// WebSocket日志（高频调用）
export const DEBUG_WEBSOCKET = false

// 组件生命周期日志
export const DEBUG_COMPONENTS = DEBUG_ENABLED

// 状态管理日志（Pinia stores）
export const DEBUG_STORES = DEBUG_ENABLED

// 工具函数日志
export const DEBUG_UTILS = DEBUG_ENABLED

// 性能监控日志
export const DEBUG_PERFORMANCE = DEBUG_ENABLED

/**
 * 条件日志输出 - 只在启用时才执行
 * 避免字符串拼接和对象序列化的性能开销
 */
export function debugLog(category: boolean, ...args: unknown[]): void {
  if (category && import.meta.env.DEV) {
    console.log(...args)
  }
}

/**
 * 条件warn输出
 */
export function debugWarn(category: boolean, ...args: unknown[]): void {
  if (category && import.meta.env.DEV) {
    console.warn(...args)
  }
}

/**
 * 条件error输出 - 始终输出
 */
export function debugError(...args: unknown[]): void {
  console.error(...args)
}
