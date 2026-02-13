/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Stub module for @tauri-apps/plugin-clipboard-manager
 * Used in web development where Tauri plugins are not available
 */

export async function readText(): Promise<string> {
  throw new Error('Tauri clipboard plugin not available in web mode')
}

export async function writeText(): Promise<void> {
  throw new Error('Tauri clipboard plugin not available in web mode')
}
