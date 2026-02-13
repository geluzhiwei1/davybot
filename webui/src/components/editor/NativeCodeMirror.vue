/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div ref="containerRef" class="code-editor-container" :style="{ height }"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { EditorView } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { javascript } from '@codemirror/lang-javascript'
import { python } from '@codemirror/lang-python'
import { html } from '@codemirror/lang-html'
import { css } from '@codemirror/lang-css'
import { json } from '@codemirror/lang-json'
import { vue } from '@codemirror/lang-vue'
import { oneDark } from '@codemirror/theme-one-dark'
import { keymap, lineNumbers as cmLineNumbers, highlightSpecialChars, drawSelection, dropCursor } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { bracketMatching as cmBracketMatching, syntaxHighlighting, defaultHighlightStyle } from '@codemirror/language'
import { closeBrackets as cmCloseBrackets } from '@codemirror/autocomplete'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'

import { getLanguageFromPath } from './languages'
import type { Extension } from '@codemirror/state'

// 创建自定义 basicSetup，避免使用 codemirror 便利包（这会导致多实例问题）
const customBasicSetup: Extension = [
  cmLineNumbers(),
  highlightSpecialChars(),
  drawSelection(),
  dropCursor(),
  EditorState.allowMultipleSelections.of(true),
  syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
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
  (e: 'ready', view: EditorView): void
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
const containerRef = ref<HTMLElement>()
let editorView: EditorView | null = null

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
    customBasicSetup,
    languageExtension.value,
  ]

  // Theme
  if (props.theme === 'one-dark' || props.theme === 'dark') {
    extensions.push(oneDark)
  }

  if (props.readonly) {
    extensions.push(EditorState.readOnly.of(true))
  }

  return extensions
})

const createEditor = () => {
  if (!containerRef.value) return

  // Destroy existing editor
  if (editorView) {
    editorView.destroy()
  }

  // Create new editor
  const state = EditorState.create({
    doc: props.modelValue,
    extensions: [
      ...computedExtensions.value,
      EditorView.theme({
        '&': { height: '100%' },
        '.cm-scroller': { overflow: 'auto' },
        '.cm-content': { padding: '8px 0' },
        '.cm-line': { padding: '0 8px' },
      }),
      EditorView.domEventHandlers({
        focus: () => emit('focus'),
        blur: () => emit('blur'),
      }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          const newValue = update.state.doc.toString()
          emit('update:modelValue', newValue)
          emit('change', newValue)
        }
      }),
    ],
  })

  editorView = new EditorView({
    state,
    parent: containerRef.value,
  })

  emit('ready', editorView)
}

// Watch for external value changes
watch(
  () => props.modelValue,
  (newValue) => {
    if (editorView && newValue !== editorView.state.doc.toString()) {
      const transaction = editorView.state.update({
        changes: {
          from: 0,
          to: editorView.state.doc.length,
          insert: newValue,
        },
      })
      editorView.dispatch(transaction)
    }
  }
)

// Watch for config changes that require recreation
watch(
  () => [props.theme, props.readonly, detectedLanguage.value, props.filePath],
  () => {
    // Use nextTick to avoid multiple recreations during rapid changes
    nextTick(() => {
      createEditor()
    })
  }
)

onMounted(() => {
  createEditor()
})

onUnmounted(() => {
  if (editorView) {
    editorView.destroy()
    editorView = null
  }
})

// Expose methods
defineExpose({
  getEditor: () => editorView,
  focus: () => editorView?.focus(),
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
