/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="audio-content">
    <div class="audio-player">
      <audio
        ref="audioRef"
        :src="block.audio"
        controls
        @loadstart="handleLoadStart"
        @canplay="handleCanPlay"
        @error="handleError"
      >
        您的浏览器不支持音频播放
      </audio>
      <div v-if="isLoading" class="audio-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载音频中...</span>
      </div>
    </div>
    <div v-if="block.filename || block.format" class="audio-info compact-mt-sm">
      <span v-if="block.filename" class="filename compact-code">{{ block.filename }}</span>
      <span v-if="block.format" class="format compact-tag">{{ block.format.toUpperCase() }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import type { AudioContentBlock } from '@/types/websocket'

defineProps<{
  block: AudioContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

const audioRef = ref<HTMLAudioElement>()
const isLoading = ref(true)

const handleLoadStart = () => {
  isLoading.value = true
}

const handleCanPlay = () => {
  isLoading.value = false
}

const handleError = (event: Event) => {
  isLoading.value = false
  const audio = event.target as HTMLAudioElement

  // 发送错误事件
  emit('contentAction', 'audio-error', {
    src: audio.src,
    error: 'Failed to load audio'
  })
}
</script>

<style scoped>
/* ============================================================================
   Audio Content - 使用统一紧凑样式系统
   ============================================================================ */

.audio-content {
  max-width: 100%;
}

.audio-player {
  position: relative;
  margin-bottom: var(--modern-spacing-sm, 8px);
}

audio {
  width: 100%;
  max-width: 400px;
  border-radius: var(--modern-radius-md, 8px);
  box-shadow: var(--modern-shadow-md, 0 2px 8px rgba(0, 0, 0, 0.08));
}

/* 加载状态 - 功能性样式，保留 */
.audio-loading {
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

/* 音频信息 - 使用紧凑样式 */
.audio-info {
  display: flex;
  gap: var(--modern-spacing-sm, 8px);
  align-items: center;
  font-size: var(--modern-font-sm, 12px);
  color: var(--el-text-color-secondary, #64748b);
}
</style>
