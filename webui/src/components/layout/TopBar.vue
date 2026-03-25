/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-header class="top-bar">
    <div class="left-content">
      <el-button @click="$emit('toggle-mobile-panel')" class="mobile-menu-button" :icon="Menu" text circle />
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

      <!-- 缩放控制 -->
      <div class="zoom-controls">
        <el-button-group>
          <el-tooltip :content="t('topBar.zoomOut')" placement="bottom">
            <el-button :icon="ZoomOut" :disabled="!canZoomOut" @click="handleZoomOut" text size="small" />
          </el-tooltip>
          <el-dropdown @command="handleZoomCommand" trigger="click">
            <el-button text size="small" class="zoom-display">
              {{ zoomPercentage }}
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="0.5">50%</el-dropdown-item>
                <el-dropdown-item command="0.67">67%</el-dropdown-item>
                <el-dropdown-item command="0.75">75%</el-dropdown-item>
                <el-dropdown-item command="0.8">80%</el-dropdown-item>
                <el-dropdown-item command="0.9">90%</el-dropdown-item>
                <el-dropdown-item command="1.0">100%</el-dropdown-item>
                <el-dropdown-item command="1.1">110%</el-dropdown-item>
                <el-dropdown-item command="1.25">125%</el-dropdown-item>
                <el-dropdown-item command="1.5">150%</el-dropdown-item>
                <el-dropdown-item command="1.75">175%</el-dropdown-item>
                <el-dropdown-item command="2.0">200%</el-dropdown-item>
                <el-dropdown-item command="2.5">250%</el-dropdown-item>
                <el-dropdown-item command="3.0">300%</el-dropdown-item>
                <el-dropdown-item divided command="reset">{{ t('topBar.resetZoom') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip :content="t('topBar.zoomIn')" placement="bottom">
            <el-button :icon="ZoomIn" :disabled="!canZoomIn" @click="handleZoomIn" text size="small" />
          </el-tooltip>
        </el-button-group>
      </div>

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
import { useI18n } from 'vue-i18n';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import { ElHeader, ElButton, ElTag, ElButtonGroup, ElTooltip, ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus';
import { Menu, ZoomIn, ZoomOut } from '@element-plus/icons-vue';
import ThemeToggle from '@/components/ThemeToggle.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import { useZoom } from '@/composables/useZoom';

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const { t } = useI18n();
const { connectionStatus } = storeToRefs(chatStore);
const { currentConversation } = storeToRefs(workspaceStore);

const agentName = ref('Dawei');

// Zoom functionality
const {
  zoomLevel,
  zoomPercentage,
  canZoomIn,
  canZoomOut,
  zoomIn,
  zoomOut,
  zoomReset,
  setZoom
} = useZoom();

const handleZoomIn = () => {
  zoomIn();
};

const handleZoomOut = () => {
  zoomOut();
};

const handleZoomCommand = (command: string | number) => {
  if (command === 'reset') {
    zoomReset();
  } else {
    const level = typeof command === 'string' ? parseFloat(command) : command;
    setZoom(level);
  }
};

// 计算当前会话标题
const conversationTitle = computed(() => {
  if (currentConversation.value) {
    // 尝试多个可能的字段名（后端可能使用不同的命名）
    const conv = currentConversation.value as any;
    return conv?.title || conv?.name || t('topBar.unnamedConversation');
  }

  return t('topBar.selectOrCreateConversation');
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
    connected: t('topBar.connected'),
    connecting: t('topBar.connecting'),
    reconnecting: t('topBar.reconnecting'),
    error: t('topBar.connectionError'),
    disconnected: t('topBar.disconnected'),
  };
  return map[connectionStatus.value] || t('topBar.notConnected');
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
  max-width: 300px;
  /* 减少最大宽度，为右侧内容留出更多空间 */
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
    max-width: 120px;
    /* 移动端进一步减少宽度 */
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

.zoom-controls {
  display: flex;
  align-items: center;
}

.zoom-display {
  min-width: 48px;
  font-size: 12px;
  font-weight: 500;
  padding: 4px 8px !important;
}
</style>