/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

export type MarkdownMode = 'markdown' | 'plain'

/**
 * Markdown 渲染设置 Store
 *
 * 管理全局默认模式和消息级覆盖
 */
export const useMarkdownSettingsStore = defineStore('markdownSettings', () => {
  // 全局默认模式（默认为 Markdown）
  const defaultMode = ref<MarkdownMode>('markdown')

  // 消息级模式覆盖（messageId -> mode）
  const messageOverrides = ref<Map<string, MarkdownMode>>(new Map())

  /**
   * 获取消息的实际渲染模式
   * @param messageId 消息 ID
   * @returns 渲染模式
   */
  const getMessageMode = (messageId: string): MarkdownMode => {
    return messageOverrides.value.get(messageId) || defaultMode.value
  }

  /**
   * 切换指定消息的渲染模式
   * @param messageId 消息 ID
   */
  const toggleMessageMode = (messageId: string): MarkdownMode => {
    const current = getMessageMode(messageId)
    const next: MarkdownMode = current === 'markdown' ? 'plain' : 'markdown'
    // 创建新 Map 以触发 Vue 响应式更新
    const newMap = new Map(messageOverrides.value)
    newMap.set(messageId, next)
    messageOverrides.value = newMap
    return next
  }

  /**
   * 设置全局默认渲染模式
   * @param mode 渲染模式
   */
  const setDefaultMode = (mode: MarkdownMode) => {
    defaultMode.value = mode
  }

  /**
   * 清除所有消息级覆盖
   */
  const clearOverrides = () => {
    messageOverrides.value.clear()
  }

  /**
   * 清除指定消息的覆盖
   * @param messageId 消息 ID
   */
  const clearMessageOverride = (messageId: string) => {
    messageOverrides.value.delete(messageId)
  }

  return {
    defaultMode,
    messageOverrides,
    getMessageMode,
    toggleMessageMode,
    setDefaultMode,
    clearOverrides,
    clearMessageOverride
  }
})
