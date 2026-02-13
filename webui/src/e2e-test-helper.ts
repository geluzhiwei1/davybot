/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * E2E测试辅助模块
 * 在开发环境将parallelTasks store暴露到window对象
 */

import { onMounted } from 'vue'
import { useParallelTasksStore } from '@/stores/parallelTasks'

export function setupE2ETestHelpers() {
  onMounted(() => {
    // 只在开发环境且在浏览器中执行
    if (import.meta.env.DEV && typeof window !== 'undefined') {
      const store = useParallelTasksStore()

      // 暴露store到window对象
      ;(window as unknown).parallelTasksStore = store

      // 添加测试辅助函数
      ;(window as unknown).e2eTest = {
        clearAllTasks: () => store.clearAllTasks(),
        getStats: () => store.stats,
        getAllTasks: () => store.allTasks,
      }

      console.log('[E2E Test] Store exposed to window.parallelTasksStore')
      console.log('[E2E Test] Available helpers:', Object.keys((window as unknown).e2eTest))
    }
  })
}
