/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="user-input-container">
    <div class="input-wrapper">
      <el-button :icon="Paperclip" circle text />
      <div class="input-container" ref="inputContainer">
        <el-input
          ref="textareaRef"
          v-model="inputValue"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入您的消息... (@引用文件或技能)"
          @keydown="handleKeyDown"
          @input="handleInput"
          @click="handleClick"
          class="user-input"
          data-testid="user-input"
        />
      </div>
      <el-button
        :icon="Promotion"
        type="primary"
        circle
        :disabled="!inputValue.trim()"
        @click="handleSendMessage"
        data-testid="send-button"
      />
    </div>

    <!-- 统一资源提及组件 (文件 + 技能) -->
    <ResourceMention
      :visible="showResourceMention"
      :position="resourceMentionPosition"
      :workspace-id="currentWorkspaceId"
      :file-tree="fileTreeData"
      :on-select="handleResourceSelect"
      :on-close="closeResourceMention"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { Paperclip, Promotion } from '@element-plus/icons-vue'
import ResourceMention from './ResourceMention.vue'

interface FileItem {
  path: string
  name: string
  type: 'file' | 'directory'
  size?: number
  language?: string
}

interface Skill {
  name: string
  description: string
  mode?: string
  scope?: string
  icon: string
  category?: string
}

const chatStore = useChatStore()
const inputValue = ref('')
const textareaRef = ref()
const inputContainer = ref()

// @命令相关状态
const showResourceMention = ref(false)
const resourceMentionPosition = ref({ x: 0, y: 0 })
const currentWorkspaceId = computed(() => chatStore.workspaceId || 'default')
const mentionStartIndex = ref(-1)
const mentionQuery = ref('')
const fileTreeData = ref([])

// 方法
const handleSendMessage = () => {
  if (inputValue.value.trim()) {
    chatStore.sendMessage(inputValue.value)
    inputValue.value = ''
    closeResourceMention()
  }
}

const handleKeyDown = (event: KeyboardEvent) => {
  // 如果资源提及框显示，让ResourceMention组件处理键盘事件
  if (showResourceMention.value) {
    // 阻止默认行为，让ResourceMention组件处理
    if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab'].includes(event.key)) {
      event.preventDefault()
      return
    }
  }

  // 处理Enter键发送消息
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSendMessage()
  }
}

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  const value = target.value
  const cursorPosition = target.selectionStart

  // 检查是否输入了@符号
  checkForMention(value, cursorPosition, target)
}

const handleClick = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  const cursorPosition = target.selectionStart

  // 检查点击位置是否在@符号后
  checkForMention(target.value, cursorPosition, target)
}

const checkForMention = (value: string, cursorPosition: number, textarea: HTMLTextAreaElement) => {
  // 查找光标位置前最近的@符号
  let atPosition = -1
  let spaceAfterAt = -1

  for (let i = cursorPosition - 1; i >= 0; i--) {
    const char = value[i]
    if (char === '@') {
      atPosition = i
      break
    }
    if (char === ' ' || char === '\n') {
      break
    }
  }

  // 查找@符号后的空格或换行符
  if (atPosition !== -1) {
    for (let i = atPosition + 1; i < value.length; i++) {
      const char = value[i]
      if (char === ' ' || char === '\n') {
        spaceAfterAt = i
        break
      }
    }
  }

  // 如果找到了@符号且光标在@符号后面，且@符号后没有空格
  if (atPosition !== -1 && cursorPosition > atPosition &&
      (spaceAfterAt === -1 || cursorPosition <= spaceAfterAt)) {

    // 提取查询字符串
    mentionQuery.value = value.substring(atPosition + 1, cursorPosition)
    mentionStartIndex.value = atPosition

    // 计算弹出框位置
    const rect = textarea.getBoundingClientRect()
    const lineHeight = parseInt(getComputedStyle(textarea).lineHeight) || 20
    const charWidth = parseInt(getComputedStyle(textarea).fontSize) || 14

    // 估算@符号的位置
    const linesBefore = value.substring(0, atPosition).split('\n').length - 1
    const charsInCurrentLine = atPosition - value.lastIndexOf('\n', atPosition - 1) - 1

    resourceMentionPosition.value = {
      x: rect.left + 10 + charsInCurrentLine * charWidth,
      y: rect.top + 20 + linesBefore * lineHeight
    }

    showResourceMention.value = true
  } else {
    closeResourceMention()
  }
}

const handleResourceSelect = (item: FileItem | Skill, type: string) => {
  if (mentionStartIndex.value === -1) return

  // 替换@符号和查询内容为选中项
  const beforeMention = inputValue.value.substring(0, mentionStartIndex.value)
  const afterMention = inputValue.value.substring(mentionStartIndex.value + 1 + mentionQuery.value.length)

  let insertText = ''

  if (type === 'file') {
    const file = item as FileItem
    // 文件路径：@path/to/file
    insertText = file.path
    if (file.type === 'directory' && !insertText.endsWith('/')) {
      insertText += '/'
    }
  } else if (type === 'skill') {
    const skill = item as Skill
    // 技能引用：@skill:name
    insertText = `skill:${skill.name}`
  }

  inputValue.value = beforeMention + insertText + afterMention

  // 设置光标位置到插入内容后
  nextTick(() => {
    const newCursorPosition = beforeMention.length + insertText.length
    if (textareaRef.value) {
      const textarea = textareaRef.value.textarea as HTMLTextAreaElement
      textarea.setSelectionRange(newCursorPosition, newCursorPosition)
      textarea.focus()
    }
  })

  closeResourceMention()
}

const closeResourceMention = () => {
  showResourceMention.value = false
  mentionStartIndex.value = -1
  mentionQuery.value = ''
}

const handleGlobalClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  // backdrop 会处理点击关闭，但保留以防止边缘情况
  if (!inputContainer.value?.contains(target) &&
      !target.closest('.resource-mention-popup') &&
      !target.closest('.resource-mention-backdrop')) {
    closeResourceMention()
  }
}

// 生命周期
onMounted(() => {
  document.addEventListener('click', handleGlobalClick)
})

onUnmounted(() => {
  document.removeEventListener('click', handleGlobalClick)
})
</script>

<style scoped>
.user-input-container {
  padding: 8px;
  background-color: var(--el-bg-color-page);
  border-top: 1px solid var(--el-border-color-lighter);
  position: relative;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background-color: var(--el-fill-color-blank);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-wrapper:focus-within {
  border-color: var(--el-color-primary);
}

.input-container {
  flex: 1;
  position: relative;
  min-width: 0; /* 允许flex子元素缩小 */
  overflow: hidden; /* 防止内容溢出 */
}

.user-input {
  width: 100%;
  max-width: 100%;
  display: block;
}

/* 确保发送按钮在上层 */
:deep(.el-button--primary) {
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

:deep(.el-textarea__inner) {
  background-color: transparent;
  border: none;
  box-shadow: none;
  resize: none;
  padding: 4px 52px 4px 0; /* 增加右侧padding为发送按钮留出空间 */
  line-height: 1.5;
}
</style>
