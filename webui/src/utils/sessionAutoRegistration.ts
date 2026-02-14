/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Session→Workspace 自动注册工具
 * 在WebSocket连接成功时自动建立session→workspace映射
 */

import type { ConnectionStore } from '@/stores/connection'
import type { WorkspaceStore } from '@/stores/workspace'

export interface SessionRegistrationConfig {
  // 是否启用自动注册
  enabled: boolean

  // 注册失败时是否重试
  retryOnFailure: boolean

  // 最大重试次数
  maxRetries: number

  // 重试延迟（毫秒）
  retryDelay: number
}

const DEFAULT_CONFIG: SessionRegistrationConfig = {
  enabled: true,
  retryOnFailure: true,
  maxRetries: 3,
  retryDelay: 1000
}

/**
 * Session注册器类
 */
export class SessionRegistrar {
  private config: SessionRegistrationConfig
  private registrationAttempts: Map<string, number> = new Map()

  constructor(config: Partial<SessionRegistrationConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  /**
   * 在WebSocket连接成功时自动注册session→workspace映射
   */
  async registerOnConnect(
    sessionId: string,
    connectionStore: ConnectionStore,
    workspaceStore: WorkspaceStore
  ): Promise<boolean> {
    if (!this.config.enabled) {
      return false
    }

    const workspaceId = workspaceStore.currentWorkspaceId || 'default'

    try {
      // 注册映射
      connectionStore.updateSessionMapping(sessionId, workspaceId)

      // 清除重试计数
      this.registrationAttempts.delete(sessionId)

      return true
    } catch (error) {
      console.error('[SessionRegistrar] ❌ Registration failed:', error)

      // 重试逻辑
      if (this.config.retryOnFailure) {
        const attempts = this.registrationAttempts.get(sessionId) || 0

        if (attempts < this.config.maxRetries) {
          this.registrationAttempts.set(sessionId, attempts + 1)

          // 延迟重试
          await this.delay(this.config.retryDelay * (attempts + 1))

          return this.registerOnConnect(sessionId, connectionStore, workspaceStore)
        } else {
          console.error('[SessionRegistrar] Max retries exceeded for session:', sessionId)
          this.registrationAttempts.delete(sessionId)
          return false
        }
      }

      return false
    }
  }

  /**
   * 批量注册多个session→workspace映射
   */
  async batchRegister(
    mappings: Array<{ sessionId: string; workspaceId: string }>,
    connectionStore: ConnectionStore
  ): Promise<{ success: number; failed: number }> {
    let success = 0
    let failed = 0

    for (const { sessionId, workspaceId } of mappings) {
      try {
        connectionStore.updateSessionMapping(sessionId, workspaceId)
        success++
      } catch (error) {
        console.error('[SessionRegistrar] Batch registration failed:', {
          session_id: sessionId,
          workspace_id: workspaceId,
          error
        })
        failed++
      }
    }

    return { success, failed }
  }

  /**
   * 清理过期的session映射
   */
  cleanupExpiredSessions(
    connectionStore: ConnectionStore
  ): number {
    const sessionMap = connectionStore.sessionToWorkspaceMap
    const cleaned = 0

    for (const [,] of sessionMap.entries()) {
      // 这里可以添加session时间戳检查逻辑
      // 暂时跳过，因为Map中没有存储时间戳
      // TODO: 需要在connectionStore中添加sessionTimestamps Map
    }

    return cleaned
  }

  /**
   * 验证session映射是否存在
   */
  verifyMapping(
    sessionId: string,
    expectedWorkspaceId: string,
    connectionStore: ConnectionStore
  ): boolean {
    const actualWorkspaceId = connectionStore.getWorkspaceIdBySession(sessionId)
    const isValid = actualWorkspaceId === expectedWorkspaceId

    if (!isValid) {
      console.warn('[SessionRegistrar] Mapping verification failed:', {
        session_id: sessionId,
        expected: expectedWorkspaceId,
        actual: actualWorkspaceId
      })
    }

    return isValid
  }

  /**
   * 延迟工具函数
   */
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * 获取注册统计信息
   */
  getStats(): {
    totalAttempts: number
    activeRegistrations: number
    config: SessionRegistrationConfig
  } {
    return {
      totalAttempts: Array.from(this.registrationAttempts.values()).reduce((a, b) => a + b, 0),
      activeRegistrations: this.registrationAttempts.size,
      config: this.config
    }
  }
}

// 单例实例
export const sessionRegistrar = new SessionRegistrar()

/**
 * 初始化session自动注册
 * 在WebSocket连接管理器中调用
 */
export function initSessionAutoRegistration(
  connectionStore: ConnectionStore,
  workspaceStore: WorkspaceStore
): void {
  // 监听连接状态变化
  connectionStore.$onAction(({ name, after }) => {
    if (name === 'connect') {
      after(async () => {
        // 连接成功后自动注册session
        try {
          const wsClient = connectionStore.getCurrentClient()
          if (wsClient) {
            const sessionId = wsClient.getSessionId()
            if (sessionId) {
              await sessionRegistrar.registerOnConnect(
                sessionId,
                connectionStore,
                workspaceStore
              )
            }
          }
        } catch (error) {
          console.error('[SessionAutoRegistration] Auto-registration failed:', error)
        }
      })
    }
  })
}

/**
 * 定期清理过期session（后台任务）
 */
export function startSessionCleanup(
  connectionStore: ConnectionStore,
  intervalMs: number = 300000 // 默认5分钟
): () => void {
  const intervalId = setInterval(() => {
    sessionRegistrar.cleanupExpiredSessions(connectionStore)
  }, intervalMs)

  // 返回清理函数
  return () => {
    clearInterval(intervalId)
  }
}

export default sessionRegistrar
