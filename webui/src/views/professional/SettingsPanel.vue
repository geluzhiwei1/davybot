/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <div class="settings-overlay" @click="$emit('close')"></div>
    <div class="settings-panel">
      <div class="settings-header">
        <h2 class="settings-title">Settings</h2>
        <button class="close-button" @click="$emit('close')">×</button>
      </div>
      <div class="settings-body">
        <div class="setting-group">
          <label class="setting-label">Refresh Interval</label>
          <select class="setting-select" v-model="localSettings.refreshInterval">
            <option :value="1000">1 second</option>
            <option :value="3000">3 seconds</option>
            <option :value="5000">5 seconds</option>
            <option :value="10000">10 seconds</option>
          </select>
        </div>
        <div class="setting-group">
          <label class="setting-label">Auto-refresh</label>
          <div class="toggle-switch" :class="{ active: localSettings.enableAutoRefresh }" @click="localSettings.enableAutoRefresh = !localSettings.enableAutoRefresh">
            <div class="toggle-slider"></div>
          </div>
        </div>
        <div class="setting-group">
          <label class="setting-label">Enable Alerts</label>
          <div class="toggle-switch" :class="{ active: localSettings.enableAlerts }" @click="localSettings.enableAlerts = !localSettings.enableAlerts">
            <div class="toggle-slider"></div>
          </div>
        </div>
      </div>
      <div class="settings-footer">
        <button class="save-button" @click="$emit('save', localSettings)">Save Settings</button>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { reactive } from 'vue'

defineProps<{
  initialSettings?: unknown
}>()

const localSettings = reactive({
  refreshInterval: 5000,
  enableAutoRefresh: true,
  enableAlerts: true
})
</script>

<style scoped>
.settings-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
}

.settings-panel {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #ffffff;
  border-radius: 8px;
  width: 400px;
  max-width: 90vw;
  z-index: 101;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.settings-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.close-button {
  background: transparent;
  border: none;
  font-size: 24px;
  color: #9ca3af;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-button:hover {
  background: #f3f4f6;
  color: #374151;
}

.settings-body {
  padding: 24px;
}

.setting-group {
  margin-bottom: 20px;
}

.setting-group:last-child {
  margin-bottom: 0;
}

.setting-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  margin-bottom: 8px;
}

.setting-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  color: #111827;
  background: #ffffff;
  cursor: pointer;
}

.toggle-switch {
  width: 44px;
  height: 24px;
  background: #e5e7eb;
  border-radius: 12px;
  position: relative;
  cursor: pointer;
  transition: background 0.2s;
}

.toggle-switch.active {
  background: #2563eb;
}

.toggle-slider {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  background: #ffffff;
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.toggle-switch.active .toggle-slider {
  transform: translateX(20px);
}

.settings-footer {
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: flex-end;
}

.save-button {
  padding: 8px 16px;
  background: #111827;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.save-button:hover {
  background: #374151;
}
</style>
