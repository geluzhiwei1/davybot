/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * useConversationNotifications - 会话通知管理
 *
 * 职责:
 * - 管理后台会话的新消息通知
 * - 提供通知计数和预览
 * - 清除通知
 */

import { computed } from 'vue'
import { useMessageStore } from '@/stores/messages'
import { useWorkspaceStore } from '@/stores/workspace'
import { useParallelTasksStore } from '@/stores/parallelTasks'

export function useConversationNotifications() {
  const messageStore = useMessageStore()
  const workspaceStore = useWorkspaceStore()
  const parallelTasksStore = useParallelTasksStore()

  /**
   * 获取指定会话的通知信息
   */
  const getConversationNotification = (conversationId: string) => {
    return messageStore.getBackgroundNotification(conversationId)
  }

  /**
   * 获取所有后台会话的通知
   */
  const getAllNotifications = computed(() => {
    return messageStore.getAllBackgroundNotifications()
  })

  /**
   * 获取有新消息的会话列表 (用于UI显示)
   */
  const conversationsWithNotifications = computed(() => {
    const notifications = messageStore.getAllBackgroundNotifications()
    const conversations = workspaceStore.conversationList

    return conversations
      .filter(conv => notifications.has(conv.id))
      .map(conv => {
        const notification = notifications.get(conv.id)!
        return {
          conversation: conv,
          unreadCount: notification.count,
          lastMessageTime: notification.lastMessageTime,
          lastMessagePreview: notification.lastMessagePreview
        }
      })
      .sort((a, b) => b.lastMessageTime - a.lastMessageTime)  // 按时间倒序
  })

  /**
   * 检查指定会话是否有活跃的Agent
   * 注意: 这是简化实现，实际需要后端提供task到conversation的映射
   */
  const hasActiveAgentInConversation = (conversationId: string): boolean => {
    // ✅ 临时修复：只检查是否是当前会话且有活跃任务
    // TODO: 需要后端提供 task_id → conversation_id 映射
    const isCurrentConversation = conversationId === workspaceStore.currentConversationId
    return isCurrentConversation && parallelTasksStore.hasActiveTasks
  }

  /**
   * 获取会话状态 (用于UI显示)
   */
  const getConversationStatus = (conversationId: string) => {
    const notification = getConversationNotification(conversationId)
    const hasActiveAgent = hasActiveAgentInConversation(conversationId)

    return {
      hasNewMessages: notification !== undefined,
      unreadCount: notification?.count || 0,
      lastMessagePreview: notification?.lastMessagePreview || '',
      hasActiveAgent,
      isBackgroundConversation: conversationId !== workspaceStore.currentConversationId
    }
  }

  return {
    getConversationNotification,
    getAllNotifications,
    conversationsWithNotifications,
    hasActiveAgentInConversation,
    getConversationStatus
  }
}
