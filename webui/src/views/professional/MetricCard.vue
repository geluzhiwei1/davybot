/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="metric-card">
    <div class="metric-header">
      <span class="metric-label">{{ metric.label }}</span>
      <span class="metric-unit">{{ metric.unit }}</span>
    </div>
    <div class="metric-value">{{ metric.value }}</div>
    <div class="metric-footer">
      <span class="metric-change" :class="metric.trend">
        {{ metric.change }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Metric {
  id: string
  label: string
  value: string
  unit: string
  trend: 'up' | 'down' | 'neutral'
  change: string
}

defineProps<{
  metric: Metric
}>()
</script>

<style scoped>
.metric-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.2s;
}

.metric-card:hover {
  border-color: #d1d5db;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.metric-label {
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
}

.metric-unit {
  font-size: 12px;
  color: #9ca3af;
  font-weight: 400;
}

.metric-value {
  font-size: 32px;
  font-weight: 700;
  color: #111827;
  line-height: 1;
  margin-bottom: 12px;
  font-family: 'IBM Plex Mono', monospace;
}

.metric-footer {
  display: flex;
  align-items: center;
}

.metric-change {
  font-size: 12px;
  font-weight: 500;
}

.metric-change.up {
  color: #059669;
}

.metric-change.down {
  color: #dc2626;
}

.metric-change.neutral {
  color: #6b7280;
}
</style>
