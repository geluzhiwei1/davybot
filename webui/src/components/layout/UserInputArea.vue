/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="user-input-area">
    <el-alert
      v-if="showCommandHint"
      :title="commandHintTitle"
      type="info"
      :closable="false"
      show-icon
      class="command-hint"
    >
      <template #title>
        <div class="command-hint-content">
          <el-tag size="small" type="primary" effect="light">{{ commandType === 'mention' ? '@' : '/' }}</el-tag>
          <span>{{ commandHintText }}</span>
        </div>
      </template>
    </el-alert>

    <div class="input-main-area">
      <el-button :icon="Paperclip" circle @click="handleAttachment" title="添加附件" />
      <input
        ref="fileInputRef"
        type="file"
        class="hidden-file-input"
        multiple
        accept="image/*,.pdf,.doc,.docx,.txt"
        @change="handleFileInputChange"
      />

      <div class="input-wrapper">
        <el-input
          ref="textareaRef"
          v-model="inputValue"
          type="textarea"
          :placeholder="placeholder"
          :autosize="{ minRows: 1, maxRows: 10 }"
          resize="vertical"
          @keydown="handleKeyDown"
          @input="handleInput"
          @paste="handlePaste"
          @click="handleClick"
          data-testid="user-input"
        />
        <el-button
          :icon="Promotion"
          type="primary"
          circle
          :disabled="!canSend"
          @click="handleSend"
          title="发送消息 (Enter)"
          class="send-button"
          data-testid="send-button"
        />
      </div>
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

    <!-- Slash命令组件 -->
    <SlashCommands
      :visible="showSlashCommands"
      :position="slashCommandsPosition"
      :commands="availableCommands"
      @select="handleSlashCommandSelect"
      @close="closeSlashCommands"
    />

    <div v-if="attachments.length > 0" class="attachment-preview-area">
      <el-tag
        v-for="(file, index) in attachments"
        :key="index"
        closable
        @close="removeAttachment(index)"
        type="info"
        effect="light"
        class="attachment-tag"
      >
        <el-icon><Document /></el-icon>
        <span class="attachment-name">{{ file.name }}</span>
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { Paperclip, Promotion, Document } from '@element-plus/icons-vue'
import type { ElInput } from 'element-plus'
import ResourceMention from '@/components/controls/ResourceMention.vue'
import SlashCommands from '@/components/controls/SlashCommands.vue'
import { listSlashCommands } from '@/services/api'
import type { Skill } from '@/services/api/services/skills'

interface FileItem {
  path: string
  name: string
  type: 'file' | 'directory'
  size?: number
  language?: string
}

// Local interface that matches the API response
interface SlashCommand {
  name: string
  description: string | null
  argument_hint: string | null
  mode: string | null
  source: string
}

const props = defineProps({
  fileTree: {
    type: Array,
    default: () => []
  }
})

const chatStore = useChatStore()

const textareaRef = ref<InstanceType<typeof ElInput> | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const inputValue = ref('')
const attachments = ref<File[]>([])
const showCommandHint = ref(false)
const commandType = ref<'mention' | 'slash' | null>(null)

// @命令相关状态
const showResourceMention = ref(false)
const resourceMentionPosition = ref({ x: 0, y: 0 })
const currentWorkspaceId = computed(() => chatStore.workspaceId || 'default')
const mentionStartIndex = ref(-1)
const mentionQuery = ref('')
const fileTreeData = ref<unknown[]>([])

// Slash命令相关状态
const showSlashCommands = ref(false)
const slashCommandsPosition = ref({ x: 0, y: 0 })
const availableCommands = ref<SlashCommand[]>([])
const slashCommandStartIndex = ref(-1)

// 监听文件树变化
watch(() => props.fileTree, (newTree) => {
  fileTreeData.value = newTree || []
}, { immediate: true, deep: true })

const placeholder = computed(() => {
  if (commandType.value === 'mention') return '输入文件名或工作区名称...'
  if (commandType.value === 'slash') return '选择命令...'
  return 'Ask me anything...'
})

const commandHintTitle = computed(() => (commandType.value === 'mention' ? '提及' : '命令'))
const commandHintText = computed(() => (commandType.value === 'mention' ? '提及文件、工作区或上下文' : '触发特定功能或模式'))

