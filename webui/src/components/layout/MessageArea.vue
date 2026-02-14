/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-scrollbar ref="scrollbarRef" class="message-area">
    <div ref="innerRef" class="message-list">
      <div v-for="message in messages" :key="message.id" class="message-wrapper" :class="`role-${message.role}`">
        <!-- 用户消息 -->
        <div name="chatUserMsg" v-if="message.role === 'user'" class="user-message-container">
          <div class="user-avatar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <div class="message-content-wrapper">
            <!-- 用户消息头部：显示时间 -->
            <div class="user-header-row">
              <span class="message-sender">你</span>
              <span class="message-time">{{ formatTimestamp(message.timestamp, 'time') }}</span>
            </div>
            <div
              class="user-card"
              :class="{
                'collapsed': !isUserExpanded(message.id) && !shouldAlwaysExpandUserMessage(message),
                'always-expand': shouldAlwaysExpandUserMessage(message)
              }"
              :data-summary="getUserMessageSummary(message)"
              @click="!shouldAlwaysExpandUserMessage(message) && toggleUserExpand(message.id)"
            >
              <!-- 内容区域 -->
              <el-collapse-transition>
                <div v-show="isUserExpanded(message.id) || shouldAlwaysExpandUserMessage(message)" class="user-message-content">
                  <div v-for="(contentBlock, index) in message.content" :key="`${message.id}-${contentBlock.type}-${index}`">
                    <div v-if="contentBlock.type === ContentType.TEXT"
                      class="user-text-block"
                      :title="contentBlock.text">{{ contentBlock.text }}</div>
                    <div v-else-if="contentBlock.type === ContentType.SIMPLE_TEXT"
                      class="user-text-block"
                      :title="(contentBlock as unknown).text">{{ (contentBlock as unknown).text }}</div>
                  </div>
                </div>
              </el-collapse-transition>

              <!-- 操作按钮 -->
              <div class="message-actions user-actions" @click.stop>
                <el-button
                  size="small"
                  circle
                  @click.stop="copyMessage(message)"
                >
                  <el-icon><DocumentCopy /></el-icon>
                </el-button>
                <el-button
                  v-if="!shouldAlwaysExpandUserMessage(message)"
                  size="small"
                  circle
                  @click.stop="toggleUserExpand(message.id)"
                >
                  <el-icon :class="{ 'rotate-180': isUserExpanded(message.id) }">
                    <ArrowDown />
                  </el-icon>
                </el-button>
              </div>

            </div>
          </div>
        </div>

        <!-- AI助手消息 -->
        <div id="chatAiMsg" v-else-if="message.role === 'assistant'" class="assistant-message-container">
          <div class="message-content-wrapper">
            <!-- 头部：头像 + 发送者信息 -->
            <div class="assistant-header-row">
              <div class="assistant-avatar">小</div>
              <div class="message-sender">
                大微
                <span class="message-time">{{ formatTimestamp(message.timestamp, 'time') }}</span>
              </div>
            </div>

            <!-- 独立的推理气泡 -->
            <div v-for="(block, index) in getReasoningBlocks(message)" :key="`reasoning-${message.id}-${index}`"
              class="independent-bubble reasoning-bubble">
              <ReasoningContent :block="block" />
            </div>

            <!-- 独立的工具调用气泡 -->
            <div v-for="(block, index) in getToolCallBlocks(message)" :key="`toolcall-${message.id}-${index}`"
              class="independent-bubble tool-call-bubble">
              <ToolCallContent :block="block" :key="block.toolCall?.tool_call_id" />
            </div>

            <!-- 主消息气泡（包含文本和其他内容） -->
            <div v-if="getOtherBlocks(message).length > 0" class="message-card assistant-card">
              <div class="assistant-message-content">
                <CollapsibleMessage
                  ref="collapsibleMsgRefs"
                  :max-height="400"
                  :collapsed="!isMessageExpanded(message.id, 'assistant')"
                >
                  <div v-for="(contentBlock, index) in getOtherBlocks(message)" :key="`${message.id}-${contentBlock.type}-${index}`" class="content-block">
                    <TextContent
                      v-if="contentBlock.type === ContentType.TEXT"
                      :block="contentBlock"
                      :is-streaming="isMessageStreaming(message)"
                    />
                    <ErrorContent v-else-if="contentBlock.type === ContentType.ERROR" :block="contentBlock"
                      :key="`error-${contentBlock.type}`" />
                    <div v-else-if="contentBlock.type === ContentType.SIMPLE_TEXT" class="simple-text">{{ (contentBlock as unknown).text }}</div>
                    <ToolExecutionContent v-else-if="contentBlock.type === ContentType.TOOL_EXECUTION" :block="contentBlock"
                      :key="contentBlock.toolCallId" />
                    <UnknownContent v-else :block="contentBlock" :key="`unknown-${contentBlock.type}`" />
                  </div>
                </CollapsibleMessage>
              </div>
              <!-- 操作按钮 -->
              <div class="message-actions assistant-actions">
                <el-button
                  size="small"
                  circle
                  @click="copyMessage(message)"
                >
                  <el-icon><DocumentCopy /></el-icon>
                </el-button>
                <el-button
                  size="small"
                  circle
                  @click="toggleMessageExpand(message.id)"
                >
                  <el-icon :class="{ 'rotate-180': isMessageExpanded(message.id, 'assistant') }">
                    <ArrowDown />
                  </el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>


        <!-- 工具消息 -->
        <div name="chatToolMsg" v-else-if="message.role === 'tool'" class="tool-message-container">
          <div class="tool-avatar">T</div>
          <div class="message-content-wrapper">
            <div class="message-card tool-card" :class="{ 'collapsed': !isToolExpanded(message.id) }">
              <!-- 可点击的头部 -->
              <div class="tool-card-header" @click="toggleToolExpand(message.id)" :class="{ 'clickable': !isToolExpanded(message.id) }">
                <div class="tool-header-info">
                  <span class="tool-icon-text">🔧</span>
                  <span class="tool-title-text">工具消息</span>
                  <span v-if="getToolMessageSummary(message)" class="tool-summary">{{ getToolMessageSummary(message) }}</span>
                </div>
                <div class="tool-header-actions">
                  <el-button
                    size="small"
                    circle
                    @click.stop="copyMessage(message)"
                  >
                    <el-icon><DocumentCopy /></el-icon>
                  </el-button>
                  <el-button
                    size="small"
                    circle
                    @click.stop="toggleToolExpand(message.id)"
                  >
                    <el-icon :class="{ 'rotate-180': isToolExpanded(message.id) }">
                      <ArrowDown />
                    </el-icon>
                  </el-button>
                </div>
              </div>

              <!-- 可折叠的内容区域 -->
              <el-collapse-transition>
                <div v-show="isToolExpanded(message.id)" class="tool-message-content">
                  <div v-for="(contentBlock, index) in message.content" :key="`${message.id}-${contentBlock.type}-${index}`" class="content-block">
                    <TextContent name="textContent" v-if="contentBlock.type === ContentType.TEXT" :block="contentBlock" />
                    <div v-else-if="contentBlock.type === ContentType.SIMPLE_TEXT" class="simple-text">{{ (contentBlock as unknown).text }}</div>
                    <ToolCallContent name="toolContent" v-else-if="contentBlock.type === ContentType.TOOL_CALL" :block="contentBlock"
                      :key="contentBlock.toolCall?.tool_call_id" />
                    <ToolExecutionContent name="toolExecutionContent" v-else-if="contentBlock.type === ContentType.TOOL_EXECUTION" :block="contentBlock"
                      :key="contentBlock.toolCallId" />
                    <UnknownContent v-else :block="contentBlock" :key="`unknown-${contentBlock.type}`" />
                  </div>
                </div>
              </el-collapse-transition>
            </div>
          </div>
        </div>

        <!-- 系统消息（错误等） -->
        <div v-else-if="message.role === 'system'" class="system-message-container">
          <div class="message-content-wrapper">
            <div
              class="message-card system-card"
              :class="{ 'collapsed': !isMessageExpanded(message.id, 'system') }"
            >
              <!-- 折叠状态：显示摘要 -->
              <div v-if="!isMessageExpanded(message.id, 'system')" class="system-summary" @click="toggleMessageExpand(message.id)">
                <span class="error-icon">⚠️</span>
                <span class="summary-text">{{ getSystemMessageSummary(message) }}</span>
              </div>

              <!-- 展开状态：显示完整内容 -->
              <el-collapse-transition>
                <div v-show="isMessageExpanded(message.id, 'system')" class="system-message-content">
                  <div v-for="(contentBlock, index) in message.content" :key="`${message.id}-${contentBlock.type}-${index}`" class="content-block">
                    <ErrorContent v-if="contentBlock.type === ContentType.ERROR" :block="contentBlock" />
                    <TextContent v-else-if="contentBlock.type === ContentType.TEXT" :block="contentBlock" />
                    <div v-else-if="contentBlock.type === ContentType.SIMPLE_TEXT" class="simple-text">{{ (contentBlock as unknown).text }}</div>
                    <UnknownContent v-else :block="contentBlock" />
                  </div>
                </div>
              </el-collapse-transition>

              <!-- 操作按钮：仅在展开状态显示 -->
              <div v-show="isMessageExpanded(message.id, 'system')" class="message-actions system-actions" @click.stop>
                <el-button
                  size="small"
                  circle
                  @click="copyMessage(message)"
                >
                  <el-icon><DocumentCopy /></el-icon>
                </el-button>
                <el-button
                  size="small"
                  circle
                  @click="toggleMessageExpand(message.id)"
                >
                  <el-icon :class="{ 'rotate-180': isMessageExpanded(message.id, 'system') }">
                    <ArrowDown />
                  </el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 正在输入指示器 -->
      <div v-if="isTyping" class="assistant-message-container">
        <el-avatar class="assistant-avatar">R</el-avatar>
        <el-card shadow="never" class="message-card assistant-card typing-indicator">
          <div class="dots">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
        </el-card>
      </div>
    </div>
  </el-scrollbar>
