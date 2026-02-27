/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/// <reference types="vite/client" />

// Tauri 2.x type declaration
// __TAURI__ is an object in Tauri 2.x, not a boolean
declare interface Window {
  __TAURI__?: Record<string, unknown>
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
