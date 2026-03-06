/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Mobile detection and responsive utilities composable
 * 移动端检测和响应式工具组合式函数
 */

import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useWindowSize } from '@vueuse/core'

/**
 * Breakpoint definitions
 * 断点定义 (单位: px)
 */
export const BREAKPOINTS = {
  XS: 320,   // Extra small devices (small phones)
  SM: 375,   // Small devices (large phones)
  MD: 768,   // Medium devices (tablets)
  LG: 1024,  // Large devices (small laptops)
  XL: 1280,  // Extra large devices (desktops)
  XXL: 1440, // Extra extra large devices (large desktops)
} as const

/**
 * Breakpoint type
 */
export type Breakpoint = keyof typeof BREAKPOINTS

/**
 * Window size reactive state
 */
const { width: windowWidth } = useWindowSize()

/**
 * Current breakpoint based on window width
 */
export const currentBreakpoint = computed<Breakpoint>(() => {
  const w = windowWidth.value
  if (w < BREAKPOINTS.SM) return 'XS'
  if (w < BREAKPOINTS.MD) return 'SM'
  if (w < BREAKPOINTS.LG) return 'MD'
  if (w < BREAKPOINTS.XL) return 'LG'
  if (w < BREAKPOINTS.XXL) return 'XL'
  return 'XXL'
})

/**
 * Check if current viewport is mobile (width < 768px)
 */
export const isMobile = computed(() => windowWidth.value < BREAKPOINTS.MD)

/**
 * Check if current viewport is tablet (768px <= width < 1024px)
 */
export const isTablet = computed(
  () => windowWidth.value >= BREAKPOINTS.MD && windowWidth.value < BREAKPOINTS.LG
)

/**
 * Check if current viewport is desktop (width >= 1024px)
 */
export const isDesktop = computed(() => windowWidth.value >= BREAKPOINTS.LG)

/**
 * Check if current viewport is small mobile (width < 375px)
 */
export const isSmallMobile = computed(() => windowWidth.value < BREAKPOINTS.SM)

/**
 * Detect if device is touch-enabled
 */
export const isTouchDevice = computed(() => {
  if (typeof window === 'undefined') return false
  return (
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0 ||
    // @ts-ignore - vendor prefix
    navigator.msMaxTouchPoints > 0
  )
})

/**
 * Detect if device is a mobile phone (user agent based)
 */
export const isMobilePhone = computed(() => {
  if (typeof navigator === 'undefined') return false
  const regex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i
  return regex.test(navigator.userAgent)
})

/**
 * Detect if device is a tablet (user agent based)
 */
export const isTabletDevice = computed(() => {
  if (typeof navigator === 'undefined') return false
  const regex = /iPad|Android(?!.*Mobile)|Tablet/i
  return regex.test(navigator.userAgent)
})

/**
 * Get safe area insets (for devices with notches)
 */
export const safeAreaInsets = computed(() => {
  if (typeof window === 'undefined') {
    return { top: 0, right: 0, bottom: 0, left: 0 }
  }

  const style = getComputedStyle(document.documentElement)
  return {
    top: parseInt(style.getPropertyValue('env(safe-area-inset-top)') || '0', 10),
    right: parseInt(style.getPropertyValue('env(safe-area-inset-right)') || '0', 10),
    bottom: parseInt(style.getPropertyValue('env(safe-area-inset-bottom)') || '0', 10),
    left: parseInt(style.getPropertyValue('env(safe-area-inset-left)') || '0', 10),
  }
})

/**
 * Mobile orientation
 */
export const orientation = computed<'portrait' | 'landscape'>(() => {
  if (typeof window === 'undefined') return 'portrait'
  return window.innerHeight > window.innerWidth ? 'portrait' : 'landscape'
})

/**
 * Main composable function
 *
 * @example
 * ```ts
 * const { isMobile, isTablet, isDesktop, currentBreakpoint } = useMobile()
 * ```
 */
export function useMobile() {
  return {
    // Breakpoint
    currentBreakpoint,
    windowWidth: computed(() => windowWidth.value),

    // Device type
    isMobile,
    isTablet,
    isDesktop,
    isSmallMobile,

    // Device capabilities
    isTouchDevice,
    isMobilePhone,
    isTabletDevice,

    // Display
    safeAreaInsets,
    orientation,

    // Breakpoints constants
    BREAKPOINTS,
  }
}

/**
 * Default export
 */
export default useMobile
