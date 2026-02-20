/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div ref="elementRef" class="text-content">
    <div
      class="text-body compact-body markdown-body"
      :class="{ 'text-body--streaming': isStreaming }"
      v-html="renderedHtml"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useMarkdownParser } from '@/composables/useMarkdownParser'
import { useMarkdownSettingsStore } from '@/stores/markdownSettings'
import type { TextContentBlock } from '@/types/websocket'

interface Props {
  block: TextContentBlock
  isStreaming?: boolean
  messageId?: string  // 新增：消息 ID，用于模式切换
}

const props = withDefaults(defineProps<Props>(), {
  isStreaming: false
})

const settingsStore = useMarkdownSettingsStore()

// 获取当前消息的渲染模式
const mode = computed(() => {
  return props.messageId
    ? settingsStore.getMessageMode(props.messageId)
    : settingsStore.defaultMode
})

const elementRef = ref<HTMLElement>()
const textRef = computed(() => props.block.text)

// 使用支持模式的解析器
const { renderedHtml, reparse } = useMarkdownParser(elementRef, textRef, {
  immediate: props.isStreaming,
  parseOnIdle: !props.isStreaming,
  mode: mode  // 传入 computed ref (会自动解包)
})

// 监听文本变化，在流式传输时重新解析
watch(
  () => props.block.text,
  (newText, oldText) => {
    if (newText !== oldText && newText) {
      reparse()
    }
  },
  { flush: 'post' }
)

// 切换模式
const toggleMode = async () => {
  if (props.messageId) {
    settingsStore.toggleMessageMode(props.messageId)
    await nextTick()  // 等待 Vue 响应式更新
    reparse()  // 重新解析
  }
}

// 暴露给父组件使用
defineExpose({
  toggleMode,
  mode
})
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   Text Content - Markdown/纯文本双模式支持
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

/* 操作按钮区域 */
.text-actions {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
  margin-bottom: 4px;
  gap: 6px;
}

.mode-toggle {
  font-size: 11px;
  padding: 4px 10px;
  background: var(--modern-bg-subtle, rgba(0, 0, 0, 0.02));
  border: 1px solid var(--modern-border-light, rgba(0, 0, 0, 0.06));
  border-radius: var(--modern-radius-sm, 6px);
  cursor: pointer;
  transition: all 0.2s ease;
  color: #64748b;
  font-weight: 500;
  font-family: inherit;
  line-height: 1.5;
  display: flex;
  align-items: center;
  gap: 4px;
}

.mode-toggle:hover {
  background: var(--modern-color-primary-light, #e0e3ff);
  color: var(--modern-color-primary, #667eea);
  border-color: var(--modern-color-primary, #667eea);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(102, 126, 234, 0.2);
}

.mode-toggle:active {
  transform: translateY(0);
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

/* ============================================================================
   Markdown 渲染样式
   ============================================================================ */

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 1em 0 0.4em 0;
  font-weight: 600;
  line-height: 1.4;
  color: #1e293b;
}

.markdown-body :deep(h1) {
  font-size: 1.5em;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
}

.markdown-body :deep(h2) {
  font-size: 1.3em;
  margin-top: 1.2em;
}

.markdown-body :deep(h3) {
  font-size: 1.15em;
  margin-top: 1em;
}

.markdown-body :deep(p) {
  margin: 0.6em 0;
  line-height: 1.7;
  color: #374151;
}

.markdown-body :deep(br) {
  content: '';
  display: block;
  margin: 0.5em 0;
}

/* 列表样式 */
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.6em 0;
  padding-left: 1.6em;
}

.markdown-body :deep(li) {
  margin: 0.4em 0;
  line-height: 1.6;
}

.markdown-body :deep(li::marker) {
  color: var(--modern-color-primary, #667eea);
  font-weight: 500;
}

/* 引用样式 */
.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--modern-color-primary, #667eea);
  padding-left: 1em;
  margin: 0.8em 0;
  color: #64748b;
  background: var(--modern-bg-subtle, rgba(0, 0, 0, 0.02));
  padding: 8px 12px;
  border-radius: 0 6px 6px 0;
}

/* 行内代码 */
.markdown-body :deep(code) {
  font-family: 'JetBrains Mono', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  background: var(--modern-bg-subtle, rgba(0, 0, 0, 0.04));
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  color: #dc2626;
  border: 1px solid var(--modern-border-light, rgba(0, 0, 0, 0.06));
}

/* 代码块 */
.markdown-body :deep(pre) {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  border: 1px solid rgba(255, 255, 255, 0.1);
  max-width: 100%;
  margin: 1em 0;
  line-height: 1.5;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  color: inherit;
  font-size: inherit;
}

/* 链接样式 */
.markdown-body :deep(a) {
  color: var(--modern-color-primary, #667eea);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: all 0.2s ease;
}

.markdown-body :deep(a:hover) {
  border-bottom-color: var(--modern-color-primary, #667eea);
}

/* 粗体和斜体 */
.markdown-body :deep(strong) {
  font-weight: 600;
  color: #1e293b;
}

.markdown-body :deep(em) {
  font-style: italic;
  color: #475569;
}

/* 表格样式 - 保留 */
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  max-width: 100%;
  margin: 0.6em 0;
  font-size: var(--modern-font-sm, 12px);
  table-layout: auto;
  overflow: hidden;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--modern-border-light, #e0e0e0);
  padding: 6px 10px;
  text-align: left;
  max-width: 100%;
  overflow: hidden;
  word-wrap: break-word;
}

.markdown-body :deep(th) {
  background: var(--modern-bg-subtle, #fafafa);
  font-weight: 600;
  color: var(--modern-color-text, #1a1a1a);
}

.markdown-body :deep(tr:nth-child(even)) {
  background: var(--modern-bg-subtle, #fafafa);
}

/* 图片样式 - 保留 */
.markdown-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--modern-radius-sm, 6px);
  margin: 0.6em 0;
}

/* 水平分割线 */
.markdown-body :deep(hr) {
  border: none;
  border-top: 2px solid #e2e8f0;
  margin: 1.5em 0;
}

/* ============================================================================
   深色模式支持
   ============================================================================ */
@media (prefers-color-scheme: dark) {
  .markdown-body :deep(h1),
  .markdown-body :deep(h2),
  .markdown-body :deep(h3),
  .markdown-body :deep(h4),
  .markdown-body :deep(h5),
  .markdown-body :deep(h6) {
    color: #e2e8f0;
  }

  .markdown-body :deep(p) {
    color: #cbd5e1;
  }

  .markdown-body :deep(blockquote) {
    color: #94a3b8;
    background: rgba(255, 255, 255, 0.03);
    border-left-color: #8b5cf6;
  }

  .markdown-body :deep(code) {
    background: rgba(255, 255, 255, 0.05);
    color: #fca5a5;
    border-color: rgba(255, 255, 255, 0.08);
  }

  .markdown-body :deep(strong) {
    color: #e2e8f0;
  }

  .markdown-body :deep(em) {
    color: #cbd5e1;
  }

  .markdown-body :deep(li::marker) {
    color: #8b5cf6;
  }

  .mode-toggle {
    background: rgba(255, 255, 255, 0.05);
    color: #94a3b8;
    border-color: rgba(255, 255, 255, 0.08);
  }

  .mode-toggle:hover {
    background: rgba(139, 92, 246, 0.15);
    color: #a78bfa;
    border-color: #8b5cf6;
  }
}
</style>
