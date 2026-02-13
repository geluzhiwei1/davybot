/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="theme-toggle-wrapper">
    <el-button
      @click="handleToggle"
      class="theme-toggle-btn"
      :class="`theme-${currentTheme}`"
      :title="`当前主题: ${currentTheme === 'light' ? '明亮' : '深色'} - 点击切换`"
      :icon="isLight ? Sunny : Moon"
      circle
      text
    />


    <!-- 主题切换提示 -->
    <transition name="toast">
      <div v-if="showToast" class="theme-toast">
        已切换到{{ currentTheme === 'light' ? '明亮' : '深色' }}主题
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { Sunny, Moon } from '@element-plus/icons-vue'
import { useTheme } from '@/themes/composables/useTheme'

// 使用主题composable
const { currentTheme, toggleTheme: switchTheme, setTheme } = useTheme()

// 提示状态
const showToast = ref(false)
const toastTimer = ref<number | null>(null)

// 是否为浅色主题
const isLight = computed(() => currentTheme.value === 'light')

/**
 * 处理切换按钮点击
 */
function handleToggle() {
  switchTheme()
  showToast.value = true
  hideToastAfterDelay()
}

/**
 * 延迟隐藏提示
 */
function hideToastAfterDelay() {
  if (toastTimer.value) {
    clearTimeout(toastTimer.value)
  }
  toastTimer.value = window.setTimeout(() => {
    showToast.value = false
  }, 2000)
}

onUnmounted(() => {
  if (toastTimer.value) {
    clearTimeout(toastTimer.value)
  }
})

// 暴露方法供外部调用
defineExpose({
  toggleTheme: handleToggle,
  setTheme,
  currentTheme,
})
</script>

<style scoped>
.theme-toggle-wrapper {
  position: relative;
  display: inline-block;
}

.theme-toggle-btn {
  font-size: 18px;
}

/* 提示消息 */
.theme-toast {
  position: fixed;
  top: 60px;
  right: 10px;
  padding: 8px 16px;
  background: var(--theme-bg-primary, #FFFFFF);
  border: 1px solid var(--theme-border, #DCDFE6);
  border-left: 4px solid var(--theme-success, #67C23A);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 12px;
  color: var(--theme-text-primary, #303133);
  z-index: 10001;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* 提示消息动画 */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
