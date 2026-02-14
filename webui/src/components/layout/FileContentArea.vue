/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="file-content-area">
    <el-tabs
      v-if="hasFiles"
      :model-value="activeFileId || ''"
      type="card"
      class="file-tabs"
      closable
      @tab-remove="closeFile"
      @tab-change="handleTabChange"
    >
      <el-tab-pane
        v-for="file in files"
        :key="file.id"
        :label="file.name"
        :name="file.id"
      >
        <template #label>
          <span class="tab-label">
            <el-icon>
              <Document v-if="isGenericFile(file) || isPDFFile(file) || isHTMLFile(file)" />
              <Picture v-else-if="isImageFile(file)" />
              <VideoPlay v-else-if="isVideoFile(file)" />
              <Headset v-else-if="isAudioFile(file)" />
              <Document v-else />
            </el-icon>
            {{ file.name }}
            <span v-if="file.isDirty" class="dirty-indicator">●</span>
          </span>
        </template>
      </el-tab-pane>
    </el-tabs>

    <el-card class="content-card" shadow="never" v-loading="isLoading">
      <div v-if="activeFile" class="active-file-content">
        <!-- HTML 文件的标签页 -->
        <el-tabs v-if="isHTMLFile(activeFile)" v-model="htmlActiveTab" type="border-card" class="html-editor-tabs">
          <el-tab-pane name="preview">
            <template #label>
              <span>预览</span>
            </template>
            <div class="html-preview-wrapper">
              <HTMLViewer
                :model-value="activeFile.content"
                :filename="activeFile.name"
                class="html-viewer-wrapper"
              />
            </div>
          </el-tab-pane>
          <el-tab-pane name="edit">
            <template #label>
              <span>编辑</span>
            </template>
            <div class="html-edit-wrapper">
              <NativeCodeMirror
                v-model="editableContent"
                :file-path="activeFile.name"
                :theme="editorTheme"
                :line-numbers="true"
                :bracket-matching="true"
                :close-brackets="true"
                :search="true"
                language="html"
                class="code-editor-wrapper"
                @change="handleContentChange"
              />
            </div>
          </el-tab-pane>
        </el-tabs>

        <!-- HTML 编辑模式下的保存按钮 -->
        <div v-if="isHTMLFile(activeFile) && htmlActiveTab === 'edit'" class="floating-save-button">
          <el-button
            @click="handleSave"
            :loading="isSaving"
            type="success"
            size="small"
          >
            保存
          </el-button>
        </div>

        <!-- Markdown 文件的保存按钮 -->
        <div v-if="isMarkdownFile(activeFile)" class="toolbar-simple">
          <el-button
            @click="handleSave"
            :loading="isSaving"
            :disabled="!isContentModified"
            type="success"
            size="small"
          >
            保存
          </el-button>
        </div>

        <!-- 其他文件类型的保存按钮 -->
        <div v-if="!isHTMLFile(activeFile) && !isMarkdownFile(activeFile) && (isTextFile(activeFile) || isCodeFile(activeFile))" class="toolbar-simple">
          <el-button
            @click="handleSave"
            :loading="isSaving"
            type="success"
            size="small"
          >
            保存
          </el-button>
        </div>

        <div v-show="isMarkdownFile(activeFile)" ref="vditorRef" class="editor-container"></div>
        <ImageViewer
          v-if="imageFiles.length > 0"
          :images="allImageFiles"
          :initial-index="currentImageIndex"
          :visible="imageViewerVisible"
          @update:visible="imageViewerVisible = $event"
        />
        <div v-show="isImageFile(activeFile)" class="image-preview-container">
          <el-image
            :src="activeFile.content"
            :alt="activeFile.name"
            fit="contain"
            class="image-preview"
            style="cursor: pointer;"
            @click="openImageViewer"
          />
          <div class="open-viewer-overlay" @click="openImageViewer">
            <el-icon :size="16"><ZoomIn /></el-icon>
            <span>打开查看器</span>
            <span v-if="allImageFiles.length > 1" class="image-hint">
              ({{ currentImageIndex + 1 }} / {{ allImageFiles.length }})
            </span>
          </div>
        </div>
        <video
          v-show="isVideoFile(activeFile)"
          :src="activeFile.content"
          controls
          class="media-preview"
        >
          您的浏览器不支持视频播放。
        </video>
        <audio
          v-show="isAudioFile(activeFile)"
          :src="activeFile.content"
          controls
          class="media-preview"
        >
          您的浏览器不支持音频播放。
        </audio>
        <NativeCodeMirror
          v-show="isCodeFile(activeFile) && !isHTMLFile(activeFile)"
          v-model="editableContent"
          :file-path="activeFile.name"
          :theme="editorTheme"
          :line-numbers="true"
          :bracket-matching="true"
          :close-brackets="true"
          :search="true"
          class="code-editor-wrapper"
          @change="handleContentChange"
        />
        <CSVEditor
          v-show="isCSVFile(activeFile)"
          v-model="editableContent"
          class="csv-editor-wrapper"
          @change="handleContentChange"
        />
        <PDFViewer
          v-if="activeFile && isPDFFile(activeFile)"
          v-model="activeFile.content"
          :filename="activeFile.name"
          class="pdf-viewer-wrapper"
        />
        <el-input
          v-show="isTextFile(activeFile)"
          v-model="editableContent"
          type="textarea"
          class="text-editor"
          :autosize="{ minRows: 10 }"
          @input="handleContentChange"
        />
        <pre v-show="!isMarkdownFile(activeFile) && !isCodeFile(activeFile) && !isImageFile(activeFile) && !isVideoFile(activeFile) && !isAudioFile(activeFile) && !isCSVFile(activeFile) && !isPDFFile(activeFile) && !isHTMLFile(activeFile) && !isTextFile(activeFile)" class="readonly-content"><code>{{ activeFile.content }}</code></pre>
      </div>
      <el-empty v-else description="没有打开的文件" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import Vditor from 'vditor'
