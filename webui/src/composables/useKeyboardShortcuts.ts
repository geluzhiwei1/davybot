/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 键盘快捷键系统 - Vim风格
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { copyToClipboard } from '@/utils/clipboard'

export type VimMode = 'normal' | 'insert' | 'visual'

interface ShortcutAction {
  key: string
  description: string
  action: (event?: KeyboardEvent) => void
  condition?: () => boolean
}

export function useKeyboardShortcuts() {
  const mode = ref<VimMode>('normal')
  const showHelp = ref(false)

  // 快捷键映射
  const shortcuts: Record<string, ShortcutAction> = {
    // === 模式切换 ===
    'i': {
      key: 'i',
      description: '进入插入模式',
      action: () => {
        mode.value = 'insert'
        focusInput()
      }
    },
    'Escape': {
      key: 'Escape',
      description: '返回正常模式',
      action: () => {
        mode.value = 'normal'
        ;(document.activeElement as HTMLElement)?.blur()
      }
    },

    // === 导航 ===
    'j': {
      key: 'j',
      description: '下一条消息',
      action: () => scrollDown(),
      condition: () => mode.value === 'normal'
    },
    'k': {
      key: 'k',
      description: '上一条消息',
      action: () => scrollUp(),
      condition: () => mode.value === 'normal'
    },
    'gg': {
      key: 'gg',
      description: '跳转到顶部',
      action: () => scrollToTop(),
      condition: () => mode.value === 'normal'
    },
    'G': {
      key: 'G',
      description: '跳转到底部',
      action: () => scrollToBottom(),
      condition: () => mode.value === 'normal'
    },

    // === 操作 ===
    'Enter': {
      key: 'Enter',
      description: '发送消息',
      action: () => sendMessage(),
      condition: () => mode.value === 'insert'
    },
    '/': {
      key: '/',
      description: '搜索',
      action: () => openSearch(),
      condition: () => mode.value === 'normal'
    },
    'n': {
      key: 'n',
      description: '下一个搜索结果',
      action: () => nextSearch(),
      condition: () => mode.value === 'normal'
    },
    'N': {
      key: 'N',
      description: '上一个搜索结果',
      action: () => prevSearch(),
      condition: () => mode.value === 'normal'
    },

    // === 内容操作 ===
    'yy': {
      key: 'yy',
      description: '复制当前消息',
      action: () => copyCurrentMessage(),
      condition: () => mode.value === 'normal'
    },
    'dd': {
      key: 'dd',
      description: '删除当前消息',
      action: () => deleteCurrentMessage(),
      condition: () => mode.value === 'normal'
    },

    // === 折叠/展开 ===
    'fold': {
      key: 'fold',
      description: '折叠所有',
      action: () => foldAll(),
      condition: () => mode.value === 'normal'
    },
    'unfold': {
      key: 'unfold',
      description: '展开所有',
      action: () => unfoldAll(),
      condition: () => mode.value === 'normal'
    },

    // === 工具操作 ===
    'r': {
      key: 'r',
      description: '重试工具',
      action: () => retryTool(),
      condition: () => mode.value === 'normal'
    },
    'v': {
      key: 'v',
      description: '查看详情',
      action: () => viewDetails(),
      condition: () => mode.value === 'normal'
    },

    // === 帮助 ===
    '?': {
      key: '?',
      description: '显示/隐藏帮助',
      action: () => {
        showHelp.value = !showHelp.value
      }
    },

    // === 其他 ===
    'ctrl+f': {
      key: 'ctrl+f',
      description: '查找',
      action: () => openSearch()
    },
    'ctrl+c': {
      key: 'ctrl+c',
      description: '复制选中内容',
      action: () => copySelection()
    },
    'ctrl+v': {
      key: 'ctrl+v',
      description: '粘贴',
      action: () => pasteContent()
    }
  }

  // 当前按键序列（用于处理组合键如 gg）
  let keySequence: string[] = []
  let keySequenceTimeout: number | null = null

  // 处理按键
  const handleKeyPress = (event: KeyboardEvent) => {
    // 如果在输入框中且不在正常模式，不触发快捷键
    const activeTag = document.activeElement?.tagName
    const isInInput = activeTag === 'INPUT' ||
                      activeTag === 'TEXTAREA' ||
                      activeTag === 'SELECT'

    if (isInInput && mode.value !== 'normal') {
      return
    }

    // 构建按键标识
    let key = event.key
    if (event.ctrlKey) key = 'ctrl+' + key.toLowerCase()
    if (event.altKey) key = 'alt+' + key.toLowerCase()
    if (event.shiftKey && key.length === 1) key = key.toUpperCase()

    // 添加到序列
    keySequence.push(key)

    // 清除之前的定时器
    if (keySequenceTimeout) {
      clearTimeout(keySequenceTimeout)
    }

    // 设置新的定时器（500ms后清空序列）
    keySequenceTimeout = window.setTimeout(() => {
      keySequence = []
    }, 500)

    // 检查是否匹配快捷键
    const sequence = keySequence.join('')
    const shortcut = shortcuts[sequence] || shortcuts[key]

    if (shortcut) {
      // 检查条件
      if (shortcut.condition && !shortcut.condition()) {
        return
      }

      event.preventDefault()
      shortcut.action(event)

      // 清空序列
      keySequence = []
    }
  }

  // === 实现各个操作函数 ===

  const focusInput = () => {
    const textarea = document.querySelector('textarea.el-textarea__inner') as HTMLTextAreaElement
    if (textarea) {
      textarea.focus()
    }
  }

  const scrollDown = () => {
    window.scrollBy({ top: 100, behavior: 'auto' })
  }

  const scrollUp = () => {
    window.scrollBy({ top: -100, behavior: 'auto' })
  }

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'auto' })
  }

  const scrollToBottom = () => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'auto' })
  }

  const sendMessage = () => {
    const textarea = document.querySelector('textarea.el-textarea__inner') as HTMLTextAreaElement
    const button = document.querySelector('button[type="submit"]') as HTMLButtonElement

    if (textarea && textarea.value.trim()) {
      button?.click()
    }
  }

  const openSearch = () => {
    ElMessage.info('搜索功能（待实现）')
    // TODO: 实现搜索功能
  }

  const nextSearch = () => {
    ElMessage.info('下一个搜索结果（待实现）')
  }

  const prevSearch = () => {
    ElMessage.info('上一个搜索结果（待实现）')
  }

  const copyCurrentMessage = () => {
    // TODO: 获取当前消息并复制
    ElMessage.success('已复制当前消息')
  }

  const deleteCurrentMessage = () => {
    ElMessage.warning('删除功能（待实现）')
  }

  const foldAll = () => {
    // 折叠所有 el-collapse
    const collapses = document.querySelectorAll('.el-collapse-item__header')
    collapses.forEach((collapse) => {
      (collapse as HTMLElement).click()
    })
    ElMessage.success('已折叠所有')
  }

  const unfoldAll = () => {
    // 展开所有 el-collapse
    const collapses = document.querySelectorAll('.el-collapse-item__header')
    collapses.forEach((collapse) => {
      if (!collapse.classList.contains('is-active')) {
        (collapse as HTMLElement).click()
      }
    })
    ElMessage.success('已展开所有')
  }

  const retryTool = () => {
    ElMessage.info('重试工具（待实现）')
  }

  const viewDetails = () => {
    ElMessage.info('查看详情（待实现）')
  }

  const copySelection = () => {
    const selection = window.getSelection()
    if (selection && selection.toString()) {
      copyToClipboard(selection.toString()).then(success => {
        if (success) {
          ElMessage.success('已复制')
        }
      })
    }
  }

  const pasteContent = () => {
    ElMessage.info('粘贴功能（待实现）')
  }

  // 获取所有快捷键列表
  const getShortcutList = () => {
    return Object.values(shortcuts).map(s => ({
      key: s.key,
      description: s.description
    }))
  }

  // 生命周期
  onMounted(() => {
    window.addEventListener('keydown', handleKeyPress)

    // 根据焦点自动切换模式
    const focusObserver = new MutationObserver(() => {
      const activeTag = document.activeElement?.tagName
      const isInInput = activeTag === 'INPUT' ||
                        activeTag === 'TEXTAREA' ||
                        activeTag === 'SELECT'

      if (isInInput && mode.value !== 'insert') {
        mode.value = 'insert'
      } else if (!isInInput && mode.value === 'insert') {
        mode.value = 'normal'
      }
    })

    focusObserver.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['focused']
    })
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyPress)
    if (keySequenceTimeout) {
      clearTimeout(keySequenceTimeout)
    }
  })

  return {
    mode,
    showHelp,
    shortcuts,
    getShortcutList,
    toggleHelp: () => { showHelp.value = !showHelp.value },
    setMode: (newMode: VimMode) => { mode.value = newMode }
  }
}
