/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Markdown/纯文本 解析器
 *
 * 支持 Markdown 和纯文本两种模式
 * 特性：
 * 1. 双模式渲染：Markdown 纯文本
 * 2. 懒加载：只在元素可见时解析
 * 3. 双缓存：两种模式独立缓存
 * 4. 空闲时解析：使用 requestIdleCallback 在浏览器空闲时解析
 */

import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import MarkdownIt from 'markdown-it'
import type { MarkdownMode } from '@/stores/markdownSettings'

// 初始化 Markdown-it
const md = new MarkdownIt({
  html: true,        // 允许 HTML 标签
  linkify: true,     // 自动转换 URL 为链接
  typographer: true, // 启用排版优化
  breaks: true       // 转换换行符为 <br>
})

// LRU 缓存实现
class TextCache {
  private cache: Map<string, { html: string; timestamp: number }>
  private maxSize: number
  private ttl: number // 5分钟缓存

  constructor(maxSize = 200, ttl = 5 * 60 * 1000) {
    this.cache = new Map()
    this.maxSize = maxSize
    this.ttl = ttl
  }

  get(key: string): string | null {
    const item = this.cache.get(key)
    if (!item) return null

    // 检查是否过期
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key)
      return null
    }

    // LRU: 移到最后
    this.cache.delete(key)
    this.cache.set(key, item)
    return item.html
  }

  set(key: string, html: string): void {
    // 删除最旧的项（如果超出限制）
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value
      this.cache.delete(firstKey)
    }

    this.cache.set(key, { html, timestamp: Date.now() })
  }

  clear(): void {
    this.cache.clear()
  }

  get size(): number {
    return this.cache.size
  }
}

// 两个独立的缓存实例
const markdownCache = new TextCache(200, 5 * 60 * 1000)
const plainTextCache = new TextCache(200, 5 * 60 * 1000)

/**
 * Markdown/纯文本 解析 Hook
 *
 * @param elementRef - 元素引用
 * @param text - 文本内容
 * @param options - 配置选项
 */
export function useMarkdownParser(
  elementRef: Ref<HTMLElement | undefined>,
  text: Ref<string> | string,
  options: {
    immediate?: boolean // 是否立即解析（默认为 false，等待可见）
    parseOnIdle?: boolean // 是否在空闲时解析（默认 true）
    mode?: Ref<MarkdownMode> // 渲染模式（新增）
  } = {}
) {
  const {
    immediate = false,
    parseOnIdle = true,
    mode = ref<MarkdownMode>('plain')
  } = options

  const renderedHtml = ref<string>('')
  const isParsing = ref<boolean>(false)
  const isParsed = ref<boolean>(false)

  let observer: IntersectionObserver | null = null
  let idleCallbackId: number | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  /**
   * 解析文本为 HTML
   */
  const parseMarkdown = async (text: string): Promise<string> => {
    // 根据模式选择缓存
    const cache = mode.value === 'markdown' ? markdownCache : plainTextCache
    const cached = cache.get(text)
    if (cached) {
      return cached
    }

    let result: string

    if (mode.value === 'markdown') {
      // Markdown 模式：使用 markdown-it 解析
      result = md.render(text)
    } else {
      // 纯文本模式：仅解码 Unicode 转义序列
      result = text.replace(/\\u([0-9a-fA-F]{4})/g, (match, hex) => {
        return String.fromCharCode(parseInt(hex, 16))
      })
    }

    // 缓存结果
    cache.set(text, result)
    return result
  }

  /**
   * 在空闲时解析（不阻塞主线程）
   */
  const parseWhenIdle = (markdownText: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      const textToParse = markdownText

      const handleError = (error: unknown) => {
        console.error('[useMarkdownParser] Failed to parse markdown:', error)
        reject(error)
      }

      const parseTask = () => {
        parseMarkdown(textToParse).then(resolve).catch(handleError)
      }

      if (typeof requestIdleCallback !== 'undefined') {
        idleCallbackId = requestIdleCallback(
          parseTask,
          { timeout: 2000 } // 2秒后强制执行
        )
      } else {
        // 降级：使用 setTimeout
        timeoutId = setTimeout(parseTask, 0)
      }
    })
  }

  /**
   * 执行解析
   */
  const doParse = async () => {
    const markdownText = typeof text === 'string' ? text : text.value
    if (!markdownText) return

    isParsing.value = true

    try {
      if (parseOnIdle) {
        renderedHtml.value = await parseWhenIdle(markdownText)
      } else {
        renderedHtml.value = await parseMarkdown(markdownText)
      }
      isParsed.value = true
    } finally {
      isParsing.value = false
    }
  }

  /**
   * 设置 Intersection Observer
   */
  const setupIntersectionObserver = () => {
    if (!elementRef.value || immediate) {
      doParse()
      return
    }

    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !isParsed.value) {
            // 元素可见，开始解析
            doParse()
            // 解析完成后停止观察
            if (observer && elementRef.value) {
              observer.unobserve(elementRef.value)
            }
          }
        })
      },
      {
        rootMargin: '100px', // 提前 100px 开始加载
        threshold: 0
      }
    )

    observer.observe(elementRef.value)
  }

  /**
   * 重新解析（当文本或模式变化时）
   */
  const reparse = async () => {
    isParsed.value = false
    await doParse()
  }

  /**
   * 清理资源
   */
  const cleanup = () => {
    if (observer && elementRef.value) {
      observer.unobserve(elementRef.value)
      observer.disconnect()
      observer = null
    }

    // Cancel pending idle callback
    if (idleCallbackId !== null && typeof cancelIdleCallback !== 'undefined') {
      cancelIdleCallback(idleCallbackId)
      idleCallbackId = null
    }

    // Cancel pending timeout
    if (timeoutId !== null) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  onMounted(() => {
    setupIntersectionObserver()

    // Watch for text changes and re-parse
    watch(
      () => typeof text === 'string' ? text : text.value,
      () => {
        isParsed.value = false
        doParse()
      }
    )

    // Watch for mode changes and re-parse
    watch(
      mode,
      () => {
        isParsed.value = false
        doParse()
      }
    )
  })

  onUnmounted(() => {
    cleanup()
  })

  return {
    renderedHtml,
    isParsing,
    isParsed,
    reparse,
    parse: doParse
  }
}

/**
 * 清除所有文本缓存
 */
export function clearMarkdownCache() {
  markdownCache.clear()
  plainTextCache.clear()
}

/**
 * 获取缓存统计信息
 */
export function getMarkdownCacheStats() {
  return {
    markdown: {
      size: markdownCache.size,
      maxSize: 200,
      ttl: 5 * 60 * 1000
    },
    plain: {
      size: plainTextCache.size,
      maxSize: 200,
      ttl: 5 * 60 * 1000
    }
  }
}
