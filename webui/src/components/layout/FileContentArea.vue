/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <!-- 正常显示的文件内容区域 -->
  <div class="file-content-area-wrapper" :class="{ 'mobile-drawer-mode': isMobileDrawer }">
    <!-- 移动端关闭按钮 -->
    <div v-if="isMobileDrawer" class="mobile-close-btn">
      <el-button :icon="Close" circle @click="handleCloseMobileDrawer" />
    </div>

    <div class="file-content-area" :class="{ 'has-mobile-close': isMobileDrawer }">
      <el-tabs v-if="hasFiles" :model-value="activeFileId || ''" type="card" class="file-tabs" closable
        @tab-remove="closeFile" @tab-change="handleTabChange">
        <el-tab-pane v-for="file in files" :key="`pane-${file.id}`" :label="file.name" :name="file.id">
          <template #label>
            <span class="tab-label" @contextmenu.prevent="handleTabContextMenu($event, file)"
              @dblclick="handleTabDoubleClick(file)">
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

      <!-- Tab 右键菜单 -->
      <!-- 使用 teleport to="body" 以确保在 Tauri 和全屏模式下都能正常工作 -->
      <teleport to="body">
        <div v-if="tabContextMenuVisible" class="tab-context-menu"
          :style="{ left: tabContextMenuPosition.x + 'px', top: tabContextMenuPosition.y + 'px' }">
          <div class="context-menu-item" @click="handlePageFullscreen">
            <el-icon>
              <FullScreen />
            </el-icon>
            <span>{{ isPageFullscreen ? '退出全屏' : '全屏' }}</span>
          </div>
          <!-- 浏览器全屏在 Tauri 中不可用，使用 v-if 隐藏 -->
          <div v-if="!isTauri()" class="context-menu-item" @click="handleFullscreen">
            <el-icon>
              <Monitor />
            </el-icon>
            <span>{{ isBrowserFullscreen ? '退出全屏' : '全屏' }}</span>
          </div>
          <div class="context-menu-divider"></div>
          <div class="context-menu-item" @click="handleCloseTab">
            <el-icon>
              <Close />
            </el-icon>
            <span>关闭</span>
          </div>
          <div class="context-menu-item danger" @click="handleCloseAllTabs">
            <el-icon>
              <CloseBold />
            </el-icon>
            <span>关闭所有</span>
          </div>
        </div>
      </teleport>

      <el-card class="content-card" shadow="never" v-loading="isLoading">
        <div v-if="activeFile" class="active-file-content">
          <!-- HTML 文件的标签页 -->
          <el-tabs v-if="isHTMLFile(activeFile)" v-model="htmlActiveTab" type="border-card" class="html-editor-tabs">
            <el-tab-pane name="preview">
              <template #label>
                <span>预览</span>
              </template>
              <div class="html-preview-wrapper">
                <HTMLViewer :model-value="activeFile.content" :filename="activeFile.name" class="html-viewer-wrapper" />
              </div>
            </el-tab-pane>
            <el-tab-pane name="edit">
              <template #label>
                <span>编辑</span>
              </template>
              <div class="html-edit-wrapper">
                <NativeCodeMirror v-model="editableContent" :file-path="activeFile.name" :theme="editorTheme"
                  :line-numbers="true" :bracket-matching="true" :close-brackets="true" :search="true" language="html"
                  class="code-editor-wrapper" @change="handleContentChange" />
              </div>
            </el-tab-pane>
          </el-tabs>

          <!-- HTML 编辑模式下的保存按钮 -->
          <div v-if="isHTMLFile(activeFile) && htmlActiveTab === 'edit'" class="floating-save-button">
            <el-button @click="handleSave" :loading="isSaving" type="success" size="small">
              保存
            </el-button>
          </div>

          <!-- Drawio XML 编辑模式下的保存按钮 -->
          <div v-if="isDrawioFile(activeFile) && drawioActiveTab === 'xml'" class="floating-save-button">
            <el-button @click="handleSave" :loading="isSaving" type="success" size="small">
              保存
            </el-button>
          </div>

          <!-- Markdown 文件的保存按钮 -->
          <div v-if="isMarkdownFile(activeFile)" class="toolbar-simple">
            <el-button @click="handleSave" :loading="isSaving" :disabled="!isContentModified" type="success"
              size="small">
              保存
            </el-button>
          </div>

          <!-- 其他文件类型的保存按钮 -->
          <!-- <div
            v-if="!isHTMLFile(activeFile) && !isMarkdownFile(activeFile) && (isTextFile(activeFile) || isCodeFile(activeFile))"
            class="toolbar-simple">
            <el-button @click="handleSave" :loading="isSaving" type="success" size="small">
              保存
            </el-button>
          </div> -->

          <div v-show="isMarkdownFile(activeFile)" ref="vditorRef" class="editor-container"></div>
          <ImageViewer v-if="imageFiles.length > 0" :images="allImageFiles" :initial-index="currentImageIndex"
            :visible="imageViewerVisible" @update:visible="imageViewerVisible = $event" />
          <div v-if="isImageFile(activeFile)" class="image-preview-container">
            <el-image :src="activeFile.content" :alt="activeFile.name" fit="contain" class="image-preview"
              style="cursor: pointer;" @click="openImageViewer" />
            <div class="open-viewer-overlay" @click="openImageViewer">
              <el-icon :size="16">
                <ZoomIn />
              </el-icon>
              <span>打开查看器</span>
              <span v-if="allImageFiles.length > 1" class="image-hint">
                ({{ currentImageIndex + 1 }} / {{ allImageFiles.length }})
              </span>
            </div>
          </div>
          <video v-if="isVideoFile(activeFile)" :src="activeFile.content" controls class="media-preview">
            您的浏览器不支持视频播放。
          </video>
          <audio v-if="isAudioFile(activeFile)" :src="activeFile.content" controls class="media-preview">
            您的浏览器不支持音频播放。
          </audio>
          <NativeCodeMirror v-show="isCodeFile(activeFile) && !isHTMLFile(activeFile)" v-model="editableContent"
            :file-path="activeFile.name" :theme="editorTheme" :line-numbers="true" :bracket-matching="true"
            :close-brackets="true" :search="true" class="code-editor-wrapper" @change="handleContentChange" />
          <CSVEditor v-show="isCSVFile(activeFile)" v-model="editableContent" class="csv-editor-wrapper"
            @change="handleContentChange" />
          <PDFViewer v-if="activeFile && isPDFFile(activeFile)" v-model="activeFile.content" :filename="activeFile.name"
            class="pdf-viewer-wrapper" />

          <!-- Office 文件预览（DOCX、Excel）- 使用 vue-office -->
          <VueOfficeEditor v-if="activeFile && isOfficeFile(activeFile)" v-model="activeFile.content"
            :filename="activeFile.name" :filepath="activeFile.path" :editable="false" :workspace-id="getCurrentWorkspaceId()"
            @error="handleOfficeError" class="office-viewer-wrapper" />
          <el-tabs v-if="isDrawioFile(activeFile)" v-model="drawioActiveTab" type="border-card"
            class="drawio-editor-tabs">
            <el-tab-pane name="drawio">
              <template #label><span>drawio</span></template>
              <div class="drawio-preview-wrapper">
                <DrawioEditor v-model="editableContent" :filename="activeFile.name" class="drawio-viewer-wrapper"
                  @change="handleContentChange" @save="handleSave" />
              </div>
            </el-tab-pane>
            <el-tab-pane name="xml">
              <template #label><span>xml</span></template>
              <div class="drawio-edit-wrapper">
                <NativeCodeMirror v-model="editableContent" :file-path="activeFile.name" :theme="editorTheme"
                  :line-numbers="true" :bracket-matching="true" :close-brackets="true" :search="true" language="xml"
                  class="code-editor-wrapper" @change="handleContentChange" />
              </div>
            </el-tab-pane>
          </el-tabs>
          <!-- <el-input v-show="isTextFile(activeFile)" v-model="editableContent" type="textarea" class="text-editor"
            :autosize="{ minRows: 10 }" @input="handleContentChange" /> -->
          <pre
            v-show="!isMarkdownFile(activeFile) && !isCodeFile(activeFile) && !isImageFile(activeFile) && !isVideoFile(activeFile) && !isAudioFile(activeFile) && !isCSVFile(activeFile) && !isPDFFile(activeFile) && !isHTMLFile(activeFile) && !isDrawioFile(activeFile) && !isOfficeFile(activeFile) && !isTextFile(activeFile)"
            class="readonly-content"><code>{{ activeFile.content }}</code></pre>
        </div>
        <el-empty v-else description="没有打开的文件" />
      </el-card>
    </div>
  </div>

  <!-- 全屏 teleport 容器 - 传送到 body 以完全脱离父容器 -->
  <teleport to="body">
    <transition name="fullscreen-fade">
      <div v-if="isPageFullscreen" class="page-fullscreen-overlay">
        <div class="file-content-area">
          <!-- 全屏退出按钮 -->
          <div class="fullscreen-exit-btn">
            <el-button @click="handlePageFullscreen" circle :icon="Close" title="退出全屏" />
          </div>

          <!-- 完全复制 tabs 结构 -->
          <el-tabs v-if="hasFiles" :model-value="activeFileId || ''" type="card" class="file-tabs" closable
            @tab-remove="closeFile" @tab-change="handleTabChange">
            <el-tab-pane v-for="file in files" :key="`pane-fullscreen-${file.id}`" :label="file.name" :name="file.id">
              <template #label>
                <span class="tab-label" @contextmenu.prevent="handleTabContextMenu($event, file)"
                  @dblclick="handleTabDoubleClick(file)">
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

          <!-- 完全复制内容卡片 -->
          <el-card class="content-card" shadow="never" v-loading="isLoading">
            <div v-if="activeFile" class="active-file-content">
              <!-- HTML 文件 -->
              <div v-if="isHTMLFile(activeFile)" class="html-editor-tabs">
                <el-tabs v-model="htmlActiveTab" type="border-card">
                  <el-tab-pane name="preview">
                    <template #label><span>预览</span></template>
                    <div class="html-preview-wrapper">
                      <HTMLViewer :model-value="activeFile.content" :filename="activeFile.name" />
                    </div>
                  </el-tab-pane>
                  <el-tab-pane name="edit">
                    <template #label><span>编辑</span></template>
                    <div class="html-edit-wrapper">
                      <NativeCodeMirror v-model="editableContent" :file-path="activeFile.name" :theme="editorTheme"
                        :line-numbers="true" :bracket-matching="true" :close-brackets="true" :search="true"
                        language="html" @change="handleContentChange" />
                    </div>
                  </el-tab-pane>
                </el-tabs>
                <div v-if="htmlActiveTab === 'edit'" class="floating-save-button">
                  <el-button @click="handleSave" :loading="isSaving" type="success" size="small">保存</el-button>
                </div>
              </div>

              <!-- 保存按钮 -->
              <div v-if="isMarkdownFile(activeFile)" class="toolbar-simple">
                <el-button @click="handleSave" :loading="isSaving" :disabled="!isContentModified" type="success"
                  size="small">保存</el-button>
              </div>

              <!-- <div
                v-if="!isHTMLFile(activeFile) && !isMarkdownFile(activeFile) && (isTextFile(activeFile) || isCodeFile(activeFile))"
                class="toolbar-simple">
                <el-button @click="handleSave" :loading="isSaving" type="success" size="small">保存</el-button>
              </div> -->

              <!-- Markdown 编辑器 -->
              <div v-show="isMarkdownFile(activeFile)" ref="vditorRefFullscreen" class="editor-container"></div>

              <!-- 图片查看器 -->
              <ImageViewer v-if="imageFiles.length > 0" :images="allImageFiles" :initial-index="currentImageIndex"
                :visible="imageViewerVisible" @update:visible="imageViewerVisible = $event" />

              <!-- 图片预览 -->
              <div v-if="isImageFile(activeFile)" class="image-preview-container">
                <el-image :src="activeFile.content" :alt="activeFile.name" fit="contain" class="image-preview"
                  style="cursor: pointer;" @click="openImageViewer" />
                <div class="open-viewer-overlay" @click="openImageViewer">
                  <el-icon :size="16">
                    <ZoomIn />
                  </el-icon>
                  <span>打开查看器</span>
                  <span v-if="allImageFiles.length > 1" class="image-hint">({{ currentImageIndex + 1 }} / {{
                    allImageFiles.length }})</span>
                </div>
              </div>

              <!-- 视频/音频 -->
              <video v-if="isVideoFile(activeFile)" :src="activeFile.content" controls class="media-preview"></video>
              <audio v-if="isAudioFile(activeFile)" :src="activeFile.content" controls class="media-preview"></audio>

              <!-- 代码编辑器 -->
              <NativeCodeMirror v-show="isCodeFile(activeFile) && !isHTMLFile(activeFile)" v-model="editableContent"
                :file-path="activeFile.name" :theme="editorTheme" :line-numbers="true" :bracket-matching="true"
                :close-brackets="true" :search="true" class="code-editor-wrapper" @change="handleContentChange" />

              <!-- PDF 查看器 -->
              <PDFViewer v-if="activeFile && isPDFFile(activeFile)" v-model="activeFile.content"
                :filename="activeFile.name" class="pdf-viewer-wrapper" />

              <!-- Office 文件预览（DOCX、Excel）- 使用 vue-office -->
              <VueOfficeEditor v-if="activeFile && isOfficeFile(activeFile)" v-model="activeFile.content"
                :filename="activeFile.name" :filepath="activeFile.path" :editable="false" :workspace-id="getCurrentWorkspaceId()"
                @error="handleOfficeError" class="office-viewer-wrapper" />

              <!-- Drawio 编辑器 -->
              <el-tabs v-if="isDrawioFile(activeFile)" v-model="drawioActiveTab" type="border-card"
                class="drawio-editor-tabs">
                <el-tab-pane name="drawio">
                  <template #label>
                    <span>drawio</span>
                  </template>
                  <div class="drawio-preview-wrapper">
                    <DrawioEditor v-model="editableContent" :filename="activeFile.name" class="drawio-viewer-wrapper"
                      @change="handleContentChange" @save="handleSave" />
                  </div>
                </el-tab-pane>
                <el-tab-pane name="xml">
                  <template #label>
                    <span>xml</span>
                  </template>
                  <div class="drawio-edit-wrapper">
                    <NativeCodeMirror v-model="editableContent" :file-path="activeFile.name" :theme="editorTheme"
                      :line-numbers="true" :bracket-matching="true" :close-brackets="true" :search="true" language="xml"
                      class="code-editor-wrapper" @change="handleContentChange" />
                  </div>
                </el-tab-pane>
              </el-tabs>

              <!-- HTML 预览 -->
              <HTMLViewer v-if="isHTMLFile(activeFile) && htmlActiveTab === 'preview'" :model-value="activeFile.content"
                :filename="activeFile.name" />

              <!-- 文本编辑器 -->
              <!-- <el-input v-show="isTextFile(activeFile)" v-model="editableContent" type="textarea" class="text-editor"
                :autosize="{ minRows: 10 }" @input="handleContentChange" /> -->

              <!-- 只读内容 -->
              <pre
                v-show="!isMarkdownFile(activeFile) && !isCodeFile(activeFile) && !isImageFile(activeFile) && !isVideoFile(activeFile) && !isAudioFile(activeFile) && !isCSVFile(activeFile) && !isPDFFile(activeFile) && !isHTMLFile(activeFile) && !isDrawioFile(activeFile) && !isOfficeFile(activeFile) && !isTextFile(activeFile)"
                class="readonly-content"><code>{{ activeFile.content }}</code></pre>
            </div>
            <el-empty v-else description="没有打开的文件" />
          </el-card>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import Vditor from 'vditor'