const canSend = computed(() => inputValue.value.trim().length > 0 || attachments.value.length > 0)

const handleSend = () => {
  if (!canSend.value) return
  chatStore.sendMessage(inputValue.value)
  inputValue.value = ''
  attachments.value = []
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

const handleKeyDown = (e: KeyboardEvent) => {
  // 如果资源提及框显示，让ResourceMention组件处理键盘事件
  if (showResourceMention.value) {
    // 阻止默认行为，让ResourceMention组件处理
    if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape'].includes(e.key)) {
      e.preventDefault()
      return
    }
  }

  // 如果slash命令框显示，让SlashCommands组件处理键盘事件
  if (showSlashCommands.value) {
    if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape'].includes(e.key)) {
      e.preventDefault()
      return
    }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
  if (e.key === '@' && inputValue.value.length === 0) {
    commandType.value = 'mention'
    showCommandHint.value = true
  } else if (e.key === '/' && inputValue.value.length === 0) {
    commandType.value = 'slash'
    showCommandHint.value = true
    // 打开slash命令弹出框
    openSlashCommands()
  } else if (e.key === 'Escape') {
    commandType.value = null
    showCommandHint.value = false
    closeResourceMention()
    closeSlashCommands()
  }
}

const handleInput = () => {
  if (inputValue.value.length > 1) {
    showCommandHint.value = false
  }
  
  // 检查是否输入了@符号
  if (textareaRef.value) {
    const textarea = textareaRef.value.input || textareaRef.value.textarea
    if (textarea) {
      const value = textarea.value
      const cursorPosition = textarea.selectionStart || 0
      checkForMention(value, cursorPosition, textarea)
    }
  }
}

const handleClick = () => {
  if (textareaRef.value) {
    const textarea = textareaRef.value.input || textareaRef.value.textarea
    if (textarea) {
      const cursorPosition = textarea.selectionStart || 0
      checkForMention(textarea.value, cursorPosition, textarea)
    }
  }
}

const checkForMention = (value: string, cursorPosition: number, textarea: HTMLInputElement | HTMLTextAreaElement) => {
  // 查找光标位置前最近的@符号
  let atPosition = -1

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

  // 只有刚输入@符号时才弹出文件选择框（@后面还没有内容）
  // 条件：找到了@符号 且 光标就在@符号后面（@后面还没有输入任何字符）
  if (atPosition !== -1 && cursorPosition === atPosition + 1) {
    // 提取查询字符串（此时应该为空）
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
  if (mentionStartIndex.value !== -1) {
    const beforeMention = inputValue.value.substring(0, mentionStartIndex.value)
    const afterMention = inputValue.value.substring(mentionStartIndex.value + 1 + mentionQuery.value.length)

    let insertText = ''

    if (type === 'skill') {
      const skill = item as Skill
      insertText = `skill:${skill.name}`
    } else if (type === 'file') {
      const file = item as FileItem
      insertText = file.path
      if (file.type === 'directory' && !insertText.endsWith('/')) {
        insertText += '/'
      }
    } else if (type === 'recent') {
      const recent = item as unknown
      if (recent.type === 'skill') {
        insertText = `skill:${recent.name}`
      } else {
        insertText = recent.path
      }
    }

    // 添加空格，避免与后续输入连接
    insertText += ' '

    inputValue.value = beforeMention + '@' + insertText + afterMention

    nextTick(() => {
      const newCursorPosition = beforeMention.length + 1 + insertText.length
      if (textareaRef.value) {
        const textarea = textareaRef.value.input || textareaRef.value.textarea
        if (textarea) {
          textarea.setSelectionRange(newCursorPosition, newCursorPosition)
          textarea.focus()
        }
      }
    })
  }

  closeResourceMention()
}

const closeResourceMention = () => {
  showResourceMention.value = false
  mentionStartIndex.value = -1
  mentionQuery.value = ''
}

// Slash命令相关函数
const openSlashCommands = async () => {
  const { response, position } = await loadSlashCommands()

  availableCommands.value = response
  slashCommandsPosition.value = position
  showSlashCommands.value = true
  slashCommandStartIndex.value = 0
}

const loadSlashCommands = async () => {
  try {
    // Only pass workspace parameter if there's a valid workspace (not 'default')
    const workspaceParam = currentWorkspaceId.value && currentWorkspaceId.value !== 'default'
      ? currentWorkspaceId.value
      : undefined

    const response = await listSlashCommands({ workspace: workspaceParam })

    const commands = response.success && response.commands
      ? response.commands.map(cmd => ({
          name: cmd.name,
          description: cmd.description,
          argument_hint: cmd.argument_hint,
          mode: cmd.mode,
          source: cmd.source
        }))
      : []

    const position = calculatePopupPosition()

    return { response: commands, position }
  } catch (error) {
    console.error('Error loading slash commands:', error)
    return { response: [], position: calculatePopupPosition() }
  }
}

const calculatePopupPosition = () => {
  if (!textareaRef.value) return { x: 0, y: 0 }

  const textarea = textareaRef.value.input || textareaRef.value.textarea
  if (!textarea) return { x: 0, y: 0 }

  const rect = textarea.getBoundingClientRect()

  // Slash命令在输入框为空时触发，位置在输入框底部左侧
  // 与@mention的对齐方式一致
  return {
    x: rect.left + 10,
    y: rect.bottom + 5
  }
}

const closeSlashCommands = () => {
  showSlashCommands.value = false
  slashCommandStartIndex.value = -1
}

const handleSlashCommandSelect = (command: SlashCommand) => {
  // 将命令插入到输入框
  inputValue.value = command.name

  // 关闭弹出框
  closeSlashCommands()
  commandType.value = null
  showCommandHint.value = false

  // 聚焦输入框
  nextTick(() => {
    textareaRef.value?.focus()
  })
}

const handleGlobalClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement
  if (!target.closest('.input-wrapper') && !target.closest('.resource-mention-popup')) {
    closeResourceMention()
  }
  if (!target.closest('.input-wrapper') && !target.closest('.slash-commands-popup')) {
    closeSlashCommands()
  }
}

