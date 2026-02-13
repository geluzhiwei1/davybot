/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-container class="chat-container">
    <!-- 左侧窄条按钮区 - 独立的 aside -->
    <el-aside class="activity-bar" width="60px">
      <div class="activity-bar-content">
        <!-- 上部按钮 -->
        <div class="top-buttons">
          <template v-if="!isSidePanelCollapsed">
            <el-tooltip content="收起侧边栏" placement="right">
              <el-button :icon="Fold" @click="toggleSidePanel" text circle />
            </el-tooltip>
            <el-tooltip :content="isChatPanelCollapsed ? '显示对话框' : '隐藏对话框'" placement="right">
              <el-button :icon="isChatPanelCollapsed ? DArrowRight : DArrowLeft" @click="toggleChatPanel" text circle />
            </el-tooltip>
          </template>
          <template v-else>
            <el-tooltip content="展开侧边栏" placement="right">
              <el-button :icon="Expand" @click="toggleSidePanel" text circle />
            </el-tooltip>
          </template>
        </div>

        <!-- 下部按钮 -->
        <div class="bottom-buttons">
          <el-tooltip content="工作区设置" placement="right">
            <el-button :icon="Setting" @click="handleOpenSettings" text circle />
          </el-tooltip>
          <el-tooltip content="切换工作区" placement="right">
            <el-button :icon="Switch" @click="handleSwitchWorkspace" text circle />
          </el-tooltip>
          <el-tooltip content="用户设置" placement="right">
            <el-button :icon="User" @click="handleUserSettings" text circle />
          </el-tooltip>
        </div>
      </div>
    </el-aside>

    <!-- 左侧内容区 - 独立的 aside，可折叠 -->
    <el-aside v-show="!isSidePanelCollapsed" class="content-panel" width="400px">
      <SidePanel ref="sidePanelRef" @open-file="handleOpenFile" :side-panel-collapsed="isSidePanelCollapsed"
        :chat-panel-collapsed="isChatPanelCollapsed" :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-aside>

    <el-container v-show="!isChatPanelCollapsed" class="main-content">
      <el-header height="auto">
        <TopBar :is-side-panel-collapsed="isChatPanelCollapsed"
          @open-settings="handleOpenSettings" @toggle-side-panel="toggleChatPanel" />
      </el-header>
      <el-main>
        <!-- Agents 下拉监控面板 -->
        <MinimalMonitoringPanel v-if="isMonitoringPanelVisible" />

        <div class="main-scroll-area">
          <MessageArea ref="messageAreaRef" />
          <UserOperationArea ref="userOperationAreaRef" />
        </div>
        <UserInputArea />
      </el-main>
      <el-footer height="auto">
        <BottomBar />
        <ServerStatusIndicator />
      </el-footer>
    </el-container>

    <el-aside v-if="isRightPanelVisible" class="right-panel">
      <FileContentArea :files="openFiles" :active-file-id="currentActiveFileId" @close-file="handleCloseFile"
        @update:active-file-id="handleActiveFileChange" @save-file="saveFileContent"
        @update-file-content="updateFileContent" />
    </el-aside>

    <WorkspaceSettingsDrawer
      v-model="isSettingsDrawerVisible"
      :workspace-id="chatStore.workspaceId"
      :initial-tab="initialSettingsTab"
    />

    <!-- 追问问题对话框 -->
    <FollowupQuestionDialog v-model:visible="showFollowupDialog" :question="followupData.question"
      :suggestions="followupData.suggestions" :tool-call-id="followupData.toolCallId" :task-id="followupData.taskId"
      @response="handleFollowupResponse" />

    <!-- Global Image Viewer -->
    <ImageViewer v-model:visible="globalImageViewerVisible" :images="globalImageViewerImages"
      :initial-index="globalImageViewerIndex" />
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import { useConnectionStore } from '@/stores/connection';
import { useParallelTasksStore } from '@/stores/parallelTasks';
import { apiManager } from '@/services/api';
import { MessageType } from '@/types/websocket';
import type { FollowupQuestionMessage } from '@/types/websocket';
import { ElContainer, ElAside, ElHeader, ElMain, ElFooter, ElButton, ElTooltip } from 'element-plus';
import { getApiBaseUrl } from '@/utils/platform';
import { Fold, Expand, DArrowLeft, DArrowRight, Setting, Switch, User } from '@element-plus/icons-vue';

