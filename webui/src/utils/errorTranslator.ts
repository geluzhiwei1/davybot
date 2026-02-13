/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * API Error Translation Utility
 *
 * Translates backend error codes to localized messages
 */

import { useI18n } from 'vue-i18n'
import type { ApiError } from '@/services/api/types'

/**
 * Translate API error to localized message
 *
 * @param error - The API error object
 * @returns Localized error message
 *
 * @example
 * const error = {
 *   code: 404,
 *   details: { code: "workspace.not_found", params: { workspace_id: "123" } }
 * }
 * const message = translateApiError(error)
 * // "找不到ID为 '123' 的工作区" (Chinese) or "Workspace with ID '123' not found" (English)
 */
export function translateApiError(error: ApiError | unknown): string {
  const { t } = useI18n()

  // Handle non-ApiError objects
  if (!error || typeof error !== 'object') {
    return t('common.unknownError')
  }

  const err = error as ApiError

  // Check if error has a code and details with error code
  if (err.details?.code) {
    const errorCode = err.details.code as string
    const params = err.details.params || {}

    try {
      // Try to translate using the error code
      return t(`apiErrors.${errorCode}`, params)
    } catch (e) {
      // Translation failed, fall back to original message
      console.warn(`[ErrorTranslator] Failed to translate error code: ${errorCode}`, e)
    }
  }

  // Fallback to error message if available
  if (err.message) {
    return err.message
  }

  // Final fallback
  return t('common.unknownError')
}

/**
 * Get error code from ApiError
 *
 * @param error - The API error object
 * @returns Error code string or null
 */
export function getErrorCode(error: ApiError | unknown): string | null {
  if (!error || typeof error !== 'object') {
    return null
  }

  const err = error as ApiError
  return err.details?.code as string || null
}

/**
 * Check if error is a specific error code
 *
 * @param error - The API error object
 * @param code - Error code to check
 * @returns True if error matches the code
 */
export function isErrorCode(error: ApiError | unknown, code: string): boolean {
  return getErrorCode(error) === code
}

/**
 * Format error for display
 *
 * @param error - The API error object
 * @returns Formatted error object with localized message
 */
export function formatError(error: ApiError | unknown): {
  code: number | string
  message: string
  originalMessage?: string
} {
  const err = error as ApiError

  return {
    code: err.details?.code || err.code || 'UNKNOWN',
    message: translateApiError(err),
    originalMessage: err.message
  }
}
