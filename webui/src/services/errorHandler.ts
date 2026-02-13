/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 全局错误处理和崩溃报告服务
 *
 * 功能：
 * - 捕获全局 JavaScript 错误
 * - 捕获未处理的 Promise 拒绝
 * - 捕获 Vue 组件错误
 * - 自动保存崩溃报告到本地
 * - 发送错误到 Analytics
 * - 严重错误自动提交 Feedback
 */

interface ErrorContext {
  userAgent: string;
  url: string;
  timestamp: number;
  userId?: string;
  sessionId?: string;
  platform: 'web' | 'tauri';
  [key: string]: unknown;
}

interface CrashReport {
  id: string;
  error: Error | string;
  context: ErrorContext;
  stackTrace?: string;
  componentStack?: string;
  reported: boolean; // 是否已上报
}

class ErrorHandler {
  private crashReports: CrashReport[] = [];
  private maxCrashReports = 10;
  private storageKey = 'crash_reports';
  private initialized = false;

  /**
   * 初始化全局错误捕获
   */
  init() {
    if (this.initialized) {
      console.warn('[ErrorHandler] Already initialized');
      return;
    }

    console.log('[ErrorHandler] Initializing...');
    this.setupGlobalErrorHandler();
    this.setupUnhandledRejectionHandler();
    this.loadCrashReports();
    this.initialized = true;

    console.log('[ErrorHandler] Initialized successfully');
  }

  /**
   * 捕获全局 JavaScript 错误
   */
  private setupGlobalErrorHandler() {
    window.onerror = (
      message: string | Event,
      source?: string,
      lineno?: number,
      colno?: number,
      error?: Error
    ) => {
      console.error('[ErrorHandler] Global error caught:', { message, source, lineno, colno, error });

      const crashReport: CrashReport = {
        id: this.generateId(),
        error: error || new Error(String(message)),
        context: this.getErrorContext({
          type: 'global_error',
          source,
          lineno,
          colno,
        }),
        stackTrace: error?.stack,
        reported: false,
      };

      this.handleCrash(crashReport);

      // 返回 false 阻止默认控制台错误（我们已经处理了）
      return false;
    };
  }

  /**
   * 捕获未处理的 Promise 拒绝
   */
  private setupUnhandledRejectionHandler() {
    window.addEventListener('unhandledrejection', (event) => {
      console.error('[ErrorHandler] Unhandled rejection caught:', event.reason);

      const crashReport: CrashReport = {
        id: this.generateId(),
        error: event.reason,
        context: this.getErrorContext({
          type: 'unhandled_rejection',
          promise: event.promise?.toString(),
        }),
        stackTrace: event.reason?.stack,
        reported: false,
      };

      this.handleCrash(crashReport);

      // 阻止默认控制台输出
      event.preventDefault();
    });
  }

  /**
   * Vue 错误处理器 (在 main.ts 中调用)
   */
  setupVueErrorHandler(app: unknown) {
    app.config.errorHandler = (err: Error, instance: unknown, info: string) => {
      console.error('[ErrorHandler] Vue error caught:', { err, instance, info });

      const crashReport: CrashReport = {
        id: this.generateId(),
        error: err,
        context: this.getErrorContext({
          type: 'vue_error',
          info,
          component: instance?.$options?.name || instance?.$?.type?.name,
        }),
        stackTrace: err.stack,
        componentStack: info,
        reported: false,
      };

      this.handleCrash(crashReport);
    };
  }

  /**
   * 处理崩溃/错误
   */
  private async handleCrash(crashReport: CrashReport) {
    console.error('[ErrorHandler] Processing crash report:', crashReport.id);

    // 1. 保存到本地 (防止丢失)
    this.addCrashReport(crashReport);

    // 2. 尝试发送到 Analytics (如果用户同意且服务可用)
    try {
      // 动态导入 analyticsService (避免循环依赖)
      const { analyticsService } = await import('./analytics');
      await analyticsService.trackError(crashReport.error, crashReport.context);
      console.log('[ErrorHandler] Error sent to analytics');
    } catch (e) {
      console.warn('[ErrorHandler] Analytics not available or failed:', e);
    }

    // 3. 判断是否为严重错误，如果是则提示用户报告
    if (this.isCriticalError(crashReport.error)) {
      console.log('[ErrorHandler] Critical error detected, prompting user report');
      await this.promptUserReport(crashReport);
    }
  }

  /**
   * 添加崩溃报告
   */
  private addCrashReport(crashReport: CrashReport) {
    this.crashReports.push(crashReport);

    // 限制数量
    if (this.crashReports.length > this.maxCrashReports) {
      this.crashReports.shift();
    }

    this.saveCrashReports();
  }

  /**
   * 判断是否为严重错误
   */
  private isCriticalError(error: Error | string): boolean {
    const errorMsg = typeof error === 'string' ? error : error.message;

    // 白名单：非严重错误（通常由网络或资源加载导致）
    const nonCriticalPatterns = [
      /network/i,
      /timeout/i,
      /loading/i,
      /chunk.*load/i,
      /fetch/i,
      /404/i,
      /abort/i,
    ];

    return !nonCriticalPatterns.some(pattern => pattern.test(errorMsg));
  }

