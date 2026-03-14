/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* Office 文件查看器 - 使用 @vue-office 源码
*/

<template>
  <div class="office-viewer">
    <!-- 工具栏 -->
    <div class="office-toolbar" v-if="fileType">
      <el-button-group>
        <el-button size="small" @click="downloadFile" :icon="Download">
          下载文件
        </el-button>
      </el-button-group>

      <div class="file-info">
        <el-tag type="success">{{ fileType.toUpperCase() }}</el-tag>
        <span class="filename">{{ filename }}</span>
      </div>
    </div>

    <!-- 预览区域 -->
    <div class="office-preview">
      <!-- Excel 预览 -->
      <div v-if="isExcelFile" class="excel-viewer">
        <ExcelViewer v-if="fileContent" :src="fileContent" class="excel-component" />
      </div>

      <!-- Word 预览 -->
      <div v-else-if="isWordFile" class="word-viewer">
        <DocxViewer v-if="fileContent" :src="fileContent" class="docx-component" />
      </div>

      <!-- PPT 预览 -->
      <div v-else-if="isPPTFile" class="ppt-viewer">
        <PptxViewer v-if="fileContent" :src="fileContent" class="pptx-component" />
      </div>

      <!-- 不支持的文件类型 -->
      <div v-else class="office-fallback">
        <el-alert
          :title="`${fileType.toUpperCase()} 文件预览`"
          type="info"
          :description="`暂不支持 ${fileType.toUpperCase()} 文件预览。请下载文件或在新标签页中打开。`"
          :closable="false"
          show-icon
        />
        <div class="preview-placeholder">
          <el-icon :size="64" color="#909399">
            <Document />
          </el-icon>
          <p class="hint-text">{{ fileType.toUpperCase() }} 文件内容预览不可用</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, TopRight, Document } from '@element-plus/icons-vue'
import ExcelViewer from '../office/ExcelViewer.vue'
import DocxViewer from '../office/DocxViewer.vue'
import PptxViewer from '../office/PptxViewer.vue'

interface Props {
  modelValue: string // 文件内容（base64 或 URL）
  filename: string // 文件名
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'error': [error: Error]
}>()

const fileContent = ref('')

// 检测文件类型
const fileType = computed(() => {
  const ext = props.filename.split('.').pop()?.toLowerCase()
  return ext || ''
})

const isExcelFile = computed(() => {
  return ['xlsx', 'xls'].includes(fileType.value)
})

const isWordFile = computed(() => {
  return ['docx', 'doc'].includes(fileType.value)
})

const isPPTFile = computed(() => {
  return ['pptx', 'ppt'].includes(fileType.value)
})

// 处理文件内容
const processFileContent = (content: string) => {
  if (!content) {
    console.warn('[OfficeViewer] 文件内容为空')
    return
  }
  fileContent.value = content
}

// 下载文件
const downloadFile = () => {
  try {
    let content: BlobPart

    if (props.modelValue.startsWith('data:')) {
      // base64 格式
      const base64Data = props.modelValue.split(',')[1]
      content = atob(base64Data)
    } else {
      // 文本内容（URL 或纯文本）
      content = props.modelValue
    }

    const blob = new Blob([content], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = props.filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch (error) {
    console.error('[OfficeViewer] 下载失败:', error)
    ElMessage.error('文件下载失败')
    emit('error', error as Error)
  }
}

// 监听 modelValue 变化
watch(() => props.modelValue, (newValue) => {
  if (newValue) {
    processFileContent(newValue)
  }
}, { immediate: true })

onMounted(() => {
  if (props.modelValue) {
    processFileContent(props.modelValue)
  }
})
</script>

<style scoped>
.office-viewer {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background-color: var(--el-bg-color-page);
}

.office-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filename {
  font-size: 14px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.office-preview {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.excel-viewer,
.word-viewer,
.ppt-viewer {
  height: 100%;
  overflow: auto;
  padding: 0;
}

.excel-component,
.docx-component,
.pptx-component {
  width: 100%;
  height: 100%;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
  color: var(--el-text-color-secondary);
}

.office-fallback {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
  padding: 20px;
}

.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 300px;
  border: 2px dashed var(--el-border-color);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
}

.hint-text {
  margin-top: 20px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

/* 滚动条样式 */
.office-preview::-webkit-scrollbar,
.excel-viewer::-webkit-scrollbar,
.word-viewer::-webkit-scrollbar,
.ppt-viewer::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

.office-preview::-webkit-scrollbar-track,
.excel-viewer::-webkit-scrollbar-track,
.word-viewer::-webkit-scrollbar-track,
.ppt-viewer::-webkit-scrollbar-track {
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.office-preview::-webkit-scrollbar-thumb,
.excel-viewer::-webkit-scrollbar-thumb,
.word-viewer::-webkit-scrollbar-thumb,
.ppt-viewer::-webkit-scrollbar-thumb {
  background: var(--el-border-color-darker);
  border-radius: 6px;
  transition: background 0.3s;
}

.office-preview::-webkit-scrollbar-thumb:hover,
.excel-viewer::-webkit-scrollbar-thumb:hover,
.word-viewer::-webkit-scrollbar-thumb:hover,
.ppt-viewer::-webkit-scrollbar-thumb:hover {
  background: var(--el-border-color-dark);
}
</style>
