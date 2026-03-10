/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="workspaces-view">
    <!-- 顶部语言选择器和登录按钮 -->
    <div class="top-bar">
      <div class="top-actions-container">
        <!-- 远程访问 -->
        <el-popover :width="400" trigger="click" placement="bottom-end" @show="handleRemotePopoverShow">
          <template #reference>
            <el-button :loading="remoteLoading" :disabled="true">
              <el-icon v-if="!remoteConfig.running && !remoteLoading">
                <Connection />
              </el-icon>
              <el-icon v-else-if="remoteConfig.running">
                <CircleCheck />
              </el-icon>
              NAT访问
            </el-button>
          </template>

          <!-- 远程访问配置面板 -->
          <div class="remote-access-panel">
            <!-- 服务控制按钮区域 -->
            <div class="service-control-section">
              <div class="control-buttons">
                <el-button type="primary" :loading="remoteActionLoading" :disabled="remoteConfig.running"
                  :icon="VideoPlay" @click="handleStartRemoteService" size="default">
                  开启服务
                </el-button>
                <el-button type="danger" :loading="remoteActionLoading" :disabled="!remoteConfig.running"
                  :icon="VideoPause" @click="handleStopRemoteService" size="default">
                  关闭服务
                </el-button>
                <el-button :icon="Refresh" @click="handleRefreshRemoteStatus" :loading="remoteStatusLoading"
                  size="default">
                  刷新
                </el-button>
              </div>
            </div>

            <!-- 配置选项 -->
            <div class="remote-config-section">
              <div class="config-item">
                <div class="config-item-header">
                  <el-icon>
                    <Connection />
                  </el-icon>
                  <span class="config-label">允许远程访问</span>
                </div>
                <el-switch v-model="remoteConfig.allowRemote" :loading="remoteConfigLoading"
                  @change="handleRemoteConfigChange" />
              </div>

              <div class="config-item">
                <div class="config-item-header">
                  <el-icon>
                    <Monitor />
                  </el-icon>
                  <span class="config-label">允许 SSH 访问</span>
                </div>
                <el-switch v-model="remoteConfig.allowSSH" :loading="remoteConfigLoading"
                  @change="handleSSHConfigChange" />
              </div>

              <!-- NAT 配置信息 -->
              <div v-if="natConfig" class="nat-config-info">
                <el-divider style="margin: 12px 0;" />
                <div class="config-info-title">系统配置</div>
                <div class="config-info-item">
                  <span class="config-info-key">支持系统 URL:</span>
                  <span class="config-info-value">{{ natConfig.support_system_url }}</span>
                </div>
                <div class="config-info-item">
                  <span class="config-info-key">OAuth 客户端 ID:</span>
                  <span class="config-info-value">{{ natConfig.oauth_client_id }}</span>
                </div>
                <div class="config-info-item">
                  <span class="config-info-key">NAT 服务器地址:</span>
                  <span class="config-info-value">{{ natConfig.default_nat_server_addr }}</span>
                </div>
                <div class="config-info-item">
                  <span class="config-info-key">支持的服务类型:</span>
                  <div class="service-types-tags">
                    <el-tag v-for="type in natConfig.supported_service_types" :key="type" size="small"
                      :type="getServiceTypeColor(type)">
                      {{ type.toUpperCase() }}
                    </el-tag>
                  </div>
                </div>
                <div class="config-info-item">
                  <span class="config-info-key">客户端名称:</span>
                  <span class="config-info-value">{{ natConfig.user_client_name }}</span>
                </div>
              </div>
            </div>

            <!-- 服务状态 -->
            <div class="remote-status-section" v-if="remoteConfig.allowRemote">
              <el-divider style="margin: 12px 0;" />
              <div class="status-header">
                <span class="status-title">服务状态</span>
                <el-tag :type="remoteConfig.running ? 'success' : 'info'" size="small">
                  {{ remoteConfig.running ? '运行中' : '已停止' }}
                </el-tag>
              </div>

              <!-- NAT 服务详细信息 -->
              <div class="nat-service-details">
                <div class="service-detail-item">
                  <span class="service-detail-key">客户端 ID:</span>
                  <span class="service-detail-value">{{ natServiceStatus.client_id || '未连接' }}</span>
                </div>
                <div class="service-detail-item">
                  <span class="service-detail-key">客户端名称:</span>
                  <span class="service-detail-value">{{ natServiceStatus.client_name || '未设置' }}</span>
                </div>
                <div class="service-detail-item">
                  <span class="service-detail-key">隧道数量:</span>
                  <span class="service-detail-value">{{ natServiceStatus.tunnel_count }}</span>
                </div>
              </div>

              <!-- 隧道列表 -->
              <div v-if="remoteConfig.running && remoteTunnels.length > 0" class="tunnels-section">
                <div class="tunnels-section-title">活跃隧道 ({{ remoteTunnels.length }})</div>
                <div class="tunnels-list">
                  <div v-for="tunnel in remoteTunnels" :key="tunnel.tunnel_id" class="tunnel-item">
                    <div class="tunnel-main">
                      <div class="tunnel-header">
                        <div class="tunnel-name">
                          <el-icon>
                            <Link />
                          </el-icon>
                          {{ tunnel.name }}
                        </div>
                        <el-tag size="small" type="primary">{{ tunnel.service_type }}</el-tag>
                      </div>
                      <div class="tunnel-url">
                        <span class="url-label">公网地址:</span>
                        <a :href="tunnel.public_url" target="_blank" class="url-link">{{ tunnel.public_url }}</a>
                      </div>
                      <div class="tunnel-meta">
                        <span class="meta-item">
                          <span class="meta-label">本地端口:</span>
                          <span class="meta-value">{{ tunnel.local_port }}</span>
                        </span>
                        <span class="meta-item">
                          <span class="meta-label">创建时间:</span>
                          <span class="meta-value">{{ formatTime(tunnel.created_at) }}</span>
                        </span>
                        <span class="meta-item">
                          <span class="meta-label">隧道 ID:</span>
                          <span class="meta-value tunnel-id">{{ tunnel.tunnel_id }}</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 空状态 -->
              <div v-else-if="!remoteConfig.running" class="empty-tunnels">
                <el-icon>
                  <Link />
                </el-icon>
                <span>未启动</span>
              </div>
            </div>

            <!-- 提示信息 -->
            <div v-if="!remoteConfig.allowRemote" class="remote-hint">
              <el-icon>
                <InfoFilled />
              </el-icon>
              <span>启用远程访问后，可将本地服务暴露到公网</span>
            </div>
          </div>
        </el-popover>
        <!-- 分隔线 -->
        <div class="action-divider"></div>

        <!-- 登录状态 -->
        <div class="auth-section-top" v-if="authenticated && authenticatedUser">
          <el-dropdown @command="handleUserMenuCommand">
            <div class="user-dropdown-trigger">
              <el-avatar :size="32" :src="authenticatedUser.avatar">
                {{ authenticatedUser.nickname?.charAt(0)?.toUpperCase() || 'U' }}
              </el-avatar>
              <span class="user-nickname">{{ authenticatedUser.nickname || 'User' }}</span>
              <el-icon>
                <ArrowDown />
              </el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <div class="user-info-dropdown">
                    <div class="user-email">{{ authenticatedUser.email }}</div>
                    <div class="token-stats">
                      Token: {{ authenticatedUser.token_used || 0 }} / {{ authenticatedUser.token_quota || 0 }}
                    </div>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item divided :command="'logout'">
                  <el-icon>
                    <SwitchButton />
                  </el-icon>
                  {{ t('userSettings.profile.logout') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <!-- 未登录状态 -->
        <div class="auth-section-top" v-else>
          <el-button :disabled="true" type="primary" @click="handleLogin" :loading="loggingIn" size="small">
            <el-icon>
              <User />
            </el-icon>
            {{ t('userSettings.profile.login') }}
          </el-button>
        </div>

        <!-- 语言选择器 -->
        <div class="language-selector-wrapper">
          <LanguageSelector />
        </div>

      </div>
    </div>

    <!-- Hero Title -->
    <div class="hero-section">
      <h1 class="hero-title">DaweiBot</h1>
      <p class="hero-description">AI驱动的智能工作平台</p>
    </div>

    <!-- 全局统计卡片 -->
    <div class="stats-section" v-loading="isLoadingStats">
      <div class="stats-grid">
        <div class="stat-card global-stat">
          <div class="stat-icon stat-icon-workspace">
            <el-icon :size="24">
              <OfficeBuilding />
            </el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('workspaces.stats.totalWorkspaces') }}</div>
            <div class="stat-value">{{ globalStats.workspacesCount }}</div>
          </div>
        </div>

        <div class="stat-card global-stat">
          <div class="stat-icon stat-icon-skill">
            <el-icon :size="24">
              <Star />
            </el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('workspaces.stats.totalSkills') }}</div>
            <div class="stat-value">{{ globalStats.skillsCount }}</div>
          </div>
        </div>

        <div class="stat-card global-stat">
          <div class="stat-icon stat-icon-agent">
            <el-icon :size="24">
              <User />
            </el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">{{ t('workspaces.stats.totalAgents') }}</div>
            <div class="stat-value">{{ globalStats.agentsCount }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <!-- 工作区列表（独立展示） -->
      <div class="workspaces-section">
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
            <div v-for="(workspace, index) in workspaces" :key="workspace.id" class="workspace-card"
              :style="{ 'animation-delay': `${index * 100}ms` }" @click="goToChat(workspace.id)">
              <div class="card-decoration"></div>
              <div class="card-glow"></div>

              <div class="card-header">
                <div class="workspace-icon-wrapper">
                  <div class="workspace-icon">
                    <el-icon :size="28">
                      <OfficeBuilding />
                    </el-icon>
                  </div>
                  <div class="icon-pulse"></div>
                </div>
                <div class="workspace-meta">
                  <h3 class="workspace-name">{{ workspace.display_name || workspace.name }}</h3>
                  <div v-if="workspace.path" class="workspace-path">
                    <el-icon>
                      <Folder />
                    </el-icon>
                    {{ workspace.path }}
                  </div>
                  <div class="workspace-id">ID: {{ workspace.id.slice(0, 8) }}...</div>
                </div>
              </div>

              <p v-if="workspace.description" class="workspace-description">
                {{ workspace.description }}
              </p>

              <!-- 工作区统计信息 -->
              <div class="workspace-stats" v-if="workspaceStats[workspace.id]">
                <div class="workspace-stat-item">
                  <el-icon :size="16">
                    <Star />
                  </el-icon>
                  <span>{{ workspaceStats[workspace.id].skillsCount }} {{ t('workspaces.stats.skills') }}</span>
                </div>
                <div class="workspace-stat-item">
                  <el-icon :size="16">
                    <User />
                  </el-icon>
                  <span>{{ workspaceStats[workspace.id].agentsCount }} {{ t('workspaces.stats.agents') }}</span>
                </div>
              </div>

              <div class="card-footer">
                <div class="workspace-date">
                  <el-icon>
                    <Calendar />
                  </el-icon>
                  <span>{{ formatDate(workspace.created_at || workspace.createdAt) }}</span>
                </div>
                <div class="workspace-actions">
                  <!-- 独立的操作按钮 -->
                  <el-button type="primary" :icon="ArrowRight" @click.stop="goToChat(workspace.id)" size="small"
                    class="action-btn enter-btn">
                    {{ t('workspaces.enter') }}
                  </el-button>
                  <el-button :icon="Edit" @click.stop="showEditDialog(workspace)" size="small"
                    class="action-btn edit-btn">
                    {{ t('workspaces.edit') }}
                  </el-button>
                  <el-button type="danger" :icon="Delete" @click.stop="showDeleteDialogFn(workspace)" size="small"
                    class="action-btn delete-btn">
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
                <el-icon :size="64">
                  <FolderOpened />
                </el-icon>
              </div>
              <h3>{{ t('workspaces.noWorkspaces') }}</h3>
              <p>{{ t('workspaces.noWorkspacesDesc') }}</p>
              <el-button type="primary" size="large" :icon="Plus" @click="showCreateDialog">
                {{ t('workspaces.createWorkspace') }}
              </el-button>
            </div>
          </transition>
        </div>
      </div>

      <!-- Tab 结构（设置相关） -->
      <el-tabs v-model="activeTab" type="border-card" class="workspace-tabs">
        <!-- Tab 1: 偏好设置 -->
        <el-tab-pane :label="t('workspaces.tabs.preferences')" name="preferences">
          <div class="tab-content">
            <PreferencesTab />
          </div>
        </el-tab-pane>

        <!-- Tab 2: 安全设置 -->
        <el-tab-pane :label="t('workspaces.tabs.security')" name="security">
          <div class="tab-content">
            <SecuritySettingsTab v-model="securitySettings" @update:model-value="handleSecuritySettingsUpdate" />
          </div>
        </el-tab-pane>

        <!-- Tab 3: 快捷键 -->
        <el-tab-pane :label="t('workspaces.tabs.shortcuts')" name="shortcuts">
          <div class="tab-content">
            <ShortcutsTab />
          </div>
        </el-tab-pane>

        <!-- Tab 4: 关于 -->
        <el-tab-pane :label="t('workspaces.tabs.about')" name="about">
          <div class="tab-content">
            <AboutTab />
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- Dialogs -->
      <WorkspaceFormDialog v-model="showFormDialog" :workspace="currentWorkspace" @created="handleWorkspaceCreated"
        @updated="handleWorkspaceUpdated" />

      <WorkspaceDeleteDialog v-model="showDeleteDialog" :workspace="currentWorkspace"
        @deleted="handleWorkspaceDeleted" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  OfficeBuilding,
  Calendar,
  ArrowRight,
  FolderOpened,
  Folder,
  Plus,
  Edit,
  Delete,
  Star,
  User,
  ArrowDown,
  SwitchButton,
  Connection,
  CircleCheck,
  Monitor,
  Link,
  VideoPlay,
  VideoPause,
  Refresh,
  InfoFilled
} from '@element-plus/icons-vue';
import WorkspaceFormDialog from '@/components/workspace/WorkspaceFormDialog.vue';
import WorkspaceDeleteDialog from '@/components/workspace/WorkspaceDeleteDialog.vue';
import LanguageSelector from '@/components/LanguageSelector.vue';
import SecuritySettingsTab from '@/components/user/SecuritySettingsTab.vue';
import PreferencesTab from '@/components/user/PreferencesTab.vue';
import ShortcutsTab from '@/components/user/ShortcutsTab.vue';
import AboutTab from '@/components/user/AboutTab.vue';
import { workspacesApi, getGlobalStats, getWorkspaceStats } from '@/services/api/services/workspaces';
import { useI18n } from 'vue-i18n';
import type { UserSecuritySettings } from '@/services/api/types';
import { authService, type UserInfo } from '@/services/auth';
import { httpClient } from '@/services/api/http';

