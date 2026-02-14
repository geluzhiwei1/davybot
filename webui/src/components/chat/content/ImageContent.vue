/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="image-content compact-content">
    <div class="image-container">
      <img
        :src="block.image"
        :alt="block.filename || 'Image'"
        :class="['image', `detail-${block.detail || 'auto'}`]"
        @load="handleImageLoad"
        @error="handleImageError"
        @click="openViewer"
      />
      <div v-if="isLoading" class="image-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
      </div>
      <!-- Open in viewer button -->
      <div class="open-viewer-btn compact-btn" @click="openViewer">
        <el-icon :size="16"><ZoomIn /></el-icon>
        <span>查看大图</span>
      </div>
    </div>
    <div v-if="block.filename" class="image-info compact-mt-sm">
      <span class="filename compact-code">{{ block.filename }}</span>
    </div>

    <!-- Image Viewer Modal -->
    <ImageViewer
      v-model:visible="viewerVisible"
      :images="viewerImages"
      :initial-index="viewerInitialIndex"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, inject, computed } from 'vue'
import { Loading, ZoomIn } from '@element-plus/icons-vue'
import ImageViewer from '@/components/chat/ImageViewer.vue'
import type { ImageContentBlock } from '@/types/websocket'

const props = defineProps<{
  block: ImageContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

// Inject message images from parent Message component
const messageImages = inject<{ src: string; filename?: string }[]>('messageImages', [])

const isLoading = ref(true)
const viewerVisible = ref(false)
const viewerInitialIndex = ref(0)

// Use message images if available, otherwise use current image only
const viewerImages = computed(() => {
  return messageImages.length > 0
    ? messageImages
    : [{ src: props.block.image, filename: props.block.filename }]
})

const handleImageLoad = () => {
  isLoading.value = false
}

const handleImageError = (event: Event) => {
  isLoading.value = false
  const img = event.target as HTMLImageElement
  img.style.display = 'none'

  // 发送错误事件
  emit('contentAction', 'image-error', {
    src: img.src,
    error: 'Failed to load image'
  })
}

const openViewer = () => {
  // Find the index of current image in the message images
  const currentIndex = viewerImages.value.findIndex(img => img.src === props.block.image)
  viewerInitialIndex.value = currentIndex >= 0 ? currentIndex : 0
  viewerVisible.value = true
}
</script>

<style scoped>
/* ============================================================================
   Image Content - 使用统一紧凑样式系统
   ============================================================================ */

.image-content {
  max-width: 100%;
  /* 移除卡片样式，因为是内联内容 */
  border: none;
  box-shadow: none;
  background: transparent;
}

.image-container {
  position: relative;
  display: inline-block;
  max-width: 100%;
}

/* 图片样式 - 功能性样式，保留 */
.image {
  max-width: 100%;
  height: auto;
  border-radius: var(--modern-radius-md, 8px);
  box-shadow: var(--modern-shadow-md, 0 2px 8px rgba(0, 0, 0, 0.08));
  transition: transform 0.2s ease;
  cursor: pointer;
}

.image:hover {
  transform: scale(1.02);
  box-shadow: var(--modern-shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.1));
}

/* Detail级别 - 功能性样式，保留 */
.detail-low {
  max-width: 200px;
}

.detail-high {
  max-width: 100%;
}

.detail-auto {
  max-width: 400px;
}

/* 加载状态 - 功能性样式，保留 */
.image-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100px;
  height: 100px;
  background-color: var(--modern-bg-elevated, var(--el-fill-color-light));
  border-radius: var(--modern-radius-md, 8px);
}

/* 查看大图按钮 - 功能性样式，保留 */
.open-viewer-btn {
  position: absolute;
  top: var(--modern-spacing-sm, 8px);
  right: var(--modern-spacing-sm, 8px);
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-xs, 6px);
  background-color: rgba(0, 0, 0, 0.75);
  color: white;
  border-radius: var(--modern-radius-sm, 6px);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s ease, transform 0.2s ease;
  font-size: var(--modern-font-md, 13px);
  font-weight: 500;
  z-index: 2;
}

.image-container:hover .open-viewer-btn {
  opacity: 1;
}

.open-viewer-btn:hover {
  background-color: rgba(0, 0, 0, 0.85);
  transform: scale(1.05);
}

.open-viewer-btn:active {
  transform: scale(0.95);
}

/* 图片信息 - 使用紧凑样式 */
.image-info {
  font-size: var(--modern-font-sm, 12px);
  color: var(--el-text-color-secondary, #64748b);
}
</style>
