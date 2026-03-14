/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* Office 文件编辑器 - 基于 OnlyOffice WebSDK
* 支持本地编辑 DOCX、XLSX、PPTX 文件
* 使用完整的 X2T 转换逻辑
*/

<template>
  <div class="onlyoffice-editor" v-loading="loading" element-loading-text="加载编辑器...">
    <!-- OnlyOffice iframe 容器 -->
    <div id="onlyoffice-iframe-container" ref="containerRef"></div>

    <!-- 工具栏（可选） -->
    <div v-if="!loading && showToolbar" class="editor-toolbar">
      <el-button-group>
        <el-button size="small" @click="handleDownload" :icon="Download">
          下载副本
        </el-button>
        <el-button size="small" @click="handleSave" :loading="isSaving" type="success" :icon="Check">
          保存文件
        </el-button>
      </el-button-group>

      <div class="file-info">
        <el-tag :type="editable ? 'success' : 'info'">
          {{ editable ? '可编辑' : '只读' }}
        </el-tag>
        <span class="filename">{{ filename }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Check } from '@element-plus/icons-vue'
// @ts-ignore
import {
  initX2TScript,
  initX2T,
  convertDocument,
  convertBinToDocumentAndDownload,
  c_oAscFileType2
} from '@/utils/onlyoffice/x2t-full'
import { getDocumentType } from '@/utils/onlyoffice/util'

/**
 * 组件 Props
 */
interface Props {
  modelValue: string
  filename: string
  editable?: boolean
  showToolbar?: boolean
  workspaceId?: string
}

const props = withDefaults(defineProps<Props>(), {
  editable: true,
  showToolbar: false
})

/**
 * 组件 Emits
 */
interface Emits {
  'update:modelValue': [value: string]
  'save': [blob: Blob, filename: string]
  'error': [error: Error]
  'ready': []
}

const emit = defineEmits<Emits>()

/**
 * 状态管理
 */
const loading = ref(true)
const isSaving = ref(false)
const containerRef = ref<HTMLDivElement>()
let editorInstance: any = null

/**
 * 获取文件 MIME 类型
 */
function getMimeType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const mimeTypes: Record<string, string> = {
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'doc': 'application/msword',
    'odt': 'application/vnd.oasis.opendocument.text',
    'rtf': 'application/rtf',
    'txt': 'text/plain',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls': 'application/vnd.ms-excel',
    'ods': 'application/vnd.oasis.opendocument.spreadsheet',
    'csv': 'text/csv',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'ppt': 'application/vnd.ms-powerpoint',
    'odp': 'application/vnd.oasis.opendocument.presentation'
  }
  return mimeTypes[ext] || 'application/octet-stream'
}

/**
 * 将 modelValue 转换为 File 对象
 */
async function convertToFile(): Promise<File> {
  const { modelValue, filename } = props

  try {
    if (modelValue.startsWith('data:')) {
      const [mimeInfo, base64Data] = modelValue.split(',')
      const byteString = atob(base64Data)
      const bytes = new Uint8Array(byteString.length)

      for (let i = 0; i < byteString.length; i++) {
        bytes[i] = byteString.charCodeAt(i)
      }

      const mimeType = mimeInfo.match(/:(.*?);/)?.[1] || getMimeType(filename)
      const blob = new Blob([bytes], { type: mimeType })
      return new File([blob], filename, { type: mimeType })
    } else if (modelValue.startsWith('http://') || modelValue.startsWith('https://')) {
      const response = await fetch(modelValue)
      if (!response.ok) {
        throw new Error(`无法获取文件: ${response.statusText}`)
      }
      const blob = await response.blob()
      return new File([blob], filename, { type: blob.type })
    } else {
      throw new Error('不支持的文件格式')
    }
  } catch (error) {
    console.error('[OnlyOfficeEditor] 文件转换失败:', error)
    throw error
  }
}

/**
 * 加载 OnlyOffice API 脚本
 */
function loadEditorAPI(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.DocsAPI) {
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = '/onlyoffice/web-apps/apps/api/documents/api.js'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('无法加载 OnlyOffice API'))
    document.head.appendChild(script)
  })
}

/**
 * 初始化编辑器
 */
async function initEditor(): Promise<void> {
  try {
    loading.value = true

    // 1. 加载依赖
    await initX2TScript()
    await initX2T()

    await loadEditorAPI()

    // 2. 转换文件
    const file = await convertToFile()

    // 3. 使用 X2T 转换文档
    const documentData = await convertDocument(file)

    // 4. 创建编辑器实例
    await createEditorInstance(file, documentData.bin)

  } catch (error) {
    console.error('[OnlyOfficeEditor] 初始化失败:', error)
    emit('error', error as Error)
    ElMessage.error(`编辑器加载失败: ${(error as Error).message}`)
    loading.value = false
  }
}