const { t } = useI18n();

// 当前激活的 tab（默认偏好设置）
const activeTab = ref('preferences');

interface Workspace {
  id: string;
  name: string;
  display_name?: string;
  description?: string;
  path?: string;
  created_at?: string;
  createdAt?: string;
}

interface GlobalStats {
  workspacesCount: number;
  skillsCount: number;
  agentsCount: number;
}

interface WorkspaceStats {
  skillsCount: number;
  agentsCount: number;
}

const workspaces = ref<Workspace[]>([]);
const isLoading = ref(true);
const isLoadingStats = ref(false);
const globalStats = ref<GlobalStats>({
  workspacesCount: 0,
  skillsCount: 0,
  agentsCount: 0
});
const workspaceStats = ref<Record<string, WorkspaceStats>>({});
const router = useRouter();

// Dialog 状态
const showFormDialog = ref(false);
const showDeleteDialog = ref(false);
const currentWorkspace = ref<Workspace | null>(null);

// 安全配置状态 - 将由 SecuritySettingsTab 组件加载
const securitySettings = ref<UserSecuritySettings>({} as UserSecuritySettings);

// 认证状态
const authenticated = ref(false);
const authenticatedUser = ref<UserInfo | null>(null);
const loggingIn = ref(false);
const loggingOut = ref(false);