// 导入极简样式
import '@/styles/chat-ultra-minimal.css';

import SidePanel from '@/components/layout/SidePanel.vue';
import FileContentArea from '@/components/layout/FileContentArea.vue';
import TopBar from '@/components/layout/TopBar.vue';
import MessageArea from '@/components/layout/MessageArea.vue';
import UserOperationArea from '@/components/layout/UserOperationArea.vue';
import UserInputArea from '@/components/layout/UserInputArea.vue';
import ServerStatusIndicator from '@/components/ServerStatusIndicator.vue';
import BottomBar from '@/components/layout/BottomBar.vue';
import WorkspaceSettingsDrawer from '@/components/layout/WorkspaceSettingsDrawer.vue';
import FollowupQuestionDialog from '@/components/FollowupQuestionDialog.vue';
import MinimalMonitoringPanel from '@/components/monitoring/MinimalMonitoringPanel.vue';
import ImageViewer from '@/components/chat/ImageViewer.vue';

const route = useRoute();
const router = useRouter();
const chatStore = useChatStore();
const connectionStore = useConnectionStore();
const parallelTasksStore = useParallelTasksStore();

// 追问问题相关状态
const showFollowupDialog = ref(false);
const followupData = ref<{
  question: string;
  suggestions: string[];
  toolCallId: string;
  taskId: string;
}>({
  question: '',
  suggestions: [],
  toolCallId: '',
  taskId: ''
});

// 全局图片查看器状态
const globalImageViewerVisible = ref(false);
const globalImageViewerImages = ref<{ src: string; filename?: string }[]>([]);
const globalImageViewerIndex = ref(0);

// 提供全局图片查看器给子组件
import { provide } from 'vue';
provide('globalImageViewer', {
  open: (images: { src: string; filename?: string }[], index = 0) => {
    globalImageViewerImages.value = images;
    globalImageViewerIndex.value = index;
    globalImageViewerVisible.value = true;
  }
});

const openFiles = ref<unknown[]>([]);
const currentActiveFileId = ref<string | null>(null);
const messageAreaRef = ref<InstanceType<typeof MessageArea> | null>(null);
const sidePanelRef = ref<InstanceType<typeof SidePanel> | null>(null);
const isSidePanelCollapsed = ref(false);
const isChatPanelCollapsed = ref(false);
const isSettingsDrawerVisible = ref(false);
const initialSettingsTab = ref<string | undefined>(undefined);

// Agents状态 - 默认显示面板
const isMonitoringPanelVisible = ref(true);

// 切换工作区
const handleSwitchWorkspace = () => {
  router.push('/workspaces');
};

// 删除未使用的函数
// const _handleCloseFile = (fileId: string) => { ... }

// 添加全局测试函数（仅用于开发调试）
if (import.meta.env.DEV) {
  (window as unknown).testFollowupDialog = () => {
    console.log('========== 手动触发测试对话框 ==========');
    followupData.value = {
      question: '这是一个测试问题：你的名字是什么？',
      suggestions: ['张三', '李四', '王五'],
      toolCallId: 'test-tool-call-id',
      taskId: 'test-task-id'
    };
    showFollowupDialog.value = true;
    console.log('showFollowupDialog 设置为:', showFollowupDialog.value);
    console.log('followupData:', followupData.value);
    console.log('=========================================');
  };
}

const isRightPanelVisible = computed(() => openFiles.value.length > 0);

