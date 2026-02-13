/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="loading-indicator">
    <div class="avatar-container">
      <el-icon :size="20" class="thinking-icon">
        <Cpu />
      </el-icon>
    </div>
    <div class="loading-content">
      <div class="loading-text">{{ loadingText }}</div>
      <div class="loading-dots">
        <span class="dot" :class="{ active: dotIndex === 0 }"></span>
        <span class="dot" :class="{ active: dotIndex === 1 }"></span>
        <span class="dot" :class="{ active: dotIndex === 2 }"></span>
      </div>
      <div v-if="showThinking" class="thinking-preview">
        <el-collapse v-model="activeThinking">
          <el-collapse-item name="thinking">
            <template #title>
              <div class="thinking-title">
                <el-icon><Loading /></el-icon>
                <span>思考中...</span>
              </div>
            </template>
            <div class="thinking-content">
              <div v-if="currentThinking" class="current-thinking">
                {{ currentThinking }}
              </div>
              <div v-else class="placeholder-thinking">
                正在分析您的问题...
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Cpu, Loading } from '@element-plus/icons-vue'

interface Props {
  type?: 'thinking' | 'processing' | 'connecting'
  showThinking?: boolean
  currentThinking?: string
}

const props = withDefaults(defineProps<Props>(), {
  type: 'thinking',
  showThinking: false,
  currentThinking: ''
})

const dotIndex = ref(0)
const activeThinking = ref(['thinking'])
let intervalId: number | null = null

const loadingText = computed(() => {
  switch (props.type) {
    case 'thinking':
      return '正在思考'
    case 'processing':
      return '正在处理'
    case 'connecting':
      return '正在连接'
    default:
      return '加载中'
  }
})

onMounted(() => {
  // 创建动画效果
  intervalId = setInterval(() => {
    dotIndex.value = (dotIndex.value + 1) % 3
  }, 400)
})

onUnmounted(() => {
  if (intervalId) {
    clearInterval(intervalId)
  }
})
</script>

<style scoped>
.loading-indicator {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  animation: fadeInUp 0.3s ease-out forwards;
}

.avatar-container {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: relative;
}

.thinking-icon {
  animation: pulse 2s infinite;
}

.loading-content {
  background-color: var(--el-bg-color);
  padding: 12px 16px;
  border-radius: 12px 12px 12px 4px;
  border: 1px solid var(--el-border-color-lighter);
  flex: 1;
  max-width: 80%;
  box-shadow: var(--el-box-shadow-light);
}

.loading-text {
  font-size: 14px;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-dots {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--el-text-color-placeholder);
  transition: all 0.3s ease;
}

.dot.active {
  background-color: var(--el-color-primary);
  transform: scale(1.2);
}

.thinking-preview {
  margin-top: 8px;
}

.thinking-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.thinking-content {
  padding: 8px 0;
}

.current-thinking {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  font-style: italic;
}

.placeholder-thinking {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

:deep(.el-collapse) {
  border: none;
}

:deep(.el-collapse-item__header) {
  border: none;
  padding: 0;
  height: auto;
  line-height: normal;
  font-size: 13px;
}

:deep(.el-collapse-item__content) {
  padding: 0;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}
</style>