/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="video-content">
    <div class="video-container">
      <video
        ref="videoRef"
        :src="block.video"
        controls
        :poster="poster"
        @loadstart="handleLoadStart"
        @canplay="handleCanPlay"
        @error="handleError"
      >
        您的浏览器不支持视频播放
      </video>
      <div v-if="isLoading" class="video-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载视频中...</span>
      </div>
    </div>
    <div v-if="block.filename || block.format" class="video-info compact-mt-sm">
      <span v-if="block.filename" class="filename compact-code">{{ block.filename }}</span>
      <span v-if="block.format" class="format compact-tag">{{ block.format.toUpperCase() }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import type { VideoContentBlock } from '@/types/websocket'

defineProps<{
  block: VideoContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

const videoRef = ref<HTMLVideoElement>()
const isLoading = ref(true)

// 生成视频缩略图（这里简化处理，实际项目中可能需要后端支持）
const poster = computed(() => {
  // 如果有自定义poster，使用自定义的
  // 否则可以使用视频的第一帧作为缩略图
  return ''
})

const handleLoadStart = () => {
  isLoading.value = true
}

const handleCanPlay = () => {
  isLoading.value = false
}

const handleError = (event: Event) => {
  isLoading.value = false
  const video = event.target as HTMLVideoElement

  // 发送错误事件
  emit('contentAction', 'video-error', {
    src: video.src,
    error: 'Failed to load video'
  })
}
</script>

<style scoped>
/* ============================================================================
   Video Content - 使用统一紧凑样式系统
   ============================================================================ */

.video-content {
  max-width: 100%;
}

.video-container {
  position: relative;
  margin-bottom: var(--modern-spacing-sm, 8px);
  max-width: 100%;
}

.video-container video {
  width: 100%;
  height: auto;
  border-radius: var(--modern-radius-md, 8px);
  box-shadow: var(--modern-shadow-md, 0 2px 8px rgba(0, 0, 0, 0.08));
}

/* 加载状态 - 功能性样式，保留 */
.video-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--modern-spacing-sm, 8px);
  padding: var(--modern-spacing-lg, 16px);
  background-color: var(--modern-bg-elevated, rgba(0, 0, 0, 0.75));
  border-radius: var(--modern-radius-md, 8px);
  color: white;
  font-size: var(--modern-font-sm, 12px);
}

/* 视频信息 - 使用紧凑样式 */
.video-info {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm, 8px);
  flex-wrap: wrap;
}

.filename {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.format {
  font-size: var(--modern-font-xs, 11px);
  text-transform: uppercase;
}
</style>
