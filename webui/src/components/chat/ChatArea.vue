/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-container class="chat-area">
    <el-scrollbar ref="scrollbarRef" class="message-display-scrollbar">
      <div ref="innerRef" class="message-display">
        <!-- Load More Button for Historical Messages -->
        <div v-if="workspaceStore.messagePagination.hasMore" class="load-more-container">
          <el-button
            @click="handleLoadMore"
            :loading="workspaceStore.isLoadingMore"
            class="load-more-button"
            text
          >
            <template v-if="!workspaceStore.isLoadingMore">
              加载更多历史消息 (还有 {{ workspaceStore.messagePagination.total - workspaceStore.messagePagination.loaded }} 条)
            </template>
            <template v-else>
              加载中...
            </template>
          </el-button>
        </div>

        <MessageStream
          :messages="chatStore.messages"
          :is-thinking="chatStore.isThinking"
          @scroll-to-bottom="scrollToBottom"
        />
      </div>
    </el-scrollbar>

    <el-footer class="message-input-footer">
      <div class="message-input-wrapper">
        <el-button :icon="Paperclip" circle @click="handleFileUpload" />
        <el-input
          v-model="newMessage"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="请输入消息..."
          @keydown.enter.prevent="handleSendMessage"
          class="message-textarea"
          :disabled="!chatStore.isConnected"
        />
        <el-button
          type="primary"
          :icon="Promotion"
          circle
          :disabled="!newMessage.trim() || isLoading || !chatStore.isConnected"
          @click="handleSendMessage"
        />
      </div>
      <div class="connection-status" v-if="!chatStore.isConnected">
        <el-alert
          :title="getConnectionStatusText()"
          :type="getConnectionStatusType()"
          :closable="false"
          show-icon
        />
      </div>
    </el-footer>
  </el-container>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import MessageStream from './MessageStream.vue';
import { ElContainer, ElScrollbar, ElFooter, ElInput, ElButton, ElAlert } from 'element-plus';
import { Paperclip, Promotion } from '@element-plus/icons-vue';
import type { ElScrollbar as ElScrollbarType } from 'element-plus';
import { ConnectionState } from '@/types/websocket';

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const newMessage = ref('');
const scrollbarRef = ref<InstanceType<typeof ElScrollbarType>>();
const innerRef = ref<HTMLDivElement>();

const isLoading = computed(() => {
  return chatStore.isThinking;
});

const handleSendMessage = () => {
  if (newMessage.value.trim() && !isLoading.value && chatStore.isConnected) {
    chatStore.sendMessage(newMessage.value);
    newMessage.value = '';
  }
};

const handleFileUpload = () => {
  // TODO: 实现文件上传功能
};

const handleLoadMore = async () => {
  if (!workspaceStore.currentConversationId) {
    console.warn('[CHAT_AREA] No conversation selected');
    return;
  }

  try {
    // 调用 workspace store 的 loadMoreMessages 方法
    const newMessages = await workspaceStore.loadMoreMessages(
      workspaceStore.currentConversationId,
      chatStore.convertBackendMessage.bind(chatStore)
    );

    // 将新加载的消息添加到现有消息列表的顶部
    if (newMessages.length > 0) {
      chatStore.messages.unshift(...newMessages);
    }
  } catch (error) {
    console.error('[CHAT_AREA] Failed to load more messages:', error);
  }
};

const scrollToBottom = () => {
  nextTick(() => {
    if (scrollbarRef.value && innerRef.value) {
      const maxScrollTop = innerRef.value.clientHeight;
      scrollbarRef.value.setScrollTop(maxScrollTop);
    }
  });
};

const getConnectionStatusText = () => {
  switch (chatStore.connectionStatus) {
    case ConnectionState.CONNECTING:
      return '正在连接...';
    case ConnectionState.RECONNECTING:
      return '重新连接中...';
    case ConnectionState.ERROR:
      return '连接错误，请刷新页面重试';
    default:
      return '连接已断开，请刷新页面重试';
  }
};

const getConnectionStatusType = () => {
  switch (chatStore.connectionStatus) {
    case ConnectionState.CONNECTING:
    case ConnectionState.RECONNECTING:
      return 'warning';
    case ConnectionState.ERROR:
      return 'error';
    default:
      return 'info';
  }
};

// 监听消息变化，自动滚动到底部
watch([() => chatStore.messages, isLoading], scrollToBottom, { deep: true, immediate: true });

// 注意：不在这里调用 initializeConnection()
// WebSocket 连接已在 App.vue 的 onMounted 中统一初始化
// 避免重复创建连接或监听器
</script>

<style scoped>
.chat-area {
  height: 100%;
  background-color: var(--color-surface-1);
  color: var(--color-text-primary);
  display: flex;
  flex-direction: column;
}

.message-display-scrollbar {
  flex-grow: 1;
}

.message-display {
  padding: var(--spacing-xl);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.load-more-container {
  display: flex;
  justify-content: center;
  padding: var(--spacing-md) 0;
  margin-bottom: var(--spacing-md);
}

.load-more-button {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  transition: all var(--duration-base) var(--ease-default);
}

.load-more-button:hover {
  color: var(--color-primary);
}

.message-input-footer {
  border-top: 1px solid var(--color-border-default);
  padding: var(--spacing-lg);
  background-color: var(--color-surface-1);
  height: auto;
  position: relative;
}

.message-input-footer::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  width: 100px;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--color-primary), transparent);
  transform: translateX(-50%);
  border-radius: var(--radius-full);
}

.message-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background-color: var(--color-surface-2);
  border-radius: var(--radius-xl);
  border: 2px solid var(--color-border-default);
  transition: all var(--duration-base) var(--ease-default);
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  box-shadow: var(--shadow-sm);
}

.message-input-wrapper:focus-within {
  border-color: var(--color-primary);
  background-color: var(--color-surface-1);
  box-shadow:
    var(--shadow-glow),
    0 0 0 4px rgba(var(--color-primary-rgb), 0.1);
  transform: translateY(-2px);
}

.message-textarea {
  flex: 1;
}

:deep(.el-textarea__inner) {
  background-color: transparent;
  border: none;
  box-shadow: none;
  resize: none;
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--color-text-primary);
  font-family: var(--font-body);
  font-size: var(--text-base);
  line-height: 1.6;
}

:deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

:deep(.el-textarea__inner::placeholder) {
  color: var(--color-text-tertiary);
}

/* Button styling */
:deep(.el-button) {
  transition: all var(--duration-base) var(--ease-default);
}

:deep(.el-button.is-circle) {
  flex-shrink: 0;
}

:deep(.el-button--primary) {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  border: none;
}

:deep(.el-button--primary:hover) {
  transform: scale(1.05);
}

:deep(.el-button:not(.el-button--primary)) {
  background-color: var(--color-surface-3);
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
}

:deep(.el-button:not(.el-button--primary):hover) {
  background-color: var(--color-primary-lighter);
  color: var(--color-primary);
  border-color: var(--color-primary);
}

.connection-status {
  max-width: 900px;
  margin: var(--spacing-md) auto 0;
  width: 100%;
}

:deep(.el-alert) {
  border-radius: var(--radius-lg);
  border: none;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive */
@media (max-width: 768px) {
  .message-display {
    padding: var(--spacing-md);
  }

  .message-input-footer {
    padding: var(--spacing-md);
  }

  .message-input-wrapper {
    padding: var(--spacing-sm);
    gap: var(--spacing-sm);
  }
}
</style>