</template>

<script setup lang="ts">
import { copyToClipboard } from '@/utils/clipboard'
import { formatTimestamp } from '@/utils/formatters'
import { ref, watch, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import { ContentType, type ChatMessage } from '@/types/websocket';
import { ElScrollbar, ElAvatar, ElButton, ElMessage, ElCollapseTransition } from 'element-plus';
import { DocumentCopy, ArrowDown } from '@element-plus/icons-vue';
import CollapsibleMessage from '@/components/chat/content/CollapsibleMessage.vue';

// 导入子组件
import TextContent from '../chat/content/TextContent.vue';
import ToolCallContent from '../chat/content/ToolCallContent.vue';
import ToolExecutionContent from '../chat/content/ToolExecutionContent.vue';
import ErrorContent from '../chat/content/ErrorContent.vue';
import ReasoningContent from '../chat/content/ReasoningContent.vue';
import UnknownContent from '../chat/content/UnknownContent.vue';

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const { messages } = storeToRefs(chatStore);

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const innerRef = ref<HTMLDivElement>();
const isTyping = ref(false);

// 用户消息展开状态管理
const userExpandedStates = ref<Map<string, boolean>>(new Map());

// 工具消息展开状态管理
const toolExpandedStates = ref<Map<string, boolean>>(new Map());

// 统一的消息展开状态管理（用于assistant和system消息）
const messageExpandedStates = ref<Map<string, boolean>>(new Map());

// 分离不同类型的 content blocks（用于每条消息）- 使用缓存避免重复计算
const messageBlockCache = new Map<string, { reasoning: unknown[], toolCalls: unknown[], others: unknown[] }>()

const getMessageBlocks = (message: ChatMessage) => {
  // 每次都重新计算以支持流式更新（不再使用缓存）
  const reasoning = message.content.filter(block => block.type === ContentType.REASONING)
  const toolCalls = message.content.filter(block => block.type === ContentType.TOOL_CALL)
  const others = message.content.filter(block =>
    block.type !== ContentType.REASONING && block.type !== ContentType.TOOL_CALL
  )
  return { reasoning, toolCalls, others }
}

const getReasoningBlocks = (message: ChatMessage) => getMessageBlocks(message).reasoning
const getToolCallBlocks = (message: ChatMessage) => getMessageBlocks(message).toolCalls
const getOtherBlocks = (message: ChatMessage) => getMessageBlocks(message).others

// 判断消息是否正在streaming
const isMessageStreaming = (message: ChatMessage) => {
  if (!chatStore.isThinking) return false
  if (message.role !== 'assistant') return false
  const lastMessage = messages.value[messages.value.length - 1]
  return message.id === lastMessage?.id
}

// 监听消息数组变化（包括内容更新），使用 deep watch
watch(() => messages.value, (newMessages, oldMessages) => {
  // 清理已删除消息的缓存
  const oldLength = oldMessages?.length || 0
  const newLength = newMessages.length

  if (newLength < oldLength) {
    const currentIds = new Set(messages.value.map(m => m.id))
    for (const [id] of messageBlockCache) {
      if (!currentIds.has(id)) {
        messageBlockCache.delete(id)
      }
    }
  }
  nextTick(() => {
    scrollToBottom();
  });
}, { deep: true });

const scrollToBottom = () => {
  if (scrollbarRef.value && innerRef.value) {
    const maxScrollTop = innerRef.value.clientHeight;
    scrollbarRef.value.setScrollTop(maxScrollTop);
  }
};

// 复制消息
const copyMessage = async (message: ChatMessage) => {
  // 获取消息的文本内容
  const textBlocks = message.content
    .filter(block => block.type === ContentType.TEXT)
    .map(block => 'text' in block ? block.text : '')
    .filter(Boolean)
    .join('\n')

  const success = await copyToClipboard(textBlocks)
  if (success) {
    ElMessage.success('消息已复制到剪贴板')
  } else {
    ElMessage.error('复制失败')
  }
}

// 工具消息展开状态管理
const isToolExpanded = (messageId: string) => {
  // 默认折叠工具消息
  return toolExpandedStates.value.get(messageId) ?? false
}

const toggleToolExpand = (messageId: string) => {
  const currentState = toolExpandedStates.value.get(messageId) ?? false
  toolExpandedStates.value.set(messageId, !currentState)
}

// 获取工具消息摘要
const getToolMessageSummary = (message: ChatMessage) => {
  // 统计内容块类型
  const textBlocks = message.content.filter(b => b.type === ContentType.TEXT)
  const toolCallBlocks = message.content.filter(b => b.type === ContentType.TOOL_CALL)
  const toolExecutionBlocks = message.content.filter(b => b.type === ContentType.TOOL_EXECUTION)

  const parts = []

  if (toolCallBlocks.length > 0) {
    parts.push(`${toolCallBlocks.length} 个工具调用`)
  }

  if (toolExecutionBlocks.length > 0) {
    parts.push(`${toolExecutionBlocks.length} 个执行记录`)
  }

  if (textBlocks.length > 0) {
    parts.push('附加信息')
  }

  return parts.length > 0 ? parts.join(' · ') : '工具消息'
}

// 用户消息展开状态管理
const isUserExpanded = (messageId: string) => {
  // 默认折叠用户消息
  return userExpandedStates.value.get(messageId) ?? false
}

const toggleUserExpand = (messageId: string) => {
  const currentState = userExpandedStates.value.get(messageId) ?? false
  userExpandedStates.value.set(messageId, !currentState)
}

// 判断用户消息是否应该始终展开(单行短文本)
const shouldAlwaysExpandUserMessage = (message: ChatMessage) => {
  const textBlocks = message.content.filter(b => b.type === ContentType.TEXT || b.type === ContentType.SIMPLE_TEXT)
  if (textBlocks.length === 0) return false

  const text = textBlocks[0] as unknown
  const textContent = text.text || ''

  // 如果文本为空或很短(少于50字符),不折叠
  return textContent.length <= 50
}

// 获取用户消息摘要
const getUserMessageSummary = (message: ChatMessage) => {
  const textBlocks = message.content.filter(b => b.type === ContentType.TEXT)
  if (textBlocks.length > 0) {
    const text = textBlocks[0] as unknown
    const preview = text.text?.substring(0, 50) || ''
    return preview + (text.text?.length > 50 ? '...' : '')
  }
  return '用户消息'
}

// ============================================================================
// 统一的消息展开状态管理（用于assistant和system消息）
// ============================================================================

// 助手消息默认展开,系统消息默认折叠
const isMessageExpanded = (messageId: string, role?: string) => {
  // 助手消息默认展开
  if (role === 'assistant') {
    return messageExpandedStates.value.get(messageId) ?? true
  }
  // 其他消息(如system)默认折叠
  return messageExpandedStates.value.get(messageId) ?? false
}

const toggleMessageExpand = (messageId: string) => {
  const currentState = messageExpandedStates.value.get(messageId) ?? false
  messageExpandedStates.value.set(messageId, !currentState)
}

// 获取系统消息摘要（用于折叠状态显示）
const getSystemMessageSummary = (message: ChatMessage) => {
  // 查找错误类型内容块
  const errorBlock = message.content.find(b => b.type === ContentType.ERROR)
  if (errorBlock && 'message' in errorBlock) {
    const errorMsg = (errorBlock as unknown).message || '未知错误'
    // 提取关键错误信息
    if (errorMsg.includes('Agent initialization failed')) {
      return 'Agent 初始化失败'
    }
    if (errorMsg.includes('No module named')) {
      return '缺少依赖模块'
    }
    if (errorMsg.includes('Connection')) {
      return '连接错误'
    }
    // 返回错误消息的前30个字符
    return errorMsg.substring(0, 30) + (errorMsg.length > 30 ? '...' : '')
  }

  // 查找文本内容块
  const textBlock = message.content.find(b => b.type === ContentType.TEXT || b.type === ContentType.SIMPLE_TEXT)
  if (textBlock) {
    const text = (textBlock as unknown).text || ''
    return text.substring(0, 30) + (text.length > 30 ? '...' : '')
  }

  return '系统消息'
}
</script>

<style scoped>
/* ========================================
   专利AI助手 - 专业精密工业风设计
   ======================================== */

/* Using system fonts for offline compatibility */

.message-area {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f8fafc !important;
  position: relative;
}

/* Subtle grid background pattern */
.message-area::before {
  display: none;
}

.message-list {
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.message-wrapper {
  display: flex;
  gap: 16px;
  animation: messageSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes messageSlideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ========================================
   USER MESSAGE - 专业右侧设计
   ======================================== */
.user-message-container {
  display: flex;
  flex-direction: row-reverse;
  gap: 12px;
  align-items: flex-start;
}

/* 用户消息头部 - 显示发送者和时间 */
.user-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  justify-content: flex-end; /* 右对齐 */
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.user-header-row .message-sender {
  font-weight: 600;
  font-size: 12px;
  color: #2d2d2d;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
  position: relative;
  overflow: hidden;
}

.user-avatar::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%);
  animation: shimmer 3s infinite;
}

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.user-avatar svg {
  width: 20px;
  height: 20px;
  position: relative;
  z-index: 1;
}

.message-content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 100%;
}