// 检查 LLM 配置，如果为空则自动打开设置
const checkLLMConfiguration = async () => {
  if (!chatStore.workspaceId) {
    console.log('[ChatView] No workspace ID, skipping LLM configuration check');
    return;
  }

  try {
    console.log('[ChatView] Checking LLM configuration...');

    // 使用新的 API 获取所有级别的 LLM 配置（用户级和工作区级）
    const response = await apiManager.getWorkspacesApi().getLLMSettingsAllLevels(chatStore.workspaceId);
    const userConfigs = response.settings.user || [];
    const workspaceConfigs = response.settings.workspace || [];

    console.log('[ChatView] User LLM configs:', userConfigs.length);
    console.log('[ChatView] Workspace LLM configs:', workspaceConfigs.length);

    // 检查是否有任何 LLM provider 配置（用户级或工作区级）
    const hasConfigs = userConfigs.length > 0 || workspaceConfigs.length > 0;

    if (!hasConfigs) {
      console.warn('[ChatView] No LLM providers configured, opening settings drawer');
      // 设置初始 tab 为 'llm-providers'
      initialSettingsTab.value = 'llm-providers';
      // 打开设置抽屉
      isSettingsDrawerVisible.value = true;

      // 显示提示消息
      setTimeout(() => {
        ElMessage({
          message: '请先配置 LLM Provider 后再使用 AI 功能',
          type: 'warning',
          duration: 5000,
          showClose: true
        });
      }, 500);
    } else {
      console.log('[ChatView] LLM configuration check passed');
    }
  } catch (error) {
    console.error('[ChatView] Failed to check LLM configuration:', error);
    // 失败时不强制打开设置，可能是权限问题或 API 错误
  }
};

// 在组件挂载时立即打印API配置
onMounted(async () => {
  const apiBaseUrl = getApiBaseUrl();
  console.log('='.repeat(60));
  console.log('[ChatView] ========== Component Mounted ==========');
  console.log('[ChatView] Workspace ID:', chatStore.workspaceId);
  console.log('[ChatView] API Base URL:', apiBaseUrl);
  console.log('[ChatView] Environment VITE_API_BASE_URL:', import.meta.env.VITE_API_BASE_URL);
  console.log('[ChatView] Is Tauri:', import.meta.env.CLIENT_TAWSI ?? 'false');
  console.log('[ChatView] Expected API URL:', apiBaseUrl === '/api' ? '✅ /api (correct for Web dev mode)' : `❌ ${apiBaseUrl} (should be /api)`);
  console.log('='.repeat(60));
});

const toggleSidePanel = () => {
  isSidePanelCollapsed.value = !isSidePanelCollapsed.value;
};

const toggleChatPanel = () => {
  isChatPanelCollapsed.value = !isChatPanelCollapsed.value;
};

const fetchFileContent = async (node: { path: string; name: string; is_directory?: boolean }): Promise<{ content: string; type: string }> => {
  if (node.is_directory) return { content: '', type: 'directory' };
  try {
    const workspaceId = chatStore.workspaceId || 'default';
    const extension = node.name.split('.').pop()?.toLowerCase() || '';

    // 图像文件扩展名
    const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico'];
    // 视频文件扩展名
    const videoExtensions = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv'];
    // 音频文件扩展名
    const audioExtensions = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'];
    // PDF文件扩展名
    const pdfExtensions = ['pdf'];

    let fileType = 'text';
    if (imageExtensions.includes(extension)) fileType = 'image';
    else if (videoExtensions.includes(extension)) fileType = 'video';
    else if (audioExtensions.includes(extension)) fileType = 'audio';
    else if (pdfExtensions.includes(extension)) fileType = 'pdf';
    else if (['md', 'markdown'].includes(extension)) fileType = 'markdown';
    else if (['json', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'py', 'sql', 'yaml', 'yml', 'xml', 'sh'].includes(extension)) fileType = 'code';
    else if (extension === 'csv') fileType = 'csv';

    // 处理媒体文件（图像、视频、音频、PDF）
    if (fileType === 'image' || fileType === 'video' || fileType === 'audio' || fileType === 'pdf') {
      try {
        // 使用fetch获取二进制数据
        const apiBaseUrl = getApiBaseUrl();
        const mediaUrl = `${apiBaseUrl}/workspaces/${workspaceId}/files?path=${encodeURIComponent(node.path)}`;
        console.log('[ChatView] API Base URL:', apiBaseUrl);
        console.log('[ChatView] Fetching media file from:', mediaUrl);

        const response = await fetch(mediaUrl);

        if (!response.ok) {
          throw new Error(`Failed to fetch media file: ${response.statusText}`);
        }

        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);

        console.log('[ChatView] Created blob URL for', fileType, ':', blobUrl);
        return { content: blobUrl, type: fileType };
      } catch (error) {
        console.error(`[ChatView] Failed to fetch ${fileType} file:`, error);
        throw error;
      }
    }

    // 处理文本文件
    const response = await apiManager.getFilesApi().getFileContent(workspaceId, node.path);
    return { content: response.content || '', type: fileType };
  } catch (error) {
    console.error('[ChatView] 获取文件内容失败:', error);
    throw error;
  }
};

