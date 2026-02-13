/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-dialog
    v-model="visible"
    title="检测到异常退出"
    width="600px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="true"
  >
    <div class="crash-recovery-content">
      <!-- 警告图标 -->
      <div class="warning-icon">
        <el-icon :size="60" color="#E6A23C">
          <Warning />
        </el-icon>
      </div>

      <!-- 主要信息 -->
      <div class="message">
        <p class="title">应用上次异常退出</p>
        <p class="description">
          检测到应用在上次运行时发生了异常。您可以：
        </p>
      </div>

      <!-- 崩溃报告列表 -->
      <div v-if="crashReports.length > 0" class="crash-list">
        <el-collapse v-model="activeCollapse">
          <el-collapse-item
            v-for="(report, index) in crashReports"
            :key="report.id"
            :title="`崩溃 #${crashReports.length - index} - ${formatTime(report.context.timestamp)}`"
            :name="index"
          >
            <div class="crash-details">
              <div class="detail-row">
                <span class="label">类型:</span>
                <span class="value">{{ report.context.type || '未知' }}</span>
              </div>
              <div class="detail-row">
                <span class="label">错误:</span>
                <span class="value error-text">{{ formatError(report.error) }}</span>
              </div>
              <div v-if="report.context.url" class="detail-row">
                <span class="label">页面:</span>
                <span class="value">{{ report.context.url }}</span>
              </div>
              <div v-if="report.stackTrace" class="detail-row stack-trace">
                <span class="label">堆栈:</span>
                <pre class="value">{{ report.stackTrace }}</pre>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 操作选项 -->
      <div class="actions-info">
        <el-alert
          type="info"
          :closable="false"
          show-icon
        >
          <template #default>
            <div class="info-content">
              <p>💡 <strong>建议操作：</strong></p>
              <ul>
                <li>点击"发送报告"可以帮助我们改进应用</li>
                <li>您的报告已自动包含系统信息和错误详情</li>
                <li>发送报告后，您可以清除本地崩溃记录</li>
              </ul>
            </div>
          </template>
        </el-alert>
      </div>

      <!-- Analytics 同意状态 -->
      <div v-if="consentLevel === 'none'" class="consent-notice">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
        >
          <template #default>
            <p>当前隐私设置为"不允许数据收集"，将不会自动发送崩溃报告。</p>
            <p>您可以在设置中更改此选项。</p>
          </template>
        </el-alert>
      </div>
    </div>

    <!-- 底部按钮 -->
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleIgnore">
          忽略
        </el-button>
        <el-button @click="handleClear">
          清除记录
        </el-button>
        <el-button
          type="primary"
          :loading="sending"
          :disabled="consentLevel === 'none'"
          @click="handleSendReport"
        >
          {{ consentLevel === 'none' ? '已禁用发送' : '发送报告' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'
import type { CrashReport } from '@/services/errorHandler'

interface Props {
  crashReports: CrashReport[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'close': []
  'sent': []
  'cleared': []
}>()

const visible = defineModel<boolean>({ required: true })
const sending = ref(false)
const activeCollapse = ref<number[]>([0]) // 默认展开第一个

// 获取用户同意级别
const consentLevel = computed(() => {
  return localStorage.getItem('analytics_consent') || 'none'
})

// 格式化时间
const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))

  if (diffMins < 1) {
    return '刚刚'
  } else if (diffMins < 60) {
    return `${diffMins} 分钟前`
  } else if (diffMins < 1440) {
    const hours = Math.floor(diffMins / 60)
    return `${hours} 小时前`
  } else {
    return date.toLocaleString('zh-CN')
  }
}

// 格式化错误信息
const formatError = (error: Error | string) => {
  const errorStr = typeof error === 'string' ? error : error.message
  // 限制长度
  if (errorStr.length > 200) {
    return errorStr.substring(0, 200) + '...'
  }
  return errorStr
}