// 远程访问配置
interface RemoteConfig {
  allowRemote: boolean;
  allowSSH: boolean;
  running: boolean;
}

interface TunnelInfo {
  tunnel_id: string;
  name: string;
  service_type: string;
  local_port: number;
  public_url: string;
  created_at: string;
}

interface NATConfig {
  support_system_url: string;
  oauth_client_id: string;
  default_nat_server_addr: string;
  supported_service_types: string[];
  user_client_name: string;
}

interface NATServiceStatus {
  running: boolean;
  client_id: string | null;
  client_name: string | null;
  tunnels: TunnelInfo[];
  tunnel_count: number;
}

const remoteConfig = ref<RemoteConfig>({
  allowRemote: false,
  allowSSH: false,
  running: false
});

const natConfig = ref<NATConfig | null>(null);
const natServiceStatus = ref<NATServiceStatus | null>(null);
const remoteTunnels = ref<TunnelInfo[]>([]);
const remoteLoading = ref(false);
const remoteConfigLoading = ref(false);
const remoteActionLoading = ref(false);
const remoteStatusLoading = ref(false);

// 处理安全配置更新
const handleSecuritySettingsUpdate = (value: UserSecuritySettings) => {
  securitySettings.value = value;
};

// 处理用户菜单命令
const handleUserMenuCommand = async (command: string) => {
  if (command === 'logout') {
    await handleLogout();
  }
};

