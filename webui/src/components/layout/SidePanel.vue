/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-aside :width="collapsed ? '57px' : '400px'" class="side-panel">
    <div class="side-panel-container">
      <div v-if="!collapsed" class="content-area">
        <!-- 侧边栏切换按钮 -->
        <div class="sidebar-tabs">
          <button
            :class="['tab-button', { active: activeTab === 'conversations' }]"
            @click="activeTab = 'conversations'"
            data-testid="conversations-tab"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span>会话</span>
          </button>
          <button
            :class="['tab-button', { active: activeTab === 'files' }]"
            @click="activeTab = 'files'"
            data-testid="files-tab"
          >
            <el-icon><Folder /></el-icon>
            <span>工作区</span>
          </button>
          <button
            :class="['tab-button', { active: activeTab === 'memory' }]"
            @click="activeTab = 'memory'"
            data-testid="memory-tab"
          >
            <el-icon><Connection /></el-icon>
            <span>记忆</span>
          </button>
        </div>

        <!-- 历史会话面板 -->
        <div v-show="activeTab === 'conversations'" class="tab-panel">
          <div class="panel-content">
            <div class="conversation-actions">
              <el-button type="primary" :icon="Plus" @click="handleNewChat" class="flex-1" size="small">新建会话</el-button>
              <el-button type="danger" :icon="Delete" @click="handleDeleteAllConversations" class="flex-1" size="small">删除所有</el-button>
            </div>
            <el-scrollbar>
              <el-menu :default-active="activeConversationId" @select="handleSelectConversation" v-loading="loading" class="conversation-menu">
                <el-menu-item v-for="conv in conversations" :key="conv.id" :index="conv.id" class="conversation-menu-item">
                  <div class="conversation-item">
                    <div class="conv-content">
                      <span class="conv-title">{{ conv.title }}</span>
                      <span class="conv-date">{{ formatDate(conv.lastUpdated) }}</span>
                      <span class="conv-id">ID: {{ conv.id }}</span>
                    </div>
                    <el-button
                      :icon="Delete"
                      type="danger"
                      text
                      circle
                      size="small"
                      class="conv-delete-btn"
                      @click.stop="handleDeleteConversation(conv)"
                      title="删除对话"
                    />
                  </div>
                </el-menu-item>
              </el-menu>
              <el-empty v-if="!loading && conversations.length === 0" description="暂无历史对话" :image-size="60" />
            </el-scrollbar>
          </div>
        </div>

        <!-- 项目文件面板 -->
        <div v-show="activeTab === 'files'" class="tab-panel">
          <div class="panel-content">
            <el-scrollbar>
              <div v-loading="filesLoading">
                <div v-if="filesError" class="error-text">{{ filesError }}</div>
                <div v-else>
                  <!-- 项目文件树 -->
                  <div class="section-block">
                    <div class="section-header">
                      <h4>文件树</h4>
                      <div class="file-actions">
                        <el-tooltip content="刷新" placement="top">
                          <el-button :icon="Refresh" text circle size="small" @click="handleRefreshFiles" />
                        </el-tooltip>
                        <el-tooltip content="上传文件" placement="top">
                          <el-button :icon="Upload" text circle size="small" @click="handleUploadFile()" />
                        </el-tooltip>
                        <el-tooltip content="新建文件" placement="top">
                          <el-button :icon="Document" text circle size="small" @click="handleCreateFile()" />
                        </el-tooltip>
                        <el-tooltip content="新建目录" placement="top">
                          <el-button :icon="FolderAdd" text circle size="small" @click="handleCreateDirectory()" />
                        </el-tooltip>
                      </div>
                    </div>
                    <el-tree
                      ref="fileTreeRef"
                      :data="nestedFileTree"
                      :props="defaultProps"
                      node-key="path"
                      lazy
                      :load="loadTreeNode"
                      @node-click="handleTreeNodeClick"
                      @node-contextmenu="handleNodeContextMenu"
                      :expand-on-click-node="false"
                      :highlight-current="true"
                    >
                      <template #default="{ node, data }">
                        <span class="custom-tree-node">
                          <span class="tree-node-label">
                            <el-icon v-if="data.is_directory || data.type === 'directory'"><Folder /></el-icon>
                            <el-icon v-else><Document /></el-icon>
                            {{ node.label }}
                          </span>
                          <span class="tree-node-actions">
                            <el-button
                              :icon="Delete"
                              type="danger"
                              text
                              circle
                              size="small"
                              class="node-delete-btn"
                              @click.stop="handleQuickDelete(data)"
                              title="删除"
                            />
                          </span>
                        </span>
                      </template>
                    </el-tree>
                    <el-empty v-if="nestedFileTree.length === 0" description="暂无文件" :image-size="40" />
                  </div>
                </div>
              </div>
            </el-scrollbar>
          </div>
        </div>

        <!-- 记忆面板 -->
        <div v-show="activeTab === 'memory'" class="tab-panel">
          <MemoryBrowser
            v-if="workspaceId"
            :workspace-id="workspaceId"
            @select-memory="handleSelectMemory"
          />
        </div>
      </div>
    </div>

    <!-- 用户设置抽屉 -->
    <UserSettingsDrawer v-model="isUserSettingsVisible" />

    <!-- 文件上传对话框 -->
    <FileUploadDialog
      v-model="isUploadDialogVisible"
      :workspace-id="workspaceId"
      parent-path=""
      parent-name=""
      @success="handleUploadSuccess"
    />

    <!-- 文件右键菜单 -->
    <teleport to="body">
      <div
        v-if="contextMenuVisible"
        class="context-menu"
        :style="{ left: contextMenuPosition.x + 'px', top: contextMenuPosition.y + 'px' }"
        @click.stop
      >
        <div class="context-menu-item" @click="handleCreateFile(selectedFileNode)">
          <el-icon><Document /></el-icon>
          <span>新建文件</span>
        </div>
        <div class="context-menu-item" @click="handleCreateDirectory(selectedFileNode)">
          <el-icon><FolderAdd /></el-icon>
          <span>新建目录</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-divider"></div>
        <div v-if="selectedFileNode" class="context-menu-item" @click="handleRename">
          <el-icon><Edit /></el-icon>
          <span>重命名</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-item" @click="handleCopy">
          <el-icon><CopyDocument /></el-icon>
          <span>复制</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-item danger" @click="handleDelete">
          <el-icon><Delete /></el-icon>
          <span>删除</span>
        </div>
      </div>
    </teleport>
  </el-aside>
