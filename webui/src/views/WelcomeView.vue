/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="welcome-container">
    <div class="welcome-content">
      <!-- Logo 和标题 -->
      <div class="welcome-header">
        <div class="logo-section">
          <h1 class="app-title">大微</h1>
          <p class="app-subtitle">AI 个人助手平台</p>
        </div>
      </div>

      <!-- 服务器状态卡片 -->
      <div class="server-status-section">
        <el-card class="status-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon><Connection /></el-icon>
              <span>服务器状态</span>
            </div>
          </template>

          <!-- 服务器状态指示器 -->
          <div class="status-banner" :class="statusBannerClass">
            <div class="status-indicator">
              <div :class="['status-icon-wrapper', statusPulseClass]">
                <el-icon :size="36" class="status-icon">
                  <component :is="statusIcon" />
                </el-icon>
              </div>
              <div class="status-text">
                <div class="status-title">{{ statusTitle }}</div>
                <div class="status-desc">{{ statusDescription }}</div>
              </div>
            </div>
          </div>

          <!-- 当前服务器连接状态 -->
          <div class="current-status">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="连接状态">
                <el-tag v-if="restarting" type="warning" effect="plain" size="large">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  <span style="margin-left: 4px">重启中...</span>
                </el-tag>
                <el-tag v-else :type="serverConnected ? 'success' : 'danger'" effect="plain" size="large">
                  <el-icon><component :is="serverConnected ? CircleCheck : CircleClose" /></el-icon>
                  <span style="margin-left: 4px">{{ serverConnected ? '已连接' : '未连接' }}</span>
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="服务器地址">
                <code>{{ serverUrl }}</code>
              </el-descriptions-item>
              <el-descriptions-item label="DAWEI_HOME">
                <code>{{ daweiHome || '未设置' }}</code>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>

        <!-- 服务器启动历史 -->
        <el-card class="history-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon><Clock /></el-icon>
              <span>启动历史</span>
            </div>
          </template>

          <div v-if="serverStartInfo" class="server-history">
            <div class="history-item">
              <div class="history-label">上次启动时间</div>
              <div class="history-value">{{ formatDate(serverStartInfo.timestamp) }}</div>
            </div>
            <div class="history-item">
              <div class="history-label">主机</div>
              <div class="history-value">{{ serverStartInfo.host }}</div>
            </div>
            <div class="history-item">
              <div class="history-label">端口</div>
              <div class="history-value">{{ serverStartInfo.port }}</div>
            </div>
            <div v-if="serverStartInfo.workers" class="history-item">
              <div class="history-label">工作进程</div>
              <div class="history-value">{{ serverStartInfo.workers }}</div>
            </div>
          </div>

          <el-empty v-else description="暂无启动历史" :image-size="80" />
        </el-card>
      </div>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <el-button
          type="primary"
          size="large"
          @click="goToWorkspaces"
          :disabled="!serverConnected && !restarting"
        >
          <el-icon><FolderOpened /></el-icon>
          进入工作空间
        </el-button>
        <el-button
          :type="serverConnected ? 'warning' : 'success'"
          size="large"
          @click="restartBackend"
          :loading="restarting"
          :disabled="restarting"
        >
          <el-icon><RefreshRight /></el-icon>
          {{ restarting ? '处理中...' : (serverConnected ? '重启后端' : '启动后端') }}
        </el-button>
        <el-button size="large" @click="refreshServerInfo" :disabled="restarting">
          <el-icon><Refresh /></el-icon>
          刷新状态
        </el-button>
      </div>

      <!-- 帮助提示 -->
      <div class="help-text">
        <el-alert
          :type="serverConnected ? 'success' : 'info'"
          :closable="false"
          show-icon
        >
          <template #title>
            <template v-if="serverConnected">
              后端服务运行正常，可以开始使用
            </template>
            <template v-else>
              后端服务未启动
              <template v-if="!serverConnected">
                <br>
                <span style="font-size: 12px; opacity: 0.9">
                  启动方法：在终端运行 <code>cd agent && dawei server start</code>
                </span>
              </template>
            </template>
          </template>
        </el-alert>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { invoke } from '@tauri-apps/api/core'
