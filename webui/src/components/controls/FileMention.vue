/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <!-- 遮罩层 -->
    <div v-if="visible" class="file-mention-backdrop" @click="close"></div>

    <!-- 弹出框 -->
    <div v-if="visible" class="file-mention-popup" :style="popupStyle">
    <div class="file-mention-header">
      <span class="file-mention-title">选择文件</span>
      <span class="file-mention-count">{{ filteredFiles.length }} 个文件</span>
    </div>
    <div class="file-mention-search">
      <input ref="searchInput" v-model="searchQuery" type="text" placeholder="搜索文件..." class="file-mention-input"
        @keydown.down.prevent="selectNext" @keydown.up.prevent="selectPrevious" @keydown.enter.prevent="selectCurrent"
        @keydown.esc.prevent="close" />
    </div>
    <div class="file-mention-list" ref="fileList">
      <div v-for="(file, index) in filteredFiles" :key="file.path" class="file-mention-item" :class="{
        'file-mention-item--selected': index === selectedIndex,
        'file-mention-item--directory': file.type === 'directory'
      }" @click="selectFile(file)" @mouseenter="selectedIndex = index">
        <div class="file-mention-icon">
          <svg v-if="file.type === 'directory'" class="icon" viewBox="0 0 24 24">
            <path d="M10 4H4c-1.11 0-2 .89-2 2v12c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2h-8l-2-2z" />
          </svg>
          <svg v-else class="icon" viewBox="0 0 24 24">
            <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
          </svg>
        </div>
        <div class="file-mention-info">
          <div class="file-mention-name">{{ file.name }}</div>
          <div class="file-mention-path">{{ file.path }}</div>
        </div>
        <div class="file-mention-meta">
          <span v-if="file.type === 'file' && file.size" class="file-mention-size">
            {{ formatFileSize(file.size) }}
          </span>
          <span v-if="file.language" class="file-mention-language">
            {{ file.language }}
          </span>
        </div>
      </div>
    </div>
    <div v-if="filteredFiles.length === 0" class="file-mention-empty">
      <div class="file-mention-empty-icon">📁</div>
      <div class="file-mention-empty-text">未找到匹配的文件</div>
    </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { apiManager } from '@/services/api'

interface FileItem {
  path: string
  name: string
  type: 'file' | 'directory'
  size?: number
  language?: string
}

interface Props {
  visible: boolean
  position: { x: number; y: number }
  workspaceId?: string
  fileTree?: unknown[]
  onSelect: (file: FileItem) => void
  onClose: () => void
}

const props = withDefaults(defineProps<Props>(), {
  workspaceId: 'default'
})


// 响应式数据
const files = ref<FileItem[]>([])
const searchQuery = ref('')
const selectedIndex = ref(0)
const searchInput = ref<HTMLInputElement>()
const fileList = ref<HTMLElement>()

// 计算属性
const filteredFiles = computed(() => {
  if (!searchQuery.value.trim()) {
    return files.value
  }

  const query = searchQuery.value.toLowerCase()
  return files.value.filter(file =>
    file.name.toLowerCase().includes(query) ||
    file.path.toLowerCase().includes(query)
  )
})

const popupStyle = computed(() => {
  // 将弹出框居中显示在屏幕中间
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const popupWidth = 500
  const popupHeight = 500

  // 居中显示
  const left = (viewportWidth - popupWidth) / 2
  const top = (viewportHeight - popupHeight) / 2

  return {
    left: `${left}px`,
    top: `${top}px`,
    position: 'fixed' as const,
    width: `${popupWidth}px`,
    maxHeight: `${popupHeight}px`,
    zIndex: 10000,
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)'
  }
})