</template>

<script setup lang="ts">
/* eslint-disable */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import { apiManager } from '@/services/api';
import { ElMessageBox, ElMessage } from 'element-plus';
import {
  ChatDotRound, Folder, Document, Plus, Delete,
  FolderAdd, Edit, CopyDocument, Upload, Refresh, Connection
} from '@element-plus/icons-vue';
import UserSettingsDrawer from './UserSettingsDrawer.vue';
import FileUploadDialog from '@/components/FileUploadDialog.vue';
import MemoryBrowser from './MemoryBrowser.vue';

const chatStore = useChatStore();




// 点击外部关闭右键菜单
const handleClickOutside = () => {
  closeContextMenu();
};

// 更新临时会话为真实会话
const updateTempConversation = (tempId: string, realId: string) => {
  console.log(`[SIDE_PANEL] 更新临时会话: ${tempId} -> ${realId}`);

  // 查找临时会话在列表中的索引
  const tempIndex = conversations.value.findIndex((c: any) => c.id === tempId);

  if (tempIndex !== -1) {
    // 更新会话ID和移除临时标记
    conversations.value[tempIndex].id = realId;
    conversations.value[tempIndex].isTemp = false;

    // 如果当前选中的是临时会话，更新选中状态
    if (activeConversationId.value === tempId) {
      activeConversationId.value = realId;
    }

    console.log(`[SIDE_PANEL] 临时会话已更新为真实会话`);
  } else {
    console.warn(`[SIDE_PANEL] 未找到临时会话: ${tempId}`);
  }
};

const props = defineProps({
  collapsed: Boolean,
  workspaceId: String
});

const emit = defineEmits(['open-file', 'open-settings']);

// 注册全局函数供chat store调用
onMounted(() => {
  document.addEventListener('click', handleClickOutside);

  // 注册更新临时会话的全局函数
  if (typeof window !== 'undefined') {
    (window as unknown).updateTempConversation = updateTempConversation;
  }
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});

// 用户设置抽屉
const isUserSettingsVisible = ref(false);

// 文件上传对话框
const isUploadDialogVisible = ref(false);

