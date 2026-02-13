/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 纯文本显示解析器
 *
 * 不使用markdown解析，直接将文本转换为HTML显示
 * 特性：
 * 1. 懒加载：只在元素可见时解析
 * 2. 缓存：避免重复解析相同内容
 * 3. 空闲时解析：使用 requestIdleCallback 在浏览器空闲时解析
 */

import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'

// LRU 缓存实现
class TextCache {
  private cache: Map<string, { html: string; timestamp: number }>
  private maxSize: number
  private ttl: number // 5分钟缓存

  constructor(maxSize = 100, ttl = 5 * 60 * 1000) {
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

// 全局缓存实例
const textCache = new TextCache(200, 5 * 60 * 1000)

/**
 * 纯文本解析 Hook
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
  } = {}
) {
  const {
    immediate = false,
    parseOnIdle = true
  } = options

  const renderedHtml = ref<string>('')
  const isParsing = ref<boolean>(false)
  const isParsed = ref<boolean>(false)

  let observer: IntersectionObserver | null = null
  let idleCallbackId: number | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  /**
   * 解析文本为HTML（直接返回原文本）
   */
  const parseMarkdown = async (text: string): Promise<string> => {
    // 检查缓存
    const cached = textCache.get(text)
    if (cached) {
      return cached
    }

    // 解码Unicode转义序列
    const decodedText = text.replace(/\\u([0-9a-fA-F]{4})/g, (match, hex) => {
      return String.fromCharCode(parseInt(hex, 16))
    })

    // 不做任何处理，直接返回原文本
    // 缓存结果
    textCache.set(text, decodedText)
    return decodedText
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
    if (isParsing.value || isParsed.value) return

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
   * 重新解析（当文本变化时）
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
  textCache.clear()
}

/**
 * 获取缓存统计信息
 */
export function getMarkdownCacheStats() {
  return {
    size: textCache.size,
    maxSize: 200,
    ttl: 5 * 60 * 1000
  }
}
