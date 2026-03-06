/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 页面缩放管理 Composable
 * 支持 Tauri 桌面应用和 Web 浏览器
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { isTauri } from '@/utils/platform'
import { invoke } from '@tauri-apps/api/core'

// Zoom level storage key
const ZOOM_STORAGE_KEY = 'dawei-zoom-level'

export interface ZoomOptions {
  min?: number
  max?: number
  step?: number
}

export function useZoom(options: ZoomOptions = {}) {
  const {
    min = 0.5,   // 50%
    max = 3.0,   // 300%
    step = 0.1   // 10%
  } = options

  // Current zoom level (1.0 = 100%)
  const zoomLevel = ref<number>(1.0)
  const isTauriEnv = ref<boolean>(false)

  // Initialize zoom level from localStorage
  const initZoom = () => {
    try {
      const saved = localStorage.getItem(ZOOM_STORAGE_KEY)
      if (saved) {
        const level = parseFloat(saved)
        if (!isNaN(level) && level >= min && level <= max) {
          zoomLevel.value = level
        }
      }
    } catch (error) {
      console.warn('Failed to load zoom level:', error)
    }
  }

  // Save zoom level to localStorage
  const saveZoom = (level: number) => {
    try {
      localStorage.setItem(ZOOM_STORAGE_KEY, level.toString())
    } catch (error) {
      console.warn('Failed to save zoom level:', error)
    }
  }

  // Apply zoom to document
  const applyZoom = (level: number) => {
    // 无论是 Tauri 还是 Web 模式，都使用 CSS zoom
    // 这是最可靠和跨平台的解决方案

    // 方法1: 使用 documentElement.style.zoom (现代浏览器)
    document.documentElement.style.zoom = level.toString()

    // 方法2: 使用 transform scale 作为备选方案
    if (document.documentElement.style.zoom === '' || document.documentElement.style.zoom === undefined) {
      document.body.style.transform = `scale(${level})`
      document.body.style.transformOrigin = 'top left'
      document.body.style.width = `${100 / level}%`
      document.body.style.height = 'auto'
    }

    // 保存到 data 属性，用于调试
    document.documentElement.setAttribute('data-zoom-level', level.toString())
  }

  // Zoom in
  const zoomIn = async () => {
    const newLevel = Math.min(zoomLevel.value + step, max)

    if (isTauriEnv.value) {
      try {
        await invoke('zoom_in')
      } catch (error) {
        console.error('Failed to call Tauri zoom_in:', error)
      }
    }

    // 无论是在 Tauri 还是 Web 环境，都在前端应用缩放
    zoomLevel.value = newLevel
    saveZoom(newLevel)
    applyZoom(newLevel)
    ElMessage.success(`放大: ${(newLevel * 100).toFixed(0)}%`)
  }

  // Zoom out
  const zoomOut = async () => {
    const newLevel = Math.max(zoomLevel.value - step, min)

    if (isTauriEnv.value) {
      try {
        await invoke('zoom_out')
      } catch (error) {
        console.error('Failed to call Tauri zoom_out:', error)
      }
    }

    // 无论是在 Tauri 还是 Web 环境，都在前端应用缩放
    zoomLevel.value = newLevel
    saveZoom(newLevel)
    applyZoom(newLevel)
    ElMessage.success(`缩小: ${(newLevel * 100).toFixed(0)}%`)
  }

  // Reset zoom
  const zoomReset = async () => {
    if (isTauriEnv.value) {
      try {
        await invoke('zoom_reset')
      } catch (error) {
        console.error('Failed to call Tauri zoom_reset:', error)
      }
    }

    // 无论是在 Tauri 还是 Web 环境，都在前端应用缩放
    zoomLevel.value = 1.0
    saveZoom(1.0)
    applyZoom(1.0)
    ElMessage.success('重置缩放: 100%')
  }

  // Set specific zoom level
  const setZoom = async (level: number) => {
    const newLevel = Math.max(min, Math.min(max, level))

    if (isTauriEnv.value) {
      try {
        await invoke('set_zoom', { zoomLevel: newLevel })
      } catch (error) {
        console.error('Failed to call Tauri set_zoom:', error)
      }
    }

    // 无论是在 Tauri 还是 Web 环境，都在前端应用缩放
    zoomLevel.value = newLevel
    saveZoom(newLevel)
    applyZoom(newLevel)
    ElMessage.success(`缩放: ${(newLevel * 100).toFixed(0)}%`)
  }

  // Computed properties
  const zoomPercentage = computed(() => `${(zoomLevel.value * 100).toFixed(0)}%`)
  const canZoomIn = computed(() => zoomLevel.value < max)
  const canZoomOut = computed(() => zoomLevel.value > min)
  const isDefaultZoom = computed(() => zoomLevel.value === 1.0)

  // Handle keyboard shortcuts
  const handleKeydown = (event: KeyboardEvent) => {
    // Ctrl + Plus/Equal (+/=): Zoom in
    if ((event.ctrlKey || event.metaKey) && (event.key === '+' || event.key === '=')) {
      event.preventDefault()
      zoomIn()
    }
    // Ctrl + Minus (-): Zoom out
    else if ((event.ctrlKey || event.metaKey) && event.key === '-') {
      event.preventDefault()
      zoomOut()
    }
    // Ctrl + 0: Reset zoom
    else if ((event.ctrlKey || event.metaKey) && event.key === '0') {
      event.preventDefault()
      zoomReset()
    }
  }

  // Listen for zoom changes from Tauri backend
  const setupTauriListener = () => {
    if (!isTauriEnv.value) return

    try {
      // Listen for zoom change events from Tauri
      import('@tauri-apps/api/event').then(({ listen }) => {
        const unlisten = listen<number>('zoom-change', (event) => {
          zoomLevel.value = event.payload
          saveZoom(event.payload)
        })

        onUnmounted(() => {
          unlisten.then(fn => fn())
        })
      })
    } catch (error) {
      console.warn('Failed to setup Tauri zoom listener:', error)
    }
  }

  // Lifecycle
  onMounted(() => {
    // Check if running in Tauri
    isTauriEnv.value = isTauri()

    // Initialize zoom level
    initZoom()

    // Apply initial zoom
    if (!isTauriEnv.value) {
      applyZoom(zoomLevel.value)
    }

    // Setup keyboard shortcuts
    window.addEventListener('keydown', handleKeydown)

    // Setup Tauri event listener
    setupTauriListener()
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
  })

  return {
    zoomLevel,
    zoomPercentage,
    canZoomIn,
    canZoomOut,
    isDefaultZoom,
    zoomIn,
    zoomOut,
    zoomReset,
    setZoom
  }
}