/* ========================================
   MESSAGE CARDS - 工业精密设计
   ======================================== */
.message-card {
  position: relative;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  overflow: hidden;
}

/* User card - minimal professional theme */
.user-card {
  position: relative;
  width: 100%;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  overflow: visible;
  display: flex;
  flex-direction: column;
}

.user-card.collapsed {
  cursor: pointer;
  min-height: 40px;
}

.user-card.collapsed .user-message-content {
  display: none;
}

.user-card.collapsed::before {
  content: attr(data-summary);
  color: #94a3b8;
  font-size: 13px;
  padding: 10px 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-card::before {
  display: none;
}

/* 始终展开的短消息样式 */
.user-card.always-expand {
  cursor: default;
}

.user-card.always-expand .user-message-content {
  display: block;
}

/* 用户消息操作按钮 */
.user-actions {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
  transition: all 0.2s ease;
  justify-content: flex-start;
  background: rgba(99, 102, 241, 0.05);
  border-top: 1px solid rgba(99, 102, 241, 0.1);
}

.user-actions .el-button {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(99, 102, 241, 0.2);
  transition: all 0.2s ease;
}

.user-actions .el-button:hover {
  color: #6366f1;
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.4);
}

.user-card .user-message-content {
  color: #1e293b;
  padding: 0 !important;
  font-size: 14px;
  line-height: 1.6;
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  pointer-events: none;
}

