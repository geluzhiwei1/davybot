/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div>
    <!-- Backdrop -->
    <transition name="backdrop-fade">
      <div
        v-if="visible && showBackdrop"
        class="slide-out-backdrop"
        @click="handleBackdropClick"
      ></div>
    </transition>

    <!-- Panel -->
    <transition
      :name="position === 'right' ? 'slide-right' : 'slide-left'"
      @after-enter="handleAfterEnter"
      @after-leave="handleAfterLeave"
    >
      <div
        v-if="visible"
        class="slide-out-panel"
        :class="[`slide-out-panel--${position}`, { 'slide-out-panel--fullscreen': isFullScreen }]"
        :style="panelStyle"
      >
        <!-- Header -->
        <div v-if="showHeader || $slots.header" class="slide-out-header">
          <div class="header-left">
            <slot name="header">
              <h3 class="header-title">{{ title }}</h3>
              <el-tag v-if="badge !== undefined" :type="badgeType" size="small">
                {{ badge }}
              </el-tag>
            </slot>
          </div>
          <div class="header-right">
            <slot name="header-actions"></slot>
            <el-button
              v-if="showCloseButton"
              :icon="Close"
              circle
              size="small"
              text
              @click="handleClose"
            />
          </div>
        </div>

        <!-- Body -->
        <div class="slide-out-body">
          <slot></slot>
        </div>

        <!-- Footer -->
        <div v-if="$slots.footer" class="slide-out-footer">
          <slot name="footer"></slot>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { ElButton, ElTag } from 'element-plus'
import { Close } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    position?: 'left' | 'right'
    width?: string
    maxWidth?: string
    title?: string
    badge?: number | string
    badgeType?: 'success' | 'warning' | 'danger' | 'info' | 'primary'
    showHeader?: boolean
    showCloseButton?: boolean
    showBackdrop?: boolean
    closeOnClickOutside?: boolean
    closeOnEscape?: boolean
    fullScreenOnMobile?: boolean
  }>(),
  {
    position: 'right',
    width: '500px',
    maxWidth: '60vw',
    title: '',
    badgeType: 'primary',
    showHeader: true,
    showCloseButton: true,
    showBackdrop: true,
    closeOnClickOutside: true,
    closeOnEscape: true,
    fullScreenOnMobile: true
  }
)

const emit = defineEmits<{
  'update:visible': [value: boolean]
  close: []
  'before-open': []
  'after-open': []
  'before-close': []
  'after-close': []
}>()

const panelStyle = computed(() => ({
  width: isFullScreen.value ? '100vw' : props.width,
  maxWidth: isFullScreen.value ? '100vw' : props.maxWidth
}))

const isFullScreen = computed(() => {
  if (!props.fullScreenOnMobile) return false
  return window.innerWidth < 768
})

function handleClose() {
  emit('before-close')
  emit('update:visible', false)
  emit('close')
}

function handleBackdropClick() {
  if (props.closeOnClickOutside) {
    handleClose()
  }
}

function handleAfterEnter() {
  emit('after-open')
}

function handleAfterLeave() {
  emit('after-close')
}

// Handle escape key
function handleEscape(event: KeyboardEvent) {
  if (props.visible && props.closeOnEscape && event.key === 'Escape') {
    handleClose()
  }
}

onMounted(() => {
  if (props.closeOnEscape) {
    document.addEventListener('keydown', handleEscape)
  }
})

onUnmounted(() => {
  if (props.closeOnEscape) {
    document.removeEventListener('keydown', handleEscape)
  }
})
</script>

<style scoped>
/* Backdrop */
.backdrop-fade-enter-active,
.backdrop-fade-leave-active {
  transition: opacity 0.3s ease;
}

.backdrop-fade-enter-from,
.backdrop-fade-leave-to {
  opacity: 0;
}

.slide-out-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 999;
}

/* Panel */
.slide-out-panel {
  position: fixed;
  top: 64px; /* Below TopBar */
  bottom: 0;
  background: var(--el-bg-color-overlay);
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.slide-out-panel--right {
  right: 0;
}

.slide-out-panel--left {
  left: 0;
}

.slide-out-panel--fullscreen {
  top: 0;
  width: 100vw !important;
  max-width: 100vw !important;
  border-radius: 0;
}

/* Slide animations */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(-100%);
}

/* Header */
.slide-out-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-extra-light);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.header-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* Body */
.slide-out-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
}

/* Footer */
.slide-out-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-extra-light);
  flex-shrink: 0;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .slide-out-backdrop {
    background: rgba(0, 0, 0, 0.5);
  }

  .slide-out-panel {
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .slide-out-panel {
    top: 56px; /* Smaller header on mobile */
  }

  .slide-out-header {
    padding: 12px 16px;
  }

  .slide-out-body {
    padding: 0;
  }

  .slide-out-footer {
    padding: 12px 16px;
  }
}
</style>
