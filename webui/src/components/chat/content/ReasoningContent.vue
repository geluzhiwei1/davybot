/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="reasoning compact-content">
    <el-collapse v-model="activeNames" class="reasoning-collapse compact-collapse">
      <el-collapse-item name="reasoning">
        <template #title>
          <div class="reasoning-header compact-header">
            <svg class="reasoning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="4" y="4" width="16" height="16" rx="2"/>
              <path d="M9 9h6M9 12h6M9 15h4"/>
            </svg>
            <span class="compact-title">推理过程</span>
            <span class="reasoning-depth compact-tag">{{ reasoningDepth }}</span>
          </div>
        </template>

        <div class="reasoning-body compact-body">
          <!-- Reasoning text -->
          <div
            ref="reasoningElementRef"
            class="reasoning-text compact-markdown"
            v-html="renderedHtml"
          ></div>

          <!-- Stats -->
          <div class="reasoning-stats compact-stats">
            <div class="stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span>{{ charCount }} 字符</span>
            </div>
            <div class="stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              <span>{{ estimatedTime }}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="reasoning-actions compact-actions">
            <button class="compact-btn" @click.stop="copyReasoning">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              复制
            </button>
            <button class="compact-btn" @click.stop="toggleRawView">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              {{ showRaw ? '隐藏' : '查看' }}
            </button>
          </div>

          <!-- Raw text -->
          <div v-if="showRaw" class="reasoning-raw compact-detail-block">
            <pre class="compact-pre">{{ block.reasoning }}</pre>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef } from 'vue'
import { ElCollapse, ElCollapseItem, ElMessage } from 'element-plus'
import { useMarkdownParser } from '@/composables/useMarkdownParser'
import type { ReasoningContentBlock } from '@/types/websocket'
import { copyToClipboard } from '@/utils/clipboard'

const props = defineProps<{
  block: ReasoningContentBlock
}>()

const activeNames = ref<string[]>([])
const showRaw = ref(false)
const reasoningElementRef = ref<HTMLElement>()

const textRef = toRef(props.block, 'reasoning')

// 推理内容使用懒加载解析（只在展开且可见时解析）
const { renderedHtml } = useMarkdownParser(reasoningElementRef, textRef, {
  immediate: false,
  parseOnIdle: true
})

// 监听展开状态，展开时触发解析
watch(activeNames, (newNames) => {
  if (newNames.includes('reasoning') && reasoningElementRef.value) {
    // 折叠面板已展开，元素可能可见
    // IntersectionObserver 会自动处理
  }
})

const reasoningDepth = computed(() => {
  const text = props.block.reasoning || ''
  const nestingLevel = (text.match(/\d+\./g) || []).length
  return Math.min(nestingLevel, 10)
})

const charCount = computed(() => {
  return (props.block.reasoning || '').length
})

const estimatedTime = computed(() => {
  const chars = charCount.value
  if (chars < 500) return '< 1分钟'
  if (chars < 2000) return '1-3分钟'
  if (chars < 5000) return '3-5分钟'
  return '> 5分钟'
})

const toggleRawView = () => {
  showRaw.value = !showRaw.value
}

const copyReasoning = async () => {
  const success = await copyToClipboard(props.block.reasoning || '')
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
   Reasoning Content - 使用统一紧凑样式系统
   ============================================================================ */

/* 推理图标 - 功能性样式，保留 */
.reasoning-icon {
  width: 16px;
  height: 16px;
  color: #8b7355;
  flex-shrink: 0;
}

/* 推理深度标签 - 功能性样式，保留 */
.reasoning-depth {
  font-size: var(--modern-font-xs, 10px);
  font-weight: 600;
  background: #e8e6e3;
  color: #6b5b4a;
  letter-spacing: 0.05em;
}

/* 推理文本 - 使用紧凑Markdown样式 */
.reasoning-text {
  font-size: var(--modern-font-sm, 12px);
  line-height: 1.5;
  color: #4a4a4a;
  margin-bottom: var(--modern-spacing-sm, 10px);
}

/* 统计信息 - 使用紧凑样式，保留功能 */
.stat {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-xs, 4px);
  font-size: var(--modern-font-xs, 11px);
  color: #666;
  font-weight: 500;
}

.stat svg {
  width: 14px;
  height: 14px;
  color: #8b7355;
}

/* 按钮图标样式 */
button svg {
  width: 14px;
  height: 14px;
}
</style>
