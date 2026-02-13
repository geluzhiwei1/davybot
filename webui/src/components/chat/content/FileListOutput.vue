/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="file-list-output compact-content">
    <div class="file-list compact-body">
      <div
        v-for="(item, index) in parsedFiles"
        :key="index"
        class="file-item"
      >
        <span class="file-icon">{{ item.icon }}</span>
        <span class="file-name compact-code">{{ item.name }}</span>
        <span v-if="item.size" class="file-size">{{ item.size }}</span>
        <span v-if="item.date" class="file-date">{{ item.date }}</span>
        <span v-if="item.perms" class="file-perms compact-code">{{ item.perms }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content: string
}>()

interface FileItem {
  icon: string
  name: string
  size?: string
  date?: string
  perms?: string
}

const parsedFiles = computed<FileItem[]>(() => {
  const lines = props.content.split('\n')
  return lines
    .map(line => {
      // Parse ls output
      // Example: drwxrwxr-x  5 user user 4096 Jan 22 10:00 src/
      const parts = line.trim().split(/\s+/)
      if (parts.length < 8) return null

      const perms = parts[0] || ''
      const icon = perms.startsWith('d') ? '📁' : '📄'
      const size = parts[4]
      const date = `${parts[5]} ${parts[6]} ${parts[7]}`
      const name = parts.slice(8).join(' ')

      return {
        icon,
        perms,
        size,
        date,
        name
      } as FileItem
    })
    .filter((item): item is FileItem => item !== null && item.name !== '')
})
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.file-list-output {
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
}

.file-list {
  display: flex;
  flex-direction: column;
  padding: var(--modern-spacing-sm);
}

.file-item {
  display: grid;
  grid-template-columns: 20px 1fr auto auto auto;
  gap: var(--modern-spacing-sm);
  padding: var(--modern-spacing-xs) var(--modern-spacing-sm);
  border-bottom: 1px solid var(--modern-border-light);
  align-items: center;
  transition: background 0.2s ease;
}

.file-item:hover {
  background: var(--modern-bg-subtle);
}

.file-item:last-child {
  border-bottom: none;
}

.file-icon {
  font-size: 14px;
  text-align: center;
}

.file-name {
  color: var(--modern-color-success);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--modern-font-sm);
}

.file-size {
  color: #9e9e9e;
  text-align: right;
  font-size: var(--modern-font-xs);
}

.file-date {
  color: var(--modern-color-info);
  text-align: right;
  font-size: var(--modern-font-xs);
}

.file-perms {
  color: var(--modern-color-warning);
  font-family: monospace;
  text-align: right;
  font-size: var(--modern-font-xs);
}

/* Responsive */
@media (max-width: 640px) {
  .file-item {
    grid-template-columns: 20px 1fr;
  }

  .file-size,
  .file-date,
  .file-perms {
    display: none;
  }
}
</style>