const handleOpenFile = async (fileInfo: { path: string; name: string; is_directory?: boolean }) => {
  console.log('[ChatView] handleOpenFile called with:', fileInfo);

  // 检查文件是否已经打开
  const existingFile = openFiles.value.find(f => f.id === fileInfo.path);

  if (existingFile) {
    // 文件已打开，直接切换到该 tab
    console.log('[ChatView] File already open, switching to tab:', existingFile.id);
    currentActiveFileId.value = existingFile.id;
    return;
  }

  // 文件未打开，获取内容并打开新 tab
  try {
    console.log('[ChatView] Fetching file content...');
    const { content, type } = await fetchFileContent(fileInfo);

    // 如果是目录，不打开
    if (type === 'directory') {
      console.log('[ChatView] Skipping directory:', fileInfo.path);
      return;
    }

    // 创建新文件对象
    const newFile = {
      id: fileInfo.path,
      name: fileInfo.name,
      type,
      content,
      isDirty: false
    };

    console.log('[ChatView] Opening new file tab:', newFile);
    console.log('[ChatView] Current openFiles count:', openFiles.value.length);

    openFiles.value.push(newFile);
    currentActiveFileId.value = newFile.id;

    console.log('[ChatView] After adding, openFiles count:', openFiles.value.length);
    console.log('[ChatView] isRightPanelVisible:', isRightPanelVisible.value);
  } catch (error) {
    console.error('[ChatView] Failed to open file:', error);
    console.error('[ChatView] Error details:', error);
  }
};


const saveFileContent = async (fileId: string, content: string) => {
  try {
    const workspaceId = chatStore.workspaceId || 'default';
    const file = openFiles.value.find(f => (f as { id: string }).id === fileId);
    if (!file) throw new Error('文件未找到');
    await apiManager.getFilesApi().saveFileContent(workspaceId, { path: (file as { id: string }).id, content });
    (file as { content: string; isDirty: boolean }).content = content;
    (file as { isDirty: boolean }).isDirty = false;
  } catch (error) {
    console.error('保存文件失败:', error);
    throw error;
  }
};

const updateFileContent = (fileId: string, content: string) => {
  const file = openFiles.value.find(f => f.id === fileId);
  if (file) {
    // 只在内容真正变化时才标记为 dirty
    if (file.content !== content) {
      file.content = content;
      file.isDirty = true;
    }
  }
};

const handleActiveFileChange = (fileId: string | null) => {
  currentActiveFileId.value = fileId;
};

// 打开工作区设置抽屉
const handleOpenSettings = () => {
  // 手动打开设置时，清空 initialTab，使用默认 tab
  initialSettingsTab.value = undefined;
  isSettingsDrawerVisible.value = true;
};


// 用户设置
const handleUserSettings = () => {
  console.log('用户设置');
};

const getValidWorkspaceId = async (): Promise<string | null> => {
  const routeWorkspaceId = route.params.workspaceId as string;
  console.log('[ChatView] getValidWorkspaceId - route.params.workspaceId:', routeWorkspaceId);
  if (routeWorkspaceId) {
    console.log('[ChatView] getValidWorkspaceId - 使用 URL 中的 workspaceId:', routeWorkspaceId);
    return routeWorkspaceId;
  }

  try {
    const workspaces = await apiManager.getWorkspacesApi().getWorkspaces();
    if (workspaces && workspaces.length > 0 && workspaces[0]) {
      console.log('[ChatView] getValidWorkspaceId - 从 API 获取的 workspace:', workspaces[0].id);
      return workspaces[0].id;
    }
    return null;
  } catch (error) {
    console.error('获取工作区列表失败:', error);
    return null;
  }
};

