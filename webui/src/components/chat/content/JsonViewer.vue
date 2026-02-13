/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="json-viewer">
    <pre class="compact-pre"><code>{{ formattedJson }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  data: unknown
}>()

const formattedJson = computed(() => {
  if (!props.data) return ''
  return JSON.stringify(props.data, null, 2)
})
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.json-viewer {
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
}

.json-viewer code {
  color: #A5D6A7;
  line-height: 1.6;
}
</style>
