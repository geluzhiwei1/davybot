/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-aside :width="collapsed ? '57px' : '400px'" class="side-panel" :class="{ 'mobile-drawer-mode': isMobileDrawer }">
    <div class="side-panel-container">
      <!-- 移动端关闭按钮 -->
      <div v-if="isMobileDrawer" class="mobile-close-btn">
        <el-button :icon="Close" circle @click="handleCloseMobileDrawer" />
      </div>

      <div v-if="!collapsed" class="content-area" :class="{ 'has-mobile-close': isMobileDrawer }">
        <el-collapse v-model="activeCollapse" class="sidebar-collapse" :class="{ 'mobile-collapse': isMobileDrawer }">
          <!-- 工作区面板 -->
          <el-collapse-item name="workspace" class="collapse-item">
            <template #title>
              <div class="collapse-title">
                <el-icon>
                  <Folder />
                </el-icon>
                <span>{{ t('sidePanel.workspace') }}</span>
              </div>
            </template>
            <div class="collapse-content">
              <el-scrollbar>
                <div v-loading="filesLoading">
                  <div v-if="filesError" class="error-text">{{ filesError }}</div>
                  <div v-else>
                    <!-- 文件操作按钮 -->
                    <div class="file-operations">
                      <el-tooltip :content="t('sidePanel.refresh')" placement="top">
                        <el-button :icon="Refresh" text circle size="small" @click="handleRefreshFiles" />
                      </el-tooltip>
                      <el-tooltip :content="t('sidePanel.uploadFile')" placement="top">
                        <el-button :icon="Upload" text circle size="small" @click="handleUploadFile()" />
                      </el-tooltip>
                      <el-tooltip :content="t('sidePanel.newFile')" placement="top">
                        <el-button :icon="Document" text circle size="small" @click="handleCreateFile()" />
                      </el-tooltip>
                      <el-tooltip :content="t('sidePanel.newDirectory')" placement="top">
                        <el-button :icon="FolderAdd" text circle size="small" @click="handleCreateDirectory()" />
                      </el-tooltip>
                    </div>
                    <!-- 文件树 -->
                    <el-tree ref="fileTreeRef" :data="nestedFileTree" :props="defaultProps" node-key="path" lazy
                      :load="loadTreeNode" @node-click="handleTreeNodeClick" @node-contextmenu="handleNodeContextMenu"
                      :expand-on-click-node="false" :highlight-current="true" draggable :allow-drag="allowDrag"
                      :allow-drop="allowDrop" @node-drag-start="handleDragStart" @node-drag-end="handleDragEnd"
                      @node-drop="handleDrop">
                      <template #default="{ node, data }">
                        <span class="custom-tree-node" :class="{ 'is-dragging': isDragging }">
                          <span class="tree-node-label">
                            <el-icon v-if="data.is_directory || data.type === 'directory'">
                              <Folder />
                            </el-icon>
                            <el-icon v-else>
                              <Document />
                            </el-icon>
                            {{ node.label }}
                          </span>
                          <span class="tree-node-actions">
                            <el-button :icon="Delete" type="danger" text circle size="small" class="node-delete-btn"
                              @click.stop="handleQuickDelete(data)" :title="t('sidePanel.delete')" />
                          </span>
                        </span>
                      </template>
                    </el-tree>
                    <el-empty v-if="nestedFileTree.length === 0" :description="t('sidePanel.noFiles')"
                      :image-size="40" />
                  </div>
                </div>
              </el-scrollbar>
            </div>
          </el-collapse-item>

          <!-- 会话面板 -->
          <el-collapse-item name="conversations" class="collapse-item">
            <template #title>
              <div class="collapse-title">
                <el-icon>
                  <ChatDotRound />
                </el-icon>
                <span>{{ t('sidePanel.conversations') }}</span>
              </div>
            </template>
            <div class="collapse-content">
              <!-- 会话操作按钮 -->
              <div class="conversation-operations">
                <el-button :icon="Refresh" @click="loadConversations" size="small" :title="t('sidePanel.refresh')">
                </el-button>
                <el-button type="primary" :icon="Plus" @click="handleNewChat" class="flex-1" size="small">{{
                  t('sidePanel.newConversation') }}</el-button>
                <el-button type="danger" :icon="Delete" @click="handleDeleteAllConversations" class="flex-1"
                  size="small">{{ t('sidePanel.deleteAll') }}</el-button>
              </div>
              <el-scrollbar>
                <el-menu :default-active="activeConversationId" @select="handleSelectConversation" v-loading="loading"
                  class="conversation-menu">
                  <el-menu-item v-for="conv in conversations" :key="conv.id" :index="conv.id"
                    class="conversation-menu-item">
                    <div class="conversation-item">
                      <div class="conv-content">
                        <span class="conv-title">{{ conv.title }}</span>
                        <span class="conv-date">{{ formatDate(conv.lastUpdated) }}</span>
                        <span class="conv-id">ID: {{ conv.id }}</span>
                      </div>
                      <el-button :icon="Delete" type="danger" text circle size="small" class="conv-delete-btn"
                        @click.stop="handleDeleteConversation(conv)" :title="t('sidePanel.deleteConversation')" />
                    </div>
                  </el-menu-item>
                </el-menu>
                <el-empty v-if="!loading && conversations.length === 0" :description="t('sidePanel.noConversations')"
                  :image-size="60" />
              </el-scrollbar>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <!-- 用户设置抽屉 -->
    <UserSettingsDrawer v-model="isUserSettingsVisible" />

    <!-- 文件上传对话框 -->
    <FileUploadDialog v-model="isUploadDialogVisible" :workspace-id="workspaceId" parent-path="" parent-name=""
      @success="handleUploadSuccess" />

    <!-- 文件右键菜单 -->
    <teleport to="body">
      <div v-if="contextMenuVisible" class="context-menu"
        :style="{ left: contextMenuPosition.x + 'px', top: contextMenuPosition.y + 'px' }" @click.stop.prevent>
        <div class="context-menu-item" @click.stop.prevent="handleCreateFile(selectedFileNode)">
          <el-icon>
            <Document />
          </el-icon>
          <span>{{ t('sidePanel.newFile') }}</span>
        </div>
        <div class="context-menu-item" @click.stop.prevent="handleCreateDirectory(selectedFileNode)">
          <el-icon>
            <FolderAdd />
          </el-icon>
          <span>{{ t('sidePanel.newDirectory') }}</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-divider"></div>
        <div v-if="selectedFileNode" class="context-menu-item" @click.stop.prevent="handleRename">
          <el-icon>
            <Edit />
          </el-icon>
          <span>{{ t('sidePanel.rename') }}</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-item" @click.stop.prevent="handleCopy">
          <el-icon>
            <CopyDocument />
          </el-icon>
          <span>{{ t('sidePanel.copy') }}</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-item" @click.stop.prevent="handleDownload">
          <el-icon>
            <Download />
          </el-icon>
          <span>{{ t('sidePanel.download') }}</span>
        </div>
        <div v-if="selectedFileNode" class="context-menu-item danger" @click.stop.prevent="handleDelete">
          <el-icon>
            <Delete />
          </el-icon>
          <span>{{ t('sidePanel.delete') }}</span>
        </div>
      </div>
    </teleport>
  </el-aside>
