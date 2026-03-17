/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*
* Office 文件预览组件 - 基于 vue-office
* 支持 DOCX 和 Excel 文件预览（只读）
*
* 技术实现：
* - 使用 @vue-office/docx 预览 Word 文档
* - 使用 @vue-office/excel 预览 Excel 表格
* - 不支持 PPTX（按照要求）
*/

<template>
  <div class="vue-office-editor" v-loading="loading" element-loading-text="加载文档...">
    <!-- DOCX 预览 -->
    <vue-office-docx
      v-if="fileType === 'docx'"
      :src="documentSrc"
      class="office-preview"
      @rendered="handleRendered"
      @error="handleError"
    />

    <!-- Excel 预览 -->
    <vue-office-excel
      v-else-if="fileType === 'excel'"
      :src="documentSrc"
      :options="excelOptions"
      class="office-preview"
      @rendered="handleRendered"
      @error="handleError"
    />

    <!-- 错误提示 -->
    <div v-if="error" class="error-message">
      <el-alert
        :title="`文档加载失败: ${error}`"
        type="error"
        :closable="false"
        show-icon
      >
        <template #default>
          <p>{{ error }}</p>
          <p class="error-suggestion">建议：检查文件格式是否正确（支持 .docx, .xlsx）</p>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElAlert } from 'element-plus'
// @ts-ignore
import VueOfficeDocx from '@vue-office/docx'
// @ts-ignore
import VueOfficeExcel from '@vue-office/excel'
import '@/assets/vue-office/docx.css'
import '@/assets/vue-office/excel.css'

/**
 * 组件 Props
 */
interface Props {
  modelValue: string
  filename: string
  editable?: boolean  // 保持接口兼容，但组件不支持编辑
  workspaceId?: string
}

const props = withDefaults(defineProps<Props>(), {
  editable: false  // vue-office 只支持预览
})

/**
 * 组件 Emits
 */
interface Emits {
  'update:modelValue': [value: string]
  'error': [error: Error]
  'ready': []
}

const emit = defineEmits<Emits>()

/**
 * 状态管理
 */
const loading = ref(true)
const error = ref<string | null>(null)
const documentSrc = ref<string | ArrayBuffer | null>(null)

/**
 * Excel 配置选项
 */
const excelOptions = {
  xls: false,          // 预览 xlsx 文件设为 false
  minColLength: 0,     // 最少渲染列数
  minRowLength: 0,     // 最少渲染行数
  widthOffset: 10,     // 列宽度偏移
  heightOffset: 10,    // 行高度偏移
}

/**
 * 获取文件类型
 */
const fileType = computed(() => {
  const ext = props.filename.split('.').pop()?.toLowerCase() || ''
  const docxExts = ['docx', 'doc']
  const excelExts = ['xlsx', 'xls', 'csv']

  if (docxExts.includes(ext)) {
    return 'docx'
  } else if (excelExts.includes(ext)) {
    return 'excel'
  }
  return null
})

/**
 * 检测字符串是否为 base64 编码
 */
function isBase64(str: string): boolean {
  if (typeof str !== 'string') return false

  const trimmed = str.trim()
  if (trimmed.length % 4 !== 0) return false

  const base64Regex = /^[A-Za-z0-9+/]*={0,2}$/
  if (!base64Regex.test(trimmed)) return false

  try {
    atob(trimmed)
    return true
  } catch {
    return false
  }
}

/**
 * 将 modelValue 转换为文档数据源
 * 支持多种格式：data URI, URL, base64, 文件路径
 */
