/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <div v-if="visible" class="slash-commands-popup" :style="popupStyle">
      <div class="slash-commands-header">
      <span class="slash-commands-title">Slash Commands</span>
      <span class="slash-commands-count">{{ filteredCommands.length }} 个命令</span>
    </div>
    <div v-if="commands.length > 5" class="slash-commands-search">
      <input
        ref="searchInput"
        v-model="searchQuery"
        type="text"
        placeholder="搜索命令..."
        class="slash-commands-input"
        @keydown.down.prevent="selectNext"
        @keydown.up.prevent="selectPrevious"
        @keydown.enter.prevent="selectCurrent"
        @keydown.esc.prevent="close"
      />
    </div>
    <div class="slash-commands-list" ref="commandList">
      <div
        v-for="(command, index) in filteredCommands"
        :key="command.name"
        class="slash-commands-item"
        :class="{
          'slash-commands-item--selected': index === selectedIndex,
          'slash-commands-item--mode-code': command.mode === 'code',
          'slash-commands-item--mode-ask': command.mode === 'ask'
        }"
        @click="selectCommand(command)"
        @mouseenter="selectedIndex = index"
      >
        <div class="slash-commands-icon">
          <svg class="icon" viewBox="0 0 24 24">
            <path d="M5 4v2h14V4H5zm0 10h4v6h6v-6h4l-7-7-7 7z" />
          </svg>
        </div>
        <div class="slash-commands-info">
          <div class="slash-commands-name">{{ command.name }}</div>
          <div class="slash-commands-description">{{ command.description }}</div>
        </div>
        <div class="slash-commands-meta">
          <span v-if="command.argument_hint" class="slash-commands-argument">
            {{ command.argument_hint }}
          </span>
          <el-tag v-if="command.mode" size="small" :type="getModeTagType(command.mode)">
            {{ command.mode }}
          </el-tag>
          <el-tag size="small" :type="getSourceTagType(command.source)">
            {{ command.source }}
          </el-tag>
        </div>
      </div>
    </div>
    <div v-if="filteredCommands.length === 0" class="slash-commands-empty">
      <div class="slash-commands-empty-icon">🔍</div>
      <div class="slash-commands-empty-text">未找到匹配的命令</div>
    </div>
  </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'

interface SlashCommand {
  name: string
  description: string | null
  argument_hint: string | null
  mode: string | null
  source: string
}

interface Props {
  visible: boolean
  position: { x: number; y: number }
  commands: SlashCommand[]
}

const props = withDefaults(defineProps<Props>(), {
  commands: () => []
})

const emit = defineEmits<{
  close: []
  select: [command: SlashCommand]
}>()

// 响应式数据
const searchQuery = ref('')
const selectedIndex = ref(0)
const searchInput = ref<HTMLInputElement>()
const commandList = ref<HTMLElement>()

// 计算属性
const filteredCommands = computed(() => {
  if (!searchQuery.value.trim()) {
    return props.commands
  }

  const query = searchQuery.value.toLowerCase()
  return props.commands.filter(command =>
    command.name.toLowerCase().includes(query) ||
    (command.description && command.description.toLowerCase().includes(query))
  )
})

const popupStyle = computed(() => {
  // 计算弹出框的最佳位置，避免被遮挡
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const popupWidth = 500
  const popupMaxHeight = 400

  let x = props.position.x
  let y = props.position.y

  // 确保不超出右边界
  if (x + popupWidth > viewportWidth) {
    x = viewportWidth - popupWidth - 10
  }

  // 确保不超出下边界
  if (y + popupMaxHeight > viewportHeight) {
    y = viewportHeight - popupMaxHeight - 10
  }

  // 确保不超出左边界和上边界
  x = Math.max(10, x)
  y = Math.max(10, y)

  return {
    left: `${x}px`,
    top: `${y}px`,
    maxHeight: `${popupMaxHeight}px`,
    position: 'fixed' as const
  }
})

// 方法
const selectNext = () => {
  if (selectedIndex.value < filteredCommands.value.length - 1) {
    selectedIndex.value++
    scrollToSelected()
  }
}

const selectPrevious = () => {
  if (selectedIndex.value > 0) {
    selectedIndex.value--
    scrollToSelected()
  }
}

const selectCurrent = () => {
  if (filteredCommands.value.length > 0) {
    selectCommand(filteredCommands.value[selectedIndex.value])
  }
}

const selectCommand = (command: SlashCommand) => {
  emit('select', command)
  close()
}

const close = () => {
  emit('close')
}

const scrollToSelected = () => {
  nextTick(() => {
    if (commandList.value) {
      const items = commandList.value.querySelectorAll('.slash-commands-item')
      const selected = items[selectedIndex.value] as HTMLElement
      if (selected) {
        selected.scrollIntoView({ block: 'nearest' })
      }
    }
  })
}

const getModeTagType = (mode: string | null) => {
  switch (mode) {
    case 'code':
      return 'success'
    case 'ask':
      return 'info'
    case 'plan':
      return 'warning'
    default:
      return 'info'
  }
}

const getSourceTagType = (source: string) => {
  switch (source) {
    case 'workspace':
      return 'danger'
    case 'user':
      return 'warning'
    case 'builtin':
      return 'info'
    default:
      return 'info'
  }
}

// 键盘事件处理
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if (!props.visible) return

  if (e.key === 'ArrowDown') {
    selectNext()
  } else if (e.key === 'ArrowUp') {
    selectPrevious()
  } else if (e.key === 'Enter') {
    selectCurrent()
  } else if (e.key === 'Escape') {
    close()
  }
}

// 监听visible变化，自动聚焦搜索框
watch(() => props.visible, (newVal) => {
  if (newVal) {
    selectedIndex.value = 0
    searchQuery.value = ''
    nextTick(() => {
      searchInput.value?.focus()
    })
  }
})

// 生命周期
onMounted(() => {
  document.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<style scoped>
.slash-commands-popup {
  position: fixed;
  width: 500px;
  max-height: 400px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.slash-commands-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-light);
}

.slash-commands-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.slash-commands-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.slash-commands-search {
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.slash-commands-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.slash-commands-input:focus {
  border-color: var(--el-color-primary);
}

.slash-commands-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.slash-commands-item {
  display: flex;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
  gap: 12px;
}

.slash-commands-item:hover,
.slash-commands-item--selected {
  background: var(--el-fill-color-light);
}

.slash-commands-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color);
  border-radius: 6px;
}

.slash-commands-icon .icon {
  width: 18px;
  height: 18px;
  fill: var(--el-text-color-primary);
}

.slash-commands-info {
  flex: 1;
  min-width: 0;
}

.slash-commands-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slash-commands-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slash-commands-meta {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.slash-commands-argument {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-style: italic;
}

.slash-commands-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.slash-commands-empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.slash-commands-empty-text {
  font-size: 14px;
}
</style>