import 'vditor/dist/index.css'
import { useThemeStore } from '@/stores/theme'
import { ElTabs, ElTabPane, ElCard, ElButton, ElIcon, ElImage, ElInput, ElEmpty, ElMessage } from 'element-plus'
// ElTabs 和 ElTabPane 已经在上面导入了
import { Document, VideoPlay, Headset, Picture, ZoomIn, FullScreen, Close, CloseBold, Monitor } from '@element-plus/icons-vue'
// View 和 Edit 图标用于 Markdown 文件的编辑器切换
import NativeCodeMirror from '@/components/editor/NativeCodeMirror.vue'
import CSVEditor from '@/components/editor/CSVEditor.vue'
import ImageViewer from '@/components/chat/ImageViewer.vue'
import PDFViewer from '@/components/editor/PDFViewer.vue'
import HTMLViewer from '@/components/editor/HTMLViewer.vue'
import DrawioEditor from '@/components/editor/DrawioEditor.vue'
import VueOfficeEditor from '@/components/editor/VueOfficeEditor.vue'
import { isTauri } from '@/utils/platform'
import { useWorkspaceStore } from '@/stores/workspace'

interface File {
  id: string
  name: string
  path: string  // 添加 path 字段,存储文件的完整路径
  type: string
  content: string
  isDirty?: boolean
}

