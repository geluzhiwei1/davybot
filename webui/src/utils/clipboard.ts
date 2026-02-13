/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Clipboard utilities that work in both Web and Tauri environments
 */

import { isTauri } from './platform'

// Cache the Tauri clipboard module to avoid repeated import attempts
let tauriClipboardModule: unknown = null
let tauriClipboardChecked = false

/**
 * Check if Tauri clipboard plugin is available
 * Only attempts to load the Tauri plugin when running in actual Tauri environment
 */
async function isTauriClipboardAvailable(): Promise<boolean> {
  // Fast fail: if not Tauri, don't even try to import
  if (!isTauri()) return false
  if (tauriClipboardChecked) return tauriClipboardModule !== null

  tauriClipboardChecked = true
  try {
    // Direct dynamic import - only executed in Tauri context
    // The isTauri() check above prevents this from running in web dev
    // @vite-ignore - Tauri plugin only available in Tauri context, not in web browser
    tauriClipboardModule = await import('@tauri-apps/plugin-clipboard-manager')
    return true
  } catch {
    return false
  }
}

/**
 * Copy text to clipboard
 * Works in both Web (navigator.clipboard) and Tauri (@tauri-apps/plugin-clipboard-manager)
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    // Check if Tauri clipboard plugin is available
    if (await isTauriClipboardAvailable()) {
      try {
        await tauriClipboardModule.writeText(text)
        return true
      } catch {
        console.warn('Tauri clipboard write failed, falling back to web API')
        return await fallbackToWebClipboard(text)
      }
    } else {
      return await fallbackToWebClipboard(text)
    }
  } catch (error) {
    console.error('Failed to copy to clipboard:', error)
    return false
  }
}

/**
 * Fallback to web clipboard API
 */
async function fallbackToWebClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (err) {
      console.error('Web clipboard API failed:', err)
      return await fallbackCopy(text)
    }
  } else {
    return await fallbackCopy(text)
  }
}

/**
 * Ultimate fallback using execCommand
 */
async function fallbackCopy(text: string): Promise<boolean> {
  const textArea = document.createElement('textarea')
  textArea.value = text
  textArea.style.position = 'fixed'
  textArea.style.left = '-999999px'
  document.body.appendChild(textArea)
  textArea.select()
  try {
    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    return successful
  } catch (err) {
    document.body.removeChild(textArea)
    console.error('Fallback copy failed:', err)
    return false
  }
}

/**
 * Read text from clipboard
 * Works in both Web and Tauri environments
 */
export async function readFromClipboard(): Promise<string | null> {
  try {
    // Check if Tauri clipboard plugin is available
    if (await isTauriClipboardAvailable()) {
      try {
        return await tauriClipboardModule.readText()
      } catch {
        console.warn('Tauri clipboard read failed, falling back to web API')
        return await fallbackReadWebClipboard()
      }
    } else {
      return await fallbackReadWebClipboard()
    }
  } catch (error) {
    console.error('Failed to read from clipboard:', error)
    return null
  }
}

/**
 * Fallback to web clipboard API for reading
 */
async function fallbackReadWebClipboard(): Promise<string | null> {
  if (navigator.clipboard && navigator.clipboard.readText) {
    try {
      return await navigator.clipboard.readText()
    } catch (err) {
      console.error('Web clipboard read failed:', err)
      return null
    }
  }
  return null
}
