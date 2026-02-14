/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div ref="elementRef" class="text-content">
    <div
      class="text-body compact-body compact-markdown"
      :class="{ 'text-body--streaming': isStreaming }"
      v-html="renderedHtml"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useMarkdownParser } from '@/composables/useMarkdownParser'
import type { TextContentBlock } from '@/types/websocket'

interface Props {
  block: TextContentBlock
  isStreaming?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false
})

const elementRef = ref<HTMLElement>()
const textRef = computed(() => props.block.text)

// 流式消息立即解析，历史消息懒加载
const { renderedHtml, reparse } = useMarkdownParser(elementRef, textRef, {
  immediate: props.isStreaming, // 流式消息立即解析
  parseOnIdle: !props.isStreaming // 非流式消息在空闲时解析
})

// 🔥 监听文本变化，在流式传输时重新解析
watch(
  () => props.block.text,
  (newText, oldText) => {
    // ✅ 关键改进：只要文本变化就重新解析（不限于流式传输）
    // 这样可以处理任何形式的文本更新
    if (newText !== oldText && newText) {
      reparse()
    }
  },
  { flush: 'post' } // ✅ 在 DOM 更新后执行，确保能正确渲染
)
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   Text Content - 使用统一紧凑样式系统
   ============================================================================ */

/* 修复横向溢出 */
.text-content {
  max-width: 100%;
  overflow: hidden;
}

.text-body {
  max-width: 100%;
  overflow: hidden;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* 流式输出光标动画 - 功能样式，保留 */
.text-body--streaming::after {
  content: '|';
  animation: blink 1s infinite;
  color: var(--modern-color-text, #1a1a1a);
  font-weight: 400;
  margin-left: 2px;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* 表格样式 - compact-markdown未包含，保留 */
:deep(table) {
  border-collapse: collapse;
  width: 100%;
  max-width: 100%;
  margin: 0.6em 0;
  font-size: var(--modern-font-sm, 12px);
  table-layout: auto;
  overflow: hidden;
}

:deep(th),
:deep(td) {
  border: 1px solid var(--modern-border-light, #e0e0e0);
  padding: 6px 10px;
  text-align: left;
  max-width: 100%;
  overflow: hidden;
  word-wrap: break-word;
}

:deep(th) {
  background: var(--modern-bg-subtle, #fafafa);
  font-weight: 600;
  color: var(--modern-color-text, #1a1a1a);
}

:deep(tr:nth-child(even)) {
  background: var(--modern-bg-subtle, #fafafa);
}

/* 图片样式 - compact-markdown未包含，保留 */
:deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--modern-radius-sm, 6px);
  margin: 0.6em 0;
}
</style>
