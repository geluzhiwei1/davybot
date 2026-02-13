/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-header class="top-bar">
    <div class="left-content">
      <el-button @click="$emit('toggle-mobile-panel')" class="mobile-menu-button" :icon="Menu" text circle />
      <el-button @click="$emit('toggle-side-panel')" :icon="isSidePanelCollapsed ? DArrowRight : DArrowLeft" text
        circle />
      <div>
        <h2 class="agent-name">{{ agentName }}</h2>
      </div>
    </div>

    <div class="center-content">
      <div class="conversation-title">
        {{ conversationTitle }}
      </div>
    </div>

    <div class="right-content">

      <!-- 连接状态标签 -->
      <el-tag :type="statusType" effect="light" round>
        <div class="status-indicator">
          <span class="status-dot" :class="statusDotClass"></span>
          {{ statusText }}
        </div>
      </el-tag>

      <!-- 语言选择器 -->
      <LanguageSelector />

      <!-- 主题切换按钮 -->
      <ThemeToggle />
    </div>
  </el-header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import { ElHeader, ElButton, ElTag } from 'element-plus';
import { Menu, DArrowLeft, DArrowRight } from '@element-plus/icons-vue';
import ThemeToggle from '@/components/ThemeToggle.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';

interface Props {
  isSidePanelCollapsed?: boolean;
}

withDefaults(defineProps<Props>(), {
  isSidePanelCollapsed: false
});

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const { connectionStatus } = storeToRefs(chatStore);
const { currentConversation, isTempConversation } = storeToRefs(workspaceStore);

const agentName = ref('大微');

// 计算当前会话标题
const conversationTitle = computed(() => {
  if (isTempConversation.value) {
    return '新对话';
  }
  if (currentConversation.value) {
    return currentConversation.value.title || currentConversation.value.name || '未命名会话';
  }
  return '请选择或创建会话';
});

const statusType = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'success';
    case 'connecting':
    case 'reconnecting': return 'warning';
    case 'error':
    case 'disconnected': return 'danger';
    default: return 'info';
  }
});

const statusDotClass = computed(() => {
  return `status-dot-${connectionStatus.value}`;
});

const statusText = computed(() => {
  const map = {
    connected: '已连接',
    connecting: '连接中',
    reconnecting: '重连中',
    error: '连接错误',
    disconnected: '已断开',
  };
  return map[connectionStatus.value] || '未连接';
});
</script>

<style scoped>
.top-bar {
  display: flex !important;
  align-items: center;
  height: 48px;
  padding: 0 12px;
  background-color: var(--el-bg-color-overlay);
  border-bottom: 1px solid var(--el-border-color-light);
  gap: 12px;
  position: relative;
  z-index: 1;
}

.left-content {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1 1 0;
  min-width: 0;
}

.center-content {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1 1 0;
  min-width: 0;
}

.right-content {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex: 1 1 0;
  min-width: 0;
}

.conversation-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  padding: 6px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  max-width: 300px; /* 减少最大宽度，为右侧内容留出更多空间 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: all 0.2s;
}

.conversation-title:hover {
  background: var(--el-fill-color);
}

.mobile-menu-button {
  display: none;
}

@media (max-width: 768px) {
  .mobile-menu-button {
    display: inline-flex;
  }

  .top-bar {
    height: 44px;
    padding: 0 8px;
  }

  .agent-name {
    font-size: 14px;
  }

  .conversation-title {
    max-width: 120px; /* 移动端进一步减少宽度 */
    font-size: 13px;
    padding: 4px 8px;
  }
}

.agent-avatar {
  background-color: var(--el-color-primary);
}

.agent-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.agent-role {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot-connected {
  background-color: var(--el-color-success);
}

.status-dot-connecting,
.status-dot-reconnecting {
  background-color: var(--el-color-warning);
  animation: pulse 1.5s infinite;
}

.status-dot-error,
.status-dot-disconnected {
  background-color: var(--el-color-error);
}

.status-dot-undefined {
  background-color: var(--el-color-info);
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}
</style>