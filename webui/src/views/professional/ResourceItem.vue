/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="resource-item">
    <div class="resource-header">
      <span class="resource-name">{{ resource.name }}</span>
      <span class="resource-value">{{ resource.usage.toFixed(1) }}%</span>
    </div>
    <div class="resource-bar">
      <div class="resource-fill" :style="{ width: resource.usage + '%', backgroundColor: resource.color }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Resource {
  name: string
  usage: number
  color: string
}

defineProps<{
  resource: Resource
}>()
</script>

<style scoped>
.resource-item {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
}

.resource-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.resource-name {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.resource-value {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  font-family: 'IBM Plex Mono', monospace;
}

.resource-bar {
  width: 100%;
  height: 4px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}

.resource-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 2px;
}
</style>