import { ElMessage, ElCard, ElButton, ElTag, ElDescriptions, ElDescriptionsItem, ElEmpty, ElAlert, ElIcon } from 'element-plus'
import { Connection, Clock, FolderOpened, Refresh, RefreshRight, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import { logger } from '@/utils/logger'

const router = useRouter()

// 服务器连接状态
const serverConnected = ref(false)
const serverUrl = ref('http://localhost:8465')
const daweiHome = ref('')

// 重启状态
const restarting = ref(false)

// 服务器启动信息
interface ServerStartInfo {
  timestamp: string
  host: string
  port: number
  workers?: number
}

const serverStartInfo = ref<ServerStartInfo | null>(null)

// 计算状态横幅样式
const statusBannerClass = computed(() => {
  if (restarting.value) return 'status-warning'
  return serverConnected.value ? 'status-online' : 'status-offline'
})

// 计算状态脉冲样式
const statusPulseClass = computed(() => {
  if (restarting.value) return 'pulse-warning'
  return serverConnected.value ? 'pulse-success' : 'pulse-error'
})

// 状态图标
const statusIcon = computed(() => {
  if (restarting.value) return Loading
  return serverConnected.value ? CircleCheck : CircleClose
})

// 状态标题
const statusTitle = computed(() => {
  if (restarting.value) return '正在重启后端...'
  return serverConnected.value ? '后端服务已启动' : '后端服务未启动'
})

// 状态描述
const statusDescription = computed(() => {
  if (restarting.value) return '请稍候，正在重新启动服务'
  if (serverConnected.value) return '所有系统正常运行'
  return '请启动后端服务以使用完整功能'
})

/**
 * 检查服务器连接状态
 */
const checkServerConnection = async () => {
  try {
    const response = await fetch('http://localhost:8465/health', {
      method: 'GET',
      signal: AbortSignal.timeout(3000)
    })
    serverConnected.value = response.ok
  } catch {
    serverConnected.value = false
  }
}

/**
 * 获取 DAWEI_HOME 目录
 */
const getDaweiHome = async () => {
  try {
    const home = await invoke<string>('get_dawei_home_command')
    daweiHome.value = home
  } catch (error) {
    logger.error('Failed to get DAWEI_HOME', error as Error)
  }
}

/**
 * 获取服务器启动信息
 */
const getServerStartInfo = async () => {
  try {
    const info = await invoke<ServerStartInfo | null>('get_server_start_info')
    serverStartInfo.value = info
    logger.info('Server start info loaded', info)
  } catch (error) {
    logger.error('Failed to get server start info', error as Error)
  }
}

/**
 * 格式化日期时间
 */
const formatDate = (timestamp: string) => {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return timestamp
  }
}

/**
 * 刷新服务器信息
 */
const refreshServerInfo = async () => {
  await Promise.all([
    checkServerConnection(),
    getDaweiHome(),
    getServerStartInfo()
  ])
}

/**
 * 重启后端
 */
