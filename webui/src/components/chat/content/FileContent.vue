/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="file-content">
    <div class="file-card compact-content" @click="handleFileClick">
      <div class="file-icon">
        <el-icon :size="24">
          <component :is="getFileIcon" />
        </el-icon>
      </div>
      <div class="file-info compact-body">
        <div class="file-name">{{ block.filename || '未知文件' }}</div>
        <div class="file-meta">
          <span v-if="fileSize" class="file-size compact-tag">{{ fileSize }}</span>
          <span v-if="block.mime_type" class="file-type compact-tag">{{ block.mime_type }}</span>
        </div>
      </div>
      <div class="file-actions">
        <el-button size="small" type="primary" link @click.stop="handleDownload" class="compact-btn">
          <el-icon><Download /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Document,
  Picture,
  VideoPlay,
  Headset,
  Folder,
  Download
} from '@element-plus/icons-vue'
import { ElButton, ElIcon } from 'element-plus'
import type { FileContentBlock } from '@/types/websocket'

const props = defineProps<{
  block: FileContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

// 根据文件类型获取图标
const getFileIcon = computed(() => {
  const mimeType = props.block.mime_type?.toLowerCase() || ''
  const filename = props.block.filename?.toLowerCase() || ''

  if (mimeType.startsWith('image/') || filename.match(/\.(jpg|jpeg|png|gif|bmp|svg|webp)$/)) {
    return Picture
  } else if (mimeType.startsWith('video/') || filename.match(/\.(mp4|avi|mov|wmv|flv|webm)$/)) {
    return VideoPlay
  } else if (mimeType.startsWith('audio/') || filename.match(/\.(mp3|wav|flac|aac|ogg)$/)) {
    return Headset
  } else if (mimeType.includes('pdf') || filename.match(/\.(pdf|doc|docx|txt|md)$/)) {
    return Document
  } else {
    return Folder
  }
})

// 格式化文件大小
const fileSize = computed(() => {
  // 这里简化处理，实际项目中可能需要从文件URL或元数据获取
  return null
})

const handleFileClick = () => {
  emit('contentAction', 'file-click', {
    file: props.block.file,
    filename: props.block.filename,
    mime_type: props.block.mime_type
  })
}

const handleDownload = () => {
  emit('contentAction', 'file-download', {
    file: props.block.file,
    filename: props.block.filename,
    mime_type: props.block.mime_type
  })

  // 创建下载链接
  const link = document.createElement('a')
  link.href = props.block.file
  link.download = props.block.filename || 'download'
  link.click()
}
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   File Content - 使用统一紧凑样式系统
   ============================================================================ */

.file-content {
  max-width: 100%;
  max-width: 400px;
}

.file-card {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-md, 12px);
  cursor: pointer;
  transition: all 0.2s ease;
}

.file-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--modern-shadow-md, 0 2px 8px rgba(0, 0, 0, 0.08));
}

/* 文件图标 - 功能性样式，保留 */
.file-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--el-bg-color);
  border-radius: var(--modern-radius-md, 8px);
  color: var(--modern-color-primary, var(--el-color-primary));
}

.file-info {
  flex: 1;
  min-width: 0;
  padding: 0; /* 覆盖 compact-body 的默认 padding */
}

.file-name {
  font-weight: 500;
  font-size: var(--modern-font-md, 14px);
  color: var(--el-text-color-primary);
  margin-bottom: var(--modern-spacing-xs, 4px);
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  gap: var(--modern-spacing-sm, 8px);
  font-size: var(--modern-font-sm, 12px);
  color: var(--el-text-color-secondary, #64748b);
}

.file-type {
  font-family: var(--font-mono, monospace);
  font-size: var(--modern-font-xs, 10px);
  background-color: var(--modern-color-info-light, var(--el-color-info-light-9));
  color: var(--modern-color-info, var(--el-color-info));
}

.file-actions {
  flex-shrink: 0;
}
</style>
