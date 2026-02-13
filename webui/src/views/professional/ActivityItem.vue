/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="activity-item">
    <span class="activity-time">{{ activity.time }}</span>
    <span class="activity-dot" :class="activity.type"></span>
    <span class="activity-message">{{ activity.message }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  activity: {
    id: string
    time: string
    type: 'info' | 'success' | 'error' | 'warning'
    message: string
  }
}>()
</script>

<style scoped>
.activity-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 12px;
}

.activity-time {
  color: #9ca3af;
  font-family: 'IBM Plex Mono', monospace;
  min-width: 40px;
}

.activity-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.activity-dot.info {
  background: #2563eb;
}

.activity-dot.success {
  background: #059669;
}

.activity-dot.error {
  background: #dc2626;
}

.activity-dot.warning {
  background: #d97706;
}

.activity-message {
  flex: 1;
  color: #374151;
  line-height: 1.4;
}
</style>