/* 在折叠状态下隐藏内容区域 */
.user-card.collapsed .user-message-content {
  display: none;
}

.user-card .user-message-content .user-text-block {
  color: #1e293b;
  margin: 0;
  padding: 0;
  line-height: 1.6;
  font-weight: 400;
  user-select: none !important;
  -webkit-user-select: none !important;
  -moz-user-select: none !important;
  -ms-user-select: none !important;
  pointer-events: none !important;
  cursor: default !important;
}

.user-card .user-message-content p {
  color: #1e293b;
  margin: 0;
  line-height: 1.6;
  font-weight: 400;
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  pointer-events: none;
}

.user-card .user-message-content * {
  user-select: none !important;
  -webkit-user-select: none !important;
  -moz-user-select: none !important;
  -ms-user-select: none !important;
  pointer-events: none !important;
}

/* Assistant card - refined light theme */
.assistant-card {
  width: 100%;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.3),
    0 8px 24px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
}

.assistant-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, #06b6d4, #0891b2);
  opacity: 0.6;
}

/* Tool card - utilitarian design */
.tool-card {
  width: 100%;
  background: rgba(30, 31, 46, 0.8);
  border: 1px solid rgba(255, 152, 0, 0.3);
  border-radius: 10px;
  backdrop-filter: blur(10px);
  overflow: hidden;
  padding: 0 !important;  /* 确保无内边距 */
}

