/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 错误处理性能监控工具
 * 用于监控错误消息处理性能和layer使用情况
 */

export interface ErrorMetrics {
  // 错误消息总数
  totalErrors: number

  // 各层使用次数
  layer1Usage: number  // 直接使用workspace_id
  layer2Usage: number  // 从session_id解析
  layer3Usage: number  // fallback到当前workspace

  // 失败次数
  addMessageFailures: number
  fallbackUsage: number

  // 性能指标（毫秒）
  avgResolutionTime: number
  maxResolutionTime: number
  minResolutionTime: number

  // 时间戳
  lastUpdated: string
}

class ErrorMonitoring {
  private metrics: ErrorMetrics = {
    totalErrors: 0,
    layer1Usage: 0,
    layer2Usage: 0,
    layer3Usage: 0,
    addMessageFailures: 0,
    fallbackUsage: 0,
    avgResolutionTime: 0,
    maxResolutionTime: 0,
    minResolutionTime: Infinity,
    lastUpdated: new Date().toISOString()
  }

  private resolutionTimes: number[] = []

  /**
   * 记录错误消息处理
   * @param layer 使用的解析层级 (1, 2, 3)
   * @param resolutionTime 解析耗时（毫秒）
   * @param usedFallback 是否使用了fallback机制
   */
  recordErrorHandling(
    layer: number,
    resolutionTime: number,
    usedFallback: boolean = false
  ): void {
    // 更新总数
    this.metrics.totalErrors++

    // 更新layer使用次数
    switch (layer) {
      case 1:
        this.metrics.layer1Usage++
        break
      case 2:
        this.metrics.layer2Usage++
        break
      case 3:
        this.metrics.layer3Usage++
        break
    }

    // 更新fallback使用次数
    if (usedFallback) {
      this.metrics.fallbackUsage++
    }

    // 更新性能指标
    this.resolutionTimes.push(resolutionTime)
    this.updatePerformanceMetrics()

    // 更新时间戳
    this.metrics.lastUpdated = new Date().toISOString()
  }

  /**
   * 记录addMessage失败
   */
  recordAddMessageFailure(): void {
    this.metrics.addMessageFailures++
    this.metrics.lastUpdated = new Date().toISOString()

    if (import.meta.env.DEV) {
      console.warn('[ErrorMonitoring] addMessage failure recorded')
    }
  }

  /**
   * 更新性能指标
   */
  private updatePerformanceMetrics(): void {
    if (this.resolutionTimes.length === 0) return

    const sum = this.resolutionTimes.reduce((a, b) => a + b, 0)
    this.metrics.avgResolutionTime = sum / this.resolutionTimes.length
    this.metrics.maxResolutionTime = Math.max(...this.resolutionTimes)
    this.metrics.minResolutionTime = Math.min(...this.resolutionTimes)
  }

  /**
   * 获取当前指标
   */
  getMetrics(): ErrorMetrics {
    return { ...this.metrics }
  }

  /**
   * 获取layer使用分布（百分比）
   */
  getLayerDistribution(): {
    layer1: number
    layer2: number
    layer3: number
  } {
    const total = this.metrics.totalErrors || 1 // 避免除以0

    return {
      layer1: (this.metrics.layer1Usage / total) * 100,
      layer2: (this.metrics.layer2Usage / total) * 100,
      layer3: (this.metrics.layer3Usage / total) * 100
    }
  }

  /**
   * 获取健康状态
   */
  getHealthStatus(): {
    status: 'healthy' | 'warning' | 'critical'
    issues: string[]
  } {
    const issues: string[] = []
    const distribution = this.getLayerDistribution()

    // 检查1: Layer 3 fallback使用率过高（>10%）
    if (distribution.layer3 > 10) {
      issues.push(
        `Layer 3 fallback使用率过高: ${distribution.layer3.toFixed(1)}% (建议<10%). ` +
        `这表明session→workspace映射存在问题`
      )
    }

    // 检查2: addMessage失败率过高（>5%）
    const failureRate = (this.metrics.addMessageFailures / (this.metrics.totalErrors || 1)) * 100
    if (failureRate > 5) {
      issues.push(
        `addMessage失败率过高: ${failureRate.toFixed(1)}% (建议<5%). ` +
        `这表明仍有错误消息丢失`
      )
    }

    // 检查3: 平均解析时间过长（>10ms）
    if (this.metrics.avgResolutionTime > 10) {
      issues.push(
        `平均解析时间过长: ${this.metrics.avgResolutionTime.toFixed(2)}ms (建议<10ms)`
      )
    }

    // 确定状态
    let status: 'healthy' | 'warning' | 'critical' = 'healthy'
    if (issues.length >= 2 || distribution.layer3 > 20) {
      status = 'critical'
    } else if (issues.length > 0) {
      status = 'warning'
    }

    return { status, issues }
  }

  /**
   * 重置指标
   */
  reset(): void {
    this.metrics = {
      totalErrors: 0,
      layer1Usage: 0,
      layer2Usage: 0,
      layer3Usage: 0,
      addMessageFailures: 0,
      fallbackUsage: 0,
      avgResolutionTime: 0,
      maxResolutionTime: 0,
      minResolutionTime: Infinity,
      lastUpdated: new Date().toISOString()
    }
    this.resolutionTimes = []
  }

  /**
   * 导出为JSON（用于日志聚合）
   */
  exportToJson(): string {
    return JSON.stringify({
      metrics: this.metrics,
      distribution: this.getLayerDistribution(),
      health: this.getHealthStatus()
    })
  }
}

// 单例实例
export const errorMonitoring = new ErrorMonitoring()

/**
 * 性能监控装饰器
 * 用于监控函数执行时间
 */
export function measurePerformance(layer: number) {
  return function (
    target: unknown,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value

    descriptor.value = function (...args: unknown[]) {
      const startTime = performance.now()
      let usedFallback = false

      try {
        const result = originalMethod.apply(this, args)

        // 检查是否使用了fallback
        if (result && typeof result === 'object' && 'usedFallback' in result) {
          usedFallback = result.usedFallback
        }

        const endTime = performance.now()
        const duration = endTime - startTime

        errorMonitoring.recordErrorHandling(layer, duration, usedFallback)

        return result
      } catch (error) {
        const endTime = performance.now()
        const duration = endTime - startTime

        errorMonitoring.recordErrorHandling(layer, duration, true)
        errorMonitoring.recordAddMessageFailure()

        throw error
      }
    }

    return descriptor
  }
}

/**
 * 定期上报指标（生产环境）
 */
export function startMetricsReporting(intervalMs: number = 60000): void {
  if (import.meta.env.PROD) {
    setInterval(() => {
      const health = errorMonitoring.getHealthStatus()

      // 发送到监控系统（如Sentry）
      if (typeof window !== 'undefined' && (window as unknown).Sentry) {
        ;(window as unknown).Sentry.captureMessage('Error Handling Metrics', {
          level: health.status,
          extra: {
            metrics: errorMonitoring.getMetrics(),
            distribution: errorMonitoring.getLayerDistribution(),
            health: health
          }
        })
      }

      // 或发送到后端API
      if (health.status !== 'healthy') {
        fetch('/api/metrics/error-handling', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: errorMonitoring.exportToJson()
        }).catch(err => {
          console.error('[ErrorMonitoring] Failed to report metrics:', err)
        })
      }
    }, intervalMs)
  }
}

export default errorMonitoring
