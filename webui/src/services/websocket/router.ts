/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 类型安全的消息路由器
 *
 * 提供完全类型化的消息订阅和分发机制
 */

import type { WebSocketMessage, MessageHandler, Unsubscribe } from './types'
import { logger } from '@/utils/logger'

import { MessageType } from './types'
import { useParallelTasksStore } from '@/stores/parallelTasks'

/**
 * 消息路由器
 */
export class MessageRouter {
  private handlers = new Map<MessageType, Set<(...args: unknown[]) => void>>()
  private wildcardHandlers = new Set<(message: WebSocketMessage) => void>()

  /**
   * 订阅特定类型的消息
   */
  on<T extends MessageType>(
    type: T,
    handler: MessageHandler<T>
  ): Unsubscribe {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set())
    }

    this.handlers.get(type)!.add(handler as unknown)

    // 返回取消订阅函数
    return () => {
      const handlers = this.handlers.get(type)
      if (handlers) {
        handlers.delete(handler as unknown)
        if (handlers.size === 0) {
          this.handlers.delete(type)
        }
      }
    }
  }

  /**
   * 订阅所有消息
   */
  onAny(handler: (message: WebSocketMessage) => void): Unsubscribe {
    this.wildcardHandlers.add(handler)

    return () => {
      this.wildcardHandlers.delete(handler)
    }
  }

  /**
   * 订阅一次（自动取消订阅）
   */
  once<T extends MessageType>(
    type: T,
    handler: MessageHandler<T>
  ): Unsubscribe {
    const wrappedHandler = async (message: WebSocketMessage<T>) => {
      await handler(message)
      unsubscribe()
    }

    const unsubscribe = this.on(type, wrappedHandler as unknown)
    return unsubscribe
  }

  /**
   * 分发消息到对应的处理器
   */
  async dispatch<T extends MessageType>(message: WebSocketMessage<T>): Promise<void> {
    const { type } = message

    // 分发到特定类型的处理器
    const handlers = this.handlers.get(type)
    if (handlers) {
      const promises = Array.from(handlers).map(handler => {
        try {
          return Promise.resolve(handler(message as unknown))
        } catch (error) {
          logger.error(`Error in message handler for type ${type}:`, error)
          return Promise.reject(error)
        }
      })

      await Promise.allSettled(promises)
    }

    // 分发到通配符处理器
    if (this.wildcardHandlers.size > 0) {
      const promises = Array.from(this.wildcardHandlers).map(handler => {
        try {
          return Promise.resolve(handler(message))
        } catch (error) {
          logger.error('Error in wildcard message handler:', error)
          return Promise.reject(error)
        }
      })

      await Promise.allSettled(promises)
    }
  }

  /**
   * 取消特定类型的所有订阅
   */
  off(type: MessageType): void {
    this.handlers.delete(type)
  }

  /**
   * 取消所有订阅
   */
  clear(): void {
    this.handlers.clear()
    this.wildcardHandlers.clear()
  }

  /**
   * 获取订阅统计
   */
  getStats(): { [key: string]: number } {
    const stats: Record<string, number> = {}

    for (const [type, handlers] of this.handlers.entries()) {
      stats[type] = handlers.size
    }

    stats['*'] = this.wildcardHandlers.size

    return stats
  }
}

/**
 * 创建全局消息路由器实例
 */
export const createMessageRouter = () => new MessageRouter()

/**
 * 默认导出的全局路由器实例
 */
export const globalRouter = createMessageRouter()

// ==================== 注册并行任务消息处理器 ====================

/**
 * 自动注册并行任务相关的消息处理器
 * 这些处理器将并行任务的消息转发到parallelTasks store
 */

// 延迟导入store，避免循环依赖
let parallelTasksStore: unknown = null

const getParallelTasksStore = () => {
  if (!parallelTasksStore) {
    parallelTasksStore = useParallelTasksStore()
  }
  return parallelTasksStore
}

// 注册任务节点开始消息
globalRouter.on(MessageType.TASK_NODE_START, (message) => {
  const msg = message as unknown
  getParallelTasksStore().handleTaskNodeStart(msg)
})

// 注册任务节点进度消息
globalRouter.on(MessageType.TASK_NODE_PROGRESS, (message) => {
  const msg = message as unknown
  getParallelTasksStore().handleTaskNodeProgress(msg)
})

// 注册流式推理消息
globalRouter.on(MessageType.STREAM_REASONING, (message) => {
  const msg = message as unknown
  getParallelTasksStore().handleStreamContent(msg)
})

// 注册任务节点完成消息
globalRouter.on(MessageType.TASK_NODE_COMPLETE, (message) => {
  const msg = message as unknown
  getParallelTasksStore().handleTaskNodeComplete(msg)
})

// 注册TODO更新消息
globalRouter.on(MessageType.TODO_UPDATE, (message) => {
  const msg = message as unknown
  getParallelTasksStore().handleTodoUpdate(msg)
})

// 注意：STREAM_CONTENT 消息不再通过 globalRouter 路由
// Chat store 已经通过 connectionStore 完整处理了流式内容
// ParallelTasks store 主要关注任务状态和进度，不需要实时显示流式内容

// 注册 AGENT_START 消息 - 用于在 parallelTasksStore 中创建 agent 任务
globalRouter.on(MessageType.AGENT_START, (message) => {
  const msg = message as unknown
  const task_id = msg.task_id || msg.agent_id

  if (!task_id) {
    throw new Error('[Router] AGENT_START missing required field: task_id or agent_id')
  }

  const store = getParallelTasksStore()
  store.addTask(task_id, msg.node_type || 'agent', msg.description || msg.task_name || 'Agent Task')
  store.updateTaskState(task_id, 'running')
})

// 注册 AGENT_COMPLETE 消息
globalRouter.on(MessageType.AGENT_COMPLETE, (message) => {
  const msg = message as unknown
  const task_id = msg.task_id || msg.agent_id

  if (!task_id) {
    throw new Error('[Router] AGENT_COMPLETE missing required field: task_id or agent_id')
  }

  getParallelTasksStore().updateTaskState(task_id, 'completed')
})

// 注册任务节点暂停消息
globalRouter.on(MessageType.TASK_NODE_PAUSED, (message) => {
  const msg = message as unknown
  const task_id = msg.task_node_id || msg.task_id

  if (!task_id) {
    throw new Error('[Router] TASK_NODE_PAUSED missing required field: task_node_id or task_id')
  }

  getParallelTasksStore().updateTaskState(task_id, 'paused')
})

// 注册任务节点恢复消息
globalRouter.on(MessageType.TASK_NODE_RESUMED, (message) => {
  const msg = message as unknown
  const task_id = msg.task_node_id || msg.task_id

  if (!task_id) {
    throw new Error('[Router] TASK_NODE_RESUMED missing required field: task_node_id or task_id')
  }

  getParallelTasksStore().updateTaskState(task_id, 'running')
})

// 注册任务节点停止消息
globalRouter.on(MessageType.TASK_NODE_STOPPED, (message) => {
  const msg = message as unknown
  const task_id = msg.task_node_id || msg.task_id

  if (!task_id) {
    throw new Error('[Router] TASK_NODE_STOPPED missing required field: task_node_id or task_id')
  }

  getParallelTasksStore().updateTaskState(task_id, 'cancelled')
})

// 调试：监听所有消息
globalRouter.onAny((message) => {
  if (message.type === MessageType.TASK_NODE_START ||
      message.type === MessageType.TASK_NODE_PROGRESS ||
      message.type === MessageType.TODO_UPDATE) {
    logger.debug('[Router] Message received:', message.type, message)
  }
})