.tool-card.collapsed {
  cursor: pointer;
}

.tool-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, #f97316, #fb923c);
  opacity: 0.7;
}

/* 工具消息卡片头部 */
.tool-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0 !important;  /* 统一简化 padding */
  gap: 12px;
  transition: all 0.2s ease;
}

.tool-card-header.clickable {
  cursor: pointer;
  user-select: none;
}

.tool-card-header.clickable:hover {
  background: transparent;
}

.tool-header-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.tool-icon-text {
  font-size: 16px;
  flex-shrink: 0;
}

.tool-title-text {
  font-weight: 600;
  font-size: 14px;
  color: #e2e8f0;
  flex-shrink: 0;
}

.tool-summary {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 400;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-header-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.tool-header-actions .el-button {
  padding: 4px;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.2s ease;
}

.tool-header-actions .el-button:hover {
  color: #f97316;
  background: rgba(249, 115, 22, 0.15);
  border-color: rgba(249, 115, 22, 0.3);
}

/* 箭头旋转动画 */
.rotate-180 {
  transform: rotate(180deg);
}

.tool-header-actions .el-icon {
  transition: transform 0.3s ease;
}

/* ========================================
   MESSAGE CONTENT - 精密排版
   ======================================== */
.assistant-message-content {
  padding: 0 !important;
  color: #1a202c;
  font-size: 15px;
  line-height: 1.7;
}

.tool-message-content {
  padding: 0 !important;
  color: #e2e8f0;
  font-size: 14px;
}

/* ========================================
   MESSAGE ACTIONS - 精密交互设计
   ======================================== */
.message-actions {
  display: flex;
  gap: 6px;
  padding: 10px 14px;
  transition: all 0.2s ease;
}

.assistant-actions {
  justify-content: flex-start;
  padding: 12px 20px;
  background: rgba(6, 182, 212, 0.05);
  border-top: 1px solid rgba(6, 182, 212, 0.1);
}

.assistant-actions .el-button {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(6, 182, 212, 0.2);
  transition: all 0.2s ease;
}

.assistant-actions .el-button:hover {
  color: #06b6d4;
  background: rgba(6, 182, 212, 0.1);
  border-color: rgba(6, 182, 212, 0.4);
}

/* ========================================
   EDIT MODE - 编辑体验（已移除）
   ======================================== */

/* ========================================
   TOOL MESSAGE - 工具消息
   ======================================== */
.tool-message-container {
  display: flex;
  gap: 12px;
}

.tool-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #f97316 0%, #fb923c 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(249, 115, 22, 0.3);
}