// 检查认证状态
const checkAuthStatus = async () => {
  try {
    const authState = await authService.checkAuthStatus();
    authenticated.value = authState.authenticated;
    authenticatedUser.value = authState.user;
  } catch (error) {
    console.error('Failed to check auth status:', error);
  }
};

// 处理登录
const handleLogin = async () => {
  loggingIn.value = true;
  try {
    // 发起OAuth登录
    await authService.login();

    // 开始轮询检查登录状态
    ElMessage.info(t('userSettings.profile.loginInProgress'));

    authService.startPolling((user) => {
      // 登录成功回调
      authenticated.value = true;
      authenticatedUser.value = user;
      loggingIn.value = false;

      ElMessage.success(t('userSettings.profile.loginSuccess'));
    });
  } catch (error) {
    loggingIn.value = false;
    ElMessage.error(t('userSettings.profile.loginFailed'));
    console.error('Login failed:', error);
  }
};

// 处理登出
const handleLogout = async () => {
  try {
    await ElMessageBox.confirm(
      t('userSettings.profile.logoutConfirm'),
      t('common.confirm'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning',
      }
    );

    loggingOut.value = true;
    await authService.logout();

    authenticated.value = false;
    authenticatedUser.value = null;
    loggingOut.value = false;

    ElMessage.success(t('userSettings.profile.logoutSuccess'));
  } catch (error) {
    if (error !== 'cancel') {
      loggingOut.value = false;
      ElMessage.error(t('userSettings.profile.logoutFailed'));
      console.error('Logout failed:', error);
    }
  }
};