  /**
   * 提示用户报告崩溃
   */
  private async promptUserReport(crashReport: CrashReport) {
    try {
      // 动态导入 feedbackService
      const { feedbackService } = await import('./feedback');

      const reportData = {
        type: 'bug' as const,
        title: '应用异常',
        description: this.formatErrorDescription(crashReport),
        crashReport: {
          error: String(crashReport.error),
          context: crashReport.context,
          stackTrace: crashReport.stackTrace,
        },
      };

      // 检查用户同意级别
      const consent = localStorage.getItem('analytics_consent');

      if (consent === 'full') {
        // 自动发送
        await feedbackService.submitFeedback(reportData);
        crashReport.reported = true;
        this.saveCrashReports();
        console.log('[ErrorHandler] Crash report automatically submitted');
      } else if (consent === 'minimal') {
        // 只记录，不自动发送
        console.log('[ErrorHandler] Crash report saved (minimal consent mode)');
      }
      // consent === 'none': 不处理
    } catch (e) {
      console.error('[ErrorHandler] Failed to submit crash report:', e);
    }
  }

  /**
   * 格式化错误描述
   */
  private formatErrorDescription(report: CrashReport): string {
    const errorStr = typeof report.error === 'string'
      ? report.error
      : report.error.message || String(report.error);

    let desc = `**错误信息**\n${errorStr}\n\n`;
    desc += `**发生时间**\n${new Date(report.context.timestamp).toLocaleString('zh-CN')}\n\n`;
    desc += `**页面地址**\n${report.context.url}\n\n`;

    if (report.context.component) {
      desc += `**组件**\n${report.context.component}\n\n`;
    }

    if (report.stackTrace) {
      desc += `**堆栈跟踪**\n\`\`\`\n${report.stackTrace}\n\`\`\`\n\n`;
    }

    return desc;
  }

  /**
   * 获取错误上下文
   */
  private getErrorContext(extra?: unknown): ErrorContext {
    return {
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: Date.now(),
      userId: localStorage.getItem('user_id') || undefined,
      sessionId: sessionStorage.getItem('session_id') || undefined,
      platform: this.getPlatform(),
      ...extra,
    };
  }

  /**
   * 获取平台信息
   */
  private getPlatform(): 'web' | 'tauri' {
    return '__TAURI__' in window ? 'tauri' : 'web';
  }

  /**
   * 生成唯一 ID
   */
  private generateId(): string {
    return `crash_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * 保存崩溃报告到 localStorage
   */
  private saveCrashReports() {
    try {
      const data = JSON.stringify(this.crashReports);
      localStorage.setItem(this.storageKey, data);
      console.log(`[ErrorHandler] Saved ${this.crashReports.length} crash reports`);
    } catch (e) {
      console.error('[ErrorHandler] Failed to save crash reports:', e);

      // 如果 localStorage 满了，清除旧报告
      if (e instanceof DOMException && e.name === 'QuotaExceededError') {
        console.warn('[ErrorHandler] LocalStorage quota exceeded, clearing old reports');
        this.crashReports = this.crashReports.slice(-3); // 只保留最近3个
        try {
          localStorage.setItem(this.storageKey, JSON.stringify(this.crashReports));
        } catch (e2) {
          console.error('[ErrorHandler] Still failed to save after cleanup:', e2);
        }
      }
    }
  }

  /**
   * 加载崩溃报告
   */
  loadCrashReports(): CrashReport[] {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        this.crashReports = JSON.parse(saved);
        console.log(`[ErrorHandler] Loaded ${this.crashReports.length} crash reports`);
      } else {
        this.crashReports = [];
      }
    } catch (e) {
      console.error('[ErrorHandler] Failed to load crash reports:', e);
      this.crashReports = [];
    }

    return this.crashReports;
  }

  /**
   * 清除所有崩溃报告
   */
  clearCrashReports() {
    this.crashReports = [];
    localStorage.removeItem(this.storageKey);
    console.log('[ErrorHandler] All crash reports cleared');
  }

  /**
   * 标记崩溃报告为已上报
   */
  markAsReported(id: string) {
    const report = this.crashReports.find(r => r.id === id);
    if (report) {
      report.reported = true;
      this.saveCrashReports();
    }
  }

  /**
   * 手动报告错误
   */
  async reportError(error: Error | string, context?: unknown) {
    const crashReport: CrashReport = {
      id: this.generateId(),
      error,
      context: this.getErrorContext(context),
      stackTrace: typeof error === 'object' && error instanceof Error ? error.stack : undefined,
      reported: false,
    };

    await this.handleCrash(crashReport);
    return crashReport.id;
  }

  /**
   * 获取所有崩溃报告
   */
  getCrashReports(): CrashReport[] {
    return [...this.crashReports];
  }

  /**
   * 获取未上报的崩溃报告
   */
  getUnreportedCrashes(): CrashReport[] {
    return this.crashReports.filter(r => !r.reported);
  }

  /**
   * 导出崩溃报告
   */
  exportCrashReports(): string {
    return JSON.stringify(this.crashReports, null, 2);
  }

  /**
   * 获取崩溃统计
   */
  getCrashStats() {
    const total = this.crashReports.length;
    const reported = this.crashReports.filter(r => r.reported).length;
    const unreported = total - reported;

    // 按类型分组
    const byType = this.crashReports.reduce((acc, report) => {
      const type = report.context.type || 'unknown';
      acc[type] = (acc[type] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      total,
      reported,
      unreported,
      byType,
      latest: this.crashReports[this.crashReports.length - 1],
    };
  }
}

// 导出单例
export const errorHandler = new ErrorHandler();

// 导出类型
export type { ErrorContext, CrashReport };
