/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="empty-state">
    <div class="empty-icon">{{ getIcon() }}</div>
    <div class="empty-title">{{ title }}</div>
    <div class="empty-message">{{ message }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  icon: string
  title: string
  message: string
}>()

function getIcon() {
  const icons = {
    tasks: '📋',
    files: '📁',
    settings: '⚙️'
  }
  return icons[this.icon as keyof typeof icons] || '○'
}
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.empty-message {
  font-size: 14px;
  color: #6b7280;
  max-width: 300px;
}
</style>