// 处理来自OAuth回调窗口的消息
const handleOAuthMessage = (event: MessageEvent) => {
  // 验证消息来源（安全检查）
  if (event.origin !== window.location.origin) {
    return;
  }

  const { type, error } = event.data;

  if (type === 'oauth_login_success') {
    // 登录成功，刷新用户信息
    checkAuthStatus();
    ElMessage.success(t('userSettings.profile.loginSuccess'));
  } else if (type === 'oauth_login_error') {
    // 登录失败
    loggingIn.value = false;
    authService.stopPolling();
    ElMessage.error(error || t('userSettings.profile.loginFailed'));
  }
};

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

// 加载全局统计
const loadGlobalStats = async () => {
  try {
    isLoadingStats.value = true;
    const stats = await getGlobalStats();
    globalStats.value = stats;
  } catch (error) {
    console.error('Failed to fetch global stats:', error);
    // 静默失败，不显示错误消息
  } finally {
    isLoadingStats.value = false;
  }
};

// 加载所有工作区的统计信息
const loadAllWorkspaceStats = async () => {
  try {
    const statsPromises = workspaces.value.map(async (workspace) => {
      try {
        const stats = await getWorkspaceStats(workspace.id);
        return {
          id: workspace.id,
          stats: {
            skillsCount: stats.skillsCount || 0,
            agentsCount: stats.agentsCount || 0
          }
        };
      } catch (error) {
        console.error(`Failed to fetch stats for workspace ${workspace.id}:`, error);
        return {
          id: workspace.id,
          stats: {
            skillsCount: 0,
            agentsCount: 0
          }
        };
      }
    });

    const results = await Promise.all(statsPromises);
    const statsMap: Record<string, WorkspaceStats> = {};
    results.forEach(({ id, stats }) => {
      statsMap[id] = stats;
    });
    workspaceStats.value = statsMap;
  } catch (error) {
    console.error('Failed to fetch workspace stats:', error);
    // 静默失败，不显示错误消息
  }
};

