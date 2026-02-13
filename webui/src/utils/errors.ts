/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Custom Error Classes for Fast-Fail Error Handling
 *
 * Provides typed error classes for different error scenarios
 * Enables proper error handling and recovery strategies
 */

/**
 * Base application error
 */
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly context?: Record<string, unknown>
  ) {
    super(message)
    this.name = this.constructor.name
    Error.captureStackTrace?.(this, this.constructor)
  }
}

/**
 * Network-related errors
 */
export class NetworkError extends AppError {
  constructor(message: string, context?: Record<string, unknown>) {
    super(message, 'NETWORK_ERROR', context)
    this.name = 'NetworkError'
  }
}

/**
 * WebSocket communication errors
 */
export class WebSocketError extends AppError {
  constructor(message: string, context?: Record<string, unknown>) {
    super(message, 'WEBSOCKET_ERROR', context)
    this.name = 'WebSocketError'
  }
}

/**
 * WebSocket message dispatch errors
 */
export class WebSocketDispatchError extends WebSocketError {
  constructor(message: string, context?: Record<string, unknown>) {
    super(message, 'WEBSOCKET_DISPATCH_ERROR', { ...context, dispatch: true })
    this.name = 'WebSocketDispatchError'
  }
}

/**
 * HTTP request/response errors
 */
export class HttpError extends AppError {
  constructor(
    message: string,
    public readonly statusCode: number,
    context?: Record<string, unknown>
  ) {
    super(message, 'HTTP_ERROR', { ...context, statusCode })
    this.name = 'HttpError'
  }
}

/**
 * Validation errors
 */
export class ValidationError extends AppError {
  constructor(message: string, context?: Record<string, unknown>) {
    super(message, 'VALIDATION_ERROR', context)
    this.name = 'ValidationError'
  }
}

/**
 * Workspace-related errors
 */
export class WorkspaceError extends AppError {
  constructor(message: string, context?: Record<string, unknown>) {
    super(message, 'WORKSPACE_ERROR', context)
    this.name = 'WorkspaceError'
  }
}

/**
 * Error handler utility
 */
export class ErrorHandler {
  /**
   * Determine if error is recoverable
   */
  static isRecoverable(error: Error): boolean {
    // Network errors are recoverable - can retry after delay
    if (error instanceof NetworkError) return true
    if (error instanceof HttpError) {
      // 4xx errors are recoverable, 5xx are not
      return error.statusCode >= 400 && error.statusCode < 500
    }
    if (error instanceof ValidationError) return true
    return false
  }

  /**
   * Get user-friendly error message
   */
  static getUserMessage(error: Error): string {
    if (error instanceof NetworkError) {
      return '网络连接失败，请检查网络设置'
    }
    if (error instanceof HttpError) {
      if (error.statusCode === 401) return '未授权，请重新登录'
      if (error.statusCode === 403) return '没有权限执行此操作'
      if (error.statusCode === 404) return '请求的资源不存在'
      if (error.statusCode >= 500) return '服务器错误，请稍后重试'
      return '请求失败，请稍后重试'
    }
    if (error instanceof ValidationError) {
      return error.message
    }
    if (error instanceof WorkspaceError) {
      return `工作区错误: ${error.message}`
    }
    return '操作失败，请重试'
  }

  /**
   * Log error with context
   */
  static log(error: Error, context?: Record<string, unknown>): void {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { logger } = require('./logger')
    logger.error(error.message, error, context)
  }

  /**
   * Handle async operation with error logging
   * Returns null on error instead of throwing
   */
  static async safeAsync<T>(
    operation: () => Promise<T>,
    errorMessage: string,
    context?: Record<string, unknown>
  ): Promise<T | null> {
    try {
      return await operation()
    } catch (error) {
      this.log(error as Error, { ...context, operation: errorMessage })
      return null
    }
  }

  /**
   * Validate required field exists
   * Throws ValidationError if field is missing
   */
  static validateRequired<T>(
    obj: Record<string, T | undefined | null>,
    fieldName: string,
    context?: Record<string, unknown>
  ): T {
    const value = obj[fieldName]
    if (value === undefined || value === null) {
      throw new ValidationError(
        `Required field '${fieldName}' is missing`,
        { ...context, fieldName, object: obj }
      )
    }
    return value
  }

  /**
   * Validate type of field
   * Throws ValidationError if field is not of expected type
   */
  static validateType<T>(
    value: unknown,
    expectedType: string,
    fieldName: string,
    context?: Record<string, unknown>
  ): asserts value is T {
    if (typeof value !== expectedType) {
      throw new ValidationError(
        `Field '${fieldName}' must be of type '${expectedType}', got '${typeof value}'`,
        { ...context, fieldName, expectedType, actualType: typeof value }
      )
    }
  }

  /**
   * Wrap error in additional context
   */
  static wrap(error: unknown, message: string, context?: Record<string, unknown>): Error {
    if (error instanceof Error) {
      // Standard Error has no .code property, only custom error classes do
      const code = (error as AppError).code || 'UNKNOWN_ERROR'
      return new AppError(message, code, { ...context, originalError: error.message })
    }
    return new AppError(message, 'UNKNOWN_ERROR', { ...context, originalError: String(error) })
  }

  /**
   * Execute operation with timeout
   * Throws TimeoutError if operation takes too long
   */
  static async withTimeout<T>(
    operation: Promise<T>,
    timeoutMs: number,
    timeoutMessage: string = 'Operation timed out'
  ): Promise<T> {
    let timeoutId: ReturnType<typeof setTimeout>

    const timeout = new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => reject(new Error(timeoutMessage)), timeoutMs)
    })

    try {
      return await Promise.race([operation, timeout])
    } finally {
      clearTimeout(timeoutId!)
    }
  }

  /**
   * Retry operation with exponential backoff
   * Throws last error if all retries fail
   * @param operation - The async operation to retry
   * @param maxRetries - Maximum number of retry attempts (default: 3)
   * @param baseDelayMs - Base delay in ms for exponential backoff (default: 1000)
   */
  static async retry<T>(
    operation: () => Promise<T>,
    maxRetries: number = 3,
    baseDelayMs: number = 1000,
    context?: Record<string, unknown>
  ): Promise<T> {
    let lastError: Error | undefined

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        return await operation()
      } catch (error) {
        lastError = error as Error
        const delay = baseDelayMs * Math.pow(2, attempt)
        this.log(lastError, { ...context, attempt, delay, maxRetries })
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }

    throw new AppError(
      `Operation failed after ${maxRetries} retries`,
      'RETRY_EXHAUSTED',
      { ...context, lastError: lastError?.message }
    )
  }
}