/**
 * 创建编辑器实例
 */
async function createEditorInstance(file: File, binData: ArrayBuffer): Promise<void> {
  const fileType = file.name.split('.').pop()?.toLowerCase() || ''
  const docType = getDocumentType(fileType)

  if (!docType) {
    throw new Error(`不支持的文件类型: ${fileType}`)
  }

  // 销毁旧实例
  if (editorInstance && typeof editorInstance.destroyEditor === 'function') {
    editorInstance.destroyEditor()
    editorInstance = null
  }

  // 创建编辑器实例
  editorInstance = new window.DocsAPI.DocEditor('onlyoffice-iframe-container', {
    document: {
      title: file.name,
      url: file.name,
      fileType: fileType,
      permissions: {
        edit: props.editable,
        chat: false,
        protect: false,
        download: true,
        print: true,
      },
    },
    editorConfig: {
      lang: 'zh',
      mode: props.editable ? 'edit' : 'view',
      customization: {
        help: false,
        about: false,
        hideRightMenu: true,
        features: {
          spellcheck: {
            change: false,
          },
        },
        anonymous: {
          request: false,
          label: 'Guest',
        },
      },
    },
    events: {
      onAppReady: () => {
        emit('ready')

        // 手动加载文档内容
        if (editorInstance && editorInstance.sendCommand) {
          editorInstance.sendCommand({
            command: 'asc_openDocument',
            data: { buf: binData },
          })
        }
      },
      onDocumentReady: () => {
        loading.value = false
      },
      onSave: handleSaveEvent,
      onError: handleEditorError,
    },
  })
}

/**
 * 处理编辑器保存事件
 */
async function handleSaveEvent(event: any): Promise<void> {
  try {
    if (event.data && event.data.data) {
      const { data, option } = event.data

      // 转换并下载
      await convertBinToDocumentAndDownload(
        data.data,
        props.filename,
        c_oAscFileType2[option.outputformat]
      )

      // 告知编辑器保存完成
      if (editorInstance && editorInstance.sendCommand) {
        editorInstance.sendCommand({
          command: 'asc_onSaveCallback',
          data: { err_code: 0 },
        })
      }

      ElMessage.success('文档已保存')
    }
  } catch (error) {
    console.error('[OnlyOfficeEditor] 保存失败:', error)
    emit('error', error as Error)

    if (editorInstance && editorInstance.sendCommand) {
      editorInstance.sendCommand({
        command: 'asc_onSaveCallback',
        data: { err_code: 1 },
      })
    }

    ElMessage.error(`保存失败: ${(error as Error).message}`)
  }
}

/**
 * 处理编辑器错误
 */
function handleEditorError(event: any): void {
  console.error('[OnlyOfficeEditor] 编辑器错误:', event)
  const error = new Error(event?.data?.message || '编辑器发生未知错误')
  emit('error', error)
  ElMessage.error(error.message)
}

/**
 * 手动保存
 */
async function handleSave(): Promise<void> {
  ElMessage.info('请使用编辑器内的保存功能')
}

/**
 * 下载文件副本
 */
async function handleDownload(): Promise<void> {
  try {
    const blob = await currentFileToBlob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = props.filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch (error) {
    console.error('[OnlyOfficeEditor] 下载失败:', error)
    ElMessage.error('下载失败')
  }
}

/**
 * 将当前文件转换为 Blob
 */
async function currentFileToBlob(): Promise<Blob> {
  const file = await convertToFile()
  return file
}

/**
 * 监听文件变化
 */
watch(() => props.modelValue, () => {
  if (props.modelValue && editorInstance) {
    initEditor()
  }
})

/**
 * 组件挂载
 */
onMounted(() => {
  if (props.modelValue) {
    initEditor()
  }
})

/**
 * 组件卸载
 */
onBeforeUnmount(() => {
  if (editorInstance && typeof editorInstance.destroyEditor === 'function') {
    editorInstance.destroyEditor()
    editorInstance = null
  }
})
</script>

<style scoped>
.onlyoffice-editor {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color-page);
  position: relative;
}

#onlyoffice-iframe-container {
  flex: 1;
  overflow: hidden;
  width: 100%;
  height: 100%;
}

.editor-toolbar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: var(--el-bg-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  z-index: 10;
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

#onlyoffice-iframe-container :deep(iframe) {
  width: 100% !important;
  height: 100% !important;
  border: none;
}
</style>
