/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="workspaces-view">
    <!-- Hero Section -->
    <div class="hero-section">
      <div class="hero-content">
        <div class="hero-badge">
          <span class="badge-dot"></span>
          <span>{{ t('workspaces.platformName') }}</span>
        </div>
        <h1 class="hero-title">
          {{ t('workspaces.title') }}
          <span class="text-gradient">{{ t('workspaces.workspace') }}</span>
        </h1>
        <p class="hero-description">
          {{ t('workspaces.description') }}
        </p>
      </div>

      <!-- 语言选择器 -->
      <div class="language-selector-wrapper">
        <LanguageSelector />
      </div>
    </div>

    <!-- Tool Bar -->
    <div class="toolbar-section">
      <div class="toolbar-left">
        <h2>{{ t('workspaces.myWorkspaces') }}</h2>
        <span class="workspace-count">{{ t('workspaces.workspaceCount', { count: workspaces.length }) }}</span>
      </div>
      <div class="toolbar-right">
        <el-button type="primary" :icon="Plus" @click="showCreateDialog">
          {{ t('workspaces.createWorkspace') }}
        </el-button>
      </div>
    </div>

    <!-- Workspaces Grid -->
    <div class="workspaces-container" v-loading="isLoading" :element-loading-text="t('workspaces.loading')">
      <transition-group name="workspace-card" tag="div" class="workspaces-grid">
        <div
          v-for="(workspace, index) in workspaces"
          :key="workspace.id"
          class="workspace-card"
          :style="{ 'animation-delay': `${index * 100}ms` }"
          @click="goToChat(workspace.id)"
        >
          <div class="card-decoration"></div>
          <div class="card-glow"></div>

          <div class="card-header">
            <div class="workspace-icon-wrapper">
              <div class="workspace-icon">
                <el-icon :size="28"><OfficeBuilding /></el-icon>
              </div>
              <div class="icon-pulse"></div>
            </div>
            <div class="workspace-meta">
              <h3 class="workspace-name">{{ workspace.display_name || workspace.name }}</h3>
              <span class="workspace-id">ID: {{ workspace.id.slice(0, 8) }}...</span>
            </div>
          </div>

          <p v-if="workspace.description" class="workspace-description">
            {{ workspace.description }}
          </p>

          <div class="card-footer">
            <div class="workspace-date">
              <el-icon><Calendar /></el-icon>
              <span>{{ formatDate(workspace.created_at || workspace.createdAt) }}</span>
            </div>
            <div class="workspace-actions">
              <!-- 独立的操作按钮 -->
              <el-button
                type="primary"
                :icon="ArrowRight"
                @click.stop="goToChat(workspace.id)"
                size="small"
                class="action-btn enter-btn"
              >
                {{ t('workspaces.enter') }}
              </el-button>
              <el-button
                :icon="Edit"
                @click.stop="showEditDialog(workspace)"
                size="small"
                class="action-btn edit-btn"
              >
                {{ t('workspaces.edit') }}
              </el-button>
              <el-button
                type="danger"
                :icon="Delete"
                @click.stop="showDeleteDialogFn(workspace)"
                size="small"
                class="action-btn delete-btn"
              >
                {{ t('workspaces.delete') }}
              </el-button>
            </div>
          </div>
        </div>
      </transition-group>

      <!-- Empty State -->
      <transition name="fade">
        <div v-if="workspaces.length === 0 && !isLoading" class="empty-state">
          <div class="empty-icon">
            <el-icon :size="64"><FolderOpened /></el-icon>
          </div>
          <h3>{{ t('workspaces.noWorkspaces') }}</h3>
          <p>{{ t('workspaces.noWorkspacesDesc') }}</p>
          <el-button type="primary" size="large" :icon="Plus" @click="showCreateDialog">
            {{ t('workspaces.createWorkspace') }}
          </el-button>
        </div>
      </transition>

    <!-- Dialogs -->
    <WorkspaceFormDialog
      v-model="showFormDialog"
      :workspace="currentWorkspace"
      @created="handleWorkspaceCreated"
      @updated="handleWorkspaceUpdated"
    />

    <WorkspaceDeleteDialog
      v-model="showDeleteDialog"
      :workspace="currentWorkspace"
      @deleted="handleWorkspaceDeleted"
    />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { OfficeBuilding, Calendar, ArrowRight, FolderOpened, Plus, Edit, Delete } from '@element-plus/icons-vue';
import WorkspaceFormDialog from '@/components/workspace/WorkspaceFormDialog.vue';
import WorkspaceDeleteDialog from '@/components/workspace/WorkspaceDeleteDialog.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import { workspaceService } from '@/services/workspace';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

interface Workspace {
  id: string;
  name: string;
  display_name?: string;
  description?: string;
  created_at?: string;
  createdAt?: string;
}

