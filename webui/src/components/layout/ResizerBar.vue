/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div
    :class="['resizer-bar', { 'is-dragging': isDragging }]"
    @mousedown="handleMouseDown"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  panelRef: { width: number };
  minWidth: number;
  maxWidth: number;
  storageKey?: string;
  position?: 'left' | 'right';  // 新增：标识分隔条位置
}>();

const emit = defineEmits<{
  resize: [width: number];
}>();

const isDragging = ref(false);

const handleMouseDown = (e: MouseEvent) => {
  e.preventDefault();
  isDragging.value = true;

  const startX = e.clientX;
  const startWidth = props.panelRef.width;

  // 添加拖动时的临时样式
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';

  const handleMouseMove = (e: MouseEvent) => {
    const deltaX = e.clientX - startX;
    let newWidth: number;

    // 根据分隔条位置决定宽度计算方式
    if (props.position === 'right') {
      // 右侧面板：向右拖动应该增加宽度，向左应该减少
      // 但由于布局方向，需要反转 delta
      newWidth = startWidth - deltaX;
    } else {
      // 左侧面板（默认）：向右拖动增加宽度
      newWidth = startWidth + deltaX;
    }

    // 限制在最小/最大宽度之间
    newWidth = Math.max(props.minWidth, Math.min(props.maxWidth, newWidth));

    // 实时更新宽度
    emit('resize', newWidth);
  };

  const handleMouseUp = () => {
    isDragging.value = false;

    // 移除拖动样式
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);

    // 拖动结束后保存到 localStorage
    if (props.storageKey) {
      localStorage.setItem(props.storageKey, props.panelRef.width.toString());
    }
  };

  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
};
</script>

<style scoped>
.resizer-bar {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s, width 0.2s;
  flex-shrink: 0;
  user-select: none;
  position: relative;
  z-index: 100;
}

.resizer-bar:hover {
  background: rgba(var(--color-primary-rgb), 0.3);
}

.resizer-bar.is-dragging {
  background: var(--color-primary);
  width: 6px;
}

/* 防止拖动时选中其他元素 */
.resizer-bar.is-dragging::after {
  content: '';
  position: fixed;
  inset: 0;
  cursor: col-resize;
  z-index: 9999;
}
</style>
