/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { MessageType, type BaseMessage, type WebSocketMessage } from '@/types/websocket';

// 消息验证器
export class MessageValidator {
  static validate(message: unknown): BaseMessage | null {
    if (!message || typeof message !== 'object') {
      return null;
    }

    const required = ['id', 'timestamp', 'type', 'session_id'];
    for (const field of required) {
      if (!message[field]) {
        return null;
      }
    }

    if (!Object.values(MessageType).includes(message.type)) {
      return null;
    }

    return message as BaseMessage;
  }

  static validateUserMessage(message: unknown): boolean {
    if (!this.validate(message)) return false;

    const userMessage = message as unknown;
    return userMessage.type === MessageType.USER_MESSAGE &&
      typeof userMessage.content === 'string';
  }

  static validateAssistantMessage(message: unknown): boolean {
    if (!this.validate(message)) return false;

    const assistantMessage = message as unknown;
    return assistantMessage.type === MessageType.ASSISTANT_MESSAGE &&
      typeof assistantMessage.content === 'string';
  }

  static validateTaskProgressMessage(message: unknown): boolean {
    if (!this.validate(message)) return false;

    const progressMessage = message as unknown;
    return progressMessage.type === MessageType.TASK_PROGRESS &&
      typeof progressMessage.task_id === 'string' &&
      typeof progressMessage.progress === 'number' &&
      ['planning', 'executing', 'completed', 'error'].includes(progressMessage.status) &&
      typeof progressMessage.message === 'string';
  }

  static validateErrorMessage(message: unknown): boolean {
    if (!this.validate(message)) return false;

    const errorMessage = message as unknown;
    return errorMessage.type === MessageType.ERROR &&
      typeof errorMessage.message === 'string';
  }

  static validateTaskErrorMessage(message: unknown): boolean {
    if (!this.validate(message)) return false;

    const taskErrorMessage = message as unknown;
    return taskErrorMessage.type === MessageType.TASK_ERROR &&
      typeof taskErrorMessage.task_id === 'string' &&
      typeof taskErrorMessage.code === 'string' &&
      typeof taskErrorMessage.message === 'string' &&
      typeof taskErrorMessage.recoverable === 'boolean';
  }
}

// 消息序列化器
export class MessageSerializer {
  static serialize(message: BaseMessage): string {
    try {
      // 确保枚举值被正确序列化为字符串
      const serializedMessage = {
        ...message,
        type: message.type as string  // 强制转换为字符串
      };
      return JSON.stringify(serializedMessage);
    } catch (error) {
      console.error('Failed to serialize message:', error);
      throw new Error('Message serialization failed');
    }
  }

  static deserialize(data: string): BaseMessage | null {
    try {
      const message = JSON.parse(data);
      return MessageValidator.validate(message);
    } catch (error) {
      console.error('Failed to deserialize message:', error);
      return null;
    }
  }

  static deserializeWithValidation(data: string, expectedType?: MessageType): WebSocketMessage | null {
    const message = this.deserialize(data);
    if (!message) return null;

    if (expectedType && message.type !== expectedType) {
      console.warn(`Expected message type ${expectedType}, got ${message.type}`);
      return null;
    }

    // 根据类型进行特定验证
    switch (message.type) {
      case MessageType.USER_MESSAGE:
        return MessageValidator.validateUserMessage(message) ? message as unknown : null;
      case MessageType.ASSISTANT_MESSAGE:
        return MessageValidator.validateAssistantMessage(message) ? message as unknown : null;
      case MessageType.TASK_PROGRESS:
        return MessageValidator.validateTaskProgressMessage(message) ? message as unknown : null;
      case MessageType.TASK_ERROR:
        return MessageValidator.validateTaskErrorMessage(message) ? message as unknown : null;
      case MessageType.ERROR:
        return MessageValidator.validateErrorMessage(message) ? message as unknown : null;
      default:
        return message as WebSocketMessage;
    }
  }
}

// 消息构建器
export class MessageBuilder {
  static createBaseMessage(type: MessageType, session_id: string): BaseMessage {
    return {
      id: this.generateId(),
      timestamp: new Date().toISOString(),
      type,
      session_id
    };
  }

  static createMessage(type: string, payload: unknown, session_id: string = 'default_session'): unknown {
    return {
      ...this.createBaseMessage(type as MessageType, session_id),
      payload
    };
  }

  static createUserMessage(content: string, session_id: string, metadata?: unknown, userUIContext?: unknown): unknown {
    const message = {
      ...this.createBaseMessage(MessageType.USER_MESSAGE, session_id),
      content,
      metadata
    };

    // 添加用户UI上下文（如果提供）
    if (userUIContext) {
      (message as unknown).user_ui_context = userUIContext;
    }

    return message;
  }

  static createAssistantMessage(content: string, session_id: string, task_id?: string): unknown {
    return {
      ...this.createBaseMessage(MessageType.ASSISTANT_MESSAGE, session_id),
      content,
      task_id
    };
  }

  static createTaskStartMessage(task_id: string, message: string, session_id: string): unknown {
    return {
      ...this.createBaseMessage(MessageType.TASK_START, session_id),
      task_id,
      message
    };
  }

  static createTaskProgressMessage(
    task_id: string,
    progress: number,
    status: 'planning' | 'executing' | 'completed' | 'error',
    message: string,
    session_id: string,
    data?: unknown
  ): unknown {
    return {
      ...this.createBaseMessage(MessageType.TASK_PROGRESS, session_id),
      task_id,
      progress,
      status,
      message,
      data
    };
  }

  static createTaskCompleteMessage(task_id: string, session_id: string, result?: unknown): unknown {
    return {
      ...this.createBaseMessage(MessageType.TASK_COMPLETE, session_id),
      task_id,
      result
    };
  }

  static createTaskErrorMessage(
    task_id: string,
    code: string,
    message: string,
    session_id: string,
    details?: unknown
  ): unknown {
    return {
      ...this.createBaseMessage(MessageType.TASK_ERROR, session_id),
      task_id,
      code,
      message,
      details
    };
  }

  static createErrorMessage(
    code: string,
    message: string,
    session_id: string,
    recoverable: boolean = true,
    details?: unknown
  ): unknown {
    return {
      ...this.createBaseMessage(MessageType.ERROR, session_id),
      message: message,
      code,
      recoverable,
      details
    };
  }

  static createHeartbeatMessage(session_id: string, message?: string): unknown {
    return {
      ...this.createBaseMessage(MessageType.HEARTBEAT, session_id),
      message: message || 'ping'
    };
  }

  static createConnectMessage(session_id: string, message?: string): unknown {
    return {
      ...this.createBaseMessage(MessageType.CONNECT, session_id),
      message: message || 'connection established'
    };
  }

  static createDisconnectMessage(session_id: string, reason?: string): unknown {
    return {
      ...this.createBaseMessage(MessageType.DISCONNECT, session_id),
      reason
    };
  }

  private static generateId(): string {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}

// 协议版本管理
export class ProtocolVersion {
  static readonly CURRENT_VERSION = '1.0.0';
  static readonly SUPPORTED_VERSIONS = ['1.0.0'];

  static isVersionSupported(version: string): boolean {
    return this.SUPPORTED_VERSIONS.includes(version);
  }

  static getVersionCompatibility(version: string): 'compatible' | 'deprecated' | 'unsupported' {
    if (version === this.CURRENT_VERSION) return 'compatible';
    if (this.SUPPORTED_VERSIONS.includes(version)) return 'deprecated';
    return 'unsupported';
  }
}