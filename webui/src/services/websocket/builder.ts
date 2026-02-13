/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 类型安全的消息构建器
 *
 * 提供完全类型化的消息构建方法，确保编译时类型检查
 */

import type { WebSocketMessage, MessagePayloadMap, MessageType } from './types'


import { MessageType as MT } from './types'

export class MessageBuilder {
  /**
   * 生成唯一消息ID
   */
  private static generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
  }

  /**
   * 生成时间戳
   */
  private static generateTimestamp(): string {
    return new Date().toISOString()
  }

  /**
   * 构建基础消息结构
   */
  private static buildBase<T extends MessageType>(
    type: T,
    sessionId: string
  ): Pick<WebSocketMessage<T>, 'id' | 'type' | 'timestamp' | 'session_id'> {
    return {
      id: MessageBuilder.generateId(),
      type,
      timestamp: MessageBuilder.generateTimestamp(),
      session_id: sessionId,
    }
  }

  /**
   * 构建用户消息
   */
  static buildUserMessage(
    payload: MessagePayloadMap[MT.USER_MESSAGE],
    sessionId: string
  ): WebSocketMessage<MT.USER_MESSAGE> {
    return {
      ...MessageBuilder.buildBase(MT.USER_MESSAGE, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }

  /**
   * 构建助手消息
   */
  static buildAssistantMessage(
    payload: MessagePayloadMap[MT.ASSISTANT_MESSAGE],
    sessionId: string
  ): WebSocketMessage<MT.ASSISTANT_MESSAGE> {
    return {
      ...MessageBuilder.buildBase(MT.ASSISTANT_MESSAGE, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }

  /**
   * 构建追问回复消息
   */
  static buildFollowupResponse(
    payload: MessagePayloadMap[MT.FOLLOWUP_RESPONSE],
    sessionId: string
  ): WebSocketMessage<MT.FOLLOWUP_RESPONSE> {
    return {
      ...MessageBuilder.buildBase(MT.FOLLOWUP_RESPONSE, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }

  /**
   * 构建心跳消息
   */
  static buildHeartbeat(
    sessionId: string,
    message = 'ping'
  ): WebSocketMessage<MT.HEARTBEAT> {
    return {
      ...MessageBuilder.buildBase(MT.HEARTBEAT, sessionId),
      message,  // 直接添加message字段
    }
  }

  /**
   * 构建状态同步消息
   */
  static buildStateSync(
    payload: MessagePayloadMap[MT.STATE_SYNC],
    sessionId: string
  ): WebSocketMessage<MT.STATE_SYNC> {
    return {
      ...MessageBuilder.buildBase(MT.STATE_SYNC, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }

  /**
   * 构建状态更新消息
   */
  static buildStateUpdate(
    payload: MessagePayloadMap[MT.STATE_UPDATE],
    sessionId: string
  ): WebSocketMessage<MT.STATE_UPDATE> {
    return {
      ...MessageBuilder.buildBase(MT.STATE_UPDATE, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }

  /**
   * 通用消息构建方法
   */
  static build<T extends MessageType>(
    type: T,
    payload: MessagePayloadMap[T],
    sessionId: string
  ): WebSocketMessage<T> {
    return {
      ...MessageBuilder.buildBase(type, sessionId),
      ...payload,  // 展开payload字段到顶层
    }
  }
}

/**
 * 快捷构建方法
 */
export const buildMessage = <T extends MessageType>(
  type: T,
  payload: MessagePayloadMap[T],
  sessionId: string
): WebSocketMessage<T> => {
  return MessageBuilder.build(type, payload, sessionId)
}

/**
 * 常用消息快捷构建器
 */
export const messageBuilders = {
  user: (content: string, sessionId: string, uiContext?: unknown) =>
    MessageBuilder.buildUserMessage({ content, user_ui_context: uiContext }, sessionId),

  heartbeat: (sessionId: string) =>
    MessageBuilder.buildHeartbeat(sessionId),

  followupResponse: (taskId: string, toolCallId: string, response: string, sessionId: string) =>
    MessageBuilder.buildFollowupResponse({ task_id: taskId, tool_call_id: toolCallId, response }, sessionId),

  stateSync: (data: Record<string, unknown>, sessionId: string) =>
    MessageBuilder.buildStateSync({ data }, sessionId),

  stateUpdate: (data: Record<string, unknown>, sessionId: string, path?: string) =>
    MessageBuilder.buildStateUpdate({ data, path }, sessionId),
}
