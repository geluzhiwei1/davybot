/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="collapsible-message" :class="{ 'is-collapsed': isCollapsed }">
    <div
      ref="contentRef"
      class="message-content"
      :style="{ maxHeight: isCollapsed ? `${maxHeight}px` : 'none' }"
    >
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

interface Props {
  maxHeight?: number
  autoCollapse?: boolean
  collapsed?: boolean  // 外部控制的折叠状态
}

const props = withDefaults(defineProps<Props>(), {
  maxHeight: 400,
  autoCollapse: true,
  collapsed: false
})

const contentRef = ref<HTMLElement>()
const isCollapsed = ref(false)
const showToggleButton = ref(false)
const userManuallyExpanded = ref(false) // 标记用户是否手动展开过

// 监听外部 collapsed prop 的变化
watch(() => props.collapsed, (newValue) => {
  isCollapsed.value = newValue
  if (!newValue) {
    userManuallyExpanded.value = true
  }
})

const checkHeight = () => {
  try {
    if (!contentRef.value) {
      console.warn('[CollapsibleMessage] contentRef not available')
      return
    }

    const scrollHeight = contentRef.value.scrollHeight
    const clientHeight = contentRef.value.clientHeight

    console.log('[CollapsibleMessage] Height check:', {
      scrollHeight,
      clientHeight,
      maxHeight: props.maxHeight,
      shouldShow: scrollHeight > props.maxHeight,
      userManuallyExpanded: userManuallyExpanded.value
    })

    showToggleButton.value = scrollHeight > props.maxHeight

    // 只在用户未手动展开过的情况下才自动折叠
    if (props.autoCollapse && scrollHeight > props.maxHeight && !userManuallyExpanded.value && !props.collapsed) {
      isCollapsed.value = true
      console.log('[CollapsibleMessage] Auto-collapsing content')
    }
  } catch (error) {
    console.error('[CollapsibleMessage] Error checking height:', error)
    // 如果出错，仍然显示按钮以防万一
    showToggleButton.value = true
    isCollapsed.value = false
  }
}

const toggleCollapse = () => {
  console.log('[CollapsibleMessage] Toggle clicked, current state:', isCollapsed.value)
  try {
    const newState = !isCollapsed.value
    isCollapsed.value = newState

    // 如果用户手动展开了，设置标记以防止自动折叠
    if (newState === false) {
      userManuallyExpanded.value = true
      console.log('[CollapsibleMessage] User manually expanded, preventing auto-collapse')
    }

    console.log('[CollapsibleMessage] New state:', isCollapsed.value)
  } catch (error) {
    console.error('Error toggling collapse:', error)
    // 如果出错，确保状态被重置
    isCollapsed.value = false
  }
}

onMounted(() => {
  console.log('[CollapsibleMessage] Component mounted')

  // 初始化状态
  if (props.collapsed) {
    isCollapsed.value = true
  }

  // 等待内容渲染完成后检查高度（多次尝试以处理动态加载的内容）
  nextTick(() => {
    checkHeight()
    // 延迟再次检查，确保所有内容都已渲染
    setTimeout(() => checkHeight(), 100)
    setTimeout(() => checkHeight(), 500)
  })

  // 使用 ResizeObserver 监听内容变化
  if (contentRef.value) {
    const resizeObserver = new ResizeObserver(() => {
      console.log('[CollapsibleMessage] Content resized, rechecking height')
      checkHeight()
    })
    resizeObserver.observe(contentRef.value)

    onUnmounted(() => {
      resizeObserver.disconnect()
    })
  }
})

// 暴露方法供外部调用
defineExpose({
  checkHeight,
  toggleCollapse
})
</script>

<style scoped>
.collapsible-message {
  position: relative;
}

.message-content {
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.message-content.is-collapsed {
  mask-image: linear-gradient(to bottom, black 70%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, black 70%, transparent 100%);
}
</style>