/* ========================================
   ASSISTANT MESSAGE - AI消息
   ======================================== */
.assistant-message-container {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.assistant-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #06b6d4 0%, #0891b2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 700;
  font-size: 15px;
  box-shadow: 0 4px 12px rgba(6, 182, 212, 0.3);
}

.assistant-header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.message-sender {
  font-weight: 600;
  font-size: 14px;
  color: #0c4a6e;
  letter-spacing: -0.02em;
}

.message-time {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
  font-family: 'JetBrains Mono', monospace;
}

/* ========================================
   INDEPENDENT BUBBLES - 独立气泡
   ======================================== */
.independent-bubble {
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(10px);
}

.reasoning-bubble {
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.1) 0%, rgba(245, 158, 11, 0.08) 100%);
  border-color: rgba(245, 158, 11, 0.3);
  position: relative;
}

.reasoning-bubble::before {
  content: '思考';
  position: absolute;
  top: -8px;
  left: 12px;
  background: rgba(245, 158, 11, 0.9);
  color: white;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.tool-call-bubble {
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  margin-bottom: 8px !important;
}

/* ========================================
   TYPING INDICATOR - 输入指示器
   ======================================== */
.typing-indicator {
  display: inline-block;
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.dots {
  display: flex;
  gap: 6px;
  align-items: center;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #06b6d4;
  animation: typing 1.4s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  30% {
    opacity: 1;
    transform: scale(1.2);
  }
}

/* ========================================
   CONTENT BLOCKS - 内容块
   ======================================== */
.content-block {
  margin-bottom: 8px;
  padding: 8px 0;
}

.content-block:first-child {
  padding-top: 0;
}

.content-block:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
}

/* ========================================
   RESPONSIVE DESIGN - 响应式
   ======================================== */
@media (max-width: 768px) {
  .message-list {
    padding: 20px 16px;
    gap: 20px;
  }

  .message-content-wrapper {
    max-width: 100%;
  }

  .user-avatar,
  .assistant-avatar,
  .tool-avatar {
    width: 32px;
    height: 32px;
  }

  .assistant-message-content {
    font-size: 14px;
  }

  .user-card .user-message-content {
    font-size: 14px;
  }
}

/* Scrollbar Styling */
.assistant-message-content::-webkit-scrollbar {
  width: 6px;
}

.assistant-message-content::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 3px;
}

