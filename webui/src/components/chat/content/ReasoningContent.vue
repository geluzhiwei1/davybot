/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div ref="elementRef" class="reasoning-content">
    <!-- Title bar -->
    <div class="reasoning-header">
      <svg class="reasoning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="4" y="4" width="16" height="16" rx="2"/>
        <path d="M9 9h6M9 12h6M9 15h4"/>
      </svg>
      <span class="reasoning-title">推理过程</span>
    </div>

    <!-- Content (collapsible) -->
    <div v-show="isExpanded" class="reasoning-body">
      <div
        ref="reasoningElementRef"
        class="reasoning-text markdown-body"
        v-html="renderedHtml"
      ></div>

      <!-- Raw text view -->
      <div v-if="showRaw" class="reasoning-raw">
        <pre>{{ block.reasoning }}</pre>
      </div>
    </div>

    <!-- Actions toolbar (at bottom, like main message) -->
    <div class="reasoning-actions assistant-actions">
      <el-button
        size="small"
        circle
        @click="copyReasoning"
        title="复制"
      >
        <el-icon><DocumentCopy /></el-icon>
      </el-button>
      <el-button
        size="small"
        circle
        @click="toggleRawView"
        title="查看原文"
      >
        <el-icon><View /></el-icon>
      </el-button>
      <el-button
        size="small"
        circle
        @click="toggleExpand"
        title="折叠/展开"
      >
        <el-icon :class="{ 'rotate-180': isExpanded }">
          <ArrowDown />
        </el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElButton, ElIcon } from 'element-plus'
import { DocumentCopy, View, ArrowDown } from '@element-plus/icons-vue'
import { useMarkdownParser } from '@/composables/useMarkdownParser'
import type { ReasoningContentBlock } from '@/types/websocket'
import { copyToClipboard } from '@/utils/clipboard'

const props = defineProps<{
  block: ReasoningContentBlock
}>()

const elementRef = ref<HTMLElement>()
const reasoningElementRef = ref<HTMLElement>()
const isExpanded = ref(true)
const showRaw = ref(false)

const textRef = computed(() => props.block.reasoning)

// 推理内容解析（立即解析）
const { renderedHtml } = useMarkdownParser(reasoningElementRef, textRef, {
  immediate: true,
  parseOnIdle: false
})

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const toggleRawView = () => {
  showRaw.value = !showRaw.value
}

const copyReasoning = async () => {
  // 复制清理后的内容
  const success = await copyToClipboard(textRef.value || '')
  if (success) {
    ElMessage.success('推理内容已复制')
  } else {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   Reasoning Content - 与主消息气泡完全一致的样式
   ============================================================================ */

.reasoning-content {
  max-width: 100%;
  overflow: hidden;
  margin-bottom: var(--modern-spacing-sm, 8px);
}

/* Title bar */
.reasoning-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--modern-spacing-xs, 4px);
  margin-bottom: var(--modern-spacing-xs, 4px);
}

.reasoning-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: #64748b;
}

.reasoning-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}

/* Content body */
.reasoning-body {
  max-width: 100%;
  overflow: hidden;
  padding: var(--modern-spacing-xs, 4px);
}

.reasoning-text {
  font-size: var(--modern-font-sm, 12px);
  line-height: 1.6;
  color: #4a5568;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* Raw text */
.reasoning-raw {
  margin-top: var(--modern-spacing-sm, 8px);
  padding: var(--modern-spacing-sm, 8px);
  background: var(--modern-bg-subtle, rgba(0, 0, 0, 0.03));
  border-radius: var(--modern-radius-sm, 6px);
  border: 1px solid var(--modern-border-light, rgba(0, 0, 0, 0.08));
}

.reasoning-raw pre {
  margin: 0;
  font-size: var(--modern-font-xs, 11px);
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Courier New', Courier, monospace;
  color: #2d3748;
}

/* Actions toolbar - 精简版 */
.reasoning-actions {
  display: flex;
  gap: 6px;
  padding: 0;
  justify-content: flex-start;
}

.reasoning-actions .el-button {
  color: #94a3b8;
  background: transparent;
  border: none;
}

.reasoning-actions .el-button:hover {
  color: #06b6d4;
  background: transparent;
}

/* Arrow rotation animation */
.rotate-180 {
  transform: rotate(180deg);
}
</style>