const restartBackend = async () => {
  if (restarting.value) return

  restarting.value = true

  try {
    // 先尝试使用 standalone 版本的 restart_backend 命令
    let result: string
    try {
      result = await invoke<string>('restart_backend')
      ElMessage.success(result)
    } catch (standaloneError) {
      logger.warn('Standalone restart_backend not available', standaloneError)

      // 如果 standalone 命令不可用，尝试使用 API 方式
      try {
        result = await invoke<string>('restart_backend_api')
        ElMessage.success(result)
      } catch (apiError) {
        // API 方式也失败了，提供手动操作指引
        const errorMsg = apiError instanceof Error ? apiError.message : String(apiError)
        logger.error('Both restart methods failed', { standaloneError, apiError })

        // 根据不同的错误类型给出不同的提示
        if (errorMsg.includes('Backend is not running')) {
          ElMessage.warning({
            message: '后端服务未运行\n\n请手动启动后端：\ncd agent\ndawei server start',
            duration: 6000,
            dangerouslyUseHTMLString: false,
            showClose: true
          })
        } else if (errorMsg.includes('404') || errorMsg.includes('status: 404') || errorMsg.includes('Not Found')) {
          // 后端在运行但没有重启端点
          ElMessage.info({
            message: '后端正在运行，但不支持 API 重启\n\n开发版本需要手动重启：\n1. 按 Ctrl+C 停止当前后端\n2. 运行: cd agent && dawei server start',
            duration: 8000,
            dangerouslyUseHTMLString: false,
            showClose: true
          })
        } else if (errorMsg.includes('not available') || errorMsg.includes('endpoint')) {
          ElMessage.info({
            message: '此版本不支持自动重启\n\n请手动重启后端：\ncd agent\ndawei server restart',
            duration: 6000,
            dangerouslyUseHTMLString: false,
            showClose: true
          })
        } else {
          ElMessage.error(`重启后端失败: ${errorMsg}`)
        }

        restarting.value = false
        return
      }
    }

    // 等待后端重启
    ElMessage.info('等待后端服务启动...')
    await new Promise(resolve => setTimeout(resolve, 3000))

    // 刷新状态
    await refreshServerInfo()

    // 检查后端是否成功启动
    if (serverConnected.value) {
      ElMessage.success('后端服务已成功启动')
    } else {
      ElMessage.warning('后端可能尚未启动完成，请稍后刷新状态')
    }
  } catch (error) {
    logger.error('Failed to restart backend', error as Error)
    const errorMsg = error instanceof Error ? error.message : '未知错误'
    ElMessage.error(`重启后端失败: ${errorMsg}`)
  } finally {
    restarting.value = false
  }
}

/**
 * 导航到工作空间页面
 */
const goToWorkspaces = () => {
  router.push('/workspaces')
}

// 组件挂载时初始化
onMounted(async () => {
  await refreshServerInfo()
})
</script>

<style scoped>
.welcome-container {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  overflow: hidden;
}

.welcome-content {
  width: 90%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  background: var(--el-bg-color);
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.welcome-header {
  text-align: center;
  padding: 12px 0;
}

.logo-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.app-title {
  font-size: 48px;
  font-weight: 700;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
}

.app-subtitle {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  margin: 0;
}

.server-status-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
}

/* 状态横幅 - 在卡片内部 */
.status-banner {
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 16px;
  transition: all 0.3s ease;
}

.status-banner.status-online {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  box-shadow: 0 2px 12px rgba(16, 185, 129, 0.3);
}

.status-banner.status-offline {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  box-shadow: 0 2px 12px rgba(239, 68, 68, 0.3);
}

.status-banner.status-warning {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
  box-shadow: 0 2px 12px rgba(245, 158, 11, 0.3);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 16px;
  color: white;
}

.status-icon-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.status-icon {
  color: white;
  z-index: 1;
}

.pulse-success::before,
.pulse-error::before,
.pulse-warning::before {
  content: '';
  position: absolute;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  animation: pulse 2s ease-out infinite;
  z-index: 0;
}

.pulse-success::before {
  background: rgba(255, 255, 255, 0.4);
}

.pulse-error::before {
  background: rgba(255, 255, 255, 0.3);
}

.pulse-warning::before {
  background: rgba(255, 255, 255, 0.35);
}

@keyframes pulse {
  0% {
    transform: scale(0.6);
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    transform: scale(1.4);
    opacity: 0;
  }
}

.pulse-warning .status-icon {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.status-text {
  flex: 1;
}

.status-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
  color: white;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.status-desc {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.95);
  font-weight: 400;
}

.current-status {
  padding: 8px 0;
}

.current-status code {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-color-primary);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.server-history {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.history-item:last-child {
  border-bottom: none;
}

.history-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.history-value {
  font-size: 14px;
  color: var(--el-text-color-primary);
  font-weight: 500;
  font-family: monospace;
}

.action-buttons {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 12px 0;
  flex-wrap: wrap;
}

.help-text {
  padding: 0 8px;
}

/* Dark mode adjustments */
:deep(.theme-dark) .welcome-content {
  background: var(--el-bg-color-page);
}

:deep(.theme-dark) .app-title {
  background: linear-gradient(135deg, #a78bfa 0%, #c084fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
</style>
