/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { RouterView } from 'vue-router'
import { useTheme } from '@/themes/composables/useTheme'
import CrashRecoveryDialog from '@/components/CrashRecoveryDialog.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { logger } from '@/utils/logger'
import type { CrashReport } from '@/services/errorHandler'

const theme = useTheme()

// 崩溃恢复对话框
const showCrashDialog = ref(false)
const crashReports = ref<CrashReport[]>([])

// 当前主题class
const themeClass = computed(() => `theme-${theme.currentTheme.value}`)

onMounted(async () => {
  // 0. 初始化主题系统
  theme.initTheme()

  // 注意：WebSocket 连接现在在 ChatView 中初始化，以使用正确的 workspaceId

  // 1. 检查是否有崩溃报告
  await checkCrashReports()
})

/**
 * 检查崩溃报告并显示恢复对话框
 */
const checkCrashReports = async () => {
  // 从 window 对象获取崩溃报告（由 main.ts 设置）
  const reports = (window as unknown).__CRASH_REPORTS__ as CrashReport[] | undefined

  if (reports && reports.length > 0) {
    // 过滤出最近的崩溃（24小时内）
    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000
    const recentCrashes = reports.filter(r => r.context.timestamp > oneDayAgo)

    if (recentCrashes.length > 0) {
      logger.info(`Found ${recentCrashes.length} recent crash report(s)`)

      // 延迟显示对话框，让应用先加载完成
      setTimeout(() => {
        crashReports.value = recentCrashes
        showCrashDialog.value = true
      }, 1000)
    } else {
      logger.info('Found crash reports, but they are older than 24 hours')
    }
  }
}

/**
 * 崩溃报告发送成功
 */
const handleCrashReportSent = () => {
  logger.info('Crash report sent successfully')
  showCrashDialog.value = false
}

/**
 * 崩溃记录已清除
 */
const handleCrashReportsCleared = () => {
  logger.info('Crash reports cleared')
  showCrashDialog.value = false
}

/**
 * 对话框关闭
 */
const handleCrashDialogClose = () => {
  showCrashDialog.value = false
}

/**
 * 全局错误处理
 */
const handleGlobalError = (error: Error, instance: unknown, info: string) => {
  logger.error('Global error caught', error, { component: info })
}
</script>

<template>
  <div :class="['app-wrapper', themeClass]" data-testid="app-loaded">
    <ErrorBoundary @error="handleGlobalError">
      <RouterView v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </ErrorBoundary>

    <!-- 崩溃恢复对话框 -->
    <CrashRecoveryDialog
      v-model="showCrashDialog"
      :crash-reports="crashReports"
      @sent="handleCrashReportSent"
      @cleared="handleCrashReportsCleared"
      @close="handleCrashDialogClose"
    />
  </div>
</template>

<style>
/* Page Transition Animation */
.page-enter-active,
.page-leave-active {
  transition: all var(--duration-slower) var(--ease-default);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.app-wrapper {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  position: relative;
}

/* Light主题样式 */
.theme-light .app-wrapper {
  background-color: #FFFFFF;
  color: #303133;
}

/* Dark主题样式 */
.theme-dark .app-wrapper {
  background-color: #1a1a1a;
  color: #e5e5e5;
}
</style>
