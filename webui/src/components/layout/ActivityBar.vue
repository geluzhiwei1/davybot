/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="activity-bar" :class="{ 'activity-bar--collapsed': collapsed }">
    <div
      v-for="item in items"
      :key="item.id"
      class="activity-item"
      :class="{ 'activity-item--active': item.id === activeId, 'activity-item--disabled': item.disabled }"
      :title="item.label"
      @click="handleClick(item)"
    >
      <el-icon class="activity-icon" :size="20">
        <component :is="item.icon" />
      </el-icon>
      <el-badge
        v-if="item.badge !== undefined && item.badge !== 0"
        :value="item.badge"
        :max="99"
        class="activity-badge"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { type PropType } from 'vue'
import { ElIcon, ElBadge } from 'element-plus'
import type { Component } from 'vue'

export interface ActivityBarItem {
  id: string
  icon: Component
  label: string
  badge?: number
  disabled?: boolean
}

defineProps({
  items: {
    type: Array as PropType<ActivityBarItem[]>,
    required: true
  },
  activeId: {
    type: String,
    default: ''
  },
  collapsed: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits<{
  select: [id: string]
}>()

function handleClick(item: ActivityBarItem) {
  if (!item.disabled) {
    emit('select', item.id)
  }
}
</script>

<style scoped>
.activity-bar {
  width: 56px;
  background: var(--el-bg-color-page);
  border-right: 1px solid var(--el-border-color-light);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  gap: 8px;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.activity-bar--collapsed {
  width: 48px;
}

.activity-item {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  color: var(--el-text-color-secondary);
  background: transparent;
}

.activity-item:hover:not(.activity-item--disabled) {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
  transform: scale(1.05);
}

.activity-item--active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-left: 3px solid var(--el-color-primary);
}

.activity-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.activity-item--disabled:hover {
  background: transparent;
  transform: none;
}

.activity-icon {
  flex-shrink: 0;
}

.activity-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  pointer-events: none;
}

.activity-badge :deep(.el-badge__content) {
  background: var(--el-color-danger);
  border: 2px solid var(--el-bg-color-page);
  font-size: 10px;
  padding: 2px 5px;
  height: 16px;
  line-height: 12px;
  min-width: 16px;
}

/* 深色模式支持 */
@media (prefers-color-scheme: dark) {
  .activity-bar {
    background: var(--el-bg-color);
    border-right-color: var(--el-border-color-darker);
  }

  .activity-badge :deep(.el-badge__content) {
    border-color: var(--el-bg-color);
  }
}
</style>
