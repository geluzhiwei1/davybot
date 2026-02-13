/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="system-command-result compact-content">
    <!-- Command Header -->
    <div class="command-header compact-header">
      <div class="command-input">
        <span class="prompt">{{ prompt }}</span>
        <code class="command-text compact-code">{{ block.command }}</code>
      </div>
      <div class="command-meta">
        <el-tag
          :type="getStatusTagType(block.exitCode)"
          size="small"
          class="exit-code-tag compact-tag"
        >
          Exit: {{ block.exitCode }}
        </el-tag>
        <span v-if="block.executionTime" class="execution-time">
          {{ block.executionTime }}ms
        </span>
        <el-button
          size="small"
          text
          @click="copyOutput"
          class="compact-btn"
        >
          <el-icon><CopyDocument /></el-icon>
          Copy
        </el-button>
      </div>
    </div>

    <!-- Command Output -->
    <div class="command-output compact-body" :class="{ 'has-error': hasError }">
      <!-- Standard Output -->
      <div v-if="block.stdout" class="output-section stdout">
        <pre><code>{{ formatOutput(block.stdout) }}</code></pre>
      </div>

      <!-- Error Output -->
      <div v-if="block.stderr" class="output-section stderr">
        <div class="section-header">
          <el-icon><Warning /></el-icon>
          <span>STDERR</span>
        </div>
        <pre><code>{{ formatOutput(block.stderr) }}</code></pre>
      </div>

      <!-- File List Special Format -->
      <div v-if="isFileList" class="file-list-output">
        <FileListOutput :content="block.stdout || ''" />
      </div>

      <!-- JSON Special Format -->
      <div v-if="isJsonOutput" class="json-output">
        <JsonViewer :data="jsonData" />
      </div>
    </div>

    <!-- Working Directory -->
    <div v-if="block.cwd" class="working-directory">
      <el-icon><Folder /></el-icon>
      <span>{{ block.cwd }}</span>
    </div>

    <!-- Collapse/Expand Button -->
    <div v-if="isLongOutput" class="toggle-section">
      <el-button size="small" text @click="toggleExpanded" class="compact-btn">
        <el-icon>
          <component :is="expanded ? ArrowUp : ArrowDown" />
        </el-icon>
        {{ expanded ? 'Collapse' : 'Expand' }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { CopyDocument, Warning, ArrowUp, ArrowDown, Folder } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { SystemCommandResultContentBlock } from '@/types/websocket'
import { copyToClipboard } from '@/utils/clipboard'
import FileListOutput from './FileListOutput.vue'
import JsonViewer from './JsonViewer.vue'

const props = defineProps<{
  block: SystemCommandResultContentBlock
}>()

const expanded = ref(false)
const prompt = '$'

const hasError = computed(() => props.block.exitCode !== 0)

const isLongOutput = computed(() => {
  const totalLength = (props.block.stdout || '').length + (props.block.stderr || '').length
  return totalLength > 2000
})

// Detect output type
const isFileList = computed(() => {
  // ls command output
  return props.block.command.includes('ls') && props.block.stdout
})

const isJsonOutput = computed(() => {
  try {
    JSON.parse(props.block.stdout || '')
    return true
  } catch {
    return false
  }
})

const jsonData = computed(() => {
  if (!isJsonOutput.value) return null
  try {
    return JSON.parse(props.block.stdout || '')
  } catch {
    return null
  }
})

const getStatusTagType = (exitCode: number) => {
  if (exitCode === 0) return 'success'
  if (exitCode === 1) return 'warning'
  return 'danger'
}

const formatOutput = (output: string) => {
  if (!output) return ''
  // Preserve newlines and spaces
  return output
}

const copyOutput = async () => {
  const text = [props.block.stdout, props.block.stderr]
    .filter(Boolean)
    .join('\n')

  const success = await copyToClipboard(text)
  if (success) {
    ElMessage.success('Copied to clipboard')
  }
}

const toggleExpanded = () => {
  expanded.value = !expanded.value
}
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   System Command Result - 使用统一紧凑样式系统 + 终端风格
   ============================================================================ */

/* 系统命令结果 - 保留终端特色风格 */
.system-command-result {
  /* 终端风格背景 - 特殊样式，保留 */
  background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
  border: 1px solid #404040;
}

/* 命令头部 - 使用紧凑样式，保留终端风格 */
.command-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--modern-spacing-sm, 8px);
  background: linear-gradient(135deg, #2d2d2d 0%, #3d3d3d 100%);
  border-bottom: 1px solid #404040;
}

.command-input {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm, 8px);
  flex: 1;
  min-width: 0;
}

.prompt {
  color: #4CAF50;  /* Green prompt - 终端风格，保留 */
  font-family: var(--font-mono, 'Monaco', 'Menlo', 'Consolas', monospace);
  font-weight: bold;
  font-size: var(--modern-font-md, 14px);
  flex-shrink: 0;
}

.command-text {
  color: #fff;
  font-family: var(--font-mono, 'Monaco', 'Menlo', 'Consolas', monospace);
  background: rgba(255, 255, 255, 0.05);
  overflow-x: auto;
  white-space: nowrap;
}

.command-meta {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-md, 12px);
  flex-shrink: 0;
}

.execution-time {
  color: #9e9e9e;
  font-size: var(--modern-font-sm, 12px);
  font-family: var(--font-mono, monospace);
}

/* 命令输出 - 使用紧凑样式 */
.command-output {
  max-height: 400px;
  overflow-y: auto;
  padding: var(--modern-spacing-md, 12px) var(--modern-spacing-lg, 16px);
}

.command-output.collapsed {
  max-height: 100px;
}

.command-output.has-error {
  border-left: 3px solid var(--modern-color-danger, #f56c6c);
}

.output-section {
  padding: var(--modern-spacing-md, 12px) 0;
}

.output-section.stdout {
  color: #e0e0e0;
}

.output-section.stderr {
  background: rgba(245, 108, 108, 0.1);
  border-top: 1px solid #404040;
  margin-top: var(--modern-spacing-sm, 8px);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-xs, 6px);
  margin-bottom: var(--modern-spacing-sm, 8px);
  color: var(--modern-color-danger, #f56c6c);
  font-size: var(--modern-font-sm, 12px);
  font-weight: 600;
}

pre {
  margin: 0;
  padding: 0;
}

code {
  font-family: var(--font-mono, 'Monaco', 'Menlo', 'Consolas', 'monospace');
  font-size: var(--modern-font-sm, 12px);
  line-height: 1.6;
  color: inherit;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.working-directory {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-xs, 6px);
  padding: var(--modern-spacing-sm, 8px) var(--modern-spacing-lg, 16px);
  background: #252525;
  border-top: 1px solid #404040;
  color: #9e9e9e;
  font-size: var(--modern-font-sm, 12px);
  font-family: var(--font-mono, monospace);
}

.toggle-section {
  padding: var(--modern-spacing-sm, 8px);
  background: #2d2d2d;
  border-top: 1px solid #404040;
  text-align: center;
}

/* Scrollbar style - 终端风格 */
.command-output::-webkit-scrollbar {
  width: 8px;
}

.command-output::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.command-output::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 4px;
}

.command-output::-webkit-scrollbar-thumb:hover {
  background: #555;
}

/* Responsive */
@media (max-width: 640px) {
  .command-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .command-meta {
    width: 100%;
    justify-content: flex-start;
  }

  .execution-time {
    display: none;
  }
}
</style>
