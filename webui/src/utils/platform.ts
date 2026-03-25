/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Platform detection utilities for Web and Tauri environments
 */

export enum Platform {
  Web = 'web',
  Tauri = 'tauri',
}

/**
 * Detect if the app is running in Tauri environment
 *
 * Tauri 2.x detection: window.__TAURI__ is an object, not a boolean
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && window.__TAURI__ !== undefined
}

/**
 * Get current platform
 */
export function getPlatform(): Platform {
  return isTauri() ? Platform.Tauri : Platform.Web
}

/**
 * Get backend API base URL based on platform
 *
 * In Web mode: always uses proxy in development, direct URL in production
 * In Tauri mode: uses configured remote server or localhost
 */
export function getApiBaseUrl(): string {
  const tauriDetected = isTauri();
  const isDev = import.meta.env.DEV;

  // Development mode: ALWAYS use proxy, ignore ALL environment variables
  // This prevents .env.tauri from interfering with web development
  if (isDev) {
    const devUrl = '/api';  // Relative path - will use browser's origin
    return devUrl;
  }

  // Production mode: use environment variables (including .env.tauri for Tauri builds)
  if (import.meta.env.VITE_API_BASE_URL && import.meta.env.VITE_API_BASE_URL.trim() !== '') {
    return import.meta.env.VITE_API_BASE_URL
  }

  // Production configuration fallback
  if (tauriDetected) {
    // Tauri mode: connect to remote server or localhost
    // You can configure this to point to your production server
    const tauriUrl = 'http://localhost:8465/api';
    return tauriUrl
  } else {
    // Web mode: use proxy (configured in vite.config.ts)
    const proxyUrl = '/api';
    return proxyUrl
  }
}

/**
 * Get WebSocket base URL based on platform
 */
export function getWsBaseUrl(): string {
  const tauriDetected = isTauri();
  const isDev = import.meta.env.DEV;
  const hostname = window.location.hostname;

  // Development mode: ALWAYS use proxy, ignore ALL environment variables
  // This prevents .env.tauri from interfering with web development
  if (isDev) {
    // Use Vite proxy for WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const devUrl = `${protocol}//${host}/ws`;
    return devUrl;
  }

  // Production mode: use environment variables (including .env.tauri for Tauri builds)
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL
  }

  // Production configuration fallback
  if (tauriDetected) {
    // Tauri mode: connect to remote server or localhost
    const tauriUrl = 'ws://localhost:8465/ws';
    return tauriUrl
  } else {
    // Web mode: use proxy (configured in vite.config.ts)
    const proxyUrl = '/ws';
    return proxyUrl
  }
}

/**
 * Detect mobile device by user agent
 */
export function isMobileDevice(): boolean {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return false
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
}

/**
 * Detect tablet device
 */
export function isTabletDevice(): boolean {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return false
  return /iPad|Android(?!.*Mobile)|Tablet/i.test(navigator.userAgent)
}

/**
 * Detect touch capability
 */
export function isTouchDevice(): boolean {
  if (typeof window === 'undefined') return false
  return (
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0 ||
    // @ts-ignore - vendor prefix
    navigator.msMaxTouchPoints > 0
  )
}

/**
 * Get viewport width
 */
export function getViewportWidth(): number {
  if (typeof window === 'undefined') return 1024
  return window.innerWidth
}

/**
 * Check if viewport is mobile size (< 768px)
 */
export function isMobileViewport(): boolean {
  return getViewportWidth() < 768
}

/**
 * Check if viewport is tablet size (768px - 1023px)
 */
export function isTabletViewport(): boolean {
  const width = getViewportWidth()
  return width >= 768 && width < 1024
}

/**
 * Check if viewport is desktop size (>= 1024px)
 */
export function isDesktopViewport(): boolean {
  return getViewportWidth() >= 1024
}

/**
 * Platform-specific feature flags
 */
export const platformFeatures = {
  // Can use Tauri APIs
  canUseTauriAPIs: isTauri(),

  // Can access file system directly (Tauri only)
  canAccessFileSystem: isTauri(),

  // Should show platform-specific UI elements
  showDesktopOnlyUI: isTauri(),

  // Mobile/touch detection
  isMobileDevice: isMobileDevice(),
  isTabletDevice: isTabletDevice(),
  isTouchDevice: isTouchDevice(),
  isMobileViewport: isMobileViewport(),

  // Optimize for mobile
  shouldUseMobileLayout: isMobileViewport(),
  shouldUseTouchOptimizations: isTouchDevice(),
}