interface Props {
  files: File[]
  activeFileId: string | null
  isMobileDrawer?: boolean
  workspaceId?: string  // 添加 workspaceId prop
}

interface Emits {
  (e: 'close-file', fileId: string): void
  (e: 'update:activeFileId', fileId: string | null): void
  (e: 'save-file', fileId: string, content: string): void
  (e: 'update-file-content', fileId: string, content: string): void
  (e: 'close-mobile-drawer'): void
}

const props = withDefaults(defineProps<Props>(), {
  isMobileDrawer: false,
  workspaceId: undefined
})
const emit = defineEmits<Emits>()

const themeStore = useThemeStore()
const workspaceStore = useWorkspaceStore()
const htmlActiveTab = ref('preview')

const route = useRoute()

// 获取当前 workspaceId 的辅助函数
const getCurrentWorkspaceId = () => {
  // 优先从 URL 获取，再从 props，最后从 store
  return (route.params.workspaceId as string)
    || (route.query.workspaceId as string)
    || props.workspaceId
    || workspaceStore.currentWorkspaceId
    || undefined
}
const drawioActiveTab = ref('xml')
const isSaving = ref(false)
const isLoading = ref(false)
const editableContent = ref('')
const vditorRef = ref<HTMLDivElement | null>(null)
const vditorRefFullscreen = ref<HTMLDivElement | null>(null) // 全屏模式下的 Vditor ref
const vditor = ref<Vditor | null>(null)
const vditorInitialized = ref(false)
const vditorInitFullscreen = ref(false) // 记录 Vditor 初始化时的全屏状态
const isDirty = ref(false)  // 本地 dirty 状态，用于显示保存按钮状态

