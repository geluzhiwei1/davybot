<!--
E2E测试专用页面
用于Playwright端到端测试
-->

<template>
  <div class="e2e-test-page">
    <h1>E2E Test Page</h1>
    <div v-if="storeReady">
      <p>Store is ready for testing</p>
      <p>Stats: {{ stats.total }} tasks</p>
    </div>
  </div>
</template>

/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useParallelTasksStore } from '@/stores/parallelTasks'

const storeReady = ref(false)
const store = useParallelTasksStore()

const stats = ref(store.stats)

onMounted(() => {
  // 确保store已经初始化
  if (import.meta.env.DEV) {
    // 暴露到window对象
    ;(window as unknown).parallelTasksStore = store
    ;(window as unknown).e2eReady = true
    storeReady.value = true

    console.log('[E2E Test Page] Store exposed successfully')

    // 监听变化
    store.$subscribe(() => {
      stats.value = { ...store.stats }
    })
  }
})
</script>

<style scoped>
.e2e-test-page {
  padding: 20px;
}
</style>