const handlePaste = (e: ClipboardEvent) => {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) attachments.value.push(file)
    }
  }
}

const handleAttachment = () => {
  fileInputRef.value?.click()
}

const handleFileInputChange = (e: Event) => {
  const target = e.target as HTMLInputElement
  const files = Array.from(target.files || [])
  attachments.value.push(...files)
  target.value = ''
}

const removeAttachment = (index: number) => {
  attachments.value.splice(index, 1)
}

// 生命周期
onMounted(() => {
  document.addEventListener('click', handleGlobalClick)
})

onUnmounted(() => {
  document.removeEventListener('click', handleGlobalClick)
})

nextTick(() => {
  textareaRef.value?.focus()
})
</script>

<style scoped>
.user-input-area {
  padding: 4px;
  background-color: var(--el-bg-color-page);
  border-top: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
}

.command-hint {
  margin-bottom: 12px;
}

.command-hint-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-main-area {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.hidden-file-input {
  display: none;
}

.input-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: flex-end;
  background-color: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 4px 52px 4px 4px; /* 右侧padding为发送按钮留出完整空间 */
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: visible; /* 确保按钮不被裁剪 */
}

.input-wrapper:focus-within {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

:deep(.el-textarea__inner) {
  box-shadow: none !important;
  padding: 6px 52px 6px 8px; /* 增加右侧padding为按钮留出更多空间 */
  background-color: transparent;
  width: 100%;
  display: block;
  resize: vertical; /* 确保允许垂直方向调整大小 */
  min-height: 32px; /* 设置最小高度 */
  max-height: 300px; /* 设置最大高度 */
}

/* 增强拖动手柄的可见性 */
:deep(.el-textarea__inner::-webkit-resizer) {
  background-color: transparent;
}

:deep(.el-textarea__inner:hover::-webkit-resizer) {
  background-color: #94a3b8;
}

.send-button {
  position: absolute;
  right: 8px;
  bottom: 4px; /* 调整为与输入框底部对齐 */
  z-index: 10; /* 确保按钮在输入框之上 */
  flex-shrink: 0;
}

.attachment-preview-area {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.attachment-tag {
  display: flex;
  align-items: center;
  gap: 4px;
}

.attachment-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>