// Tab 右键菜单状态
const tabContextMenuVisible = ref(false)
const tabContextMenuPosition = ref({ x: 0, y: 0 })
const selectedTabFile = ref<File | null>(null)
const isPageFullscreen = ref(false)  // 全屏状态
const isBrowserFullscreen = ref(false)  // 浏览器全屏状态

// ✅ 暴露刷新方法给父组件
const refreshAllFiles = () => {
  // 触发父组件重新加载所有已打开文件的内容
  props.files.forEach(file => {
    emit('update-file-content', file.id, file.content)
  })
}

// 移动端抽屉模式处理
const handleCloseMobileDrawer = () => {
  emit('close-mobile-drawer')
}

// ✅ 暴露方法供父组件调用
defineExpose({
  refreshAllFiles
})

// Image viewer state
const imageViewerVisible = ref(false)

// 内容是否被修改（使用本地 dirty 状态）
const isContentModified = computed(() => {
  if (!activeFile.value) return false
  return isDirty.value
})

// Computed properties
const hasFiles = computed(() => props.files.length > 0)
const activeFile = computed(() => props.files.find(f => f.id === props.activeFileId) || null)
const editorTheme = computed(() => (themeStore.theme === 'dark' ? 'one-dark' : 'light'))

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
const CODE_EXTENSIONS = [
  // JavaScript/TypeScript
  'js', 'ts', 'jsx', 'tsx',
  // Python
  'py',
  // Vue
  'vue',
  // Web
  'html', 'css',
  // Config
  'json', 'yaml', 'yml', 'toml',
  // Templates
  'jinja2', 'j2', 'jinja',
  // Shell
  'sh', 'bash', 'zsh', 'fish',
  // Database
  'sql',
  // Markup
  'xml',
  // Other
  'conf', 'config', 'ini', 'cfg'
]
const TEXT_EXTENSIONS = ['text', 'txt']  // txt 文件作为文本处理

// Office 文件扩展名（仅支持 DOCX 和 Excel，使用 vue-office 预览）
const OFFICE_EXTENSIONS = [
  // Word
  'docx',
  // Excel
  'xlsx', 'xls'
]

function isMarkdownFile(file: File): boolean {
  return file.type === 'markdown' || file.name.endsWith('.md')
}

function isOfficeFile(file: File): boolean {
  return file.type === 'office' || OFFICE_EXTENSIONS.some(ext => file.name.endsWith(`.${ext}`))
}

