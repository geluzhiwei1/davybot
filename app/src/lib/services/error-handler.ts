/**
 * Global error handler — crash reports, unhandled rejections.
 * Migrated from legalbot/webui/src/services/errorHandler.ts
 * Adapted for React (no Vue-specific error handler).
 */

import { IS_DESKTOP } from "@/lib/platform";

interface ErrorContext {
  userAgent: string;
  url: string;
  timestamp: number;
  userId?: string;
  sessionId?: string;
  platform: "web" | "desktop";
  [key: string]: unknown;
}

interface CrashReport {
  id: string;
  error: Error | string;
  context: ErrorContext;
  stackTrace?: string;
  componentStack?: string;
  reported: boolean;
}

class ErrorHandler {
  private crashReports: CrashReport[] = [];
  private maxCrashReports = 10;
  private storageKey = "crash_reports";
  private initialized = false;

  init(): void {
    if (this.initialized) return;
    this.setupGlobalErrorHandler();
    this.setupUnhandledRejectionHandler();
    this.loadCrashReports();
    this.initialized = true;
  }

  private setupGlobalErrorHandler(): void {
    window.onerror = (message, source, lineno, colno, error) => {
      console.error("[ErrorHandler] Global error:", { message, source, lineno, colno, error });

      const report: CrashReport = {
        id: this.generateId(),
        error: error || new Error(String(message)),
        context: this.getErrorContext({ type: "global_error", source, lineno, colno }),
        stackTrace: error?.stack,
        reported: false,
      };
      this.handleCrash(report);
      return false;
    };
  }

  private setupUnhandledRejectionHandler(): void {
    window.addEventListener("unhandledrejection", (event) => {
      console.error("[ErrorHandler] Unhandled rejection:", event.reason);

      const report: CrashReport = {
        id: this.generateId(),
        error: event.reason,
        context: this.getErrorContext({ type: "unhandled_rejection" }),
        stackTrace: event.reason?.stack,
        reported: false,
      };
      this.handleCrash(report);
      event.preventDefault();
    });
  }

  private handleCrash(report: CrashReport): void {
    console.error("[ErrorHandler] Crash:", report.id);
    this.addCrashReport(report);
  }

  private addCrashReport(report: CrashReport): void {
    this.crashReports.push(report);
    if (this.crashReports.length > this.maxCrashReports) {
      this.crashReports.shift();
    }
    this.saveCrashReports();
  }

  private getErrorContext(extra?: Record<string, unknown>): ErrorContext {
    return {
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: Date.now(),
      userId: localStorage.getItem("user_id") || undefined,
      sessionId: sessionStorage.getItem("session_id") || undefined,
      platform: IS_DESKTOP ? "desktop" : "web",
      ...extra,
    };
  }

  private generateId(): string {
    return `crash_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
  }

  // ─── Public API ──────────────────────────────────────────────────────

  reportError(error: Error | string, context?: Record<string, unknown>): string {
    const report: CrashReport = {
      id: this.generateId(),
      error,
      context: this.getErrorContext(context),
      stackTrace: error instanceof Error ? error.stack : undefined,
      reported: false,
    };
    this.addCrashReport(report);
    return report.id;
  }

  getCrashReports(): CrashReport[] {
    return [...this.crashReports];
  }

  getUnreportedCrashes(): CrashReport[] {
    return this.crashReports.filter((r) => !r.reported);
  }

  clearCrashReports(): void {
    this.crashReports = [];
    localStorage.removeItem(this.storageKey);
  }

  markAsReported(id: string): void {
    const report = this.crashReports.find((r) => r.id === id);
    if (report) {
      report.reported = true;
      this.saveCrashReports();
    }
  }

  getCrashStats() {
    const total = this.crashReports.length;
    const reported = this.crashReports.filter((r) => r.reported).length;
    const byType: Record<string, number> = {};
    for (const r of this.crashReports) {
      const type = (r.context.type as string) || "unknown";
      byType[type] = (byType[type] || 0) + 1;
    }
    return {
      total,
      reported,
      unreported: total - reported,
      byType,
      latest: this.crashReports[this.crashReports.length - 1],
    };
  }

  loadCrashReports(): CrashReport[] {
    try {
      const saved = localStorage.getItem(this.storageKey);
      this.crashReports = saved ? JSON.parse(saved) : [];
    } catch {
      this.crashReports = [];
    }
    return this.crashReports;
  }

  private saveCrashReports(): void {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.crashReports));
    } catch {
      this.crashReports = this.crashReports.slice(-3);
      try {
        localStorage.setItem(this.storageKey, JSON.stringify(this.crashReports));
      } catch {
        /* quota exceeded */
      }
    }
  }
}

export const errorHandler = new ErrorHandler();
export type { ErrorContext, CrashReport };
