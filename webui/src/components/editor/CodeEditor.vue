/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="code-editor-container">
    <NativeCodeMirror
      ref="editorRef"
      :model-value="internalContent"
      :file-path="filePath"
      :language="language"
      :theme="theme"
      :readonly="readonly"
      :height="height"
      :line-numbers="lineNumbers"
      :bracket-matching="bracketMatching"
      :close-brackets="closeBrackets"
      :search="search"
      @update:model-value="handleUpdate"
      @change="handleChange"
      @focus="handleFocus"
      @blur="handleBlur"
      @ready="handleReady"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import NativeCodeMirror from './NativeCodeMirror.vue'

interface Props {
  modelValue: string
  filePath?: string
  language?: string
  theme?: 'light' | 'dark' | 'one-dark'
  readonly?: boolean
  height?: string
  lineNumbers?: boolean
  bracketMatching?: boolean
  closeBrackets?: boolean
  search?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
  (e: 'focus'): void
  (e: 'blur'): void
  (e: 'ready', view: unknown): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  filePath: '',
  language: '',
  theme: 'one-dark',
  readonly: false,
  height: '100%',
  lineNumbers: true,
  bracketMatching: true,
  closeBrackets: true,
  search: true,
})

const emit = defineEmits<Emits>()
const editorRef = ref()
const internalContent = ref(props.modelValue)

// Sync external model changes
watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue !== internalContent.value) {
      internalContent.value = newValue
    }
  }
)

// Event handlers
const handleUpdate = (value: string) => {
  internalContent.value = value
  emit('update:modelValue', value)
}

const handleChange = (value: string) => {
  emit('change', value)
}

const handleFocus = () => emit('focus')

const handleBlur = () => emit('blur')

const handleReady = (view: unknown) => {
  emit('ready', view)
}

// Expose methods for parent components
defineExpose({
  getEditor: () => editorRef.value?.getEditor(),
  focus: () => editorRef.value?.focus(),
})
</script>

<style scoped>
.code-editor-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
}
</style>
