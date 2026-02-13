/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Feedback Service
 * 用于收集用户反馈和崩溃报告
 */

export interface FeedbackData {
  title: string
  description: string
  category?: string
  severity?: 'low' | 'medium' | 'high' | 'critical'
  timestamp?: number
  metadata?: Record<string, unknown>
}

export interface CrashReport extends FeedbackData {
  crashReport: {
    title: string
    description: string
    crashReport: unknown
    metadata?: Record<string, unknown>
  }
}

export interface FeedbackService {
  submitFeedback(feedback: FeedbackData): Promise<void>
  submitCrashReport(report: CrashReport): Promise<void>
  getPendingReports(): CrashReport[]
  clearPendingReports(): void
}

/**
 * Feedback Service 实现
 */
class FeedbackServiceImpl implements FeedbackService {
  private apiEndpoint = '/api/feedback'
  private pendingStorageKey = 'pending_feedback'

  async submitFeedback(feedback: FeedbackData): Promise<void> {
    try {
      // TODO: 实现实际的API调用
      console.log('[Feedback] Submitting feedback:', feedback)

      // 临时实现：保存到本地存储
      const reports = this.getPendingReports()
      reports.push({
        ...feedback,
        timestamp: Date.now()
      } as unknown)
      this.savePendingReports(reports)

      console.log('[Feedback] Feedback saved locally')
    } catch (error) {
      console.error('[Feedback] Failed to submit feedback:', error)
      throw error
    }
  }

  async submitCrashReport(report: CrashReport): Promise<void> {
    try {
      // TODO: 实现实际的API调用
      console.log('[Feedback] Submitting crash report:', report)

      // 临时实现：保存到本地存储
      const reports = this.getPendingReports()
      reports.push(report)
      this.savePendingReports(reports)

      console.log('[Feedback] Crash report saved locally')
    } catch (error) {
      console.error('[Feedback] Failed to submit crash report:', error)
      throw error
    }
  }

  getPendingReports(): CrashReport[] {
    try {
      const data = localStorage.getItem(this.pendingStorageKey)
      return data ? JSON.parse(data) : []
    } catch (error) {
      console.error('[Feedback] Failed to load pending reports:', error)
      return []
    }
  }

  clearPendingReports(): void {
    localStorage.removeItem(this.pendingStorageKey)
  }

  private savePendingReports(reports: CrashReport[]): void {
    try {
      localStorage.setItem(this.pendingStorageKey, JSON.stringify(reports))
    } catch (error) {
      console.error('[Feedback] Failed to save pending reports:', error)
    }
  }

  /**
   * 同步待处理的报告到服务器
   */
  async syncPendingReports(): Promise<number> {
    const reports = this.getPendingReports()
    if (reports.length === 0) {
      return 0
    }

    let syncedCount = 0
    for (const report of reports) {
      try {
        await this.submitCrashReport(report)
        syncedCount++
      } catch (error) {
        console.error('[Feedback] Failed to sync report:', error)
      }
    }

    if (syncedCount > 0) {
      this.clearPendingReports()
    }

    return syncedCount
  }
}

// 导出单例实例
export const feedbackService = new FeedbackServiceImpl()

// 辅助函数：创建反馈数据
export function createFeedback(
  title: string,
  description: string,
  category?: string,
  severity?: FeedbackData['severity']
): FeedbackData {
  return {
    title,
    description,
    category,
    severity,
    timestamp: Date.now()
  }
}

// 辅助函数：创建崩溃报告
export function createCrashReport(
  title: string,
  description: string,
  error: Error,
  context?: Record<string, unknown>
): CrashReport {
  return {
    title,
    description,
    category: 'crash',
    severity: 'critical',
    timestamp: Date.now(),
    crashReport: {
      title,
      description,
      crashReport: {
        error,
        context
      }
    }
  }
}