import 'vditor/dist/index.css'
import { useThemeStore } from '@/stores/theme'
import { ElTabs, ElTabPane, ElCard, ElButton, ElIcon, ElImage, ElInput, ElEmpty } from 'element-plus'
// ElTabs 和 ElTabPane 已经在上面导入了
import { Document, VideoPlay, Headset, Picture, ZoomIn } from '@element-plus/icons-vue'
// View 和 Edit 图标用于 Markdown 文件的编辑器切换
import NativeCodeMirror from '@/components/editor/NativeCodeMirror.vue'
import CSVEditor from '@/components/editor/CSVEditor.vue'
import ImageViewer from '@/components/chat/ImageViewer.vue'
import PDFViewer from '@/components/editor/PDFViewer.vue'
import HTMLViewer from '@/components/editor/HTMLViewer.vue'

interface File {
  id: string
  name: string
  type: string
  content: string
  isDirty?: boolean
}

interface Props {
  files: File[]
  activeFileId: string | null
}

interface Emits {
  (e: 'close-file', fileId: string): void
  (e: 'update:activeFileId', fileId: string | null): void
  (e: 'save-file', fileId: string, content: string): void
  (e: 'update-file-content', fileId: string, content: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const themeStore = useThemeStore()
const htmlActiveTab = ref('preview')
const isSaving = ref(false)
const isLoading = ref(false)
const editableContent = ref('')
const vditorRef = ref<HTMLDivElement | null>(null)
const vditor = ref<Vditor | null>(null)
const vditorInitialized = ref(false)

// Image viewer state
const imageViewerVisible = ref(false)

// 内容是否被修改
const isContentModified = computed(() => {
  if (!activeFile.value) return false
  return editableContent.value !== activeFile.value.content
})

// Computed properties
const hasFiles = computed(() => props.files.length > 0)
const activeFile = computed(() => props.files.find(f => f.id === props.activeFileId) || null)
const editorTheme = computed(() => (themeStore.theme === 'dark' ? 'one-dark' : 'light'))

// 调试：显示当前文件类型检测结果
const fileTypeDebug = computed(() => {
  if (!activeFile.value) return 'No file'
  return {
    name: activeFile.value.name,
    type: activeFile.value.type,
    isMarkdown: isMarkdownFile(activeFile.value),
    isHTML: isHTMLFile(activeFile.value),
    isPDF: isPDFFile(activeFile.value),
    isCode: isCodeFile(activeFile.value),
    isCSV: isCSVFile(activeFile.value),
    isImage: isImageFile(activeFile.value),
    isVideo: isVideoFile(activeFile.value),
    isAudio: isAudioFile(activeFile.value),
    isText: isTextFile(activeFile.value),
    viewer: getViewerType(activeFile.value)
  }
})

function getViewerType(file: File): string {
  if (isMarkdownFile(file)) return 'Vditor'
  if (isHTMLFile(file)) return htmlActiveTab.value === 'edit' ? 'CodeMirror (HTML)' : 'HTMLViewer'
  if (isPDFFile(file)) return 'PDFViewer'
  if (isCodeFile(file)) return 'CodeMirror'
  if (isCSVFile(file)) return 'CSVEditor'
  if (isImageFile(file)) return 'Image'
  if (isVideoFile(file)) return 'Video'
  if (isAudioFile(file)) return 'Audio'
  if (isTextFile(file)) return 'Textarea'
  return 'Readonly'
}

// Image files for navigation
const allImageFiles = computed(() => {
  return props.files
    .filter(file => isImageFile(file))
    .map(file => ({
      src: file.content,
      filename: file.name
    }))
})

const currentImageIndex = computed(() => {
  if (!activeFile.value || !isImageFile(activeFile.value)) return 0
  return allImageFiles.value.findIndex(img => img.src === activeFile.value?.content)
})

const imageFiles = computed(() => allImageFiles.value)

// File type detection utilities
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg', 'ico']
const VIDEO_EXTENSIONS = ['mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv', 'flv']
const AUDIO_EXTENSIONS = ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg']
const CODE_EXTENSIONS = ['js', 'ts', 'jsx', 'tsx', 'py', 'vue', 'html', 'css', 'json', 'yaml', 'yml', 'sql', 'sh', 'xml']
const TEXT_EXTENSIONS = ['txt', 'text']

function isMarkdownFile(file: File): boolean {
  return file.type === 'markdown' || file.name.endsWith('.md')
}

function isImageFile(file: File): boolean {
  return file.type === 'image' || IMAGE_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isVideoFile(file: File): boolean {
  return file.type === 'video' || VIDEO_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isAudioFile(file: File): boolean {
  return file.type === 'audio' || AUDIO_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isCodeFile(file: File): boolean {
  return file.type === 'code' || CODE_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isCSVFile(file: File): boolean {
  return file.name.endsWith('.csv') || file.type === 'csv'
}

function isTextFile(file: File): boolean {
  return file.type === 'text' || TEXT_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isPDFFile(file: File): boolean {
  const isPDF = file.name.endsWith('.pdf') || file.type === 'pdf' || file.type === 'application/pdf'
  if (isPDF && (file.name.endsWith('.html') || file.name.endsWith('.htm'))) {
    console.warn('[FileContentArea] File detected as both PDF and HTML:', file.name, file.type)
  }
  return isPDF
}

function isHTMLFile(file: File): boolean {
  const isHTML = file.name.endsWith('.html') || file.name.endsWith('.htm') || file.type === 'html' || file.type === 'text/html' || file.type === 'application/xhtml+xml'
  return isHTML
}

function isGenericFile(file: File): boolean {
  return !isMarkdownFile(file) && !isCodeFile(file) && !isImageFile(file) && !isVideoFile(file) && !isAudioFile(file) && !isCSVFile(file) && !isPDFFile(file) && !isHTMLFile(file)
}

// Event handlers
const handleTabChange = (fileId: string | number) => {
  emit('update:activeFileId', fileId as string)
}

const closeFile = (fileId: string | number) => {
  emit('close-file', fileId as string)
}

const openImageViewer = () => {
  imageViewerVisible.value = true
}

const handleContentChange = () => {
  if (activeFile.value) {
    emit('update-file-content', activeFile.value.id, editableContent.value)
  }
}

const handleSave = async () => {
  if (!activeFile.value) return

  isSaving.value = true
  try {
    let contentToSave = editableContent.value
    if (isMarkdownFile(activeFile.value) && vditor.value) {
      contentToSave = vditor.value.getValue()
    }
    await emit('save-file', activeFile.value.id, contentToSave)

    // 保存后对于 Markdown 文件，等待父组件更新 content
    if (isMarkdownFile(activeFile.value)) {
      await nextTick()
    } else if (isHTMLFile(activeFile.value)) {
      // HTML文件切换到预览标签页
      await nextTick()
      htmlActiveTab.value = 'preview'
    }
  } finally {
    isSaving.value = false
  }
}

// Vditor initialization
const initVditor = () => {
  if (!vditorRef.value || !activeFile.value || !isMarkdownFile(activeFile.value)) {
    return
  }

  // 如果已经初始化过，只更新值
  if (vditorInitialized.value && vditor.value) {
    const currentValue = vditor.value.getValue()
    if (currentValue !== editableContent.value) {
      vditor.value.setValue(editableContent.value)
    }
    return
  }

  // 首次初始化
  const startTime = performance.now()

  vditor.value = new Vditor(vditorRef.value, {
    theme: themeStore.theme === 'dark' ? 'dark' : 'classic',
    mode: 'wysiwyg',
    height: '100%',
    value: editableContent.value,
    cache: { enable: false },
    placeholder: '请输入 Markdown 内容...',
    toolbar: [
      'headings',
      'bold',
      'italic',
      'strike',
      '|',
      'list',
      'ordered-list',
      'check',
      '|',
      'quote',
      'code',
      'inline-code',
      'link',
      '|',
      'table',
      '|',
      'undo',
      'redo',
      '|',
      'preview',
      'fullscreen',
    ],
    input: (value: string) => {
      editableContent.value = value
      handleContentChange()
    },
    after: () => {
      vditorInitialized.value = true
    },
  })
}

// Watchers
watch(() => themeStore.theme, (newTheme) => {
  vditor.value?.setTheme(newTheme === 'dark' ? 'dark' : 'classic')
})


watch(activeFile, (newFile, oldFile) => {
  if (!newFile) return

  // 更新编辑内容
  editableContent.value = newFile.content

  // 如果是HTML文件，重置tab状态
  if (isHTMLFile(newFile)) {
    htmlActiveTab.value = 'preview'
  }

  // 只在切换到Markdown文件时初始化/更新Vditor
  if (isMarkdownFile(newFile)) {
    if (!vditorInitialized.value) {
      // 首次打开Markdown文件，初始化Vditor
      nextTick(initVditor)
    } else if (oldFile && oldFile.id !== newFile.id) {
      // 切换到不同的Markdown文件，更新内容
      nextTick(() => {
        if (vditor.value) {
          vditor.value.setValue(newFile.content)
        }
      })
    }
  }
}, { immediate: false })

// 监听 activeFile.content 变化，同步到 editableContent
watch(() => activeFile.value?.content, (newContent) => {
  if (newContent !== undefined && newContent !== editableContent.value) {
    editableContent.value = newContent
  }
}, { immediate: true })

onUnmounted(() => {
  vditor.value?.destroy()
})
</script>

<style scoped>
.file-content-area {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--el-bg-color-page);
}

.file-tabs {
  flex-shrink: 0;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dirty-indicator {
  color: var(--el-color-primary);
  font-size: 14px;
}

.content-card {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.content-card :deep(.el-card__body) {
  height: 100%;
  padding: 0;
}

.active-file-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.toolbar {
  padding: 8px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: var(--el-bg-color);
}

.toolbar-simple {
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: var(--el-bg-color);
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
}

.editor-tabs-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background-color: var(--el-bg-color);
  flex-shrink: 0;
}

.editor-mode-switch {
  display: flex;
  align-items: center;
}

.editor-mode-switch .el-radio-button {
  display: flex;
  align-items: center;
  gap: 4px;
}

.editor-mode-switch .el-icon {
  font-size: 14px;
}

.save-button {
  margin-left: 16px;
}

.editor-container {
  flex-grow: 1;
  overflow: auto;
  min-height: 0;
}

/* Vditor 内部样式修复 */
.editor-container :deep(.vditor) {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.editor-container :deep(.vditor-toolbar) {
  flex-shrink: 0;
}

.editor-container :deep(.vditor-content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

/* 预览模式下隐藏编辑器相关内容 */
.editor-container :deep(.vditor-preview) {
  padding: 0;
  margin: 0;
}

.editor-container :deep(.vditor-preview__element) {
  padding: 8px 16px;
}

.editor-container :deep(.vditor-reset) {
  padding: 8px 16px;
  margin: 0;
}

.image-preview,
.media-preview,
.text-editor,
.readonly-content,
.code-editor-wrapper,
.csv-editor-wrapper,
.pdf-viewer-wrapper,
.html-viewer-wrapper {
  flex-grow: 1;
  overflow: auto;
  min-height: 0;
}

/* 隐藏时不占用空间 */
.editor-container:not([style*="display: none"]) {
  display: flex;
}

.image-preview:not([style*="display: none"]),
.media-preview:not([style*="display: none"]),
.code-editor-wrapper:not([style*="display: none"]),
.csv-editor-wrapper:not([style*="display: none"]),
.pdf-viewer-wrapper:not([style*="display: none"]),
.html-viewer-wrapper:not([style*="display: none"]),
.text-editor:not([style*="display: none"]) {
  display: flex;
}

/* v-show隐藏的元素 */
[style*="display: none"] {
  display: none !important;
}

.image-preview {
  padding: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.image-preview-container {
  padding: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  flex-grow: 1;
  overflow: auto;
}

.image-preview-container .image-preview {
  padding: 0;
}

.open-viewer-overlay {
  position: absolute;
  top: 16px;
  right: 16px;
  transform: none;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: rgba(0, 0, 0, 0.75);
  color: white;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 10;
}

.image-preview-container:hover .open-viewer-overlay {
  opacity: 1;
}

.open-viewer-overlay:hover {
  background-color: rgba(0, 0, 0, 0.85);
  transform: scale(1.05);
}

.open-viewer-overlay span {
  font-size: 12px;
  font-weight: 500;
}

.open-viewer-overlay .el-icon {
  font-size: 16px;
}

.image-hint {
  font-size: 11px;
  opacity: 0.8;
  margin-left: 4px;
}

.media-preview {
  width: 100%;
  max-height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 16px;
}

.media-preview video,
.media-preview audio {
  max-width: 100%;
  max-height: 80vh;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.code-editor-wrapper {
  height: 100%;
  min-height: 400px;
}

.csv-editor-wrapper {
  height: 100%;
  min-height: 500px;
}

.html-viewer-wrapper {
  height: 100%;
  min-height: 400px;
}

.html-editor-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.html-editor-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.html-editor-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.html-edit-wrapper {
  height: 100%;
  position: relative;
}

.html-edit-wrapper .code-editor-wrapper {
  height: 100%;
}

.html-preview-wrapper {
  height: 100%;
  position: relative;
}

.floating-save-button {
  position: absolute;
  top: 12px;
  right: 20px;
  z-index: 100;
  background: var(--el-bg-color);
  border-radius: 4px;
  padding: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.text-editor :deep(textarea) {
  height: 100% !important;
  border: none;
  box-shadow: none;
  resize: none;
}

.readonly-content {
  padding: 16px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
