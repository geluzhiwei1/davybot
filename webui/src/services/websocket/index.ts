/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * WebSocket服务统一导出
 *
 * 提供完整的WebSocket通信功能
 */

// 核心类
export { WebSocketClient, useWebSocket, initWebSocket, getWebSocket } from './client'

// 兼容 api/index.ts 的便捷函数
export { getWebSocketClient, createWebSocketClient, initWebSocketClient } from './client'

// 类型定义
export * from './types'

// 消息构建器
export { MessageBuilder, messageBuilders, buildMessage } from './builder'

// 消息路由器
export { MessageRouter, globalRouter, createMessageRouter } from './router'


