<!--
使用示例：如何使用新的时间格式化工具

这是一个演示组件，展示如何在 Vue 组件中使用新的国际化和时区感知的时间格式化功能。
-->
<template>
  <div class="time-display-example">
    <h3>Time Display Example - 时间显示示例</h3>

    <div class="example-section">
      <h4>1. Basic Timestamp Formatting - 基础时间戳格式化</h4>
      <div class="demo-item">
        <span class="label">Full:</span>
        <span class="value">{{ formatFullTime }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Date:</span>
        <span class="value">{{ formatDate }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Time:</span>
        <span class="value">{{ formatTime }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Compact:</span>
        <span class="value">{{ formatCompact }}</span>
      </div>
    </div>

    <div class="example-section">
      <h4>2. Relative Time - 相对时间</h4>
      <div class="demo-item">
        <span class="label">Relative:</span>
        <span class="value">{{ relativeTime }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Calendar:</span>
        <span class="value">{{ calendarTime }}</span>
      </div>
    </div>

    <div class="example-section">
      <h4>3. Timezone Information - 时区信息</h4>
      <div class="demo-item">
        <span class="label">Timezone:</span>
        <span class="value">{{ userTimezone }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Locale:</span>
        <span class="value">{{ currentLocale }}</span>
      </div>
    </div>

    <div class="example-section">
      <h4>4. Duration Formatting - 时长格式化</h4>
      <div class="demo-item">
        <span class="label">Duration:</span>
        <span class="value">{{ duration }}</span>
      </div>
      <div class="demo-item">
        <span class="label">Detailed:</span>
        <span class="value">{{ durationDetailed }}</span>
      </div>
    </div>

    <div class="controls">
      <button @click="switchLocale">Toggle Language (切换语言)</button>
      <button @click="changeTimezone">Change Timezone (更改时区)</button>
    </div>

    <div class="info">
      <p>ℹ️ The times above automatically update based on your selected language and timezone.</p>
      <p>ℹ️ 以上时间会根据您选择的语言和时区自动更新。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { setLocale } from '@/i18n'
import {
  formatTimestamp as fmtTimestamp,
  formatTime as fmtTime,
  formatDate as fmtDate,
  formatCompactTime as fmtCompact,
  formatRelativeTime as fmtRelative,
  formatCalendarTime as fmtCalendar,
  formatDuration,
} from '@/utils/dateFormatter'
import { useTimezone } from '@/composables/useTimezone'

// 使用 composable
const { userTimezone, setUserTimezone, getTimezoneInfo } = useTimezone()

// 当前时间戳（用于演示）
const now = new Date().toISOString()

// 计算属性 - 展示各种格式化选项
const formatFullTime = computed(() => fmtTimestamp(now))
const formatDate = computed(() => fmtDate(now))
const formatTime = computed(() => fmtTime(now))
const formatCompact = computed(() => fmtCompact(now))
const relativeTime = computed(() => fmtRelative(now))
const calendarTime = computed(() => fmtCalendar(now))

// 时长演示（1小时30分钟）
const duration = computed(() => formatDuration(5400000)) // 1.5小时 = 90分钟 = 5400000毫秒
const durationDetailed = computed(() => formatDuration(5400000, 'detailed'))

// 当前语言
const currentLocale = computed(() => {
  const info = getTimezoneInfo()
  return info.locale
})

// 切换语言
const switchLocale = () => {
  const current = currentLocale.value
  setLocale(current === 'zh-CN' ? 'en' : 'zh-CN')
}

// 更改时区
const changeTimezone = () => {
  const current = userTimezone.value
  const timezones = ['Asia/Shanghai', 'America/New_York', 'Europe/London', 'Asia/Tokyo']
  const currentIndex = timezones.indexOf(current)
  const nextIndex = (currentIndex + 1) % timezones.length
  setUserTimezone(timezones[nextIndex])
}
</script>

<style scoped>
.time-display-example {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

h3 {
  color: #333;
  margin-bottom: 20px;
}

h4 {
  color: #666;
  font-size: 16px;
  margin: 20px 0 10px;
  border-bottom: 2px solid #e0e0e0;
  padding-bottom: 5px;
}

.example-section {
  margin-bottom: 30px;
  padding: 15px;
  background: #f9f9f9;
  border-radius: 8px;
}

.demo-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #e8e8e8;
}

.demo-item:last-child {
  border-bottom: none;
}

.label {
  font-weight: 600;
  color: #555;
  margin-right: 20px;
}

.value {
  font-family: 'Courier New', monospace;
  color: #007acc;
}

.controls {
  display: flex;
  gap: 10px;
  margin: 20px 0;
}

button {
  padding: 10px 20px;
  background: #007acc;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

button:hover {
  background: #005a9e;
}

.info {
  margin-top: 20px;
  padding: 15px;
  background: #e8f4fd;
  border-left: 4px solid #007acc;
  border-radius: 4px;
}

.info p {
  margin: 5px 0;
  color: #333;
}
</style>
