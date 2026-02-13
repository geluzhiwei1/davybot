/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * WebSocket Client Manager - 多实例管理
 *
 * 职责：
 * - 为每个workspace创建独立的WebSocket连接
 * - 管理多个WebSocket实例的生命周期
 * - 防止workspace之间的数据串台
 */

import type { WebSocketConfig } from './types'
import { logger } from '@/utils/logger'
import { validateWorkspaceId } from '@/utils/workspaceResolver'
import { WebSocketClient } from './client'

export class WebSocketClientManager {
  private static instances = new Map<string, WebSocketClient>()

  /**
   * 获取指定workspace的WebSocket客户端实例
   * @param workspaceId Workspace ID
   * @param config WebSocket配置
   * @returns WebSocket客户端实例
   */
  static getInstance(workspaceId: string, config: WebSocketConfig): WebSocketClient {
    // ✅ Fast fail: Validate workspace ID
    validateWorkspaceId(workspaceId)

    // ✅ Fast fail: Validate config URL
    if (!config?.url) {
      throw new Error('Invalid config: WebSocket URL is required')
    }

    if (!this.instances.has(workspaceId)) {
      logger.debug(`[WS_MANAGER] Creating new WebSocket instance for workspace: ${workspaceId}`)
      const client = new WebSocketClient({
        ...config,
        // 为每个workspace设置独特的元数据
        metadata: {
          workspaceId,
          createdAt: Date.now()
        }
      })
      this.instances.set(workspaceId, client)
    } else {
      logger.debug(`[WS_MANAGER] Reusing existing WebSocket instance for workspace: ${workspaceId}`)
    }

    const instance = this.instances.get(workspaceId)
    if (!instance) {
      throw new Error(`Failed to retrieve WebSocket instance for workspace: ${workspaceId}`)
    }

    return instance
  }

  /**
   * 断开指定workspace的连接
   * @param workspaceId Workspace ID
   */
  static disconnect(workspaceId: string): void {
    const client = this.instances.get(workspaceId)
    if (client) {
      logger.debug(`[WS_MANAGER] Disconnecting workspace: ${workspaceId}`)
      client.disconnect()
      this.instances.delete(workspaceId)
    }
  }

  /**
   * 断开所有workspace的连接
   */
  static disconnectAll(): void {
    logger.debug(`[WS_MANAGER] Disconnecting all workspaces (${this.instances.size} instances)`)
    this.instances.forEach((client, workspaceId) => {
      logger.debug(`[WS_MANAGER] Disconnecting workspace: ${workspaceId}`)
      try {
        client.disconnect()
      } catch (error) {
        logger.error(`[WS_MANAGER] Error disconnecting workspace ${workspaceId}:`, error)
      }
    })
    this.instances.clear()
  }

  /**
   * 获取所有活跃的workspace IDs
   */
  static getActiveWorkspaces(): string[] {
    return Array.from(this.instances.keys())
  }

  /**
   * 检查指定workspace是否已连接
   * @param workspaceId Workspace ID
   */
  static isConnected(workspaceId: string): boolean {
    const client = this.instances.get(workspaceId)
    return client ? client.getState() === 'connected' : false
  }

  /**
   * 获取指定workspace的连接状态
   * @param workspaceId Workspace ID
   */
  static getState(workspaceId: string): string {
    const client = this.instances.get(workspaceId)
    return client ? client.getState() : 'disconnected'
  }
}