function isExcelFile(file: File): boolean {
  const excelExtensions = ['xlsx', 'xls', 'ods', 'csv']
  return file.name.endsWith('.xlsx') ||
         file.name.endsWith('.xls') ||
         file.name.endsWith('.ods') ||
         file.name.endsWith('.csv') ||
         file.type === 'excel' ||
         file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
         file.type === 'application/vnd.ms-excel' ||
         file.type === 'application/vnd.oasis.opendocument.spreadsheet' ||
         file.type === 'text/csv'
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

function isDrawioFile(file: File): boolean {
  return file.name.endsWith('.drawio') ||
    file.name.endsWith('.dio') ||
    file.name.endsWith('.xml') && file.name.toLowerCase().includes('drawio') ||
    file.type === 'application/drawio' ||
    file.type === 'application/x-drawio'
}

function isGenericFile(file: File): boolean {
  return !isMarkdownFile(file) &&
    !isCodeFile(file) &&
    !isImageFile(file) &&
    !isVideoFile(file) &&
    !isAudioFile(file) &&
    !isCSVFile(file) &&
    !isPDFFile(file) &&
    !isHTMLFile(file) &&
    !isDrawioFile(file) &&
    !isOfficeFile(file)
}

// Event handlers
const handleTabChange = (fileId: string | number) => {
  emit('update:activeFileId', fileId as string)
}

const closeFile = (fileId: string | number) => {
  emit('close-file', fileId as string)
}

// Tab 右键菜单处理
const handleTabContextMenu = (event: MouseEvent, file: File) => {
  event.preventDefault()
  event.stopPropagation()

  selectedTabFile.value = file

  // 使用视口坐标（与 SidePanel 保持一致）
  tabContextMenuPosition.value = {
    x: event.clientX,
    y: event.clientY
  }

  tabContextMenuVisible.value = true
}

// Tab 双击处理 - 切换全屏
const handleTabDoubleClick = (file: File) => {
  // 双击切换全屏状态
  isPageFullscreen.value = !isPageFullscreen.value
}

const closeTabContextMenu = () => {
  tabContextMenuVisible.value = false
  selectedTabFile.value = null
}

// 全屏切换（CSS级别，占满视口）
const handlePageFullscreen = () => {
  closeTabContextMenu()
  isPageFullscreen.value = !isPageFullscreen.value
}

// 浏览器全屏切换（API级别）
// 注意：此功能在 Tauri 环境中不可用，菜单项会被隐藏
const handleFullscreen = () => {
  closeTabContextMenu()

  // 在 Tauri 环境中不执行
  if (isTauri()) {
    console.warn('浏览器全屏功能在 Tauri 环境中不可用，请使用全屏')
    return
  }

  // 检查 Fullscreen API 是否可用
  if (!document.fullscreenEnabled) {
    console.error('当前浏览器不支持全屏 API')
    return
  }

  const element = document.querySelector('.file-content-area')
  if (!element) return

  if (!document.fullscreenElement) {
    element.requestFullscreen().catch(err => {
      console.error('进入全屏失败:', err)
    })
  } else {
    document.exitFullscreen()
  }
}

// 监听全屏状态变化
const handleFullscreenChange = (_event: Event) => {
  isBrowserFullscreen.value = !!document.fullscreenElement
}

// 关闭当前 tab
const handleCloseTab = () => {
  const file = selectedTabFile.value // 先保存引用
  closeTabContextMenu()

  if (file) {
    closeFile(file.id)
  }
}

// 关闭所有 tabs
const handleCloseAllTabs = () => {
  closeTabContextMenu()

  props.files.forEach(file => {
    emit('close-file', file.id)
  })
}

const openImageViewer = () => {
  imageViewerVisible.value = true
}

const handleContentChange = () => {
  // 内容被修改，标记为 dirty
  isDirty.value = true
  // 通知父组件更新 dirty 状态（用于显示 ● 标记）
  if (activeFile.value) {
    const file = props.files.find(f => f.id === activeFile.value!.id)
    if (file && !file.isDirty) {
      emit('update-file-content', activeFile.value.id, editableContent.value)
    }
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
    emit('save-file', activeFile.value.id, contentToSave)

    // 保存成功后重置 dirty 状态
    isDirty.value = false

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

/**
 * 处理 Office 编辑器保存事件
 */
const handleOfficeSave = async (blob: Blob, filename: string) => {
  if (!activeFile.value) return

  isSaving.value = true
  try {
    // 将 Blob 转换为 base64
    const base64 = await blobToBase64(blob)

    // 通知父组件保存
    emit('save-file', activeFile.value.id, base64)

    // 重置 dirty 状态
    isDirty.value = false

    ElMessage.success(`${filename} 保存成功`)
  } catch (error) {
    console.error('[FileContentArea] Office 保存失败:', error)
    ElMessage.error(`保存失败: ${(error as Error).message}`)
  } finally {
    isSaving.value = false
  }
}

/**
 * 处理 Office 编辑器错误事件
 */
const handleOfficeError = (error: Error) => {
  console.error('[FileContentArea] Office 编辑器错误:', error)
  ElMessage.error(`文档加载失败: ${error.message}`)
}

/**
 * 将 Blob 转换为 Base64
 */
async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

const handleKeyDown = (event: KeyboardEvent) => {
  // 检查是否按下了 Ctrl+S 或 Cmd+S (Mac)
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    // 只有当有活动文件且内容被修改时才触发保存
    if (activeFile.value && isDirty.value) {
      event.preventDefault() // 阻止浏览器默认保存行为
      handleSave()
    }
  }
}

onMounted(() => {
  document.addEventListener('click', handleGlobalClick)
  document.addEventListener('keydown', handleKeyDown)
  if (!isTauri()) {
    document.addEventListener('fullscreenchange', handleFullscreenChange)
  }
})

const handleGlobalClick = (event: Event) => {
  if (tabContextMenuVisible.value) {
    const target = event.target as HTMLElement
    const contextMenu = document.querySelector('.tab-context-menu')
    if (contextMenu && !contextMenu.contains(target)) {
      closeTabContextMenu()
    }
  }
}

// 将相对路径基于 baseDir 解析为从 workspace 根目录开始的路径
const resolveRelativePath = (relativePath: string, baseDir: string): string => {
  let path = relativePath
  if (path.startsWith('./')) path = path.substring(2)
  if (path.startsWith('/')) return path.substring(1)

  const segments = baseDir ? baseDir.split('/').filter(p => p) : []
  while (path.startsWith('../')) {
    path = path.substring(3)
    if (segments.length > 0) segments.pop()
  }
  return segments.length > 0 ? [...segments, path].join('/') : path
}

// 构建图片的 API URL
const buildImageApiUrl = (imagePath: string): string | null => {
  const workspaceId = getCurrentWorkspaceId()
  if (!workspaceId || !activeFile.value) return null

  const currentDir = activeFile.value.id.includes('/')
    ? activeFile.value.id.substring(0, activeFile.value.id.lastIndexOf('/'))
    : ''

  const resolvedPath = resolveRelativePath(imagePath, currentDir)
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
  return `${apiBaseUrl}/workspaces/${workspaceId}/files?path=${encodeURIComponent(resolvedPath)}`
}

/**
 * 修复 DOM 中所有图片的 src 属性，将相对路径替换为 API URL。
 * 用于在 Vditor 初始渲染后（after 回调）修复已渲染的图片。
 */
const fixRenderedImageSrcs = () => {
  const targetRef = isPageFullscreen.value ? vditorRefFullscreen.value : vditorRef.value
  if (!targetRef) return

  const container = targetRef.querySelector('.vditor-wysiwyg .vditor-reset') as HTMLElement
  if (!container) return

  container.querySelectorAll('img').forEach((img) => {
    const src = img.getAttribute('src')
    if (!src || src.startsWith('data:') || src.startsWith('http://') || src.startsWith('https://')) return

    const apiUrl = buildImageApiUrl(src)
    if (!apiUrl) return

    img.setAttribute('src', apiUrl)
    img.style.cursor = 'pointer'
    img.onclick = () => openImageViewer()
    img.onerror = () => {
      console.error('[Vditor] 加载图片失败:', apiUrl)
    }
  })
}

/**
 * 通过 Lute 的 SetJSRenderers 设置自定义 renderLinkDest，
 * 拦截后续编辑/粘贴产生的图片和链接路径。
 */
const setupLuteImageRenderer = () => {
  if (!vditor.value) return
  const lute = vditor.value.vditor?.lute
  if (!lute) return

  const Lute = (window as any).Lute
  if (!Lute) return

  const renderLinkDest = (node: any, entering: boolean): [string, number] => {
    if (!entering) return ['', Lute.WalkContinue]

    // 只处理图片节点（Type === 34），跳过链接节点
    const parentType = node.__internal_object__?.Parent?.Type
    if (parentType !== 34) return ['', Lute.WalkContinue]

    const src = node.TokensStr()
    if (!src || src.startsWith('data:') || src.startsWith('http://') || src.startsWith('https://')) {
      return ['', Lute.WalkContinue]
    }

    const apiUrl = buildImageApiUrl(src)
    if (!apiUrl) return ['', Lute.WalkContinue]

    return [`"${apiUrl}"`, Lute.WalkSkipChildren]
  }

  lute.SetJSRenderers({
    renderers: {
      Md2VditorDOM: { renderLinkDest },
    }
  })
}

// Vditor initialization
const initVditor = () => {
  // 根据全屏状态选择正确的 ref
  const targetRef = isPageFullscreen.value ? vditorRefFullscreen.value : vditorRef.value

  if (!targetRef) {
    console.error('[initVditor] 无法找到目标 DOM 元素，全屏模式:', isPageFullscreen.value)
    return
  }

  if (!activeFile.value) {
    return
  }

  if (!isMarkdownFile(activeFile.value)) {
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
  vditor.value = new Vditor(targetRef, {
    theme: themeStore.theme === 'dark' ? 'dark' : 'classic',
    mode: 'wysiwyg',
    height: '100%',
    value: editableContent.value,
    // 禁用图片懒加载
    lazyLoadImage: {
      enable: false
    },
    cache: {
      enable: false,
      id: `markdown-file-${activeFile.value.id}`
    },
    placeholder: '请输入 Markdown 内容...',
    toolbar: [
      // 标题和基础格式
      'headings',
      'bold',
      'italic',
      'strike',
      '|',
      // 列表
      'list',
      'ordered-list',
      'check',
      'outdent',
      'indent',
      '|',
      // 引用和代码
      'quote',
      'code',
      'inline-code',
      '|',
      // 插入功能
      'insert-before',
      'insert-after',
      '|',
      // 媒体和链接
      'link',
      'upload',
      'table',
      'emoji',
      '|',
      // 分割线
      'line',
      '|',
      // 编辑操作
      'undo',
      'redo',
      '|',
      // 视图和预览
      'both',
      'preview',
      'fullscreen',
      'outline',
      '|',
      // 主题配置
      'edit-mode',
      'code-theme',
      'content-theme',
      '|',
      // 高级功能
      'export',
      'devtools',
      'info',
      'help',
    ],
    upload: {
      handler: async (files: File[]) => {
        try {
          if (!files || files.length === 0) {
            return ''
          }

          const file = files[0]
          const workspaceId = workspaceStore.currentWorkspaceId

          if (!workspaceId) {
            ElMessage.error('未找到工作区信息')
            return ''
          }

          // 使用项目的文件上传 API
          const { filesApi } = await import('@/services/api')
          const result = await filesApi.uploadFile(workspaceId, {
            file,
            path: 'assets/images',  // 上传到工作区的 assets/images 目录
            overwrite: false
          })

          // 返回相对路径用于 Markdown 引用
          const relativePath = result.path.startsWith('/')
            ? result.path.substring(1)
            : result.path

          ElMessage.success(`图片上传成功: ${result.name}`)

          return `/${relativePath}`
        } catch (error) {
          console.error('[Vditor] 上传失败:', error)
          ElMessage.error(`上传失败: ${error.message || '未知错误'}`)
          return ''
        }
      },
      filename: (file: File) => {
        // 保留原始文件名
        return file.name
      },
      linkToImgUrl: '', // 不使用自动转图服务
      max: 10 * 1024 * 1024, // 10MB
      allow: (file: File) => {
        // 只允许图片文件
        if (!file.type.startsWith('image/')) {
          ElMessage.warning('只能上传图片文件')
          return false
        }
        if (file.size > 10 * 1024 * 1024) {
          ElMessage.warning('图片大小不能超过 10MB')
          return false
        }
        return true
      }
    },
    preview: {
      parse: (element: HTMLElement) => {
        // 处理代码块的复制按钮
        const codeBlocks = element.querySelectorAll('pre code')
        codeBlocks.forEach((block) => {
          const pre = block.parentElement
          if (pre && !pre.querySelector('.copy-button')) {
            const copyBtn = document.createElement('button')
            copyBtn.className = 'copy-button'
            copyBtn.textContent = '复制'
            copyBtn.style.cssText = `
              position: absolute;
              top: 8px;
              right: 8px;
              padding: 4px 12px;
              background: rgba(0, 0, 0, 0.6);
              color: white;
              border: none;
              border-radius: 4px;
              cursor: pointer;
              font-size: 12px;
              transition: background 0.2s;
              z-index: 10;
            `
            copyBtn.onmouseover = () => {
              copyBtn.style.background = 'rgba(0, 0, 0, 0.8)'
            }
            copyBtn.onmouseout = () => {
              copyBtn.style.background = 'rgba(0, 0, 0, 0.6)'
            }
            copyBtn.onclick = async () => {
              try {
                await navigator.clipboard.writeText(block.textContent || '')
                copyBtn.textContent = '已复制!'
                setTimeout(() => {
                  copyBtn.textContent = '复制'
                }, 2000)
              } catch (err) {
                console.error('复制失败:', err)
              }
            }
            pre.style.position = 'relative'
            pre.appendChild(copyBtn)
          }
        })
      },
      hljs: {
        enable: false, // 禁用代码高亮，避免 CDN 请求
      },
      math: {
        inlineDigit: true,
        macros: {}
      },
      markdown: {
        autoSpace: true,
        gfmAutoLink: true,
        toc: true,
        mark: true
      }
    },
    input: (value: string) => {
      editableContent.value = value
      handleContentChange()
    },
    after: () => {
      vditorInitialized.value = true
      vditorInitFullscreen.value = isPageFullscreen.value

      // 修复初始渲染的图片路径（Lute 已渲染完毕，需直接操作 DOM）
      fixRenderedImageSrcs()
      // 设置 Lute 自定义渲染器，拦截后续编辑/粘贴产生的图片路径
      setupLuteImageRenderer()
    },
  })
}

// Watchers
watch(() => themeStore.theme, (newTheme) => {
  vditor.value?.setTheme(newTheme === 'dark' ? 'dark' : 'classic')
})


watch(activeFile, (newFile, oldFile) => {
  if (!newFile) {
    return
  }

  // 更新编辑内容
  editableContent.value = newFile.content

  // 重置 dirty 状态（切换到新文件时）
  if (oldFile && oldFile.id !== newFile.id) {
    isDirty.value = false
  }

  // 如果是HTML文件，重置tab状态
  if (isHTMLFile(newFile)) {
    htmlActiveTab.value = 'preview'
  }

  // 如果是Excel文件，重置tab状态
  // if (isExcelFile(newFile)) {
  //   excelActiveTab.value = 'preview'
  // }

  // 只在切换到Markdown文件时初始化/更新Vditor
  if (isMarkdownFile(newFile)) {
    // 检查是否需要重新初始化：
    // 1. 还没有初始化过
    // 2. 全屏状态发生了变化（需要切换到不同的 DOM 元素）
    const needReinit = !vditorInitialized.value ||
      isPageFullscreen.value !== vditorInitFullscreen.value

    if (needReinit) {
      // 强制重新初始化到正确的 DOM 元素
      vditorInitialized.value = false
      nextTick(initVditor)
    } else if (vditor.value) {
      // 已初始化且全屏状态一致，只更新内容
      nextTick(() => {
        if (vditor.value) {
          vditor.value.setValue(newFile.content)
        }
      })
    }
  }
}, { immediate: true })

// 监听 activeFile.content 变化，同步到 editableContent
watch(() => activeFile.value?.content, (newContent) => {
  if (newContent !== undefined && newContent !== editableContent.value) {
    editableContent.value = newContent
    // 注意：不在这里重置 isDirty，因为可能是外部更新
    // isDirty 只在 handleSave 成功后重置
  }
}, { immediate: true })

// 监听全屏状态变化
watch(isPageFullscreen, (newVal, oldVal) => {
  // 只在状态真正改变时处理
  if (newVal === oldVal) return

  // 如果当前是 Markdown 文件，需要重新初始化 Vditor
  if (activeFile.value && isMarkdownFile(activeFile.value)) {
    // 重置初始化标志
    vditorInitialized.value = false

    // 使用双重 nextTick 确保 teleport 的 DOM 完全渲染
    nextTick(() => {
      nextTick(() => {
        initVditor()
      })
    })
  }
})

onUnmounted(() => {
  // Clean up event listeners
  document.removeEventListener('click', handleGlobalClick)
  document.removeEventListener('keydown', handleKeyDown)
  if (!isTauri()) {
    document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }

  // Clean up Vditor instance to prevent memory leaks
  if (vditor.value) {
    try {
      vditor.value.destroy()
      vditor.value = null
    } catch (error) {
      console.warn('[FileContentArea] Error destroying Vditor:', error)
    }
  }
  vditorInitialized.value = false
})
</script>

<style scoped>
/* 包裹层 - 用于建立定位上下文 */
.file-content-area-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.file-content-area {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--el-bg-color-page);
}

/* 全屏覆盖层 - teleport 到 body */
.page-fullscreen-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100vw;
  height: 100vh;
  z-index: 99999;
  background-color: var(--el-bg-color-page);
  overflow: auto;
}

/* 全屏退出按钮 */
.fullscreen-exit-btn {
  position: absolute;
  top: 12px;
  right: 20px;
  z-index: 100;
}

/* 过渡动画 */
.fullscreen-fade-enter-active,
.fullscreen-fade-leave-active {
  transition: opacity 0.3s ease;
}

.fullscreen-fade-enter-from,
.fullscreen-fade-leave-to {
  opacity: 0;
}

.file-tabs {
  flex-shrink: 0;
}

/* Tab 右键菜单样式 */
.tab-context-menu {
  position: fixed;
  /* 使用 fixed 定位，配合 teleport to="body" */
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.3);
  padding: 4px 0;
  z-index: 9999;
  /* 在 body 中需要足够高的 z-index */
  min-width: 150px;
  pointer-events: auto;
}

