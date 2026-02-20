/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="error-content compact-mt-sm compact-mb-sm">
    <el-alert
      :title="errorTitle"
      type="error"
      :closable="false"
      show-icon
    >
      <template #default>
        <div class="error-details">
          <!-- 显示错误代码 -->
          <div v-if="errorCode" class="error-code compact-mb-sm">
            <span class="error-code-label">错误代码：</span>
            <span class="error-code-value compact-code">{{ errorCode }}</span>
          </div>

          <div v-if="hasDetails" class="error-info">
            <div class="error-header">
              <span>错误详情</span>
            </div>
            <div class="error-body compact-mt-sm">
              <pre class="compact-pre">{{ formatErrorDetails(block.details) }}</pre>
            </div>
          </div>
        </div>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ElAlert } from 'element-plus'
import type { ErrorContentBlock } from '@/types/websocket'
import { logger } from '@/utils/logger'

const props = defineProps<{
  block: ErrorContentBlock
}>()

// 计算错误代码
const errorCode = computed(() => {
  if (props.block.details && typeof props.block.details === 'object' && 'code' in props.block.details) {
    return props.block.details.code as string
  }
  return null
})

// 计算错误标题（包含错误代码）
const errorTitle = computed(() => {
  // 如果有 details，提取更友好的错误信息
  if (props.block.details && typeof props.block.details === 'object') {
    const details = props.block.details as unknown
    if (details.original_error) {
      // 从原始错误中提取关键信息
      const originalError = details.original_error
      if (originalError.includes('Agent initialization failed')) {
        return 'Agent 初始化失败'
      }
      if (originalError.includes('No module named')) {
        const match = originalError.match(/No module named '([^']+)'/)
        return match ? `缺少依赖: ${match[1]}` : '缺少依赖模块'
      }
      if (originalError.includes('has no attribute')) {
        const match = originalError.match(/'([^']+)' has no attribute '([^']+)'/)
        return match ? `属性错误: ${match[1]}.${match[2]}` : originalError
      }
      // 返回原始错误的前100个字符
      return originalError.length > 100 ? originalError.substring(0, 100) + '...' : originalError
    }
  }

  if (errorCode.value) {
    return `${errorCode.value}: ${props.block.message || '未知错误'}`
  }
  return props.block.message || '未知错误'
})

// 检查是否有详情（排除 code 字段）
const hasDetails = computed(() => {
  if (!props.block.details) return false
  if (typeof props.block.details === 'string') return true
  if (typeof props.block.details === 'object') {
    const detailsWithoutCode = { ...props.block.details }
    delete detailsWithoutCode.code
    return Object.keys(detailsWithoutCode).length > 0
  }
  return false
})

// 添加调试日志（仅在开发模式）
onMounted(() => {
  if (import.meta.env.DEV && import.meta.env.VITE_DEBUG === 'true') {
    logger.debug('ErrorContent component mounted with block:', props.block)
  }
})

const formatErrorDetails = (details: unknown): string => {
  if (typeof details === 'string') {
    return details
  } else if (details === null || details === undefined) {
    return 'null'
  } else if (typeof details === 'object') {
    // 如果是对象，格式化显示
    const lines: string[] = []

    // 处理原始错误信息
    if (details.original_error) {
      lines.push(`错误: ${details.original_error}`)
    }

    // 处理错误类型
    if (details.error_type) {
      lines.push(`类型: ${details.error_type}`)
    }

    // 处理task_id
    if (details.task_id) {
      lines.push(`Task ID: ${details.task_id}`)
    }

    // 其他字段
    const excludeFields = ['code', 'original_error', 'error_type', 'task_id']
    const otherFields = Object.keys(details).filter(key => !excludeFields.includes(key))

    if (otherFields.length > 0) {
      lines.push('\n其他信息:')
      for (const key of otherFields) {
        lines.push(`  ${key}: ${JSON.stringify(details[key])}`)
      }
    }

    return lines.join('\n')
  }
  return JSON.stringify(details, null, 2)
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.error-details {
  margin-top: var(--compact-padding-md);
}

.error-code {
  margin-bottom: var(--compact-padding-md);
  padding: var(--compact-padding-sm) var(--compact-padding-md);
  background-color: var(--el-color-error-light-9);
  border-left: 3px solid var(--el-color-error);
  border-radius: var(--compact-radius-md);
}

.error-code-label {
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-right: var(--compact-gap-sm);
}

.error-code-value {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: var(--compact-font-sm);
  color: var(--el-color-error);
  font-weight: 600;
}

.error-info {
  margin-bottom: var(--compact-padding-md);
}

.error-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--compact-padding-xs);
  font-weight: 500;
  font-size: var(--compact-font-sm);
  color: var(--el-text-color-primary);
}

.error-body {
  background-color: var(--el-fill-color-light);
  border-radius: var(--compact-radius-md);
  padding: var(--compact-padding-sm) var(--compact-padding-md);
}

.error-body pre {
  margin: 0;
}

:deep(.el-alert) {
  border: none;
  background-color: var(--el-color-error-light-9);
}

:deep(.el-alert__title) {
  color: var(--el-color-error);
  font-weight: 500;
  font-size: var(--compact-font-md);
}

:deep(.el-alert__icon) {
  color: var(--el-color-error);
}
</style>