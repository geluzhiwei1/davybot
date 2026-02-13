/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Workspace State Utility
 *
 * 提供按 workspace 隔离的状态管理通用工具
 * 遵循 DRY 原则，避免重复的状态映射模式
 */

import { ref, type Ref } from 'vue'
import { logger } from './logger'

/**
 * 创建按 workspace 隔离的状态 Map
 *
 * @typeparam T 状态类型
 * @param defaultFactory 默认状态工厂函数
 * @returns [stateMap, getCurrentState] 状态 Map 和获取当前状态函数的元组
 *
 * @example
 * ```ts
 * interface UIState {
 *   openFiles: string[]
 *   currentFile: string | null
 * }
 *
 * const [uiStates, getCurrentUI] = createWorkspaceMap<UIState>(() => ({
 *   openFiles: [],
 *   currentFile: null
 * }))
 *
 * // 获取当前 workspace 的状态
 * const currentUI = getCurrentUI(workspaceId)
 * currentUI.openFiles.push('file.ts')
 * ```
 */
export function createWorkspaceMap<T>(
  defaultFactory: () => T
): [Ref<Map<string, T>>, (workspaceId?: string) => T] {
  const stateMap = ref<Map<string, T>>(new Map())

  /**
   * 获取指定 workspace 的状态
   * 如果不存在则使用 defaultFactory 创建
   *
   * @param workspaceId workspace ID（可选，默认使用当前 workspace）
   * @returns 该 workspace 的状态对象
   */
  function getCurrentState(workspaceId?: string): T {
    // ⚠️ 注意：此函数需要在有 workspaceStore 上下文的地方调用
    // 或者直接传入 workspaceId 参数
    const targetWorkspaceId = workspaceId || 'default'

    if (!targetWorkspaceId || targetWorkspaceId.trim() === '') {
      throw new Error('[WorkspaceState] workspaceId cannot be empty')
    }

    if (!stateMap.value.has(targetWorkspaceId)) {
      const newState = defaultFactory()
      stateMap.value.set(targetWorkspaceId, newState)
      logger.debug(`[WorkspaceState] Created state for workspace: ${targetWorkspaceId}`)
    }

    return stateMap.value.get(targetWorkspaceId)!
  }

  return [stateMap, getCurrentState]
}

/**
 * 创建基于 workspaceStore 的计算属性状态获取器
 *
 * @typeparam T 状态类型
 * @param stateMap 状态 Map
 * @param workspaceIdGetter 获取当前 workspaceId 的函数
 * @returns 计算属性，自动返回当前 workspace 的状态
 *
 * @example
 * ```ts
 * import { useWorkspaceStore } from './workspace'
 *
 * const [uiStates, getUI] = createWorkspaceMap<UIState>(...)
 * const currentUI = computed(() => getUI(workspaceStore.currentWorkspaceId))
 * ```
 */
export function createCurrentStateGetter<T>(
  stateMap: Ref<Map<string, T>>,
  workspaceIdGetter: () => string | undefined
): () => T {
  return () => {
    const workspaceId = workspaceIdGetter() || 'default'

    if (!stateMap.value.has(workspaceId)) {
      throw new Error(`[WorkspaceState] No state found for workspace: ${workspaceId}`)
    }

    return stateMap.value.get(workspaceId)!
  }
}

/**
 * 清除指定 workspace 的状态
 *
 * @param stateMap 状态 Map
 * @param workspaceId 要清除的 workspace ID
 */
export function clearWorkspaceState<T>(
  stateMap: Ref<Map<string, T>>,
  workspaceId: string
): void {
  if (!workspaceId || workspaceId.trim() === '') {
    throw new Error('[WorkspaceState] workspaceId cannot be empty when clearing state')
  }

  const existed = stateMap.value.delete(workspaceId)
  if (existed) {
    logger.debug(`[WorkspaceState] Cleared state for workspace: ${workspaceId}`)
  }
}

/**
 * 清除所有 workspace 状态
 *
 * @param stateMap 状态 Map
 */
export function clearAllWorkspaceStates<T>(stateMap: Ref<Map<string, T>>): void {
  const count = stateMap.value.size
  stateMap.value.clear()
  logger.debug(`[WorkspaceState] Cleared all states (${count} workspaces)`)
}

/**
 * 获取所有 workspace 的状态
 *
 * @param stateMap 状态 Map
 * @returns 状态数组的副本
 */
export function getAllWorkspaceStates<T>(stateMap: Ref<Map<string, T>>): T[] {
  return Array.from(stateMap.value.values())
}

/**
 * 获取特定 workspace 的状态（不创建默认值）
 *
 * @param stateMap 状态 Map
 * @param workspaceId workspace ID
 * @returns 状态对象或 undefined
 */
export function getWorkspaceState<T>(
  stateMap: Ref<Map<string, T>>,
  workspaceId: string
): T | undefined {
  if (!workspaceId || workspaceId.trim() === '') {
    throw new Error('[WorkspaceState] workspaceId cannot be empty when getting state')
  }

  return stateMap.value.get(workspaceId)
}