onMounted(async () => {
  await router.isReady();

  const routeWorkspaceId = route.params.workspaceId as string;
  if (routeWorkspaceId) {
    chatStore.setWorkspaceId(routeWorkspaceId);
  }

  // 初始化连接并注册消息处理器
  chatStore.initializeConnection();

  // 监听来自 chat store 的 followup question 事件
  window.addEventListener('followup-question', ((event: CustomEvent) => {
    handleFollowupQuestion(event.detail as unknown);
  }) as EventListener);

  const workspaceId = await getValidWorkspaceId();
  if (!workspaceId) {
    router.push('/workspaces');
    return;
  }

  // 如果之前没有从 URL 设置，现在设置
  if (!routeWorkspaceId) {
    chatStore.setWorkspaceId(workspaceId);
  }

  // 初始化 WebSocket 连接（使用正确的 workspaceId）
  await connectionStore.connect(workspaceId);

  if (!route.params.workspaceId) {
    router.replace(`/dawei/${workspaceId}`);
  }

  // 检查 LLM 配置，如果为空则自动打开设置
  await checkLLMConfiguration();
});

// 监听并行任务，有活跃任务时自动显示监控面板
watch(() => parallelTasksStore.activeTasks.length, (count) => {
  if (count > 0 && !isMonitoringPanelVisible.value) {
    console.log('[ChatView] 检测到活跃任务，自动显示监控面板');
    isMonitoringPanelVisible.value = true;
  }
});

onUnmounted(() => {
  // 组件卸载时的清理工作（如果需要）
});

// 监听路由参数变化，切换工作区时更新状态
// 注意：不使用 immediate: true，因为 onMounted 已经处理了初始化
watch(() => route.params.workspaceId, async (newWorkspaceId) => {
  const finalWorkspaceId = (newWorkspaceId as string) || await getValidWorkspaceId();
  if (finalWorkspaceId) {
    // 检查是否需要更新（避免重复设置）
    const currentWsId = chatStore.workspaceId;
    if (currentWsId === finalWorkspaceId) {
      console.log('[ChatView] 工作区未变化，跳过重复加载');
      return;
    }

    chatStore.setWorkspaceId(finalWorkspaceId);
    // setWorkspaceId 内部已经调用了 workspaceStore.setWorkspace(),不需要重复调用

    // 断开旧连接，连接到新 workspace
    await connectionStore.connect(finalWorkspaceId);

    // 注意：文件树由 SidePanel 组件自己管理,不需要在这里加载

    if (!newWorkspaceId) {
      router.replace(`/dawei/${finalWorkspaceId}`);
    }
  }
});

// 处理追问问题
function handleFollowupQuestion(message: FollowupQuestionMessage) {
  console.log('========== 🎯 收到追问问题 ==========');
  console.log('完整消息:', message);
  console.log('问题:', message.question);
  console.log('建议:', message.suggestions);
  console.log('tool_call_id:', message.tool_call_id);
  console.log('task_id:', message.task_id);
  console.log('=====================================');

  // 更新追问数据
  followupData.value = {
    question: message.question,
    suggestions: message.suggestions || [],
    toolCallId: message.tool_call_id,
    taskId: message.task_id
  };

  console.log('✅ followupData 已更新:', followupData.value);

  // 显示对话框
  console.log('⏳ 准备显示对话框，设置 showFollowupDialog = true');
  showFollowupDialog.value = true;

  console.log('✅ showFollowupDialog 当前值:', showFollowupDialog.value);
  console.log('✅ 对话框应该已经显示');
  console.log('=====================================');
}

// 处理追问回复
async function handleFollowupResponse(toolCallId: string, response: string) {
  console.log('========== 提交追问回复 ==========');
  console.log('toolCallId:', toolCallId);
  console.log('response:', response);
  console.log('taskId:', followupData.value.taskId);

  try {
    // 使用 chatStore 的 WebSocket 连接发送消息
    const { MessageBuilder } = await import('@/services/protocol');

    const responseMessage = MessageBuilder.createBaseMessage(
      MessageType.FOLLOWUP_RESPONSE,
      chatStore.sessionId || ''
    );

    // 添加特定字段
    Object.assign(responseMessage, {
      task_id: followupData.value.taskId,
      tool_call_id: toolCallId,
      response: response
    });

    console.log('准备发送消息:', responseMessage);

    // 通过 chatStore 发送消息
    await chatStore.sendWebSocketMessage(responseMessage);

    console.log('✅ 追问回复已发送');
    console.log('==================================');
  } catch (error) {
    console.error('❌ 发送追问回复失败:', error);
  }
}
</script>