// 当前激活的标签页（默认选择"工作区"）
const activeTab = ref<'conversations' | 'files' | 'memory'>('files');

// 历史会话
const conversations = ref<unknown[]>([]);
const activeConversationId = ref<string | null>(null);
const loading = ref(false);

// 项目文件
const workspaceName = ref('');
const workspacePath = ref('');
const workspaceLoading = ref(false);
const workspaceError = ref('');
const openFiles = ref<unknown[]>([]);
const fileTree = ref<unknown[]>([]);
const filesLoading = ref(false);
const filesError = ref('');

// 右键菜单相关
const contextMenuVisible = ref(false);
const contextMenuPosition = ref({ x: 0, y: 0 });
const selectedFileNode = ref<unknown>(null);

// 文件树组件引用
const fileTreeRef = ref<unknown>(null);

// el-tree 组件的默认 props 配置（懒加载模式）
const defaultProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: { is_directory?: boolean; type?: string }) => {
    // 如果是文件或者是空目录，则认为是叶子节点
    return !data.is_directory && data.type !== 'directory';
  }
};

const nestedFileTree = computed(() => {
  return fileTree.value;
});

// 加载历史会话
const loadConversations = async () => {
  if (!props.workspaceId) return;

  loading.value = true;
  try {
    const convs = await apiManager.getWorkspacesApi().getConversations(props.workspaceId);
    conversations.value = convs?.items || [];
    if (conversations.value.length > 0 && !activeConversationId.value) {
      activeConversationId.value = conversations.value[0].id;
    }
  } catch (e) {
    console.error('Failed to load conversations:', e);
  } finally {
    loading.value = false;
  }
};

// 加载工作区信息
const loadWorkspaceInfo = async () => {
  if (!props.workspaceId) return;

  workspaceLoading.value = true;
  try {
    const ws = await apiManager.getWorkspacesApi().getWorkspaceInfo(props.workspaceId);
    workspaceName.value = ws?.name || '未知';
    workspacePath.value = ws?.path || '/';
  } catch {
    workspaceError.value = '加载失败';
  }
  workspaceLoading.value = false;
};

// 加载文件（仅顶层）
const loadFiles = async () => {
  if (!props.workspaceId) return;

  filesLoading.value = true;
  try {
    const [tree, open] = await Promise.all([
      // 只加载顶层目录，不递归加载子节点
      apiManager.getWorkspacesApi().getFileTree(props.workspaceId, {
        maxDepth: 1,  // 只加载顶层
        recursive: false  // 不递归，启用懒加载
      }),
      apiManager.getWorkspacesApi().getOpenFiles(props.workspaceId)
    ]);
    fileTree.value = tree || [];
    openFiles.value = open || [];
    console.log('[FileTree] Initial top-level directories loaded:', fileTree.value.length);
  } catch {
    console.error('加载文件失败');
    filesError.value = '加载失败';
  } finally {
    filesLoading.value = false;
  }
};