// 发送崩溃报告
const handleSendReport = async () => {
  if (props.crashReports.length === 0) {
    ElMessage.warning('没有可发送的崩溃报告')
    return
  }

  sending.value = true

  try {
    // 动态导入 feedbackService（如果存在）
    let feedbackService: unknown = null
    try {
      const module = await import('@/services/feedback')
      feedbackService = module.feedbackService
    } catch (e) {
      console.warn('[CrashRecoveryDialog] feedbackService not available:', e)
    }

    // 只发送最新的一个崩溃报告
    const latestReport = props.crashReports[props.crashReports.length - 1]

    if (!latestReport) {
      ElMessage.warning('崩溃报告数据无效')
      return
    }

    const reportData = {
      type: 'bug' as const,
      title: '应用崩溃报告 (自动提交)',
      description: `**崩溃时间**\n${formatTime(latestReport.context.timestamp)}\n\n**错误信息**\n${formatError(latestReport.error)}\n\n**平台**\n${latestReport.context.platform}`,
      crashReport: latestReport,
    }

    if (feedbackService) {
      await feedbackService.submitFeedback(reportData)
      ElMessage.success('✅ 崩溃报告已发送，感谢您的反馈！')
    } else {
      // feedback 服务不可用，将数据保存到 localStorage
      console.log('[CrashRecoveryDialog] Feedback service not available, saving locally')
      const pendingReports = JSON.parse(localStorage.getItem('pending_feedback') || '[]')
      pendingReports.push(reportData)
      localStorage.setItem('pending_feedback', JSON.stringify(pendingReports))
      ElMessage.success('✅ 崩溃报告已保存，将在反馈功能可用后自动发送')
    }

    // 标记为已上报
    const { errorHandler } = await import('@/services/errorHandler')
    errorHandler.markAsReported(latestReport.id)

    emit('sent')
    handleClose()
  } catch (error) {
    console.error('[CrashRecoveryDialog] Failed to send crash report:', error)
    ElMessage.error('❌ 发送失败，请稍后再试或联系技术支持')
  } finally {
    sending.value = false
  }
}

// 清除崩溃记录
const handleClear = () => {
  ElMessageBox.confirm(
    '确定要清除所有崩溃记录吗？此操作不可恢复。',
    '确认清除',
    {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    }
  ).then(async () => {
    const { errorHandler } = await import('@/services/errorHandler')
    errorHandler.clearCrashReports()

    ElMessage.success('✅ 崩溃记录已清除')

    emit('cleared')
    handleClose()
  }).catch(() => {
    // 用户取消
  })
}

// 忽略
const handleIgnore = () => {
  ElMessage.info('已忽略，崩溃记录将保留在本地')
  handleClose()
}

// 关闭对话框
const handleClose = () => {
  visible.value = false
  emit('close')
}
</script>

<style scoped lang="scss">
.crash-recovery-content {
  padding: 10px 0;

  .warning-icon {
    text-align: center;
    margin-bottom: 20px;
  }

  .message {
    text-align: center;
    margin-bottom: 20px;

    .title {
      font-size: 18px;
      font-weight: 600;
      margin-bottom: 10px;
      color: var(--el-text-color-primary);
    }

    .description {
      font-size: 14px;
      color: var(--el-text-color-regular);
      margin: 0;
      padding: 0 20px;
    }
  }

  .crash-list {
    margin-bottom: 20px;

    :deep(.el-collapse-item__header) {
      font-weight: 500;
    }

    .crash-details {
      font-size: 13px;

      .detail-row {
        display: flex;
        margin-bottom: 10px;
        line-height: 1.6;

        &.stack-trace {
          flex-direction: column;

          pre.value {
            margin-top: 5px;
            white-space: pre-wrap;
            word-break: break-all;
          }
        }

        .label {
          min-width: 60px;
          font-weight: 600;
          color: var(--el-text-color-secondary);
          margin-right: 10px;
        }

        .value {
          flex: 1;
          color: var(--el-text-color-primary);
          word-break: break-word;

          &.error-text {
            color: var(--el-color-danger);
          }
        }
      }
    }
  }

  .actions-info {
    margin-bottom: 15px;

    .info-content {
      ul {
        margin: 10px 0 0 0;
        padding-left: 20px;

        li {
          margin-bottom: 5px;
          line-height: 1.6;
        }
      }
    }
  }

  .consent-notice {
    margin-bottom: 15px;
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
