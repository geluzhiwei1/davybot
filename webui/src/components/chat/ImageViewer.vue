/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <transition name="fade">
      <div v-if="visible" class="image-viewer-overlay" @click.self="close" @mousewheel.prevent="handleWheel">
        <div class="image-viewer-container" @click.stop>
          <!-- Toolbar -->
          <div class="toolbar">
            <div class="toolbar-left">
              <span v-if="currentFilename" class="image-title">{{ currentFilename }}</span>
              <span v-if="images.length > 1" class="image-counter">{{ currentIndex + 1 }} / {{ images.length }}</span>
            </div>
            <div class="toolbar-center">
              <!-- Navigation controls (only show if multiple images) -->
              <el-button-group v-if="images.length > 1">
                <el-button size="small" :icon="ArrowLeft" @click="prevImage" :disabled="currentIndex === 0">
                  上一张
                </el-button>
                <el-button size="small" :icon="ArrowRight" @click="nextImage" :disabled="currentIndex === images.length - 1">
                  下一张
                </el-button>
              </el-button-group>

              <!-- Zoom controls -->
              <el-button-group class="ml-2">
                <el-button size="small" :icon="ZoomOut" @click="zoomOut" :disabled="scale <= minScale" />
                <el-button size="small" @click="toggleFit">
                  {{ fitMode === 'fit' ? '适应' : scale === 1 ? '100%' : Math.round(scale * 100) + '%' }}
                </el-button>
                <el-button size="small" :icon="ZoomIn" @click="zoomIn" :disabled="scale >= maxScale" />
              </el-button-group>

              <!-- Rotation controls -->
              <el-button-group class="ml-2">
                <el-button size="small" :icon="RefreshLeft" @click="rotateLeft" />
                <el-button size="small" :icon="RefreshRight" @click="rotateRight" />
              </el-button-group>

              <!-- Reset button -->
              <el-button size="small" :icon="Refresh" @click="resetView">重置</el-button>
            </div>
            <div class="toolbar-right">
              <!-- Download button -->
              <el-button size="small" :icon="Download" @click="downloadImage">下载</el-button>
              <!-- Fullscreen button -->
              <el-button size="small" :icon="FullScreen" @click="toggleFullscreen">
                {{ isFullscreen ? '退出' : '全屏' }}
              </el-button>
              <!-- Close button -->
              <el-button size="small" :icon="Close" @click="close" />
            </div>
          </div>

          <!-- Image canvas -->
          <div
            ref="canvasRef"
            class="image-canvas"
            @mousedown="handleMouseDown"
            @mousemove="handleMouseMove"
            @mouseup="handleMouseUp"
            @mouseleave="handleMouseUp"
            @contextmenu.prevent
          >
            <div
              class="image-wrapper"
              :style="imageStyle"
            >
              <img
                ref="imageRef"
                :src="currentImage"
                :alt="currentFilename || 'Image'"
                @load="handleImageLoad"
                @error="handleImageError"
                draggable="false"
              />
            </div>
          </div>

          <!-- Navigation arrows (for multiple images) -->
          <template v-if="images.length > 1">
            <div class="nav-arrow nav-arrow-left" @click.stop="prevImage">
              <el-icon :size="32"><ArrowLeft /></el-icon>
            </div>
            <div class="nav-arrow nav-arrow-right" @click.stop="nextImage">
              <el-icon :size="32"><ArrowRight /></el-icon>
            </div>
          </template>

          <!-- Zoom slider -->
          <div class="zoom-slider-container">
            <el-slider
              v-model="scale"
              :min="minScale"
              :max="maxScale"
              :step="0.1"
              :show-tooltip="false"
              @input="handleSliderChange"
            />
          </div>

          <!-- Info panel -->
          <div v-if="imageInfo" class="info-panel">
            <div>{{ imageInfo.width }} × {{ imageInfo.height }} px</div>
            <div v-if="imageSize">{{ formatFileSize(imageSize) }}</div>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  ZoomIn,
  ZoomOut,
  RefreshLeft,
  RefreshRight,
  Refresh,
  Download,
  FullScreen,
  Close,
  ArrowLeft,
  ArrowRight
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

interface ImageInfo {
  src: string
  filename?: string
}

