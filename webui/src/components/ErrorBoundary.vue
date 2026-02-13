/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <slot v-if="!hasError" />
  <div v-else class="error-boundary">
    <el-result icon="error" title="操作失败" :sub-title="errorMessage">
      <template #extra>
        <el-space>
          <el-button type="primary" @click="handleReload">刷新页面</el-button>
          <el-button @click="handleRetry">重试</el-button>
        </el-space>
        <div class="error-details">
          <div class="error-details-header">错误详情</div>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="错误名称">{{ error?.name }}</el-descriptions-item>
            <el-descriptions-item label="错误信息">{{ error?.message }}</el-descriptions-item>
            <el-descriptions-item v-if="errorInfo" label="组件信息">{{ errorInfo }}</el-descriptions-item>
            <el-descriptions-item v-if="error?.stack" label="堆栈跟踪">
              <pre class="error-stack">{{ error?.stack }}</pre>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onErrorCaptured } from 'vue'
import { ElResult, ElButton, ElSpace, ElDescriptions, ElDescriptionsItem } from 'element-plus'
import { logger } from '@/utils/logger'

interface Props {
  showDetails?: boolean
  onError?: (error: Error, instance: unknown, info: string) => void
}

const props = withDefaults(defineProps<Props>(), {
  showDetails: true
})

const emit = defineEmits<{
  error: [error: Error, instance: unknown, info: string]
  retry: []
}>()

const hasError = ref(false)
const error = ref<Error | null>(null)
const errorInfo = ref<string | null>(null)

const errorMessage = computed(() => {
  if (!error.value) return '未知错误'
  return error.value.message || '操作失败，请刷新重试'
})

/**
 * Capture errors from descendant components
 */
onErrorCaptured((err: Error, instance: unknown, info: string) => {
  hasError.value = true
  error.value = err
  errorInfo.value = info

  // Log error
  logger.error('ErrorBoundary caught error', err, { component: info })

  // Report to error monitoring (recordErrorHandling is for error processing metrics, not general errors)
  // Just log the error - general error recording is not implemented yet
  logger.error('Error recorded:', err, { component: info })

  // Notify parent
  if (props.onError) {
    props.onError(err, instance, info)
  }
  emit('error', err, instance, info)

  // Prevent error from propagating
  return false
})

/**
 * Reload the page
 */
const handleReload = () => {
  window.location.reload()
}

/**
 * Retry the operation
 */
const handleRetry = () => {
  hasError.value = false
  error.value = null
  errorInfo.value = null
  emit('retry')
}

/**
 * Reset error state (exposed for parent components)
 */
defineExpose({
  reset: () => {
    hasError.value = false
    error.value = null
    errorInfo.value = null
  }
})
</script>

<style scoped>
.error-boundary {
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.error-details {
  margin-top: 20px;
  width: 100%;
  max-width: 600px;
}

.error-details-header {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 12px;
}

.error-stack {
  max-height: 300px;
  overflow-y: auto;
  font-size: 12px;
  background-color: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 4px;
}

/* 修复 el-descriptions 标签竖着显示的问题 */
:deep(.el-descriptions__label) {
  width: auto !important;
  min-width: 80px;
  white-space: nowrap;
  overflow: visible;
  text-overflow: clip;
}

:deep(.el-descriptions__content) {
  width: auto;
  word-break: break-word;
}

:deep(.el-descriptions__cell) {
  padding: 8px 12px;
}

:deep(.el-descriptions) {
  font-size: 14px;
}
</style>