// 加载工作区列表
const loadWorkspaces = async () => {
  try {
    isLoading.value = true;
    const workspacesData = await workspacesApi.getWorkspaces();
    workspaces.value = workspacesData || [];
    // 加载工作区统计
    await loadAllWorkspaceStats();
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
  await loadGlobalStats();
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
  await loadGlobalStats();
};

// ==================== 远程访问功能 ====================

// API 基础 URL
const REMOTE_API_BASE = '/users/me/remote';

// 处理远程访问 Popover 显示
const handleRemotePopoverShow = async () => {
  await refreshRemoteStatus();
};

// 刷新远程服务状态
const refreshRemoteStatus = async () => {
  try {
    remoteStatusLoading.value = true;

    // 并行获取配置和状态
    const [configRes, statusRes] = await Promise.all([
      httpClient.get(`${REMOTE_API_BASE}/nat/config`),
      httpClient.get(`${REMOTE_API_BASE}/nat/status`)
    ]);

    console.log('Config response:', configRes);

    // httpClient.get() 返回的是 response.data，格式是 { success: boolean, data: T, message: string }
    if (configRes && typeof configRes === 'object' && 'success' in configRes) {
      if ((configRes as any).success && (configRes as any).data) {
        const config = (configRes as any).data;
        console.log('Processed config:', config);
        natConfig.value = config as NATConfig;
        console.log('Final natConfig:', natConfig.value);
        // 配置接口返回成功，说明允许远程访问
        remoteConfig.value.allowRemote = true;
      } else {
        console.error('Config API returned success=false');
        remoteConfig.value.allowRemote = false;
      }
    } else {
      console.error('Config API returned invalid response format');
      remoteConfig.value.allowRemote = false;
    }

    console.log('Status response:', statusRes);

    // 状态接口直接返回 NATServiceStatus，没有包装
    if (statusRes && typeof statusRes === 'object') {
      const natStatus = statusRes as NATServiceStatus;
      natServiceStatus.value = natStatus;
      remoteConfig.value.running = natStatus.running || false;
      remoteConfig.value.allowRemote = true; // 状态能获取说明服务可用

      // 获取隧道列表
      if (natStatus.running) {
        remoteTunnels.value = natStatus.tunnels || [];
      } else {
        remoteTunnels.value = [];
      }
    } else {
      console.error('Status API returned invalid response format');
    }
  } catch (error) {
    console.error('Failed to refresh remote status:', error);
    ElMessage.error('无法加载远程访问配置，请检查网络连接');
    // API 不可用时，默认不允许远程访问
    remoteConfig.value.allowRemote = false;
    remoteConfig.value.running = false;
    remoteTunnels.value = [];
    natConfig.value = null;
    natServiceStatus.value = null;
  } finally {
    remoteStatusLoading.value = false;
  }
};

// 加载远程隧道列表
const loadRemoteTunnels = async () => {
  try {
    const response = await httpClient.get(`${REMOTE_API_BASE}/nat/tunnels`);
    if (response.status === 200) {
      remoteTunnels.value = response.data;
    } else {
      remoteTunnels.value = [];
    }
  } catch (error) {
    console.error('Failed to load tunnels:', error);
    remoteTunnels.value = [];
  }
};

// 处理允许远程配置变更
const handleRemoteConfigChange = async (value: boolean) => {
  // 这里可以保存用户偏好设置到本地存储或服务器
  console.log('Remote access config changed:', value);
  if (!value) {
    // 如果关闭远程访问，同时停止服务
    if (remoteConfig.value.running) {
      await handleStopRemoteService();
    }
  }
};

// 处理 SSH 配置变更
const handleSSHConfigChange = async (value: boolean) => {
  console.log('SSH config changed:', value);
  // 这里可以保存 SSH 配置
  // 如果服务正在运行，需要动态添加/删除 SSH 隧道
  if (remoteConfig.value.running && value) {
    await addSSHService();
  }
};

// 添加 SSH 服务
const addSSHService = async () => {
  try {
    remoteActionLoading.value = true;

    const response = await httpClient.post(`${REMOTE_API_BASE}/nat/services/add`, {
      name: 'ssh',
      service_type: 'ssh',
      local_port: 22
    });

    if (response.status === 200) {
      const result = response.data as { success: boolean; message: string };
      if (result.success) {
        ElMessage.success('SSH 服务添加成功');
        await loadRemoteTunnels();
      } else {
        ElMessage.error(result.message || 'SSH 服务添加失败');
      }
    } else {
      ElMessage.error('SSH 服务添加失败');
    }
  } catch (error) {
    console.error('Failed to add SSH service:', error);
    ElMessage.error('SSH 服务添加失败');
  } finally {
    remoteActionLoading.value = false;
  }
};

// 启动远程服务
const handleStartRemoteService = async () => {
  try {
    remoteActionLoading.value = true;

    // 准备服务配置
    const services = [];

    // 始终添加 Web UI
    services.push({
      name: 'web-ui',
      type: 'http',
      local_port: 8460
    });

    // 添加 API
    services.push({
      name: 'api',
      type: 'http',
      local_port: 8465
    });

    // 如果允许 SSH，添加 SSH 服务
    if (remoteConfig.value.allowSSH) {
      services.push({
        name: 'ssh',
        type: 'ssh',
        local_port: 22
      });
    }

    const response = await httpClient.post(`${REMOTE_API_BASE}/nat/start`, {
      nat_server_addr: 'localhost:8888',
      services: services
    });

    if (response.status === 200) {
      const result = response.data as { success: boolean; message: string; tunnels: typeof remoteTunnels.value };
      if (result.success) {
        remoteConfig.value.running = true;
        remoteTunnels.value = result.tunnels || [];
        ElMessage.success(result.message || '远程服务启动成功');
      } else {
        ElMessage.error(result.message || '远程服务启动失败');
      }
    } else {
      const error = response.data as { detail?: string };
      ElMessage.error(error.detail || '远程服务启动失败');
    }
  } catch (error) {
    console.error('Failed to start remote service:', error);
    ElMessage.error('远程服务启动失败');
  } finally {
    remoteActionLoading.value = false;
  }
};

// 停止远程服务
const handleStopRemoteService = async () => {
  try {
    remoteActionLoading.value = true;

    const response = await httpClient.post(`${REMOTE_API_BASE}/nat/stop`, {});

    if (response.status === 200) {
      const result = response.data as { success: boolean; message: string };
      if (result.success) {
        remoteConfig.value.running = false;
        remoteTunnels.value = [];
        ElMessage.success('远程服务已停止');
      } else {
        ElMessage.error(result.message || '远程服务停止失败');
      }
    } else {
      ElMessage.error('远程服务停止失败');
    }
  } catch (error) {
    console.error('Failed to stop remote service:', error);
    ElMessage.error('远程服务停止失败');
  } finally {
    remoteActionLoading.value = false;
  }
};

// 刷新远程状态（按钮点击）
const handleRefreshRemoteStatus = async () => {
  await refreshRemoteStatus();
  ElMessage.success('状态已刷新');
};

// 格式化时间
const formatTime = (isoString: string) => {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 1) {
      return '刚刚';
    } else if (minutes < 60) {
      return `${minutes}分钟前`;
    } else if (hours < 24) {
      return `${hours}小时前`;
    } else if (days < 7) {
      return `${days}天前`;
    } else {
      return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  } catch (_error) {
    return isoString;
  }
};

