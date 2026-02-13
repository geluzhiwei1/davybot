/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="code-editor-container">
    <codemirror
      v-model="internalContent"
      :style="{ height }"
      :extensions="computedExtensions"
      :disabled="readonly"
      @change="handleChange"
      @focus="handleFocus"
      @blur="handleBlur"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Codemirror } from 'vue-codemirror'
import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { json } from '@codemirror/lang-json'
import { vue } from '@codemirror/lang-vue'
import { oneDark } from '@codemirror/theme-one-dark'
import { keymap, lineNumbers as cmLineNumbers, highlightSpecialChars, drawSelection, dropCursor } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { bracketMatching as cmBracketMatching } from '@codemirror/language'
import { closeBrackets as cmCloseBrackets } from '@codemirror/autocomplete'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'
import { getLanguageFromPath } from './languages'
import type { Extension } from '@codemirror/state'

// 创建自定义 basicSetup，避免使用 codemirror 便利包（这会导致多实例问题）
const basicSetup: Extension = [
  cmLineNumbers(),
  highlightSpecialChars(),
  drawSelection(),
  dropCursor(),
  EditorState.allowMultipleSelections.of(true),
  keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
  cmBracketMatching(),
  cmCloseBrackets(),
  history(),
  highlightSelectionMatches(),
]

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

// Language detection and extension mapping
const LANGUAGE_EXTENSIONS: Record<string, () => Extension | Extension[]> = {
  javascript: () => javascript(),
  jsx: () => javascript(),
  typescript: () => javascript({ typescript: true }),
  tsx: () => javascript({ typescript: true }),
  python: () => python(),
  html: () => html(),
  css: () => css(),
  json: () => json(),
  vue: () => vue(),
}

const detectedLanguage = computed(() => {
  if (props.language) return props.language
  if (props.filePath) return getLanguageFromPath(props.filePath)
  return 'plaintext'
})

const languageExtension = computed(() => {
  const lang = detectedLanguage.value
  return LANGUAGE_EXTENSIONS[lang]?.() ?? []
})

// Computed extensions for better performance
const computedExtensions = computed(() => {
  const extensions: (Extension | Extension[])[] = [
    basicSetup,
    languageExtension.value,
    history(),
    keymap.of([...defaultKeymap, ...historyKeymap]),
  ]

  // Theme
  if (props.theme === 'one-dark' || props.theme === 'dark') {
    extensions.push(oneDark)
  }

  // Optional features
  if (props.lineNumbers) extensions.push(lineNumbers())
  if (props.bracketMatching) extensions.push(bracketMatching())
  if (props.closeBrackets) extensions.push(closeBrackets())
  if (props.search) {
    extensions.push(searchKeymap, highlightSelectionMatches)
  }
  if (props.readonly) extensions.push(EditorState.readOnly.of(true))

  return extensions
})

// Event handlers
const handleChange = (value: string) => {
  emit('update:modelValue', value)
  emit('change', value)
}

const handleFocus = () => emit('focus')
const handleBlur = () => emit('blur')
</script>

<style scoped>
.code-editor-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
}

.code-editor-container :deep(.cm-editor) {
  height: 100%;
  font-size: 14px;
  font-family:
    'JetBrains Mono',
    'Fira Code',
    'Consolas',
    'Monaco',
    'Courier New',
    monospace;
}

.code-editor-container :deep(.cm-scroller) {
  overflow: auto;
}

.code-editor-container :deep(.cm-content) {
  padding: 8px 0;
}

.code-editor-container :deep(.cm-line) {
  padding: 0 8px;
}

.code-editor-container :deep(.cm-gutters) {
  background-color: var(--cm-gutter-bg);
  border-right: 1px solid var(--cm-gutter-border);
}

.code-editor-container :deep(.cm-activeLine) {
  background-color: var(--cm-active-line-bg);
}

.code-editor-container :deep(.cm-activeLineGutter) {
  background-color: var(--cm-active-line-gutter-bg);
}

.code-editor-container :deep(.cm-editor.cm-one-dark) {
  --cm-gutter-bg: #282c34;
  --cm-gutter-border: #3e4451;
  --cm-active-line-bg: #2c313c;
  --cm-active-line-gutter-bg: #2c313c;
}

.code-editor-container :deep(.cm-editor) {
  --cm-gutter-bg: #f3f4f6;
  --cm-gutter-border: #e5e7eb;
  --cm-active-line-bg: #f9fafb;
  --cm-active-line-gutter-bg: #f3f4f6;
}
</style>