const workspaces = ref<Workspace[]>([]);
const isLoading = ref(true);
const router = useRouter();

// Dialog 状态
const showFormDialog = ref(false);
const showDeleteDialog = ref(false);
const currentWorkspace = ref<Workspace | null>(null);

const goToChat = (workspaceId: string) => {
  router.push(`/dawei/${workspaceId}`);
};

const formatDate = (dateString?: string) => {
  if (!dateString) return '未知';
  try {
    return new Date(dateString).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  } catch {
    return dateString;
  }
};

// 加载工作区列表
const loadWorkspaces = async () => {
  try {
    isLoading.value = true;
    const response = await workspaceService.getWorkspaces();

    if (response.success) {
      workspaces.value = response.workspaces || [];
    } else {
      workspaces.value = [];
    }
  } catch (error) {
    console.error('Failed to fetch workspaces:', error);
    ElMessage.error(t('workspaces.loadFailed'));
    workspaces.value = [];
  } finally {
    isLoading.value = false;
  }
};

// 显示创建对话框
const showCreateDialog = () => {
  currentWorkspace.value = null;
  showFormDialog.value = true;
};

// 显示编辑对话框
const showEditDialog = (workspace: Workspace) => {
  currentWorkspace.value = workspace;
  showFormDialog.value = true;
};

// 显示删除对话框
const showDeleteDialogFn = (workspace: Workspace) => {
  currentWorkspace.value = workspace;
  showDeleteDialog.value = true;
};

// 工作区创建完成
const handleWorkspaceCreated = async () => {
  await loadWorkspaces();
  ElMessage.success(t('workspaces.createdSuccess'));
};

// 工作区更新完成
const handleWorkspaceUpdated = async () => {
  await loadWorkspaces();
  ElMessage.success(t('workspaces.updatedSuccess'));
};

// 工作区删除完成
const handleWorkspaceDeleted = async () => {
  // 先显示成功消息
  ElMessage.success(t('workspaces.deletedSuccess'));
  // 然后刷新列表
  await loadWorkspaces();
};

onMounted(() => {
  loadWorkspaces();
});
</script>

<style scoped>
.workspaces-view {
  min-height: 100vh;
  padding: var(--spacing-2xl);
  background:
    radial-gradient(at 40% 20%, rgba(var(--color-primary-rgb), 0.05) 0px, transparent 50%),
    radial-gradient(at 80% 0%, rgba(var(--color-accent-rgb), 0.04) 0px, transparent 50%),
    radial-gradient(at 0% 50%, rgba(var(--color-primary-rgb), 0.03) 0px, transparent 50%);
  overflow-y: auto;
}

/* ====================
   TOOLBAR SECTION
   ==================== */
.toolbar-section {
  max-width: 1400px;
  margin: 0 auto 40px;
  padding: 20px 30px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toolbar-left h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.workspace-count {
  font-size: 14px;
  color: #909399;
}

.toolbar-right {
  display: flex;
  gap: 12px;
}

/* ====================
   HERO SECTION
   ==================== */
.hero-section {
  position: relative;
  text-align: center;
  margin-bottom: var(--spacing-3xl);
  animation: fadeInUp 0.8s var(--ease-out);
}

.language-selector-wrapper {
  position: absolute;
  top: 0;
  right: 0;
  margin-top: -8px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-full);
  margin-bottom: var(--spacing-lg);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  box-shadow: var(--shadow-sm);
}

.badge-dot {
  width: 8px;
  height: 8px;
  background: var(--color-primary);
  border-radius: var(--radius-full);
  animation: pulse 2s var(--ease-default) infinite;
}

.hero-title {
  font-size: clamp(2.5rem, 5vw, 4rem);
  font-weight: 700;
  line-height: 1.1;
  margin-bottom: var(--spacing-lg);
  font-family: var(--font-display);
  letter-spacing: -0.02em;
}

.hero-description {
  font-size: var(--text-lg);
  color: var(--color-text-secondary);
  max-width: 600px;
  margin: 0 auto;
  line-height: 1.6;
}

/* ====================
   WORKSPACES GRID
   ==================== */
.workspaces-container {
  max-width: 1400px;
  margin: 0 auto;
}

.workspaces-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: var(--spacing-xl);
}

/* ====================
   WORKSPACE CARD
   ==================== */
.workspace-card {
  position: relative;
  background: var(--color-surface-1);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-2xl);
  padding: var(--spacing-xl);
  cursor: pointer;
  overflow: hidden;
  transition: all var(--duration-base) var(--ease-default);
  animation: fadeInUp 0.6s var(--ease-out) both;
}

.workspace-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
  opacity: 0;
  transition: opacity var(--duration-base) var(--ease-default);
}

.workspace-card:hover {
  transform: translateY(-8px);
  box-shadow:
    var(--shadow-xl),
    0 0 0 1px rgba(var(--color-primary-rgb), 0.1);
  border-color: rgba(var(--color-primary-rgb), 0.3);
}