// 获取服务类型标签颜色
const getServiceTypeColor = (type: string) => {
  const colorMap: Record<string, string> = {
    'http': 'primary',
    'https': 'success',
    'ssh': 'warning',
    'tcp': 'info',
    'udp': 'danger'
  };
  return colorMap[type] || 'info';
};

onMounted(async () => {
  await loadWorkspaces();
  await loadGlobalStats();
  await checkAuthStatus();

  // 监听来自OAuth回调窗口的消息
  window.addEventListener('message', handleOAuthMessage);
});

onUnmounted(() => {
  authService.stopPolling();
  window.removeEventListener('message', handleOAuthMessage);
});
</script>

<style scoped>
.workspaces-view {
  min-height: 100vh;
  height: auto;
  padding: var(--spacing-2xl);
  background:
    radial-gradient(at 40% 20%, rgba(var(--color-primary-rgb), 0.05) 0px, transparent 50%),
    radial-gradient(at 80% 0%, rgba(var(--color-accent-rgb), 0.04) 0px, transparent 50%),
    radial-gradient(at 0% 50%, rgba(var(--color-primary-rgb), 0.03) 0px, transparent 50%);
}

/* 顶部栏 */
.top-bar {
  max-width: 1400px;
  margin: 0 auto 20px;
  display: flex;
  justify-content: flex-end;
}

