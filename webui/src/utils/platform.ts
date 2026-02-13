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
 */
export function isTauri(): boolean {
  // Check if __TAURI__ is truthy (injected by Tauri at runtime)
  // In vite.config.ts, __TAURI__ is set to false, so we need to check if it's truthy, not just defined
  // @ts-expect-error - __TAURI__ is injected by Tauri
  return typeof window !== 'undefined' && window.__TAURI__ === true
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
 * In Web mode: uses proxy or localhost
 * In Tauri mode: uses configured remote server or localhost
 */
export function getApiBaseUrl(): string {
  // Check if environment variable is set AND not empty
  if (import.meta.env.VITE_API_BASE_URL && import.meta.env.VITE_API_BASE_URL.trim() !== '') {
    console.log('[Platform] Using VITE_API_BASE_URL from env:', import.meta.env.VITE_API_BASE_URL);
    return import.meta.env.VITE_API_BASE_URL
  }

  // DEBUG: Always log the Tauri detection (disabled for performance)
  const tauriDetected = isTauri();
  // console.log('[Platform] DEBUG - isTauri():', tauriDetected);
  // console.log('[Platform] DEBUG - window.__TAURI__:', typeof window !== 'undefined' ? window.__TAURI__ : 'N/A');
  // console.log('[Platform] DEBUG - import.meta.env.DEV:', import.meta.env.DEV);

  // Force Web mode in development (Vite dev server)
  // This ensures we always use the Vite proxy in development
  if (import.meta.env.DEV) {
    const devUrl = '/api';
    console.log('[Platform] Development mode detected, using proxy:', devUrl);
    return devUrl;
  }

  // Default configuration for production
  if (tauriDetected) {
    // Tauri mode: connect to remote server or localhost
    // You can configure this to point to your production server
    const tauriUrl = 'http://localhost:8465/api';
    console.log('[Platform] Production Tauri mode, using API URL:', tauriUrl);
    return tauriUrl
  } else {
    // Web mode: use proxy (configured in vite.config.ts)
    const proxyUrl = '/api';
    console.log('[Platform] Production Web mode, using proxy URL:', proxyUrl);
    return proxyUrl
  }
}

/**
 * Get WebSocket base URL based on platform
 */
export function getWsBaseUrl(): string {
  // Check if environment variable is set
  if (import.meta.env.VITE_WS_BASE_URL) {
    console.log('[Platform] Using VITE_WS_BASE_URL from env:', import.meta.env.VITE_WS_BASE_URL);
    return import.meta.env.VITE_WS_BASE_URL
  }

  const tauriDetected = isTauri();
  const isDev = import.meta.env.DEV;
  const hostname = window.location.hostname;

  // console.log('[Platform] DEBUG - isTauri():', tauriDetected, 'isDev:', isDev, 'hostname:', hostname);

  // Development mode: check if accessing via localhost or remote IP
  if (isDev) {
    // If accessing via localhost, use Vite proxy
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      // Construct WebSocket URL from current page URL
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host; // includes hostname and port (e.g., localhost:5175)
      const devUrl = `${protocol}//${host}/ws`;
      console.log('[Platform] Development mode (localhost), using proxy:', devUrl);
      return devUrl;
    } else {
      // Accessing via remote IP - use the same IP as the frontend but with backend port
      // This ensures we connect to the backend server on the same machine as the frontend
      const currentIp = hostname; // Use the same IP as the current page
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const remoteUrl = `${protocol}//${currentIp}:8465/ws`;
      console.log('[Platform] Development mode (remote access), direct connection to backend:', remoteUrl);
      return remoteUrl;
    }
  }

  // Production configuration
  if (tauriDetected) {
    // Tauri mode: connect to remote server or localhost
    const tauriUrl = 'ws://localhost:8465/ws';
    console.log('[Platform] Production Tauri mode, using WebSocket URL:', tauriUrl);
    return tauriUrl
  } else {
    // Web mode: use proxy (configured in vite.config.ts)
    const proxyUrl = '/ws';
    console.log('[Platform] Production Web mode, using WebSocket proxy URL:', proxyUrl);
    return proxyUrl
  }
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
}