<style scoped>
.chat-container {
  height: 100vh;
  overflow: hidden;
  background: var(--el-bg-color-page);
  display: flex;
}

/* ====================
   ACTIVITY BAR - 左侧窄条按钮区
   ==================== */
.activity-bar {
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  border-right: 1px solid var(--el-border-color);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.02);
}

.activity-bar-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  padding: 16px 0;
  box-sizing: border-box;
}

.activity-bar .top-buttons {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding-bottom: 16px;
}

.activity-bar .bottom-buttons {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  margin-top: auto;
  padding-top: 16px;
}

.activity-bar .el-button {
  margin: 0 !important;
  padding: 8px !important;
  width: 36px !important;
  height: 36px !important;
  border-radius: var(--radius-lg) !important;
  transition: all var(--duration-base) var(--ease-default) !important;
  color: var(--color-text-secondary) !important;
}

.activity-bar .el-button:hover {
  background: rgba(var(--color-primary-rgb), 0.08) !important;
  color: var(--color-primary) !important;
  transform: scale(1.05);
}

.activity-bar .el-button+.el-button {
  margin-top: 10px !important;
}

/* ====================
   CONTENT PANEL - 左侧内容区
   ==================== */
.content-panel {
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  border-right: 1px solid var(--el-border-color);
  transition: all var(--duration-base) var(--ease-default);
  flex-shrink: 0;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.03);
}

.left-panel {
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  border-right: 1px solid var(--el-border-color);
  transition: all var(--duration-base) var(--ease-default);
  flex-shrink: 0;
  box-shadow: 2px 0 12px rgba(0, 0, 0, 0.03);
}

.left-panel.side-panel-collapsed {
  width: 57px !important;
}

/* ====================
   MAIN CONTENT AREA
   ==================== */
.main-content {
  display: flex;
  flex-direction: column;
  background: transparent;
  flex: 1;
  min-width: 0;
}

.el-header,
.el-footer {
  padding: 0;
  background: transparent;
}

.el-header {
  width: 100%;
  border-bottom: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  position: relative;
  z-index: 10;
}

.el-footer {
  border-top: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
}

.el-main {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-bg-color-page);
}

.main-scroll-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  background: #ffffff !important;
  padding: 0 !important; /* 移除内边距 */
}

/* 平滑滚动 */
.main-scroll-area::-webkit-scrollbar {
  width: 8px;
}

.main-scroll-area::-webkit-scrollbar-track {
  background: transparent;
}

.main-scroll-area::-webkit-scrollbar-thumb {
  background: rgba(var(--color-primary-rgb), 0.2);
  border-radius: var(--radius-full);
  transition: background var(--duration-base) var(--ease-default);
}

.main-scroll-area::-webkit-scrollbar-thumb:hover {
  background: rgba(var(--color-primary-rgb), 0.3);
}

/* ====================
   RIGHT PANEL - 文件内容区
   ==================== */
.right-panel {
  border-left: 1px solid var(--el-border-color);
  background: var(--el-bg-color);
  backdrop-filter: blur(10px);
  transition: all var(--duration-base) var(--ease-default);
  flex: 1;
  min-width: 300px;
  max-width: 60%;
  overflow: hidden;
  box-shadow: -2px 0 12px rgba(0, 0, 0, 0.03);
}

/* ====================
   ANIMATIONS
   ==================== */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 为所有面板添加入场动画 */
.activity-bar,
.content-panel,
.main-content,
.right-panel {
  animation: fadeIn 0.4s var(--ease-out) both;
}

.activity-bar {
  animation-delay: 0ms;
}

.content-panel {
  animation-delay: 50ms;
}

.main-content {
  animation-delay: 100ms;
}

.right-panel {
  animation-delay: 150ms;
}

/* ====================
   RESPONSIVE DESIGN
   ==================== */
@media (max-width: 768px) {
  .chat-container {
    background: var(--el-bg-color-page);
  }

  .activity-bar {
    background: var(--el-bg-color);
  }

  .content-panel,
  .left-panel {
    background: var(--el-bg-color);
    backdrop-filter: none;
  }

  .el-header,
  .el-footer {
    background: var(--el-bg-color);
    backdrop-filter: none;
  }

  .right-panel {
    background: var(--el-bg-color);
    backdrop-filter: none;
  }
}
</style>