.top-actions-container {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.action-divider {
  width: 1px;
  height: 24px;
  background: var(--el-border-color);
  flex-shrink: 0;
}

.language-selector-wrapper {
  position: relative;
  flex-shrink: 0;
}

/* 认证区域顶部样式 */
.auth-section-top {
  display: flex;
  align-items: center;
}

.user-dropdown-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.user-dropdown-trigger:hover {
  background: rgba(255, 255, 255, 1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.user-nickname {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-info-dropdown {
  .user-email {
    font-size: 13px;
    color: var(--el-text-color-primary);
    margin-bottom: 4px;
  }

  .token-stats {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

/* 主内容区域 */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
}

/* 工作区独立区域 */
.workspaces-section {
  margin-bottom: 40px;
}

.workspace-tabs {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.workspace-tabs :deep(.el-tabs__header) {
  background: rgba(255, 255, 255, 0.9);
  margin: 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.workspace-tabs :deep(.el-tabs__content) {
  padding: 0;
}

.tab-content {
  padding: var(--spacing-2xl);
}

/* ====================
   STATS SECTION (全局统计卡片)
   ==================== */
.stats-section {
  max-width: 1400px;
  margin: 0 auto 30px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.05);
  transition: all var(--duration-base) var(--ease-default);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  flex-shrink: 0;
}

.stat-icon-workspace {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.stat-icon-skill {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
}

.stat-icon-agent {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
  font-weight: 500;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}

/* ====================
   TOOLBAR SECTION
   ==================== */
.toolbar-section {
  max-width: 1400px;
  margin: 0 auto 24px;
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

.workspace-path {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  margin-bottom: var(--spacing-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgba(var(--color-primary-rgb), 0.08);
  padding: 4px 8px;
  border-radius: 4px;
  width: fit-content;
  max-width: 100%;
}

.workspace-path .el-icon {
  color: var(--color-primary);
  flex-shrink: 0;
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

/* Workspace Stats (工作区统计) */
.workspace-stats {
  display: flex;
  gap: 16px;
  margin-bottom: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(0, 0, 0, 0.02);
  border-radius: var(--radius-lg);
}

.workspace-stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.workspace-stat-item .el-icon {
  color: var(--color-primary);
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
}

/* ====================
   REMOTE ACCESS PANEL
   ==================== */
.remote-access-panel {
  padding: 4px 0;
}

.service-control-section {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
}

.control-buttons {
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.control-buttons .el-button {
  flex: 1;
}

.remote-config-section {
  margin-bottom: 8px;
}

.config-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}

.config-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.config-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.nat-config-info {
  margin-top: 8px;
  padding: 8px;
  background-color: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
}

.config-info-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.config-info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
}

.config-info-key {
  color: #606266;
  font-weight: 500;
  flex-shrink: 0;
}

.config-info-value {
  color: #909399;
  text-align: right;
  word-break: break-all;
  margin-left: 12px;
}

.service-types-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-left: 12px;
}

.remote-status-section {
  margin-top: 12px;
}

.status-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.status-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.nat-service-details {
  margin-bottom: 12px;
  padding: 8px;
  background-color: #f0f9ff;
  border-radius: 4px;
  border: 1px solid #e1f5fe;
}

.service-detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}

.service-detail-key {
  color: #606266;
  font-weight: 500;
  flex-shrink: 0;
}

.service-detail-value {
  color: #409eff;
  text-align: right;
  word-break: break-all;
  margin-left: 12px;
  font-family: 'Courier New', monospace;
}

.tunnels-section {
  margin-top: 12px;
}

.tunnels-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.tunnels-list {
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 12px;
}

.tunnel-item {
  margin-bottom: 8px;
  padding: 12px;
  background-color: #f5f7fa;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  transition: all 0.2s;
}

.tunnel-item:hover {
  background-color: #ecf5ff;
  border-color: #409eff;
}

.tunnel-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tunnel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tunnel-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tunnel-url {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.url-label {
  color: #606266;
  font-weight: 500;
  flex-shrink: 0;
}

.url-link {
  color: #409eff;
  text-decoration: none;
  word-break: break-all;
  transition: color 0.2s;
}

.url-link:hover {
  color: #66b1ff;
  text-decoration: underline;
}

.tunnel-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-label {
  color: #909399;
  font-weight: 500;
}

.meta-value {
  color: #606266;
}

.meta-value.tunnel-id {
  font-family: 'Courier New', monospace;
  color: #909399;
  font-size: 10px;
}

.empty-tunnels {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: #909399;
  gap: 8px;
  background: #f5f7fa;
  border-radius: 6px;
  border: 1px dashed #dcdfe6;
}

.remote-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #ecf5ff;
  border-radius: 6px;
  color: #409eff;
  font-size: 12px;
  line-height: 1.4;
}

.remote-hint .el-icon {
  flex-shrink: 0;
}
</style>
