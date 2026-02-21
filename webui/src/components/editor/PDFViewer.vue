/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="pdf-viewer-container">
    <!-- 工具栏 -->
    <div class="pdf-toolbar">
      <div class="toolbar-left">
        <el-button-group>
          <el-button size="small" :disabled="currentPage <= 1" @click="prevPage">
            <el-icon>
              <ArrowLeft />
            </el-icon>
            上一页
          </el-button>
          <el-button size="small" :disabled="currentPage >= numPages" @click="nextPage">
            下一页
            <el-icon>
              <ArrowRight />
            </el-icon>
          </el-button>
        </el-button-group>

        <div class="page-info">
          <span class="page-text">{{ currentPage }} / {{ numPages || '--' }}</span>
        </div>
      </div>

      <div class="toolbar-center">
        <el-button-group>
          <el-tooltip content="缩小" placement="top">
            <el-button size="small" :icon="ZoomOut" @click="zoomOut" />
          </el-tooltip>
          <el-button size="small" disabled>
            {{ Math.round(scale * 100) }}%
          </el-button>
          <el-tooltip content="放大" placement="top">
            <el-button size="small" :icon="ZoomIn" @click="zoomIn" />
          </el-tooltip>
        </el-button-group>

        <el-button-group style="margin-left: 8px;">
          <el-tooltip content="适应宽度" placement="top">
            <el-button size="small" @click="fitWidth">适应宽度</el-button>
          </el-tooltip>
          <el-tooltip content="适应页面" placement="top">
            <el-button size="small" @click="fitPage">适应页面</el-button>
          </el-tooltip>
        </el-button-group>
      </div>

      <div class="toolbar-right">
        <el-button-group>
          <el-tooltip content="下载" placement="top">
            <el-button size="small" :icon="Download" @click="downloadPDF" />
          </el-tooltip>
        </el-button-group>
      </div>
    </div>

    <!-- PDF 显示区域 - 使用浏览器原生 PDF 查看器 -->
    <div class="pdf-content">
      <iframe v-if="src && !error" :src="iframeSrc" class="pdf-iframe" type="application/pdf" frameborder="0"></iframe>

      <!-- 错误提示 -->
      <el-empty v-if="error" description="PDF 加载失败" :image-size="100">
        <el-button type="primary" @click="reloadPDF">重新加载</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  ArrowRight,
  ZoomOut,
  ZoomIn,
  Download
} from '@element-plus/icons-vue'

interface Props {
  modelValue: string // PDF 文件的 URL 或 base64
  filename?: string // 文件名（可选，用于类型检测）
}

const props = defineProps<Props>()

// PDF 状态
const error = ref(false)
const currentPage = ref(1)
const numPages = ref(0)
const scale = ref(1.0)

// PDF 源
const src = ref<string | null>(null)

// 计算属性：iframe src（支持翻页、缩放）
const iframeSrc = computed(() => {
  if (!src.value) return ''

  // 如果是 blob URL 或以 http 开头，直接使用
  if (src.value.startsWith('blob:') || src.value.startsWith('http')) {
    // 添加 #page={page}&zoom={scale} 参数控制初始视图
    return `${src.value}#page=${currentPage.value}&zoom=${Math.round(scale.value * 100)}`
  }

  // 如果是 base64，转换为 data URL
  if (src.value.startsWith('data:application/pdf')) {
    return `${src.value}#page=${currentPage.value}&zoom=${Math.round(scale.value * 100)}`
  }

  return src.value
})

// 加载 PDF
const loadPDF = async () => {
  // 检查是否有内容
  if (!props.modelValue || props.modelValue.trim() === '') {
    error.value = false
    src.value = null
    return
  }

  error.value = false
  currentPage.value = 1

  // 安全检查：通过文件名检测HTML文件
  if (props.filename && (
    props.filename.toLowerCase().endsWith('.html') ||
    props.filename.toLowerCase().endsWith('.htm') ||
    props.filename.toLowerCase().endsWith('.xhtml')
  )) {
    console.error('[PDFViewer] ERROR: HTML file detected by filename:', props.filename)
    error.value = true
    ElMessage.error(`检测到HTML文件 (${props.filename})，请使用HTML查看器打开`)
    src.value = null
    return
  }

  try {
    // 安全检查：拒绝加载HTML内容
    if (props.modelValue && (
      props.modelValue.trim().startsWith('<!DOCTYPE html>') ||
      props.modelValue.trim().startsWith('<html') ||
      props.modelValue.includes('<html') ||
      props.modelValue.includes('<body')
    )) {
      console.error('[PDFViewer] ERROR: HTML content detected, refusing to load as PDF')
      error.value = true
      ElMessage.error('检测到HTML内容，请使用HTML查看器打开')
      src.value = null
      return
    }

    // 直接使用 PDF 源（浏览器原生查看器会处理）
    src.value = props.modelValue
    console.log('[PDFViewer] PDF source set successfully:', src.value?.substring(0, 50))

  } catch (err: unknown) {
    console.error('[PDFViewer] Load error:', err)
    error.value = true
    ElMessage.error('PDF 加载失败')
  }
}

// 翻页（更新 iframe src 的 page 参数）
const prevPage = () => {
  if (currentPage.value > 1) {
    currentPage.value--
  }
}

const nextPage = () => {
  if (numPages.value && currentPage.value < numPages.value) {
    currentPage.value++
  }
}

// 缩放（更新 iframe src 的 zoom 参数）
const zoomIn = () => {
  scale.value = Math.min(scale.value + 0.25, 3.0)
}

const zoomOut = () => {
  scale.value = Math.max(scale.value - 0.25, 0.25)
}

const fitWidth = () => {
  scale.value = 1.0
}

const fitPage = () => {
  scale.value = 1.0
}

// 下载 PDF
const downloadPDF = () => {
  const link = document.createElement('a')
  link.href = props.modelValue
  link.download = props.filename || 'document.pdf'
  link.click()
  ElMessage.success('开始下载')
}

// 重新加载
const reloadPDF = () => {
  loadPDF()
}

// 监听 props 变化
watch(() => props.modelValue, () => {
  loadPDF()
}, { immediate: true })
</script>

<style scoped>
.pdf-viewer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--el-bg-color-page);
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-light);
  gap: 16px;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
}

.page-text {
  color: var(--el-text-color-regular);
  font-weight: 500;
  font-size: 14px;
}

.pdf-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  justify-content: center;
  padding: 0;
  background-color: #525659;
  /* 经典 PDF 阅读器背景色 */
  position: relative;
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}

/* 滚动条样式 */
.pdf-content::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

.pdf-content::-webkit-scrollbar-track {
  background: #4a4a4a;
}

.pdf-content::-webkit-scrollbar-thumb {
  background: #6b6b6b;
  border-radius: 6px;
}

.pdf-content::-webkit-scrollbar-thumb:hover {
  background: #7b7b7b;
}
</style>