interface Props {
  visible: boolean
  images: ImageInfo[]
  initialIndex?: number
}

const props = withDefaults(defineProps<Props>(), {
  initialIndex: 0
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

// State
const currentIndex = ref(props.initialIndex)
const scale = ref(1)
const rotation = ref(0)
const translateX = ref(0)
const translateY = ref(0)
const fitMode = ref<'fit' | 'actual'>('fit')
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const isFullscreen = ref(false)
const imageInfo = ref<{ width: number; height: number } | null>(null)
const imageSize = ref(0)

// Refs
const canvasRef = ref<HTMLElement | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)

// Constants
const minScale = 0.1
const maxScale = 5
const zoomStep = 0.2

// Computed
const currentImage = computed(() => props.images[currentIndex.value]?.src || '')
const currentFilename = computed(() => props.images[currentIndex.value]?.filename || '')

const imageStyle = computed(() => {
  return {
    transform: `translate(${translateX.value}px, ${translateY.value}px) rotate(${rotation.value}deg) scale(${scale.value})`,
    transition: isDragging.value ? 'none' : 'transform 0.3s ease-out',
    cursor: isDragging.value ? 'grabbing' : 'grab'
  }
})

// Methods
const close = () => {
  emit('update:visible', false)
  // Reset state after animation
  setTimeout(() => {
    resetView()
    currentIndex.value = props.initialIndex
  }, 300)
}

const resetView = () => {
  scale.value = 1
  rotation.value = 0
  translateX.value = 0
  translateY.value = 0
  fitMode.value = 'fit'
}

const zoomIn = () => {
  console.log('[ImageViewer] Zoom in, current scale:', scale.value)
  scale.value = Math.min(scale.value + zoomStep, maxScale)
  fitMode.value = 'actual'
  console.log('[ImageViewer] New scale:', scale.value)
}

const zoomOut = () => {
  console.log('[ImageViewer] Zoom out, current scale:', scale.value)
  scale.value = Math.max(scale.value - zoomStep, minScale)
  console.log('[ImageViewer] New scale:', scale.value)
}

const handleWheel = (event: WheelEvent) => {
  console.log('[ImageViewer] Wheel event:', event.deltaY, 'Current scale:', scale.value)
  const delta = event.deltaY > 0 ? -zoomStep : zoomStep
  scale.value = Math.max(minScale, Math.min(maxScale, scale.value + delta))
  fitMode.value = 'actual'
  console.log('[ImageViewer] New scale:', scale.value)
}

const handleSliderChange = () => {
  fitMode.value = 'actual'
}

const toggleFit = () => {
  if (fitMode.value === 'fit') {
    fitMode.value = 'actual'
    scale.value = 1
  } else {
    fitToScreen()
  }
}

const fitToScreen = () => {
  if (!canvasRef.value || !imageRef.value) return

  const canvasRect = canvasRef.value.getBoundingClientRect()
  const imgRect = imageRef.value.getBoundingClientRect()

  const padding = 40
  const availableWidth = canvasRect.width - padding
  const availableHeight = canvasRect.height - padding

  const scaleX = availableWidth / imgRect.width
  const scaleY = availableHeight / imgRect.height
  const fitScale = Math.min(scaleX, scaleY, 1)

  scale.value = fitScale
  translateX.value = 0
  translateY.value = 0
  rotation.value = 0
  fitMode.value = 'fit'
}

const rotateLeft = () => {
  rotation.value = (rotation.value - 90) % 360
}

const rotateRight = () => {
  rotation.value = (rotation.value + 90) % 360
}

const handleMouseDown = (event: MouseEvent) => {
  isDragging.value = true
  dragStart.value = { x: event.clientX - translateX.value, y: event.clientY - translateY.value }
}

const handleMouseMove = (event: MouseEvent) => {
  if (!isDragging.value) return

  translateX.value = event.clientX - dragStart.value.x
  translateY.value = event.clientY - dragStart.value.y
}

const handleMouseUp = () => {
  isDragging.value = false
}

const prevImage = () => {
  if (currentIndex.value > 0) {
    currentIndex.value--
    resetView()
  }
}

const nextImage = () => {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
    resetView()
  }
}