// 方法
const loadFiles = async () => {
  try {
    let fileTreeData = props.fileTree || []

    // 如果没有传入文件树，则使用 API
    if (fileTreeData.length === 0) {
      const response = await apiManager.getWorkspacesApi().getFileTree(props.workspaceId)
      fileTreeData = response || []
    }

    // 转换文件树结构为扁平列表
    const flattenFiles = (items: unknown[], parentPath = ''): FileItem[] => {
      const result: FileItem[] = []

      for (const item of items) {
        const fullPath = parentPath ? `${parentPath}/${item.name}` : item.name

        if (item.type === 'directory' || item.type === 'folder') {
          result.push({
            path: fullPath,
            name: item.name,
            type: 'directory'
          })

          if (item.children && item.children.length > 0) {
            result.push(...flattenFiles(item.children, fullPath))
          }
        } else {
          result.push({
            path: fullPath,
            name: item.name,
            type: 'file',
            size: item.size,
            language: item.language
          })
        }
      }

      return result
    }

    files.value = flattenFiles(fileTreeData)
  } catch (error) {
    console.error('Failed to load workspace files:', error)
    files.value = []
  }
}

const selectNext = () => {
  if (selectedIndex.value < filteredFiles.value.length - 1) {
    selectedIndex.value++
    scrollToSelected()
  }
}

const selectPrevious = () => {
  if (selectedIndex.value > 0) {
    selectedIndex.value--
    scrollToSelected()
  }
}

const selectCurrent = () => {
  const selectedFile = filteredFiles.value[selectedIndex.value]
  if (selectedFile) {
    selectFile(selectedFile)
  }
}

const selectFile = (file: FileItem) => {
  props.onSelect(file)
  close()
}

const close = () => {
  props.onClose()
}

const scrollToSelected = () => {
  nextTick(() => {
    if (fileList.value) {
      const selectedItem = fileList.value.children[selectedIndex.value] as HTMLElement
      if (selectedItem) {
        selectedItem.scrollIntoView({ block: 'nearest' })
      }
    }
  })
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// 监听器
watch(() => props.visible, (visible) => {
  if (visible) {
    loadFiles()
    searchQuery.value = ''
    selectedIndex.value = 0
    nextTick(() => {
      searchInput.value?.focus()
    })
  }
})

watch(filteredFiles, () => {
  selectedIndex.value = 0
})
</script>

<style scoped>
.file-mention-popup {
  position: fixed;
  z-index: 10000;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  /* 确保弹出框始终在最上层 */
  isolation: isolate;
  /* 添加硬件加速 */
  will-change: transform;
  /* 确保弹出框不会被其他元素遮挡 */
  backdrop-filter: blur(10px);
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.file-mention-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 9999;
  animation: fadeInBackdrop 0.2s ease-out;
}

@keyframes fadeInBackdrop {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.file-mention-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}

.file-mention-title {
  font-weight: 600;
  color: #303133;
}

.file-mention-count {
  font-size: 12px;
  color: #909399;
}

.file-mention-search {
  padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.file-mention-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.file-mention-input:focus {
  border-color: #409eff;
}

.file-mention-list {
  max-height: 300px;
  overflow-y: auto;
}

.file-mention-item {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f5f5f5;
}

.file-mention-item:hover,
.file-mention-item--selected {
  background-color: #f5f7fa;
}

.file-mention-item--selected {
  background-color: #ecf5ff;
}

.file-mention-icon {
  margin-right: 12px;
  flex-shrink: 0;
}

.icon {
  width: 16px;
  height: 16px;
  fill: #909399;
}

.file-mention-item--directory .icon {
  fill: #e6a23c;
}

.file-mention-info {
  flex: 1;
  min-width: 0;
}

.file-mention-name {
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-mention-path {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.file-mention-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.file-mention-size,
.file-mention-language {
  font-size: 11px;
  color: #c0c4cc;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}

.file-mention-language {
  background: #e1f3d8;
  color: #67c23a;
}

.file-mention-empty {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
}

.file-mention-empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.file-mention-empty-text {
  font-size: 14px;
}

/* 滚动条样式 */
.file-mention-list::-webkit-scrollbar {
  width: 6px;
}

.file-mention-list::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.file-mention-list::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.file-mention-list::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>