.tab-context-menu .context-menu-item {
  padding: 8px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background-color 0.2s;
  font-size: 14px;
  color: var(--el-text-color-regular);
}

.tab-context-menu .context-menu-item:hover {
  background-color: var(--el-fill-color-light);
}

.tab-context-menu .context-menu-item.danger {
  color: var(--el-color-danger);
}

.tab-context-menu .context-menu-item.danger:hover {
  background-color: var(--el-color-danger-light-9);
}

.tab-context-menu .context-menu-divider {
  height: 1px;
  background-color: var(--el-border-color);
  margin: 4px 0;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
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
.html-viewer-wrapper,
.office-viewer-wrapper {
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

.drawio-editor-wrapper {
  height: 100%;
  min-height: 600px;
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

.drawio-editor-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.drawio-editor-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.drawio-editor-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.drawio-edit-wrapper {
  height: 100%;
  position: relative;
}

.drawio-edit-wrapper .code-editor-wrapper {
  height: 100%;
}

.drawio-preview-wrapper {
  height: 100%;
  position: relative;
}

.excel-editor-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.excel-editor-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.excel-editor-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.excel-edit-wrapper {
  height: 100%;
  position: relative;
}

.excel-preview-wrapper {
  height: 100%;
  position: relative;
}

.luckysheet-wrapper {
  height: 100%;
  min-height: 600px;
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

/* ========================================
   MOBILE DRAWER MODE STYLES
   ======================================== */

.mobile-drawer-mode.file-content-area-wrapper {
  width: 100vw;
  height: 100vh;
  position: fixed;
  top: 0;
  left: 0;
  z-index: var(--z-mobile-drawer, 1000);
  background-color: var(--el-bg-color-page);
}

.mobile-close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  padding: env(safe-area-inset-top) 12px 12px 12px;
}

.mobile-close-btn .el-button {
  width: 44px;
  height: 44px;
  font-size: 18px;
}

.file-content-area.has-mobile-close {
  padding-top: 56px;
  height: 100%;
}

/* 移动端优化 */
@media (max-width: 767px) {
  .file-tabs .el-tabs__header {
    padding: 8px 12px 0 12px;
  }

  .file-tabs .el-tabs__item {
    font-size: 13px;
    padding: 0 12px;
    height: 40px;
    line-height: 40px;
  }

  .file-tabs .el-tabs__nav .el-icon {
    font-size: 16px;
  }

  .editor-container {
    padding: 12px;
  }

  .toolbar {
    padding: 12px;
  }

  .tab-context-menu {
    font-size: 14px;
  }

  .context-menu-item {
    padding: 12px 16px;
    min-height: var(--touch-target-min, 44px);
  }
}
</style>