</template>

<script setup lang="ts">
/* eslint-disable */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import { apiManager } from '@/services/api';
import { ElMessageBox, ElMessage } from 'element-plus';
import {
  ChatDotRound, Folder, Document, Plus, Delete,
  FolderAdd, Edit, CopyDocument, Upload, Refresh, Download, Close
} from '@element-plus/icons-vue';
import UserSettingsDrawer from './UserSettingsDrawer.vue';
import FileUploadDialog from '@/components/FileUploadDialog.vue';
import { useMobile } from '@/composables/useMobile';

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const { t } = useI18n();



// 点击外部关闭右键菜单
const handleClickOutside = (event: Event) => {
  // 只在菜单可见且点击的是菜单外部时才关闭
  if (contextMenuVisible.value) {
    const target = event.target as HTMLElement;
    const contextMenu = document.querySelector('.context-menu');
    if (contextMenu && !contextMenu.contains(target)) {
      closeContextMenu();
    }
  }
};

// Update temporary conversation to real conversation
const updateTempConversation = (tempId: string, realId: string) => {
  // Find temporary conversation index in list
  const tempIndex = conversations.value.findIndex((c: any) => c.id === tempId);

  if (tempIndex !== -1) {
    // Update conversation ID and remove temporary flag
    conversations.value[tempIndex].id = realId;
    conversations.value[tempIndex].isTemp = false;

    // If currently selected is temporary, update selected state
    if (activeConversationId.value === tempId) {
      activeConversationId.value = realId;
    }
  }
};

