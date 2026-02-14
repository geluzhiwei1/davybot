/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Analytics Service
 * 用于跟踪用户行为和应用指标
 */

export interface AnalyticsEvent {
  name: string
  properties?: Record<string, unknown>
  timestamp?: number
}

export interface AnalyticsService {
  trackEvent(event: string, properties?: Record<string, unknown>): Promise<void>
  trackError(error: Error, context?: Record<string, unknown>): Promise<void>
  trackPageView(page: string, properties?: Record<string, unknown>): Promise<void>
}

/**
 * Analytics Service 实现
 */
class AnalyticsServiceImpl implements AnalyticsService {
  private enabled = false
  private queue: AnalyticsEvent[] = []

  constructor() {
    this.enabled = localStorage.getItem('analytics_consent') !== 'none'
  }

  async trackEvent(event: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.enabled) return

    this.queue.push({
      name: event,
      properties,
      timestamp: Date.now()
    })

    // TODO: 实现实际的分析服务集成
  }

  async trackError(error: Error, context?: Record<string, unknown>): Promise<void> {
    if (!this.enabled) return

    this.queue.push({
      name: 'error',
      properties: {
        error: error.message,
        stack: error.stack,
        ...context
      },
      timestamp: Date.now()
    })
  }

  async trackPageView(page: string, properties?: Record<string, unknown>): Promise<void> {
    if (!this.enabled) return

    this.queue.push({
      name: 'pageview',
      properties: {
        page,
        ...properties
      },
      timestamp: Date.now()
    })
  }

  getQueuedEvents(): AnalyticsEvent[] {
    return [...this.queue]
  }

  clearQueue(): void {
    this.queue = []
  }
}

// 导出单例实例
export const analyticsService = new AnalyticsServiceImpl()

// 重设用户同意级别
export function setAnalyticsConsent(consent: 'required' | 'analytics' | 'none'): void {
  localStorage.setItem('analytics_consent', consent)
  const service = analyticsService as unknown
  if (service.enabled !== undefined) {
    service.enabled = consent !== 'none'
  }
}
