/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div>
    <div
      class="file-tree-node"
      :class="{ selected: selected }"
      :style="{ paddingLeft: `${0.5 + (level || 0) * 1}rem` }"
      @click="handleItemClick"
    >
      <el-icon v-if="item.type === 'folder'" class="arrow-icon" :class="{ 'is-open': isOpen }">
        <ArrowRight />
      </el-icon>
      <el-icon class="item-icon" :style="{ color: fileIconColor }">
        <component :is="fileIcon" />
      </el-icon>
      <span class="node-name">{{ item.name }}</span>
    </div>
    <el-collapse-transition>
      <div v-if="isOpen && item.children && item.children.length">
        <FileTreeNode
          v-for="child in item.children"
          :key="child.path"
          :item="child"
          :level="(level || 0) + 1"
          :selected="selected"
          @item-click="$emit('item-click', $event)"
        />
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type PropType } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { getFileIconByType, getFileIconColor, type FileIconComponent } from '@/utils/fileIcons'

interface FileTreeItem {
  name: string
  path: string
  type: 'file' | 'folder'
  level: number
  children?: FileTreeItem[]
}

const props = defineProps({
  item: {
    type: Object as PropType<FileTreeItem>,
    required: true
  },
  level: {
    type: Number,
    default: 0
  },
  selected: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['item-click'])

const isOpen = ref(false)

// 计算文件图标
const fileIcon = computed<FileIconComponent>(() => {
  return getFileIconByType(props.item.type, props.item.name)
})

// 计算文件图标颜色
const fileIconColor = computed<string>(() => {
  if (props.item.type === 'folder') {
    return 'var(--el-color-warning)'
  }
  return getFileIconColor(props.item.name)
})

const handleItemClick = () => {
  if (props.item.type === 'folder') {
    isOpen.value = !isOpen.value
  }
  emit('item-click', props.item)
}
</script>

<style scoped>
.file-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s, color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-tree-node:hover {
  background-color: var(--el-fill-color-light);
}

.file-tree-node.selected {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.arrow-icon {
  transition: transform 0.2s ease-in-out;
  color: var(--el-text-color-secondary);
}

.arrow-icon.is-open {
  transform: rotate(90deg);
}

.item-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.node-name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>