const props = defineProps({
  collapsed: Boolean,
  workspaceId: String,
  // 移动端抽屉模式
  isMobileDrawer: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits<{
  'open-file': [file: any]
  'open-settings': []
  'close-mobile-drawer': []
}>();

// 注册全局函数供chat store调用
onMounted(() => {
  document.addEventListener('click', handleClickOutside);

  // Register global function for updating temporary conversations
  if (typeof window !== 'undefined') {
    (window as unknown).updateTempConversation = updateTempConversation;
  }

  // ✅ 监听任务完成事件，自动刷新文件树
  window.addEventListener('task-node-complete-refresh', handleTaskCompleteRefresh);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
  window.removeEventListener('task-node-complete-refresh', handleTaskCompleteRefresh);
});

// ✅ 处理任务完成后的自动刷新
const handleTaskCompleteRefresh = async (event: unknown) => {
  const customEvent = event as CustomEvent<{ workspaceId: string; taskNodeId: string }>

  // 只刷新当前工作区的文件树
  if (customEvent.detail.workspaceId === props.workspaceId) {
    await loadFiles()
    // 刷新 el-tree 组件的节点
    if (fileTreeRef.value) {
      // Element Plus el-tree 的刷新方法
      const tree = fileTreeRef.value as { setData?: (data: unknown[]) => void }
      if (tree.setData) {
        tree.setData(fileTree.value)
      }
    }
  }
}

// 用户设置抽屉
const isUserSettingsVisible = ref(false);

// 文件上传对话框
const isUploadDialogVisible = ref(false);

// 当前激活的折叠面板（默认展开工作区）
const activeCollapse = ref(['workspace']);

// 移动端抽屉模式处理
const handleCloseMobileDrawer = () => {
  emit('close-mobile-drawer');
};

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

// 文件树节点类型定义
interface FileTreeNode {
  name: string;
  path: string;
  type: string;
  is_directory?: boolean;
}

// 右键菜单相关
const contextMenuVisible = ref(false);
const contextMenuPosition = ref({ x: 0, y: 0 });
const selectedFileNode = ref<FileTreeNode | null>(null);

// 文件树组件引用
const fileTreeRef = ref<unknown>(null);

// 拖拽相关状态
const isDragging = ref(false);
const draggedNode = ref<FileTreeNode | null>(null);

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
      // 按更新时间排序，选择最新的会话
      const sortedConversations = [...conversations.value].sort((a: any, b: any) => {
        const dateA = new Date(a.updated_at || a.created_at || 0);
        const dateB = new Date(b.updated_at || b.created_at || 0);
        return dateB.getTime() - dateA.getTime();
      });
      const latestConversation = sortedConversations[0] as any;
      activeConversationId.value = latestConversation.id;

      await chatStore.loadConversation(latestConversation.id);

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

  // Generate temporary conversation ID (using timestamp and random number)
  const tempConversationId = `temp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

  // Set as temporary conversation (don't send conversationId to backend)
  chatStore.setTempConversation(tempConversationId);

  // Create temporary conversation object
  const tempConversation = {
    id: tempConversationId,
    title: '新会话',
    lastUpdated: new Date().toISOString(),
    isTemp: true // Mark as temporary conversation to distinguish from saved conversations
  };

  // Add temporary conversation to top of list
  conversations.value.unshift(tempConversation);

  // Set as currently selected conversation
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

    resolve(children || []);
  } catch (error) {
    console.error('[FileTree] Failed to load children for', directoryPath, ':', error);
    resolve([]);
  }
};

// 处理树节点的点击（用于打开文件，目录展开由懒加载自动处理）
const handleTreeNodeClick = (data: unknown, _node: unknown) => {
  const isDirectory = data.is_directory || data.type === 'directory';

  // 懒加载模式下，Element Plus Tree 会自动处理目录的展开/折叠
  // 我们只需要处理文件的点击
  if (!isDirectory) {
    // 如果是文件，打开文件
    emit('open-file', { path: data.path, name: data.name });
  }
  // 如果是目录，Element Plus Tree 会自动触发懒加载，无需手动处理
};

// 拖拽相关函数
// 允许拖拽的节点判断
const allowDrag = (draggingNode: unknown) => {
  // 所有文件和文件夹都可以拖拽
  return true;
};

// 允许放置的节点判断
const allowDrop = (draggingNode: unknown, dropNode: unknown, type: string) => {
  const dropData = dropNode.data as FileTreeNode;
  const isDropDirectory = dropData.is_directory || dropData.type === 'directory';

  if (type === 'inner') {
    // 只能放置在文件夹内
    return isDropDirectory;
  } else {
    // 'before' 和 'after' 类型不允许(只允许拖入文件夹)
    return false;
  }
};

// 拖拽开始
const handleDragStart = (node: unknown, event: DragEvent) => {
  isDragging.value = true;
  draggedNode.value = node.data as FileTreeNode;
};

// 拖拽结束
const handleDragEnd = (node: unknown, event: DragEvent) => {
  isDragging.value = false;
  draggedNode.value = null;
};

// 处理放置
const handleDrop = async (
  draggingNode: unknown,
  dropNode: unknown,
  dropType: string,
  event: DragEvent
) => {
  const dragData = draggingNode.data as FileTreeNode;
  const dropData = dropNode.data as FileTreeNode;

  // 只有放置在文件夹内部('inner')才执行移动
  if (dropType === 'inner' && (dropData.is_directory || dropData.type === 'directory')) {
    try {
      // 构建目标路径: 目标文件夹 + 原文件名
      const sourcePath = dragData.path;
      const targetPath = `${dropData.path}/${dragData.name}`;

      // 调用后端 API 移动文件
      await apiManager.getFilesApi().moveFile(props.workspaceId, {
        sourcePath,
        targetPath
      });

      ElMessage.success(`已移动 "${dragData.name}" 到 "${dropData.name}"`);

      // 刷新文件树
      await handleRefreshFiles();
    } catch (error) {
      console.error('[Drag] Failed to move file:', error);
      ElMessage.error(error?.response?.data?.detail || '移动文件失败');
    }
  }

  // 重置拖拽状态
  isDragging.value = false;
  draggedNode.value = null;
};

// 右键菜单处理
const handleNodeContextMenu = (event: MouseEvent, data: unknown) => {
  event.preventDefault();
  event.stopPropagation();

  selectedFileNode.value = data as FileTreeNode;
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
  // 在关闭菜单前保存选中的节点
  const node = selectedFileNode.value;
  closeContextMenu();

  if (!node) {
    return;
  }

  try {
    const { value } = await ElMessageBox.prompt('请输入新名称:', '重命名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: node.name,
      inputPattern: /.+/,
      inputErrorMessage: '名称不能为空'
    });

    if (!value || value === node.name) return;

    const oldPath = node.path;
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
  const node = selectedFileNode.value;
  closeContextMenu();

  if (!node) return;

  try {
    const { value } = await ElMessageBox.prompt('请输入目标名称:', '复制', {
      confirmButtonText: '复制',
      cancelButtonText: '取消',
      inputValue: `${node.name}_copy`,
      inputPattern: /.+/,
      inputErrorMessage: '名称不能为空'
    });

    if (!value) return;

    const sourcePath = node.path;
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

// 下载文件或目录
const handleDownload = async () => {
  const node = selectedFileNode.value;
  closeContextMenu();

  if (!node) return;

  try {
    const isDirectory = node.is_directory || node.type === 'directory';

    // 调用下载 API
    const blob = await apiManager.getWorkspacesApi().downloadFileOrDirectory(
      props.workspaceId!,
      node.path
    );

    // 创建下载链接
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;

    // 设置下载文件名
    if (isDirectory) {
      link.download = `${node.name}.zip`;
    } else {
      link.download = node.name;
    }

    // 触发下载
    document.body.appendChild(link);
    link.click();

    // 清理
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    ElMessage.success(isDirectory ? '目录下载成功（已打包为 zip）' : '文件下载成功');
  } catch (error: unknown) {
    console.error('下载失败:', error);
    ElMessage.error(error?.response?.data?.detail || '下载失败');
  }
};

// 删除文件或目录
const handleDelete = async () => {
  const node = selectedFileNode.value;
  closeContextMenu();

  if (!node) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除 "${node.name}" 吗？此操作不可撤销。`,
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
      node.path
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

/* 折叠面板样式 */
.sidebar-collapse {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: none;
  height: 100%;
}

.sidebar-collapse :deep(.el-collapse-item) {
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
}

.sidebar-collapse :deep(.el-collapse-item__wrap) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

/* 展开的项应该占据所有可用空间 */
.sidebar-collapse :deep(.el-collapse-item.is-active) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-collapse :deep(.el-collapse-item.is-active .el-collapse-item__wrap) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.sidebar-collapse :deep(.el-collapse-item__content) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  padding: 0 !important;
}

.sidebar-collapse :deep(.el-collapse-item__header) {
  height: 48px;
  line-height: 48px;
  padding: 0 16px;
  background-color: var(--el-fill-color-blank);
  font-weight: 500;
  user-select: none;
}

.sidebar-collapse :deep(.el-collapse-item__header:hover) {
  background-color: var(--el-fill-color-light);
}

.sidebar-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.sidebar-collapse :deep(.el-collapse-item__content) {
  padding: 0;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.collapse-title .el-icon {
  font-size: 18px;
  color: var(--el-color-primary);
}

.collapse-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.collapse-content .el-scrollbar {
  flex: 1;
  height: 100%;
  overflow: hidden;
}

.collapse-content .el-scrollbar :deep(.el-scrollbar__wrap) {
  height: 100%;
  overflow-y: auto;
}

.collapse-content .el-scrollbar :deep(.el-scrollbar__view) {
  height: 100%;
}

/* 文件操作按钮 */
.file-operations {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background-color: var(--el-fill-color-blank);
}

/* 会话操作按钮 */
.conversation-operations {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background-color: var(--el-fill-color-blank);
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

.flex-1 {
  flex: 1;
}

.custom-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  flex: 1;
  transition: background-color 0.2s, opacity 0.2s;
}

.custom-tree-node.is-dragging {
  opacity: 0.5;
  background-color: var(--el-fill-color-light);
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

/* 拖拽时的视觉反馈 */
:deep(.el-tree-node__content.is-dragging) {
  opacity: 0.5;
  background-color: var(--el-fill-color-light);
}

/* 拖拽进入可放置区域的高亮 */
:deep(.el-tree-node__content.drag-over) {
  background-color: var(--el-color-primary-light-9);
  border: 2px dashed var(--el-color-primary);
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

/* ========================================
   MOBILE DRAWER MODE STYLES
   ======================================== */

.mobile-drawer-mode.side-panel {
  width: 100vw !important;
  border-right: none;
}

.mobile-close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  padding: env(safe-area-inset-top) 12px 12px 12px;
}

.mobile-close-btn .el-button {
  width: 44px;
  height: 44px;
  font-size: 18px;
}

.content-area.has-mobile-close {
  padding-top: 56px;
}

/* 移动端折叠面板样式 */
.sidebar-collapse.mobile-collapse :deep(.el-collapse-item__header) {
  height: 52px;
  line-height: 52px;
  padding: 0 16px;
}

.sidebar-collapse.mobile-collapse .collapse-content {
  flex: 1;
  min-height: 0;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .sidebar-collapse :deep(.el-collapse-item__header) {
    height: 52px;
    line-height: 52px;
    font-size: 15px;
  }

  .collapse-title {
    font-size: 15px;
  }

  .collapse-title .el-icon {
    font-size: 20px;
  }

  .conversation-operations {
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 16px;
  }

  .conversation-operations .el-button {
    flex: 1 1 calc(50% - 4px);
    min-height: var(--touch-target-min, 44px);
  }

  .file-operations {
    padding: 12px 16px;
  }

  .el-tree-node {
    min-height: var(--touch-target-min, 44px);
  }

  .el-tree-node__content {
    min-height: var(--touch-target-min, 44px);
  }

  .custom-tree-node {
    font-size: 14px;
    padding: 8px 0;
  }
}
</style>
