<!-- eslint-disable vue/multi-word-component-names -->
<template>
  <div class="msg" :class="[message.role, { 'msg--user': message.role === 'user' }]">
    <!-- Avatar -->
    <div class="msg__avatar">
      <div v-if="message.role !== 'user'" class="avatar-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
          <path d="M9 9h6M9 12h6M9 15h4"/>
        </svg>
      </div>
      <div v-else class="avatar-user">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
    </div>

    <!-- Content -->
    <div class="msg__content">
      <!-- Header -->
      <div class="msg__header">
        <span class="msg__sender">{{ getSenderName(message.role) }}</span>
        <span class="msg__time">{{ formatTimestamp(message.timestamp, 'time') }}</span>
      </div>

      <!-- Reasoning Blocks -->
      <div v-for="(block, index) in reasoningBlocks" :key="`reasoning-${index}`" class="msg__block msg__block--reasoning">
        <component
          :is="getComponentForBlock(block.type)"
          :block="block as unknown"
          @content-action="handleContentAction"
        />
      </div>

      <!-- Tool Execution Blocks -->
      <div v-for="(block, index) in toolExecutionBlocks" :key="`tool-execution-${index}`" class="msg__block msg__block--tool">
        <component
          :is="getComponentForBlock(block.type)"
          :block="block as unknown"
          @content-action="handleContentAction"
        />
      </div>

      <!-- Simple Text -->
      <div v-for="(block, index) in simpleTextBlocks" :key="`simple-text-${index}`" class="msg__simple">
        {{ block.text }}
      </div>

      <!-- Main Message Bubble -->
      <div v-if="otherBlocks.length > 0" class="msg__bubble">
        <div v-for="(block, index) in otherBlocks" :key="index" class="msg__block">
          <component
            :is="getComponentForBlock(block.type)"
            :block="block as unknown"
            :is-streaming="isStreaming && block.type === 'text'"
            @content-action="handleContentAction"
          />
        </div>
        <div v-if="message.taskId" class="msg__task">
          <span class="task-tag">TASK: {{ message.taskId.slice(0, 8) }}</span>
        </div>
      </div>

      <!-- Metadata -->
      <div v-if="message.metadata" class="msg__meta">
        <span v-for="(value, key) in visibleMetadata" :key="key" class="meta-item">
          <span class="meta-key">{{ key }}</span>
          <span class="meta-val">{{ value }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
 
 
 




import { defineAsyncComponent, provide } from 'vue'
import type { PropType } from 'vue'
import { type ChatMessage, ContentType, MessageRole, type SimpleTextContentBlock } from '@/types/websocket'
import { formatTimestamp } from '@/utils/formatters'

const props = defineProps({
  message: {
    type: Object as PropType<ChatMessage>,
    required: true,
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

// Collect all images from this message
const messageImages = computed(() => {
  return props.message.content
    .filter(block => block.type === ContentType.IMAGE)
    .map((block: unknown) => ({
      src: block.image,
      filename: block.filename
    }))
})

// Provide image viewer context for child components
provide('messageImages', messageImages)

// Content component mapping
const componentMap = {
  [ContentType.TEXT]: () => import('./content/TextContent.vue'),
  [ContentType.IMAGE]: () => import('./content/ImageContent.vue'),
  [ContentType.AUDIO]: () => import('./content/AudioContent.vue'),
  [ContentType.VIDEO]: () => import('./content/VideoContent.vue'),
  [ContentType.FILE]: () => import('./content/FileContent.vue'),
  [ContentType.THINKING]: () => import('./content/ThinkingContent.vue'),
  [ContentType.TOOL_CALL]: () => import('./content/ToolCallContent.vue'),
  [ContentType.TOOL_RESULT]: () => import('./content/ToolResultContent.vue'),
  [ContentType.TOOL_EXECUTION]: () => import('./content/ToolExecutionContent.vue'),
  [ContentType.ERROR]: () => import('./content/ErrorContent.vue'),
  [ContentType.SYSTEM_COMMAND_RESULT]: () => import('./content/SystemCommandResultContent.vue'),
  [ContentType.A2UI_SURFACE]: () => import('./a2ui/A2UISurfaceContent.vue'),
}

const getComponentForBlock = (type: ContentType) => {
  const componentLoader = componentMap[type]
  return componentLoader ? defineAsyncComponent(componentLoader) : defineAsyncComponent(() => import('./content/TextContent.vue'))
}

const getSenderName = (role: MessageRole | string) => {
  switch (role) {
    case MessageRole.USER:
      return 'You'
    case MessageRole.ASSISTANT:
      return 'AI'
    case MessageRole.SYSTEM:
      return 'System'
    case MessageRole.TOOL:
      return 'Tool'
    default:
      return role
  }
}

const visibleMetadata = computed(() => {
  if (!props.message.metadata) return {}
  const visible: Record<string, unknown> = {}
  const keysToShow = ['model', 'workspaceId']
  keysToShow.forEach(key => {
    if (props.message.metadata && props.message.metadata[key] !== undefined) {
      visible[key] = props.message.metadata[key]
    }
  })
  return visible
})

const reasoningBlocks = computed(() => {
  return props.message.content.filter(block => block.type === 'reasoning')
})

const toolExecutionBlocks = computed(() => {
  return props.message.content.filter(block => block.type === 'tool_execution')
})

const simpleTextBlocks = computed(() => {
  return props.message.content.filter(block => block.type === 'simple_text') as SimpleTextContentBlock[]
})

const otherBlocks = computed(() => {
  return props.message.content.filter(block =>
    block.type !== 'reasoning' && block.type !== 'tool_execution' && block.type !== 'simple_text'
  )
})

const handleContentAction = (action: string, data: unknown) => {
  emit('contentAction', action, data)
}
</script>

<style scoped>
/* Modern Message Design - 优雅现代风格 */
.msg {
  --msg-gap: 12px;
  --msg-avatar: 36px;
  --msg-radius: 16px;
  --msg-padding: 14px 18px;
  --msg-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  --msg-shadow-hover: 0 4px 20px rgba(0, 0, 0, 0.12);

  display: flex;
  gap: var(--msg-gap);
  padding: 16px 20px;
  animation: msgEnter 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
  opacity: 0;
  transform: translateY(12px) scale(0.98);
}

.msg:nth-child(1) { animation-delay: 0ms; }
.msg:nth-child(2) { animation-delay: 60ms; }
.msg:nth-child(3) { animation-delay: 120ms; }
.msg:nth-child(n+4) { animation-delay: 180ms; }

@keyframes msgEnter {
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* Avatar - 现代渐变设计 */
.msg__avatar {
  flex-shrink: 0;
  width: var(--msg-avatar);
  height: var(--msg-avatar);
}

.avatar-icon,
.avatar-user {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: transform 0.2s ease;
}

.avatar-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.avatar-icon:hover {
  transform: scale(1.05);
}

.avatar-icon svg {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
}

.avatar-user {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: #fff;
}

.avatar-user:hover {
  transform: scale(1.05);
}

.avatar-user svg {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
}

.msg--user {
  flex-direction: row-reverse;
}

.msg--user .msg__content {
  align-items: flex-end;
}

/* Content */
.msg__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  /* Fix horizontal overflow */
  max-width: 100%;
  overflow: hidden;
}

/* Header - 更优雅的头部设计 */
.msg__header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px;
  font-size: 12px;
  margin-bottom: 2px;
}

.msg__sender {
  font-weight: 600;
  color: #2d3748;
  letter-spacing: 0.02em;
  font-size: 13px;
}

.msg__time {
  font-size: 11px;
  color: #a0aec0;
  font-weight: 500;
  letter-spacing: 0.03em;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 12px;
}

.msg--user .msg__header {
  flex-direction: row-reverse;
}

/* Blocks */
.msg__block {
  position: relative;
}

.msg__block:not(:last-child) {
  margin-bottom: 8px;
  padding-bottom: 8px;
}

.msg__block:not(:first-child) {
  padding-top: 8px;
}

/* Special blocks */
.msg__block--reasoning {
  margin-bottom: 10px;
}

.msg__block--tool {
  margin-bottom: 10px;
}

/* Simple text - 更柔和的样式 */
.msg__simple {
  font-size: 12px;
  color: #718096;
  line-height: 1.5;
  padding: 4px 6px;
  font-weight: 400;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 6px;
  border-left: 2px solid #cbd5e0;
}

/* Bubble - 统一现代卡片设计 */
.msg__bubble {
  background: linear-gradient(135deg, #ffffff 0%, #fafafa 100%);
  border: 1px solid #e2e8f0;
  border-radius: var(--msg-radius);
  padding: var(--msg-padding);
  box-shadow: var(--msg-shadow);
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  /* Fix horizontal overflow */
  max-width: 100%;
  overflow-x: hidden;
}

/* 顶部颜色条 - 已移除，所有消息使用统一样式 */
.msg__bubble::before {
  display: none;
}

.msg__bubble:hover {
  box-shadow: var(--msg-shadow-hover);
  border-color: #cbd5e0;
  transform: translateY(-1px);
}

/* 统一圆角 */
.msg__bubble {
  border-radius: var(--msg-radius);
}

/* Task info */
.msg__task {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.task-tag {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.7;
  color: #718096;
  padding: 4px 10px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 12px;
  display: inline-block;
}

/* Metadata - 更优雅的元数据显示 */
.msg__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 0;
  margin-top: 4px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #a0aec0;
  font-weight: 500;
  padding: 4px 10px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.meta-item:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #718096;
}

.meta-key {
  opacity: 0.8;
  font-weight: 600;
}

.meta-val {
  color: #4a5568;
  font-weight: 600;
}

/* Responsive */
@media (max-width: 640px) {
  .msg {
    padding: 12px 16px;
  }

  .msg__bubble {
    padding: 12px 16px;
  }

  .msg__header {
    font-size: 11px;
  }

  .msg__sender {
    font-size: 12px;
  }

  .task-tag {
    font-size: 9px;
  }
}

/* 深色模式支持 - 统一样式 */
@media (prefers-color-scheme: dark) {
  .msg {
    --msg-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
    --msg-shadow-hover: 0 4px 20px rgba(0, 0, 0, 0.4);
  }

  .msg__sender {
    color: #e2e8f0;
  }

  /* 统一的消息气泡样式 - 深色模式 */
  .msg__bubble {
    background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
    border-color: #4a5568;
  }

  .msg__bubble:hover {
    border-color: #718096;
  }

  /* 深色模式下不显示颜色条 - 统一样式 */
  .msg__bubble::before {
    display: none;
  }

  .msg__simple {
    color: #a0aec0;
    background: rgba(255, 255, 255, 0.05);
    border-left-color: #718096;
  }

  .meta-item {
    color: #a0aec0;
    background: rgba(255, 255, 255, 0.05);
  }

  .meta-item:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #e2e8f0;
  }

  .meta-val {
    color: #e2e8f0;
  }

  .task-tag {
    background: rgba(255, 255, 255, 0.05);
    color: #cbd5e1;
  }
}
</style>