const downloadImage = async () => {
  try {
    const response = await fetch(currentImage.value)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = currentFilename.value || 'image.png'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
    console.error('Download error:', error)
  }
}

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    canvasRef.value?.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

const handleImageLoad = () => {
  if (imageRef.value) {
    imageInfo.value = {
      width: imageRef.value.naturalWidth,
      height: imageRef.value.naturalHeight
    }

    // Calculate file size
    fetch(currentImage.value)
      .then(res => {
        imageSize.value = 0
        const contentLength = res.headers.get('content-length')
        if (contentLength) {
          imageSize.value = parseInt(contentLength)
        }
      })
      .catch(() => {
        imageSize.value = 0
      })

    // Fit to screen on initial load
    nextTick(() => {
      fitToScreen()
    })
  }
}

const handleImageError = () => {
  ElMessage.error('图片加载失败')
}

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

const handleKeyboard = (event: KeyboardEvent) => {
  if (!props.visible) return

  switch (event.key) {
    case 'Escape':
      close()
      break
    case 'ArrowLeft':
      if (props.images.length > 1) prevImage()
      break
    case 'ArrowRight':
      if (props.images.length > 1) nextImage()
      break
    case '+':
    case '=':
      zoomIn()
      break
    case '-':
    case '_':
      zoomOut()
      break
    case '0':
      resetView()
      break
    case 'r':
    case 'R':
      rotateRight()
      break
    case 'f':
    case 'F':
      toggleFullscreen()
      break
  }
}

// Watch for visibility changes to fit image on open
watch(() => props.visible, (newVal) => {
  console.log('[ImageViewer] Visible changed to:', newVal)
  console.log('[ImageViewer] Images:', props.images)
  if (newVal) {
    console.log('[ImageViewer] Opening with images:', props.images)
    nextTick(() => {
      console.log('[ImageViewer] NextTick - calling fitToScreen')
      fitToScreen()
    })
  }
})

// Watch for index changes
watch(currentIndex, () => {
  console.log('[ImageViewer] Current index changed to:', currentIndex.value)
  imageInfo.value = null
  imageSize.value = 0
})

// Lifecycle
onMounted(() => {
  console.log('[ImageViewer] Component mounted')
  document.addEventListener('keydown', handleKeyboard)
  document.addEventListener('fullscreenchange', () => {
    isFullscreen.value = !!document.fullscreenElement
  })
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyboard)
})
</script>

<style scoped>
.image-viewer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.9);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.image-viewer-container {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.toolbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  background-color: rgba(30, 30, 30, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  z-index: 10;
}

.toolbar-left,
.toolbar-center,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.image-title {
  color: var(--el-text-color-primary);
  font-size: 14px;
  font-weight: 500;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-counter {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  padding: 4px 8px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}

.ml-2 {
  margin-left: 8px;
}

.image-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
}

.image-canvas:active {
  cursor: grabbing;
}

.image-wrapper {
  display: inline-block;
  transform-origin: center center;
}

.image-wrapper img {
  display: block;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  user-select: none;
  pointer-events: none;
}

.nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 48px;
  height: 48px;
  background-color: rgba(30, 30, 30, 0.8);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--el-text-color-primary);
  transition: all 0.2s;
  z-index: 5;
}

.nav-arrow:hover {
  background-color: rgba(60, 60, 60, 0.9);
  transform: translateY(-50%) scale(1.1);
}

.nav-arrow-left {
  left: 20px;
}

.nav-arrow-right {
  right: 20px;
}

.zoom-slider-container {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  width: 300px;
  background-color: rgba(30, 30, 30, 0.9);
  padding: 12px 20px;
  border-radius: 8px;
  z-index: 10;
}

.info-panel {
  position: absolute;
  bottom: 20px;
  right: 20px;
  background-color: rgba(30, 30, 30, 0.9);
  padding: 8px 16px;
  border-radius: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  z-index: 10;
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .toolbar {
    background-color: rgba(20, 20, 20, 0.95);
    border-bottom-color: rgba(255, 255, 255, 0.05);
  }
}

/* Ensure button text is visible */
.toolbar-right :deep(.el-button) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.toolbar-right :deep(.el-button span) {
  display: inline;
}
</style>