.assistant-message-content::-webkit-scrollbar-thumb {
  background: rgba(6, 182, 212, 0.5);
  border-radius: 3px;
}

.assistant-message-content::-webkit-scrollbar-thumb:hover {
  background: rgba(6, 182, 212, 0.8);
}

/* ========================================
   SYSTEM MESSAGE - 系统消息（错误等）
   ======================================== */
.system-message-container {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: center;
  width: 100%;
}

.system-card {
  position: relative;
  width: 100%;
  max-width: 600px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-left: 3px solid #ef4444;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.1);
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s ease;
}

.system-card:hover {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
}

/* 折叠状态的系统卡片 */
.system-card.collapsed {
  padding: 12px 16px;
}

/* 系统消息摘要 */
.system-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #dc2626;
  font-size: 14px;
  font-weight: 500;
}

.system-summary .error-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.system-summary .summary-text {
  flex: 1;
  line-height: 1.4;
}

.system-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #ef4444, #dc2626);
  opacity: 0.8;
}

.system-message-content {
  padding: 16px !important;
  color: #1a202c;
  font-size: 14px;
  line-height: 1.6;
}

.system-actions {
  display: flex;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.03);
  border-top: 1px solid rgba(239, 68, 68, 0.1);
  justify-content: flex-end;
}

.system-actions .el-button {
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(239, 68, 68, 0.15);
  transition: all 0.2s ease;
}

.system-actions .el-button:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
}
</style>

