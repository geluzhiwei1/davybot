/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div ref="streamContainer" class="stream">
    <div v-for="message in messages" :key="message.id" class="stream__item">
      <Message
        :message="message"
        :is-streaming="isMessageStreaming(message)"
        @content-action="handleContentAction"
      />
    </div>

    <!-- Streaming indicator -->
    <div v-if="isThinking" class="stream__thinking">
      <LoadingIndicator
        type="thinking"
        :show-thinking="true"
        :current-thinking="currentThinking"
      />
    </div>

    <!-- Connection status -->
    <div v-if="showConnectionStatus" class="stream__status">
      <div class="status-badge" :class="`status-badge--${connectionStatusType}`">
        <div class="status-dot"></div>
        <span>{{ connectionStatusText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { ConnectionState } from '@/types/websocket'
import Message from './Message.vue'
import LoadingIndicator from './LoadingIndicator.vue'

interface Props {
  messages: unknown[]
  isThinking: boolean
  currentThinking?: string
  connectionStatus?: ConnectionState
}

const props = withDefaults(defineProps<Props>(), {
  currentThinking: '',
  connectionStatus: ConnectionState.CONNECTED
})

const emit = defineEmits<{
  scrollToBottom: []
  contentAction: [action: string, data: unknown]
}>()

const streamContainer = ref<HTMLDivElement | null>(null)

const showConnectionStatus = computed(() => {
  return props.connectionStatus !== ConnectionState.CONNECTED
})

const connectionStatusText = computed(() => {
  switch (props.connectionStatus) {
    case ConnectionState.CONNECTING:
      return '正在连接...'
    case ConnectionState.RECONNECTING:
      return '重新连接中...'
    case ConnectionState.ERROR:
      return '连接错误'
    case ConnectionState.DISCONNECTED:
      return '连接已断开'
    default:
      return ''
  }
})

const connectionStatusType = computed(() => {
  switch (props.connectionStatus) {
    case ConnectionState.CONNECTING:
    case ConnectionState.RECONNECTING:
      return 'warning'
    case ConnectionState.ERROR:
      return 'error'
    case ConnectionState.DISCONNECTED:
      return 'info'
    default:
      return 'success'
  }
})

const scrollToBottom = () => {
  nextTick(() => {
    if (streamContainer.value) {
      const scrollOptions = {
        top: streamContainer.value.scrollHeight,
        behavior: 'smooth' as ScrollBehavior
      }
      streamContainer.value.scrollTo(scrollOptions)
    }
  })
}

const handleContentAction = (action: string, data: unknown) => {
  emit('contentAction', action, data)
}

const isMessageStreaming = (message: unknown) => {
  // 判断消息是否正在流式输出
  // 如果isThinking为true且是最后一条assistant消息，则认为正在streaming
  if (!props.isThinking) return false
  if (message.role !== 'assistant') return false
  const lastMessage = props.messages[props.messages.length - 1]
  return message.id === lastMessage.id
}

watch(() => props.messages, () => {
  scrollToBottom()
}, { deep: true })

watch(() => props.isThinking, (newValue) => {
  if (newValue) {
    scrollToBottom()
  }
})

watch(() => props.connectionStatus, () => {
  scrollToBottom()
})

defineExpose({
  scrollToBottom
})
</script>

<style scoped>
/* Message Stream - Swiss Design */
.stream {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  scroll-behavior: smooth;
}

.stream__item {
  position: relative;
}

/* Thinking indicator */
.stream__thinking {
  padding: 0 16px;
  margin: 8px 0;
  animation: fadeIn 0.3s ease forwards;
}

/* Connection status */
.stream__status {
  padding: 0 16px;
  margin: 12px 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  animation: slideIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ddd;
  animation: pulse 2s ease-in-out infinite;
}

.status-badge--warning .status-dot {
  background: #f59e0b;
}

.status-badge--error .status-dot {
  background: #ef4444;
}

.status-badge--info .status-dot {
  background: #3b82f6;
}

/* Animations */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* Custom scrollbar */
.stream::-webkit-scrollbar {
  width: 4px;
}

.stream::-webkit-scrollbar-track {
  background: transparent;
}

.stream::-webkit-scrollbar-thumb {
  background: #e0e0e0;
  border-radius: 2px;
  transition: background 0.2s ease;
}

.stream::-webkit-scrollbar-thumb:hover {
  background: #d0d0d0;
}

/* Responsive */
@media (max-width: 640px) {
  .stream {
    padding: 8px 0;
  }

  .stream__thinking,
  .stream__status {
    padding: 0 12px;
  }
}
</style>
