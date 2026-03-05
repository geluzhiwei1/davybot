/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <div class="drawio-editor-wrapper">
    <div v-if="!isReady" class="drawio-loading">
      <el-icon class="is-loading" :size="32">
        <Loading />
      </el-icon>
      <span>正在加载编辑器...</span>
    </div>
    <iframe
      ref="drawioFrame"
      class="drawio-iframe"
      :src="drawioUrl"
      frameborder="0"
    ></iframe>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'

interface Props {
  modelValue: string
  filename?: string
  readonly?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
  (e: 'ready'): void
  (e: 'save'): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  filename: 'diagram.drawio',
  readonly: false,
})

const emit = defineEmits<Emits>()

const drawioFrame = ref<HTMLIFrameElement | null>(null)
const isReady = ref(false)
const currentXml = ref(props.modelValue)

// Use local drawio with embed mode
const drawioUrl = computed(() => {
  const baseUrl = '/drawio/index.html'
  const params = new URLSearchParams()

  // Use JSON protocol for embed mode
  params.set('proto', 'json')

  // Embed mode for integration
  params.set('embed', '1')

  // UI mode: minimal UI
  params.set('ui', 'min')

  // Language: Chinese
  params.set('lang', 'zh')

  // No flash (no file system access by default)
  params.set('flash', '0')

  return `${baseUrl}?${params.toString()}`
})

// Handle messages from drawio iframe
const handleMessage = (event: MessageEvent) => {
  // Only accept messages from drawio iframe
  if (!drawioFrame.value || event.source !== drawioFrame.value.contentWindow) {
    return
  }

  const data = event.data

  // Parse JSON message
  let msg: any
  try {
    msg = typeof data === 'string' ? JSON.parse(data) : data
  } catch (e) {
    // Ignore non-JSON messages
    return
  }

  // Handle different event types
  if (msg.event === 'init') {
    // Drawio is ready to receive data
    isReady.value = true
    emit('ready')

    // Send load action with initial XML data
    drawioFrame.value!.contentWindow!.postMessage(JSON.stringify({
      action: 'load',
      autosave: 1,
      saveAndExit: '0',
      modified: 'unsavedChanges',
      xml: currentXml.value || '',
      title: props.filename
    }), '*')
    return
  }

  if (msg.event === 'save') {
    // Drawio sent save event with updated XML data
    if (msg.xml) {
      currentXml.value = msg.xml
      emit('update:modelValue', msg.xml)
      emit('change', msg.xml)
      emit('save')  // 通知父组件保存文件
    }
    return
  }

  if (msg.event === 'exit') {
    // Drawio editor was closed
    return
  }

  if (msg.event === 'autosave') {
    // Drawio sent autosave event with updated XML data
    if (msg.xml) {
      currentXml.value = msg.xml
      emit('update:modelValue', msg.xml)
      emit('change', msg.xml)
    }
    return
  }
}

// Watch for external changes
watch(() => props.modelValue, (newValue) => {
  if (newValue !== currentXml.value && isReady.value) {
    currentXml.value = newValue
    drawioFrame.value?.contentWindow?.postMessage(JSON.stringify({
      action: 'load',
      autosave: 1,
      saveAndExit: '0',
      modified: 'unsavedChanges',
      xml: newValue,
      title: props.filename
    }), '*')
  }
})

// Expose methods
const getDiagram = () => {
  return currentXml.value
}

const loadDiagram = (xml: string) => {
  currentXml.value = xml

  if (isReady.value && drawioFrame.value?.contentWindow) {
    drawioFrame.value.contentWindow.postMessage(JSON.stringify({
      action: 'load',
      autosave: 1,
      saveAndExit: '0',
      modified: 'unsavedChanges',
      xml: xml,
      title: props.filename
    }), '*')
  }
}

// Lifecycle
onMounted(() => {
  window.addEventListener('message', handleMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handleMessage)
})

defineExpose({
  getDiagram,
  loadDiagram,
  isReady: () => isReady.value,
})
</script>

<style scoped>
.drawio-editor-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawio-iframe {
  flex: 1;
  width: 100%;
  height: 100%;
  border: none;
  overflow: hidden;
}

.drawio-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background-color: rgba(255, 255, 255, 0.9);
  color: var(--el-text-color-secondary);
  z-index: 1000;
}

.drawio-loading .el-icon {
  color: var(--el-color-primary);
}
</style>
