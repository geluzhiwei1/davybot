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
          </template>
          <template v-else>
            <el-tooltip content="展开侧边栏" placement="right">
              <el-button :icon="Expand" @click="toggleSidePanel" text circle />
            </el-tooltip>
          </template>
          <template v-if="!isChatPanelCollapsed">
            <el-tooltip content="收起聊天区" placement="right">
              <el-button :icon="Fold" @click="toggleChatPanel" text circle />
            </el-tooltip>
          </template>
          <template v-else>
            <el-tooltip content="展开聊天区" placement="right">
              <el-button :icon="Expand" @click="toggleChatPanel" text circle />
            </el-tooltip>
          </template>
        </div>

        <!-- 下部按钮 -->
        <div class="bottom-buttons">

          <!-- 语言模型 -->
          <el-tooltip :content="t('workspaceSettings.tabs.llmProvider')" placement="right">
            <el-button @click="handleOpenLLMDrawer" text circle>
              <Icon icon="hugeicons:ai-brain-05" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- 技能 -->
          <el-tooltip :content="t('workspaceSettings.tabs.skills')" placement="right">
            <el-button @click="handleOpenSkillsDrawer" text circle>
              <Icon icon="streamline-color:wind-flow-2" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- 智能体 -->
          <el-tooltip :content="t('workspaceSettings.tabs.agents')" placement="right">
            <el-button @click="handleOpenAgentsDrawer" text circle>
              <Icon icon="streamline-ultimate:professions-man-astronaut-bold" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- 插件 -->
          <el-tooltip :content="t('workspaceSettings.tabs.plugins')" placement="right">
            <el-button @click="handleOpenPluginsDrawer" text circle>
              <Icon icon="streamline-freehand:plugin-jigsaw-puzzle" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- MCP -->
          <el-tooltip :content="t('workspaceSettings.tabs.mcpServers')" placement="right">
            <el-button @click="handleOpenMCPDrawer" text circle>
              <Icon icon="octicon:mcp-24" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- 定时任务 -->
          <el-tooltip :content="t('workspaceSettings.tabs.scheduledTasks')" placement="right">
            <el-button @click="handleOpenScheduledTasksDrawer" text circle>
              <Icon icon="cil:calendar" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- Channels -->
          <el-tooltip content="Channels" placement="right">
            <el-button @click="handleOpenChannelsDrawer" text circle>
              <Icon icon="material-symbols:swap-horiz" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <!-- Evolution -->
          <el-tooltip :content="t('evolution.title')" placement="right">
            <el-button @click="handleOpenEvolutionDrawer" text circle>
              <Icon icon="streamline-plump-color:recycle-1" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('sidePanel.memory')" placement="right">
            <el-button @click="handleOpenMemoryDrawer" text circle>
              <Icon icon="arcticons:breeno-memory" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.title')" placement="right">
            <el-button @click="handleOpenKnowledgeDrawer" text circle>
              <Icon icon="hugeicons:knowledge-02" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('workspaceSettings.title')" placement="right">
            <el-button @click="handleOpenSettings" text circle>
              <Icon icon="streamline-flex:keyboard-option-setting-gear-solid" width="24" height="24" />
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('sidePanel.switchWorkspace')" placement="right">
            <el-button @click="handleSwitchWorkspace" text circle>
              <Icon icon="hugeicons:new-office" width="24" height="24" />
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </el-aside>

    <!-- 左侧内容区 - 桌面端固定侧边栏,移动端隐藏 -->
    <el-aside v-show="!isSidePanelCollapsed && !isMobile" class="content-panel" :width="sidePanelWidth + 'px'">
      <SidePanel ref="sidePanelRef" @open-file="handleOpenFile" :side-panel-collapsed="isSidePanelCollapsed"
        :chat-panel-collapsed="isChatPanelCollapsed" :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-aside>

    <!-- 主内容区 - 桌面端使用固定宽度50% -->
    <el-aside v-show="!isChatPanelCollapsed && !isMobile" class="main-content" :width="mainContentWidth + 'px'">
      <el-container style="height: 100%; display: flex; flex-direction: column;">
        <el-header height="auto">
          <TopBar @open-settings="handleOpenSettings" />
        </el-header>
        <el-main>
          <!-- Agents 下拉监控面板 -->
          <MinimalMonitoringPanel v-if="isMonitoringPanelVisible" />

          <div class="main-scroll-area">
            <MessageArea ref="messageAreaRef" />
          </div>
          <UserInputArea />
        </el-main>
        <el-footer height="auto" :class="{ 'mobile-footer': isMobile }">
          <BottomBar />
          <ServerStatusIndicator />
        </el-footer>
      </el-container>
    </el-aside>

    <!-- 移动端底部导航 -->
    <MobileBottomNav :open-files-count="openFiles.length" @navigate="handleMobileNavNavigate" />

    <!-- 右侧文件内容区 - 桌面端固定,移动端隐藏 -->
    <el-aside v-if="isRightPanelVisible && !isMobile" class="right-panel" :class="{ 'right-panel--full': isChatPanelCollapsed }" :width="rightPanelWidth + 'px'">
      <FileContentArea ref="fileContentAreaRef" :files="openFiles" :active-file-id="currentActiveFileId"
        @close-file="handleCloseFile" @update:active-file-id="handleActiveFileChange" @save-file="saveFileContent"
        @update-file-content="updateFileContent" />
    </el-aside>

    <!-- 移动端主内容区 - 使用原来的 el-container 结构 -->
    <el-container v-show="!isChatPanelCollapsed && isMobile" class="main-content">
      <el-header height="auto">
        <TopBar @open-settings="handleOpenSettings" />
      </el-header>
      <el-main>
        <!-- Agents 下拉监控面板 -->
        <MinimalMonitoringPanel v-if="isMonitoringPanelVisible" />

        <div class="main-scroll-area">
          <MessageArea ref="messageAreaRef" />
        </div>
        <UserInputArea />
      </el-main>
      <el-footer height="auto" :class="{ 'mobile-footer': isMobile }">
        <BottomBar />
        <ServerStatusIndicator />
      </el-footer>
    </el-container>

    <!-- 移动端侧边栏抽屉 -->
    <el-drawer v-model="isMobileSidePanelOpen" :with-header="false" direction="rtl" size="100%"
      class="mobile-side-panel-drawer">
      <SidePanel ref="sidePanelRef" @open-file="handleOpenFile" :side-panel-collapsed="false"
        :chat-panel-collapsed="false" :workspace-id="chatStore.workspaceId ?? undefined" :is-mobile-drawer="true"
        @close-mobile-drawer="isMobileSidePanelOpen = false" />
    </el-drawer>

    <!-- 移动端右侧文件内容抽屉 -->
    <el-drawer v-model="isMobileRightPanelOpen" :with-header="false" direction="rtl" size="100%"
      class="mobile-right-panel-drawer">
      <FileContentArea ref="fileContentAreaRef" :files="openFiles" :active-file-id="currentActiveFileId"
        :is-mobile-drawer="true" @close-file="handleCloseFile" @update:active-file-id="handleActiveFileChange"
        @save-file="saveFileContent" @update-file-content="updateFileContent"
        @close-mobile-drawer="isMobileRightPanelOpen = false" />
    </el-drawer>

    <WorkspaceSettingsDrawer v-model="isSettingsDrawerVisible" :workspace-id="chatStore.workspaceId"
      :initial-tab="initialSettingsTab" />

    <!-- 语言模型抽屉 -->
    <el-drawer v-model="isLLMDrawerVisible" :title="t('workspaceSettings.tabs.llmProvider')" direction="rtl" size="90%">
      <LLMProvidersDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- 技能抽屉 -->
    <el-drawer v-model="isSkillsDrawerVisible" :title="t('workspaceSettings.tabs.skills')" direction="rtl" size="90%">
      <SkillsDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- 智能体抽屉 -->
    <el-drawer v-model="isAgentsDrawerVisible" :title="t('workspaceSettings.tabs.agents')" direction="rtl" size="90%">
      <AgentsDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- 插件抽屉 -->
    <el-drawer v-model="isPluginsDrawerVisible" :title="t('workspaceSettings.tabs.plugins')" direction="rtl" size="90%">
      <PluginsDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- MCP抽屉 -->
    <el-drawer v-model="isMCPDrawerVisible" :title="t('workspaceSettings.tabs.mcpServers')" direction="rtl" size="90%">
      <MCPDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- 定时任务抽屉 -->
    <el-drawer v-model="isScheduledTasksDrawerVisible" :title="t('workspaceSettings.tabs.scheduledTasks')"
      direction="rtl" size="90%">
      <ScheduledTasksDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- Channels抽屉 -->
    <el-drawer v-model="isChannelsDrawerVisible" title="Channels"
      direction="rtl" size="90%">
      <ChannelsPanel v-if="chatStore.workspaceId" :workspace-id="chatStore.workspaceId" />
    </el-drawer>

    <!-- Evolution抽屉 -->
    <el-drawer v-model="isEvolutionDrawerVisible" :title="t('evolution.title')" direction="rtl" size="90%" destroy-on-close>
      <EvolutionDrawer :workspace-id="chatStore.workspaceId ?? undefined" />
    </el-drawer>

    <!-- 知识库抽屉 -->
    <KnowledgeDrawer v-model="isKnowledgeDrawerVisible" :workspace-id="chatStore.workspaceId ?? undefined" />

    <!-- 记忆抽屉 -->
    <MemoryDrawer v-model="isMemoryDrawerVisible" :workspace-id="chatStore.workspaceId ?? undefined" />

    <!-- 追问问题对话框 -->
    <FollowupQuestionDialog v-model:visible="showFollowupDialog" :question="followupData.question"
      :suggestions="followupData.suggestions" :tool-call-id="followupData.toolCallId" :task-id="followupData.taskId"
      @response="handleFollowupResponse" @cancel="handleFollowupCancel" />

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
import { httpClient } from '@/services/api/http';
import { appConfig } from '@/config/app.config';
import { MessageType } from '@/types/websocket';
import type { FollowupQuestionMessage } from '@/types/websocket';
import { ElContainer, ElAside, ElHeader, ElMain, ElFooter, ElButton, ElTooltip, ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { useMobile } from '@/composables/useMobile';
import {
  Fold,
  Expand,
  Setting,
  Switch,
  Grid,
  Connection,
  ChatLineRound,
  Tools,
  Operation,
  Clock,
  Link,
  Picture,
  Star,
  User,
  FolderOpened
} from '@element-plus/icons-vue';

import { Icon } from "@iconify/vue"

const { t } = useI18n();

// 移动端响应式检测
const { isMobile, isTablet, isDesktop, isTouchDevice } = useMobile();

// 导入极简样式
import '@/styles/chat-ultra-minimal.css';

import SidePanel from '@/components/layout/SidePanel.vue';
import FileContentArea from '@/components/layout/FileContentArea.vue';
import TopBar from '@/components/layout/TopBar.vue';
import MessageArea from '@/components/layout/MessageArea.vue';
import UserInputArea from '@/components/layout/UserInputArea.vue';
import ServerStatusIndicator from '@/components/ServerStatusIndicator.vue';
import BottomBar from '@/components/layout/BottomBar.vue';
import WorkspaceSettingsDrawer from '@/components/layout/WorkspaceSettingsDrawer.vue';
import KnowledgeDrawer from '@/components/layout/KnowledgeDrawer.vue';
import MemoryDrawer from '@/components/layout/MemoryDrawer.vue';
import LLMProvidersDrawer from '@/components/drawers/LLMProvidersDrawer.vue';
import SkillsDrawer from '@/components/drawers/SkillsDrawer.vue';
import AgentsDrawer from '@/components/drawers/AgentsDrawer.vue';
import PluginsDrawer from '@/components/drawers/PluginsDrawer.vue';
import MCPDrawer from '@/components/drawers/MCPDrawer.vue';
import ScheduledTasksDrawer from '@/components/drawers/ScheduledTasksDrawer.vue';
import ChannelsPanel from '@/components/workspace/ChannelsPanel.vue';
import EvolutionDrawer from '@/components/drawers/EvolutionDrawer.vue';
import FollowupQuestionDialog from '@/components/FollowupQuestionDialog.vue';
import MinimalMonitoringPanel from '@/components/monitoring/MinimalMonitoringPanel.vue';
import ImageViewer from '@/components/chat/ImageViewer.vue';
import MobileBottomNav from '@/components/layout/MobileBottomNav.vue';

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
const isKnowledgeDrawerVisible = ref(false);
const isMemoryDrawerVisible = ref(false);
const isLLMDrawerVisible = ref(false);
const isSkillsDrawerVisible = ref(false);
const isAgentsDrawerVisible = ref(false);
const isPluginsDrawerVisible = ref(false);
const isMCPDrawerVisible = ref(false);
const isScheduledTasksDrawerVisible = ref(false);
const isChannelsDrawerVisible = ref(false);
const isEvolutionDrawerVisible = ref(false);
const initialSettingsTab = ref<string | undefined>(undefined);

// 移动端侧边栏抽屉状态
const isMobileSidePanelOpen = ref(false);
const isMobileRightPanelOpen = ref(false);

// 面板宽度控制 - 根据设备类型响应式调整
const sidePanelWidth = computed({
  get: () => {
    // 移动端固定全屏宽度
    if (isMobile.value) return window.innerWidth;
    // 平板设备使用较小宽度
    if (isTablet.value) return 320;
    // 桌面端：固定宽度
    return 400;
  },
  set: (val) => {
    // 不再保存宽度
  }
});

const mainContentWidth = computed({
  get: () => {
    // 移动端不使用此计算
    if (isMobile.value) return window.innerWidth;
    // 平板设备使用较小宽度
    if (isTablet.value) return 400;
    // 桌面端：计算剩余空间的50%
    const sidePanelOffset = isSidePanelCollapsed.value ? 0 : sidePanelWidth.value;
    const availableWidth = window.innerWidth - 60 - sidePanelOffset;
    return Math.floor(availableWidth * 0.5);
  },
  set: (val) => {
    // 不再保存宽度
  }
});

const rightPanelWidth = computed({
  get: () => {
    // 移动端固定全屏宽度
    if (isMobile.value) return window.innerWidth;
    // 平板设备使用较小宽度
    if (isTablet.value) return 400;
    // 桌面端：计算剩余空间
    const sidePanelOffset = isSidePanelCollapsed.value ? 0 : sidePanelWidth.value;
    const availableWidth = window.innerWidth - 60 - sidePanelOffset;
    // 聊天区折叠时占满全部剩余空间，否则占50%
    if (isChatPanelCollapsed.value) return availableWidth;
    return Math.floor(availableWidth * 0.5);
  },
  set: (val) => {
    // 不再保存宽度
  }
});

// 移动端自动折叠侧边栏
watch(isMobile, (mobile) => {
  if (mobile) {
    // 移动端默认折叠侧边栏
    isSidePanelCollapsed.value = true;
  }
}, { immediate: true });

// 移动端底部导航处理
const handleMobileNavNavigate = (tab: string) => {
  switch (tab) {
    case 'chat':
      // 关闭所有抽屉,显示聊天区域
      isMobileSidePanelOpen.value = false;
      isMobileRightPanelOpen.value = false;
      break;
    case 'conversations':
      // 打开左侧会话抽屉
      isMobileSidePanelOpen.value = true;
      break;
    case 'files':
      // 如果有打开的文件,显示文件抽屉
      if (openFiles.value.length > 0) {
        isMobileRightPanelOpen.value = true;
      } else {
        // 否则打开左侧文件树
        isMobileSidePanelOpen.value = true;
      }
      break;
    case 'settings':
      // 打开设置抽屉
      isSettingsDrawerVisible.value = true;
      break;
  }
};

// Agents状态 - 默认显示面板
const isMonitoringPanelVisible = ref(true);

// 切换工作区
const handleSwitchWorkspace = () => {
  router.push('/workspaces');
};

const handleCloseFile = (fileId: string) => {
  const fileToClose = openFiles.value.find(f => f.id === fileId);
  if (!fileToClose) {
    console.warn('[ChatView] File not found in openFiles:', fileId);
    return;
  }

  // 如果是媒体文件（blob URL），需要释放资源
  if (['image', 'video', 'audio'].includes(fileToClose.type)) {
    try {
      URL.revokeObjectURL(fileToClose.content);
    } catch (error) {
      console.warn('[ChatView] Failed to revoke blob URL:', error);
    }
  }

  // 从 openFiles 数组中移除文件
  openFiles.value = openFiles.value.filter(f => f.id !== fileId);

  // 如果关闭的是当前激活的文件，需要切换到其他文件
  if (currentActiveFileId.value === fileId) {
    // 优先选择最后一个打开的文件
    if (openFiles.value.length > 0) {
      currentActiveFileId.value = openFiles.value[openFiles.value.length - 1].id;
    } else {
      currentActiveFileId.value = null;
    }
  }
};

// Development helper: expose test function globally
if (appConfig.debug.exposeGlobal) {
  (window as unknown).testFollowupDialog = () => {
    followupData.value = {
      question: '这是一个测试问题：你的名字是什么？',
      suggestions: ['张三', '李四', '王五'],
      toolCallId: 'test-tool-call-id',
      taskId: 'test-task-id'
    };
    showFollowupDialog.value = true;
  };
}

const isRightPanelVisible = computed(() => openFiles.value.length > 0);

// 检查 LLM 配置，如果为空则自动打开 LLM Providers 抽屉
const checkLLMConfiguration = async () => {
  if (!chatStore.workspaceId) {
    return;
  }

  try {
    // 使用新的 API 获取所有级别的 LLM 配置（用户级和工作区级）
    const response = await apiManager.getWorkspacesApi().getLLMSettingsAllLevels(chatStore.workspaceId);
    const userConfigs = response.settings.user || [];
    const workspaceConfigs = response.settings.workspace || [];

    // 检查是否有任何 LLM provider 配置（用户级或工作区级）
    const hasConfigs = userConfigs.length > 0 || workspaceConfigs.length > 0;

    if (!hasConfigs) {
      console.warn('[ChatView] No LLM providers configured, opening LLM Providers drawer');
      // 打开 LLM Providers 抽屉
      isLLMDrawerVisible.value = true;

      // 显示提示消息
      setTimeout(() => {
        ElMessage({
          message: '请先配置 LLM Provider 后再使用 AI 功能',
          type: 'warning',
          duration: 5000,
          showClose: true
        });
      }, 500);
    }
  } catch (error) {
    console.error('[ChatView] Failed to check LLM configuration:', error);
    // 失败时不强制打开设置，可能是权限问题或 API 错误
  }
};

// 在组件挂载时立即打印API配置
onMounted(async () => {
  // 面板宽度不再持久化，使用默认值
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
    // Office 文件扩展名（交给 VueOfficeEditor 自行通过 workspace API 拉取内容）
    const officeExtensions = ['docx', 'xlsx', 'xls'];

    let fileType = 'text';
    if (imageExtensions.includes(extension)) fileType = 'image';
    else if (videoExtensions.includes(extension)) fileType = 'video';
    else if (audioExtensions.includes(extension)) fileType = 'audio';
    else if (pdfExtensions.includes(extension)) fileType = 'pdf';
    else if (officeExtensions.includes(extension)) fileType = 'office';
    else if (['md', 'markdown'].includes(extension)) fileType = 'markdown';
    else if (['json', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'py', 'sql', 'yaml', 'yml', 'xml', 'sh'].includes(extension)) fileType = 'code';
    else if (extension === 'csv') fileType = 'csv';

    // Office 文件：不要走文本读取，避免在 Tauri 中把二进制塞进响应式状态导致页面重载
    if (fileType === 'office') {
      return { content: '', type: fileType };
    }

    // 处理媒体文件（图像、视频、音频、PDF）
    if (fileType === 'image' || fileType === 'video' || fileType === 'audio' || fileType === 'pdf') {
      try {
        // 使用统一 httpClient 获取二进制数据
        const blob = await httpClient.download(
          `/workspaces/${workspaceId}/files?path=${encodeURIComponent(node.path)}`
        );
        const blobUrl = URL.createObjectURL(blob);

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

  // 检查文件是否已经打开
  const existingFile = openFiles.value.find(f => f.id === fileInfo.path);

  if (existingFile) {
    // 文件已打开，直接切换到该 tab
    currentActiveFileId.value = existingFile.id;
    return;
  }

  // 文件未打开，获取内容并打开新 tab
  try {
    const { content, type } = await fetchFileContent(fileInfo);

    // 如果是目录，不打开
    if (type === 'directory') {
      return;
    }

    // 创建新文件对象
    const newFile = {
      id: fileInfo.path,
      name: fileInfo.name,
      path: fileInfo.path,  // 添加 path 字段
      type,
      content,
      isDirty: false
    };

    openFiles.value.push(newFile);
    currentActiveFileId.value = newFile.id;
  } catch (error) {
    console.error('[ChatView] Failed to open file:', error);
  }
};


const isBase64DataUrl = (value: string): boolean => /^data:[^;]+;base64,/.test(value);

const dataUrlToFile = (dataUrl: string, fileName: string): File => {
  const [header, base64] = dataUrl.split(',', 2);
  const mimeType = header.match(/^data:(.*?);base64$/)?.[1] || 'application/octet-stream';
  const binary = atob(base64 || '');
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new File([bytes], fileName, { type: mimeType });
};

const saveFileContent = async (fileId: string, content: string) => {
  try {
    const workspaceId = chatStore.workspaceId || 'default';
    const file = openFiles.value.find(f => (f as { id: string }).id === fileId);
    if (!file) throw new Error('文件未找到');

    const targetPath = (file as { id: string }).id;

    if (isBase64DataUrl(content)) {
      const lastSlashIndex = targetPath.lastIndexOf('/');
      const parentPath = lastSlashIndex >= 0 ? targetPath.slice(0, lastSlashIndex) : '';
      const fileName = lastSlashIndex >= 0 ? targetPath.slice(lastSlashIndex + 1) : targetPath;
      const binaryFile = dataUrlToFile(content, fileName);

      await apiManager.getFilesApi().uploadFile(workspaceId, {
        file: binaryFile,
        path: parentPath,
      });

      (file as { content: string; isDirty: boolean }).content = '';
    } else {
      await apiManager.getFilesApi().saveFileContent(workspaceId, { path: targetPath, content });
      (file as { content: string; isDirty: boolean }).content = content;
    }

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

// 打开知识库抽屉
const handleOpenKnowledgeDrawer = () => {
  isKnowledgeDrawerVisible.value = true;
};

// 打开记忆抽屉
const handleOpenMemoryDrawer = () => {
  isMemoryDrawerVisible.value = true;
};

// 打开语言模型抽屉
const handleOpenLLMDrawer = () => {
  isLLMDrawerVisible.value = true;
};

// 打开技能抽屉
const handleOpenSkillsDrawer = () => {
  isSkillsDrawerVisible.value = true;
};

// 打开智能体抽屉
const handleOpenAgentsDrawer = () => {
  isAgentsDrawerVisible.value = true;
};

// 打开插件抽屉
const handleOpenPluginsDrawer = () => {
  isPluginsDrawerVisible.value = true;
};

// 打开MCP抽屉
const handleOpenMCPDrawer = () => {
  isMCPDrawerVisible.value = true;
};

// 打开定时任务抽屉
const handleOpenScheduledTasksDrawer = () => {
  isScheduledTasksDrawerVisible.value = true;
};

const handleOpenChannelsDrawer = () => {
  isChannelsDrawerVisible.value = true;
};

// 打开Evolution抽屉
const handleOpenEvolutionDrawer = () => {
  isEvolutionDrawerVisible.value = true;
};

const getValidWorkspaceId = async (): Promise<string | null> => {
  const routeWorkspaceId = route.params.workspaceId as string;
  if (routeWorkspaceId) {
    return routeWorkspaceId;
  }

  try {
    const workspaces = await apiManager.getWorkspacesApi().getWorkspaces();
    if (workspaces && workspaces.length > 0 && workspaces[0]) {
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

  // ✅ 监听任务完成事件，自动刷新已打开的文件内容
  window.addEventListener('task-node-complete-refresh', handleTaskCompleteRefresh);

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
    isMonitoringPanelVisible.value = true;
  }
});

onUnmounted(() => {
  // 组件卸载时的清理工作（如果需要）
  window.removeEventListener('task-node-complete-refresh', handleTaskCompleteRefresh);
});

// ✅ 处理任务完成后的自动刷新
const fileContentAreaRef = ref<unknown>(null)

const handleTaskCompleteRefresh = async (event: Event) => {
  const customEvent = event as CustomEvent<{ workspaceId: string; taskNodeId: string }>

  // 只刷新当前工作区的文件
  if (customEvent.detail.workspaceId === chatStore.workspaceId) {
    // 重新加载所有已打开文件的内容
    const filesToRefresh = [...openFiles.value]
    for (const file of filesToRefresh) {
      try {
        const fileInfo = { path: (file as { id: string }).id, name: (file as { name: string }).name }
        const { content, type } = await fetchFileContent(fileInfo)

        // 更新文件内容
        const fileIndex = openFiles.value.findIndex(f => (f as { id: string }).id === fileInfo.path)
        if (fileIndex !== -1) {
          (openFiles.value[fileIndex] as { content: string; type: string }).content = content
        }
      } catch (error) {
        console.error(`[ChatView] Failed to refresh file ${(file as { name: string }).name}:`, error)
      }
    }
  }
}

// 监听路由参数变化，切换工作区时更新状态
// 注意：不使用 immediate: true，因为 onMounted 已经处理了初始化
watch(() => route.params.workspaceId, async (newWorkspaceId) => {
  const finalWorkspaceId = (newWorkspaceId as string) || await getValidWorkspaceId();
  if (finalWorkspaceId) {
    // 检查是否需要更新（避免重复设置）
    const currentWsId = chatStore.workspaceId;
    if (currentWsId === finalWorkspaceId) {
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
  // 更新追问数据
  followupData.value = {
    question: message.question,
    suggestions: message.suggestions || [],
    toolCallId: message.tool_call_id,
    taskId: message.task_id
  };

  // 显示对话框
  showFollowupDialog.value = true;
}

// 处理追问回复
async function handleFollowupResponse(toolCallId: string, response: string) {
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

    // 通过 chatStore 发送消息
    await chatStore.sendWebSocketMessage(responseMessage);
  } catch (error) {
    console.error('❌ 发送追问回复失败:', error);
  }
}

async function handleFollowupCancel(toolCallId: string) {
  try {
    // 使用 chatStore 的 WebSocket 连接发送取消消息
    const { MessageBuilder } = await import('@/services/protocol');

    const cancelMessage = MessageBuilder.createBaseMessage(
      MessageType.FOLLOWUP_CANCEL,
      chatStore.sessionId || ''
    );

    // 添加特定字段
    Object.assign(cancelMessage, {
      task_id: followupData.value.taskId,
      tool_call_id: toolCallId,
      reason: 'user_cancelled'
    });

    // 通过 chatStore 发送消息
    await chatStore.sendWebSocketMessage(cancelMessage);
  } catch (error) {
    console.error('❌ 发送追问取消失败:', error);
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
  min-width: 100px;
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
  padding: 0 !important;
  /* 移除内边距 */
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
  flex-shrink: 0;
  min-width: 100px;
  overflow: hidden;
}

.right-panel--full {
  flex: 1;
  width: auto !important;
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