const handleNewChat = () => {
  // 清空聊天
  chatStore.clearChat();

  // 生成临时会话ID（使用时间戳和随机数）
  const tempConversationId = `temp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

  // 设置为临时会话（不发送conversationId给后端）
  chatStore.setTempConversation(tempConversationId);

  // 创建临时会话对象
  const tempConversation = {
    id: tempConversationId,
    title: '新会话',
    lastUpdated: new Date().toISOString(),
    isTemp: true // 标记为临时会话，用于区分已保存的会话
  };

  // 将临时会话添加到列表顶部
  conversations.value.unshift(tempConversation);

  // 设置为当前选中会话
  activeConversationId.value = tempConversationId;
};

const handleSelectConversation = (id: string) => {
  activeConversationId.value = id;
  chatStore.loadConversation(id);
};

const handleDeleteConversation = async (conv: unknown) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除对话 "${conv.title}" 吗？此操作不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    );

    // 调用删除API
    const result = await apiManager.getWorkspacesApi().deleteConversation(props.workspaceId!, conv.id);

    if (result.success) {
      ElMessage.success('对话已删除');

      // 从列表中移除
      conversations.value = conversations.value.filter(c => c.id !== conv.id);

      // 如果删除的是当前选中的对话，清空选择
      if (activeConversationId.value === conv.id) {
        activeConversationId.value = null;
        chatStore.clearChat();
      }
    } else {
      ElMessage.error(result.message || '删除失败');
    }
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('Failed to delete conversation:', error);
      ElMessage.error(error?.response?.data?.detail || '删除失败，请重试');
    }
  }
};

const handleDeleteAllConversations = async () => {
  if (conversations.value.length === 0) {
    ElMessage.warning('暂无历史对话可删除');
    return;
  }

  try {
    await ElMessageBox.confirm(
      `确定要删除所有历史对话吗？此操作将删除 ${conversations.value.length} 个对话，且不可恢复。`,
      '删除所有对话确认',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'error',
        confirmButtonClass: 'el-button--danger'
      }
    );

    // 调用删除所有API
    const result = await apiManager.getWorkspacesApi().deleteAllConversations(props.workspaceId!);

    if (result.success) {
      ElMessage.success(`已删除 ${result.deletedCount || 0} 个对话`);

      // 清空列表
      conversations.value = [];

      // 清空当前选中
      activeConversationId.value = null;
      chatStore.clearChat();
    } else {
      ElMessage.error(result.message || '删除失败');
    }
  } catch (error: unknown) {
    if (error !== 'cancel') {
      console.error('Failed to delete all conversations:', error);
      ElMessage.error(error?.response?.data?.detail || '删除所有对话失败，请重试');
    }
  }
};

// 懒加载树节点 - 当用户展开目录时加载子节点
const loadTreeNode = async (node: unknown, resolve: (data: unknown[]) => void) => {
  console.log('[FileTree] Loading children for node:', node.data?.path || node.data?.name);

  if (!props.workspaceId) {
    resolve([]);
    return;
  }

  const directoryPath = node.data?.path;
  if (!directoryPath) {
    console.warn('[FileTree] No path found for node:', node.data);
    resolve([]);
    return;
  }

  try {
    // 获取该目录的直接子节点（只加载一层）
    const children = await apiManager.getWorkspacesApi().getFileTree(props.workspaceId, {
      path: directoryPath,
      maxDepth: 1,  // 只加载直接子节点
      recursive: false
    });

    console.log('[FileTree] Loaded children for', directoryPath, ':', children?.length || 0, 'items');
    resolve(children || []);
  } catch (error) {
    console.error('[FileTree] Failed to load children for', directoryPath, ':', error);
    resolve([]);
  }
};

// 处理树节点的点击（用于打开文件，目录展开由懒加载自动处理）
const handleTreeNodeClick = (data: unknown, _node: unknown) => {
  const isDirectory = data.is_directory || data.type === 'directory';

  console.log('[FileTree] Node clicked:', {
    name: data.name,
    path: data.path,
    isDirectory
  });

  // 懒加载模式下，Element Plus Tree 会自动处理目录的展开/折叠
  // 我们只需要处理文件的点击
  if (!isDirectory) {
    // 如果是文件，打开文件
    emit('open-file', { path: data.path, name: data.name });
  }
  // 如果是目录，Element Plus Tree 会自动触发懒加载，无需手动处理
};

// 右键菜单处理
const handleNodeContextMenu = (event: MouseEvent, data: unknown) => {
  event.preventDefault();
  event.stopPropagation();

  selectedFileNode.value = data;
  contextMenuPosition.value = {
    x: event.clientX,
    y: event.clientY
  };
  contextMenuVisible.value = true;
};

// 关闭右键菜单
const closeContextMenu = () => {
  contextMenuVisible.value = false;
  selectedFileNode.value = null;
};

// 新建文件
// 刷新文件树
const handleRefreshFiles = async () => {
  await loadFiles();
  ElMessage.success('文件树已刷新');
};

// 打开上传文件对话框
const handleUploadFile = () => {
  isUploadDialogVisible.value = true;
};

// 处理上传成功
const handleUploadSuccess = async () => {
  // 重新加载文件树
  await loadFiles();
  ElMessage.success('文件上传成功');
};

const handleCreateFile = async (parentNode?: unknown) => {
  closeContextMenu();

  try {
    const { value } = await ElMessageBox.prompt('请输入文件名:', '新建文件', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPattern: /.+/,
      inputErrorMessage: '文件名不能为空'
    });

    if (!value) return;

    const parentPath = parentNode?.path || '';
    const fullPath = parentPath ? `${parentPath}/${value}` : value;

    await apiManager.getWorkspacesApi().createFileOrDirectory(props.workspaceId!, {
      path: fullPath,
      content: '',
      is_directory: false
    });

    ElMessage.success('文件创建成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '创建文件失败');
    }
  }
};

// 新建目录
const handleCreateDirectory = async (parentNode?: unknown) => {
  closeContextMenu();

  try {
    const { value } = await ElMessageBox.prompt('请输入目录名:', '新建目录', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPattern: /.+/,
      inputErrorMessage: '目录名不能为空'
    });

    if (!value) return;

    const parentPath = parentNode?.path || '';
    const fullPath = parentPath ? `${parentPath}/${value}` : value;

    await apiManager.getWorkspacesApi().createFileOrDirectory(props.workspaceId!, {
      path: fullPath,
      is_directory: true
    });

    ElMessage.success('目录创建成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '创建目录失败');
    }
  }
};

// 重命名文件或目录
const handleRename = async () => {
  closeContextMenu();

  if (!selectedFileNode.value) return;

  try {
    const { value } = await ElMessageBox.prompt('请输入新名称:', '重命名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: selectedFileNode.value.name,
      inputPattern: /.+/,
      inputErrorMessage: '名称不能为空'
    });

    if (!value || value === selectedFileNode.value.name) return;

    const oldPath = selectedFileNode.value.path;
    const pathParts = oldPath.split('/');
    pathParts[pathParts.length - 1] = value;
    const newPath = pathParts.join('/');

    await apiManager.getWorkspacesApi().renameFileOrDirectory(props.workspaceId!, {
      old_path: oldPath,
      new_path: newPath
    });

    ElMessage.success('重命名成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '重命名失败');
    }
  }
};

// 复制文件或目录
const handleCopy = async () => {
  closeContextMenu();

  if (!selectedFileNode.value) return;

  try {
    const { value } = await ElMessageBox.prompt('请输入目标名称:', '复制', {
      confirmButtonText: '复制',
      cancelButtonText: '取消',
      inputValue: `${selectedFileNode.value.name}_copy`,
      inputPattern: /.+/,
      inputErrorMessage: '名称不能为空'
    });

    if (!value) return;

    const sourcePath = selectedFileNode.value.path;
    const pathParts = sourcePath.split('/');
    pathParts[pathParts.length - 1] = value;
    const destinationPath = pathParts.join('/');

    await apiManager.getWorkspacesApi().copyFileOrDirectory(props.workspaceId!, {
      source_path: sourcePath,
      destination_path: destinationPath
    });

    ElMessage.success('复制成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '复制失败');
    }
  }
};

// 删除文件或目录
const handleDelete = async () => {
  closeContextMenu();

  if (!selectedFileNode.value) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除 "${selectedFileNode.value.name}" 吗？此操作不可撤销。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    );

    await apiManager.getWorkspacesApi().deleteFileOrDirectory(
      props.workspaceId!,
      selectedFileNode.value.path
    );

    ElMessage.success('删除成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '删除失败');
    }
  }
};

// 快速删除（从节点上的删除按钮）
const handleQuickDelete = async (nodeData: unknown) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 "${nodeData.name}" 吗？此操作不可撤销。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    );

    await apiManager.getWorkspacesApi().deleteFileOrDirectory(
      props.workspaceId!,
      nodeData.path
    );

    ElMessage.success('删除成功');
    await loadFiles(); // 刷新文件列表
  } catch (error: unknown) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '删除失败');
    }
  }
};

// Handle memory selection
const handleSelectMemory = (memoryId: string) => {
  console.log('[SidePanel] Memory selected:', memoryId);
  // Future: Could open memory details or use memory in chat
};

const formatDate = (date: string): string => {
  if (!date) return '';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '';

  // 格式：YYYY-MM-DD HH:mm:ss
  const pad = (n: number) => String(n).padStart(2, '0');
  const yyyy = d.getFullYear();
  const MM = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const HH = pad(d.getHours());
  const mm = pad(d.getMinutes());
  const ss = pad(d.getSeconds());

  return `${yyyy}-${MM}-${dd} ${HH}:${mm}:${ss}`;
};

watch(() => props.workspaceId, (newVal) => {
  if (newVal) {
    loadConversations();
    loadWorkspaceInfo();
    loadFiles();
  }
}, { immediate: true });

defineExpose({
  loadConversations,
  loadWorkspaceInfo,
  loadFiles
});
</script>

<style scoped>
.side-panel {
  background-color: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color-light);
  transition: width 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.side-panel-container {
  display: flex;
  height: 100%;
}

.content-area {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 侧边栏切换标签 */
.sidebar-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 12px 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
}

.tab-button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  transition: all 0.2s;
}

.tab-button:hover {
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
}

.tab-button.active {
  background: var(--el-color-primary);
  color: #ffffff;
  border-color: var(--el-color-primary);
}

.tab-button .el-icon {
  font-size: 16px;
}

/* 标签面板 */
.tab-panel {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 12px;
}

.panel-content .el-scrollbar {
  flex: 1;
  overflow-y: auto;
  height: 100%;
}

.panel-content .el-scrollbar .el-scrollbar__wrap {
  height: 100%;
  overflow-y: auto;
}

.conversation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
}

.conv-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.conv-delete-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.conversation-menu-item:hover .conv-delete-btn {
  opacity: 1;
}

:deep(.conversation-menu) {
  border: none;
  background: transparent;
}

:deep(.conversation-menu .el-menu-item) {
  padding: 0;
  height: auto;
  line-height: normal;
  border-radius: 6px;
  margin-bottom: 4px;
  transition: all 0.2s;
}

:deep(.conversation-menu .el-menu-item:hover) {
  background-color: var(--el-fill-color-light);
}

:deep(.conversation-menu .el-menu-item.is-active) {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.conv-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
  font-size: 13px;
  word-break: break-word;
  padding: 0 12px;
}

.conv-date {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  padding: 0 12px;
}

.conv-id {
  font-size: 10px;
  color: var(--el-color-info);
  padding: 0 12px;
  font-family: 'Courier New', monospace;
  opacity: 0.8;
}

.graphs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.graph-card {
  padding: 8px;
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.graph-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.graph-card.active {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.graph-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.graph-icon {
  font-size: 18px;
  color: var(--el-color-primary);
}

.graph-info {
  flex: 1;
  min-width: 0;
}

.graph-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}

.graph-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.graph-header .delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
  flex-shrink: 0;
}

.graph-card:hover .graph-header .delete-btn {
  opacity: 1;
}

.graph-header:hover {
  cursor: pointer;
}

.graph-id {
  font-family: monospace;
  color: var(--el-text-color-secondary);
}

.section-block {
  margin-bottom: 16px;
}

.section-block:last-child {
  margin-bottom: 0;
}

.section-block h4 {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  text-transform: uppercase;
}

.ws-name {
  font-weight: bold;
  font-size: 13px;
}

.ws-path {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.open-files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.open-file-item {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.open-file-item:hover {
  background-color: var(--el-fill-color-light);
}

.open-file-item .file-name {
  flex-grow: 1;
  margin-left: 8px;
  font-size: 13px;
}

.error-text {
  color: var(--el-color-error);
  font-size: 12px;
  text-align: center;
  padding: 8px;
}

.mb-2 {
  margin-bottom: 8px;
}

.w-full {
  width: 100%;
}

.conversation-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.flex-1 {
  flex: 1;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.section-header h4 {
  margin: 0;
}

.file-actions {
  display: flex;
  gap: 4px;
}

.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  flex: 1;
}

.tree-node-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  flex: 1;
  overflow: hidden;
}

.tree-node-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

:deep(.el-tree-node__content:hover) .tree-node-actions {
  opacity: 1;
}

:deep(.el-tree-node__content) {
  padding: 4px 0;
}

:deep(.el-tree-node__content:hover) {
  background-color: var(--el-fill-color-light);
}

.node-delete-btn {
  padding: 4px;
}

.node-delete-btn:hover {
  background-color: var(--el-color-danger-light-9);
}

/* 右键菜单样式 */
.context-menu {
  position: fixed;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  z-index: 9999;
  min-width: 160px;
  padding: 4px 0;
  animation: context-menu-fade-in 0.1s ease;
}

@keyframes context-menu-fade-in {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-regular);
  transition: all 0.2s;
}

.context-menu-item:hover {
  background-color: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.context-menu-item.danger {
  color: var(--el-color-danger);
}

.context-menu-item.danger:hover {
  background-color: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.context-menu-item .el-icon {
  font-size: 16px;
}

.context-menu-divider {
  height: 1px;
  background-color: var(--el-border-color-lighter);
  margin: 4px 0;
}
</style>