.workspace-card:hover::before {
  opacity: 1;
}

.card-decoration {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 200%;
  height: 200%;
  background:
    radial-gradient(circle at 30% 30%, rgba(var(--color-primary-rgb), 0.03) 0%, transparent 50%),
    radial-gradient(circle at 70% 70%, rgba(var(--color-accent-rgb), 0.02) 0%, transparent 50%);
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--duration-base) var(--ease-default);
}

.workspace-card:hover .card-decoration {
  opacity: 1;
}

.card-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 120%;
  height: 120%;
  transform: translate(-50%, -50%);
  background: radial-gradient(circle, rgba(var(--color-primary-rgb), 0.1) 0%, transparent 70%);
  filter: blur(40px);
  opacity: 0;
  transition: opacity var(--duration-slow) var(--ease-default);
  pointer-events: none;
}

.workspace-card:hover .card-glow {
  opacity: 1;
}

/* Card Header */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.workspace-icon-wrapper {
  position: relative;
  flex-shrink: 0;
}

.workspace-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  border-radius: var(--radius-xl);
  color: white;
  box-shadow: var(--shadow-md);
  transition: all var(--duration-base) var(--ease-default);
}

.workspace-card:hover .workspace-icon {
  transform: scale(1.05) rotate(5deg);
  box-shadow: var(--shadow-lg);
}

.icon-pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 100%;
  height: 100%;
  transform: translate(-50%, -50%);
  border-radius: var(--radius-xl);
  border: 2px solid var(--color-primary);
  opacity: 0;
  animation: iconPulse 2s var(--ease-default) infinite;
}

.workspace-card:hover .icon-pulse {
  opacity: 1;
}

.workspace-meta {
  flex: 1;
  min-width: 0;
}

.workspace-name {
  font-size: var(--text-xl);
  font-weight: 600;
  font-family: var(--font-display);
  color: var(--color-text-primary);
  margin: 0 0 var(--spacing-xs) 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-id {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
}

/* Card Description */
.workspace-description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin-bottom: var(--spacing-lg);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Card Footer */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border-default);
}

.workspace-date {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.enter-button {
  border-radius: var(--radius-lg);
  padding: var(--spacing-sm) var(--spacing-lg);
  font-weight: 500;
  opacity: 0;
  transform: translateX(-10px);
  transition: all var(--duration-base) var(--ease-default);
}

.workspace-card:hover .enter-button {
  opacity: 1;
  transform: translateX(0);
}

/* 工作区操作按钮 */
.workspace-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.action-btn {
  border-radius: var(--radius-md);
  padding: 6px 12px;
  font-size: 13px;
  transition: all var(--duration-base) var(--ease-default);
}

.enter-btn {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  border: none;
  color: white;
}

.enter-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(var(--color-primary-rgb), 0.4);
}

.edit-btn {
  border-color: var(--color-border);
  background-color: white;
  color: var(--color-text-secondary);
}

.edit-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background-color: rgba(var(--color-primary-rgb), 0.05);
}

.delete-btn {
  border-color: #fbc4c4;
  background-color: #fef0f0;
  color: #f56c6c;
}

.delete-btn:hover {
  border-color: #f56c6c;
  background-color: #fde2e2;
  transform: translateY(-1px);
}

/* ====================
   EMPTY STATE
   ==================== */
.empty-state {
  text-align: center;
  padding: var(--spacing-3xl) var(--spacing-xl);
  animation: fadeIn 0.6s var(--ease-out);
}

.empty-icon {
  width: 120px;
  height: 120px;
  margin: 0 auto var(--spacing-xl);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-2);
  border-radius: var(--radius-2xl);
  color: var(--color-text-tertiary);
}

.empty-state h3 {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin-bottom: var(--spacing-sm);
}

.empty-state p {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xl);
}

/* ====================
   ANIMATIONS
   ==================== */
@keyframes iconPulse {
  0% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 0.5;
  }
  100% {
    transform: translate(-50%, -50%) scale(1.3);
    opacity: 0;
  }
}

/* Workspace Card Transition */
.workspace-card-enter-active {
  transition: all 0.6s var(--ease-out);
}

.workspace-card-leave-active {
  transition: all 0.4s var(--ease-in);
}

.workspace-card-enter-from {
  opacity: 0;
  transform: translateY(30px) scale(0.95);
}

.workspace-card-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

/* Fade Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s var(--ease-default);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ====================
   RESPONSIVE DESIGN
   ==================== */
@media (max-width: 768px) {
  .workspaces-view {
    padding: var(--spacing-lg);
  }

  .hero-title {
    font-size: var(--text-3xl);
  }

  .workspaces-grid {
    grid-template-columns: 1fr;
  }

  .workspace-card {
    padding: var(--spacing-lg);
  }

  .enter-button {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
