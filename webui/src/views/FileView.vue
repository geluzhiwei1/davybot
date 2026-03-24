/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* 独立文件查看页面
* 在新标签页中打开文件,复用 FileContentArea 组件
*/

<template>
  <div class="file-view-container">
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="32">
        <Loading />
      </el-icon>
      <p>{{ t('fileView.loading') }}</p>
    </div>

    <div v-else-if="error" class="error-container">
      <el-result icon="error" :title="t('fileView.errorTitle')" :sub-title="error">
        <template #extra>
          <el-button type="primary" @click="goBack">{{ t('fileView.goBack') }}</el-button>
        </template>
      </el-result>
    </div>

    <div v-else class="file-content-wrapper">
      <!-- 文件内容区域 -->
      <div class="file-content-area">
        <FileContentArea v-if="file" :files="[file]" :active-file-id="file.id" :is-mobile-drawer="false"
          :workspace-id="workspaceId" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  Loading
} from '@element-plus/icons-vue'
import FileContentArea from '@/components/layout/FileContentArea.vue'

/**
 * 组合式API
 */
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

/**
 * 状态管理
 */
const loading = ref(true)
const error = ref<string>('')
const file = ref<any>(null)

/**
 * 从路由参数获取文件信息
 */
const workspaceId = computed(() => route.params.workspaceId as string || route.query.workspaceId as string)
const filePath = computed(() => route.query.path as string || '')
const fileName = computed(() => route.query.name as string || '')

/**
 * 加载文件内容
 */
const loadFile = async () => {
  try {
    loading.value = true
    error.value = ''

    if (!workspaceId.value) {
      throw new Error(t('fileView.errors.noWorkspaceId'))
    }

    if (!filePath.value) {
      throw new Error(t('fileView.errors.noFilePath'))
    }

    // 获取文件内容
    const response = await fetch(`/api/workspaces/${workspaceId.value}/files?path=${encodeURIComponent(filePath.value)}`)

    if (!response.ok) {
      throw new Error(`${t('fileView.errors.loadFailed')}: ${response.statusText}`)
    }

    // 根据文件类型处理响应
    const contentType = response.headers.get('content-type') || ''
    let content = ''

    if (contentType.includes('application/json')) {
      const json = await response.json()
      content = json.content || ''
    } else if (contentType.includes('text/') || contentType.includes('application/json')) {
      content = await response.text()
    } else {
      // 二进制文件 (图片, PDF, Office 文件等)
      // 对于 Office 文件,保持为空字符串,由 FileContentArea 组件处理
      content = ''
    }

    // 构造文件对象
    file.value = {
      id: filePath.value,
      name: fileName.value || filePath.value.split('/').pop() || '',
      path: filePath.value,
      type: 'file',
      content: content,
      isDirty: false
    }

    // 设置页面标题
    document.title = `${file.value.name} - ${t('fileView.title')}`

  } catch (err: any) {
    console.error('[FileView] 加载文件失败:', err)
    error.value = err.message || t('fileView.errors.unknown')
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

/**
 * 返回上一页或关闭
 */
const goBack = () => {
  // 如果是独立标签页打开的,关闭窗口或返回工作区
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push({ name: 'chat', params: { workspaceId: workspaceId.value } })
  }
}

/**
 * 组件挂载时加载文件
 */
onMounted(() => {
  loadFile()
})
</script>

<style scoped>
.file-view-container {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color-page);
  overflow: hidden;
}

.loading-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--el-text-color-secondary);
}

.error-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.file-content-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-info-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  z-index: 10;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.file-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.file-name {
  font-size: 16px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-left: 8px;
}

.file-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.file-content-area {
  flex: 1;
  overflow: hidden;
  background-color: var(--el-bg-color-page);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .file-info-bar {
    padding: 8px 12px;
  }

  .file-name {
    font-size: 14px;
  }

  .file-path {
    display: none;
  }
}
</style>