async function loadDocumentSource(): Promise<void> {
  const { modelValue, filename } = props

  try {
    loading.value = true
    error.value = null

    // 情况 1: data URI (base64 with prefix)
    if (modelValue && modelValue.startsWith('data:')) {
      documentSrc.value = modelValue
      loading.value = false
      return
    }

    // 情况 2: HTTP(S) URL
    else if (modelValue && (modelValue.startsWith('http://') || modelValue.startsWith('https://'))) {
      documentSrc.value = modelValue
      loading.value = false
      return
    }

    // 情况 3: 纯 base64 字符串（不带前缀）
    else if (modelValue && isBase64(modelValue)) {
      const ext = filename.split('.').pop()?.toLowerCase() || ''
      const mimeTypes: Record<string, string> = {
        docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        xls: 'application/vnd.ms-excel',
        csv: 'text/csv',
      }
      const mimeType = mimeTypes[ext] || 'application/octet-stream'
      documentSrc.value = `data:${mimeType};base64,${modelValue}`
      loading.value = false
      return
    }

    // 情况 4: 相对或绝对文件路径（通过 API 加载）
    else if (modelValue && (modelValue.startsWith('/') || modelValue.startsWith('./') || modelValue.startsWith('../'))) {
      const response = await fetch(modelValue)
      if (!response.ok) {
        throw new Error(`无法获取文件: ${response.statusText}`)
      }

      const blob = await response.blob()
      documentSrc.value = blob
      loading.value = false
      return
    }

    // 情况 5: 空字符串 - 通过 workspace API 加载
    else if (!modelValue || modelValue === '') {
      if (props.workspaceId) {
        const filePath = encodeURIComponent(filename)
        const apiUrl = `/api/workspaces/${props.workspaceId}/files?path=${filePath}`

        const response = await fetch(apiUrl)
        if (!response.ok) {
          throw new Error(`无法加载文件: ${response.statusText}`)
        }

        const blob = await response.blob()
        documentSrc.value = blob
        loading.value = false
        return
      } else {
        throw new Error('文件内容为空且未提供 workspaceId，无法加载文件')
      }
    }

    else {
      throw new Error(`不支持的文件格式: ${typeof modelValue}`)
    }
  } catch (err) {
    console.error('[VueOfficeEditor] 文件加载失败:', err)
    const errorMessage = err instanceof Error ? err.message : '未知错误'
    error.value = errorMessage
    emit('error', err instanceof Error ? err : new Error(errorMessage))
    loading.value = false
  }
}

/**
 * 文档渲染完成回调
 */
function handleRendered() {
  loading.value = false
  emit('ready')
}

/**
 * 文档渲染错误回调
 */
function handleError(err: any) {
  console.error('[VueOfficeEditor] 文档渲染失败:', err)
  const errorMessage = err?.message || err?.toString() || '渲染失败'
  error.value = errorMessage
  emit('error', new Error(errorMessage))
  loading.value = false
}

/**
 * 监听文件变化
 */
watch(() => props.modelValue, (newValue, oldValue) => {
  if (newValue && newValue !== oldValue) {
    loadDocumentSource()
  }
})

/**
 * 监听文件名变化
 */
watch(() => props.filename, (newName, oldName) => {
  if (newName && newName !== oldName) {
    documentSrc.value = null
    loadDocumentSource()
  }
})

/**
 * 组件挂载
 */
onMounted(() => {
  // 检查文件类型
  if (!fileType.value) {
    console.warn('[VueOfficeEditor] 不支持的文件格式:', props.filename)
    error.value = `不支持的文件格式: ${props.filename}（仅支持 .docx, .xlsx）`
    loading.value = false
    return
  }

  // 加载文档
  if (props.modelValue || props.workspaceId) {
    loadDocumentSource()
  } else {
    loading.value = false
  }
})

/**
 * 组件卸载
 */
onBeforeUnmount(() => {
  documentSrc.value = null
  error.value = null
})
</script>

<style scoped>
.vue-office-editor {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color-page);
  position: relative;
}

.office-preview {
  flex: 1;
  overflow: auto;
  width: 100%;
  height: 100%;
}

.error-message {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  max-width: 600px;
  width: 90%;
  z-index: 100;
}

.error-suggestion {
  margin-top: 12px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

/* 深色主题适配 */
@media (prefers-color-scheme: dark) {
  .office-preview {
    background-color: #1e1e1e;
  }
}
</style>
