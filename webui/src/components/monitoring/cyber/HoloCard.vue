/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="holo-card" @click="handleClick">
    <!-- 全息边框效果 -->
    <div class="holo-border"></div>
    <div class="holo-corner-tl"></div>
    <div class="holo-corner-tr"></div>
    <div class="holo-corner-bl"></div>
    <div class="holo-corner-br"></div>

    <!-- 背景扫描线 -->
    <div class="scan-line"></div>

    <!-- 内容 -->
    <div class="holo-content">
      <!-- 图标 -->
      <div class="metric-icon" :style="{ color: metric.color, textShadow: `0 0 20px ${metric.color}` }">
        {{ metric.icon }}
      </div>

      <!-- 数值 -->
      <div class="metric-value">
        <span class="value-text" :style="{ color: metric.color }">{{ metric.value }}</span>
        <span class="value-unit">{{ metric.unit }}</span>
      </div>

      <!-- 标签 -->
      <div class="metric-label">{{ metric.label }}</div>

      <!-- 趋势指示器 -->
      <div class="metric-trend" :class="metric.trend">
        <span class="trend-icon">{{ trendIcon }}</span>
        <span class="trend-value">{{ metric.change }}</span>
      </div>
    </div>

    <!-- 全息倒影效果 -->
    <div class="holo-reflection"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Metric {
  id: string
  label: string
  value: string
  unit: string
  icon: string
  color: string
  trend: 'up' | 'down' | 'stable'
  change: string
}

const props = defineProps<{
  metric: Metric
}>()

const emit = defineEmits<{
  click: [metric: Metric]
}>()

const trendIcon = computed(() => {
  const icons = {
    up: '▲',
    down: '▼',
    stable: '●'
  }
  return icons[props.metric.trend] || '●'
})

function handleClick() {
  emit('click', props.metric)
}
</script>

<style scoped>
.holo-card {
  position: relative;
  background: rgba(10, 14, 39, 0.6);
  border: 1px solid rgba(0, 240, 255, 0.3);
  border-radius: 8px;
  padding: 25px 20px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.3s ease;
  backdrop-filter: blur(10px);
  animation: cardEntrance 0.6s ease-out;
}

@keyframes cardEntrance {
  from {
    opacity: 0;
    transform: translateY(20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.holo-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    135deg,
    rgba(0, 240, 255, 0.1) 0%,
    transparent 50%,
    rgba(0, 240, 255, 0.05) 100%
  );
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s;
}

.holo-card:hover {
  transform: translateY(-5px);
  box-shadow:
    0 10px 30px rgba(0, 240, 255, 0.3),
    0 0 20px rgba(0, 240, 255, 0.2),
    inset 0 0 30px rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.6);
}

.holo-card:hover::before {
  opacity: 1;
}

/* 全息边框 */
.holo-border {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: 1px solid transparent;
  background: linear-gradient(
    90deg,
    rgba(0, 240, 255, 0.3),
    transparent,
    rgba(0, 240, 255, 0.3)
  );
  background-size: 200% 100%;
  animation: borderFlow 3s linear infinite;
  pointer-events: none;
}

@keyframes borderFlow {
  0% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 200% 50%;
  }
}

/* 角落装饰 */
.holo-corner-tl,
.holo-corner-tr,
.holo-corner-bl,
.holo-corner-br {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 2px solid #00f0ff;
  opacity: 0.5;
  transition: all 0.3s;
}

.holo-corner-tl {
  top: -1px;
  left: -1px;
  border-right: none;
  border-bottom: none;
}

.holo-corner-tr {
  top: -1px;
  right: -1px;
  border-left: none;
  border-bottom: none;
}

.holo-corner-bl {
  bottom: -1px;
  left: -1px;
  border-right: none;
  border-top: none;
}

.holo-corner-br {
  bottom: -1px;
  right: -1px;
  border-left: none;
  border-top: none;
}

.holo-card:hover .holo-corner-tl,
.holo-card:hover .holo-corner-tr,
.holo-card:hover .holo-corner-bl,
.holo-card:hover .holo-corner-br {
  opacity: 1;
  width: 15px;
  height: 15px;
}

/* 扫描线 */
.scan-line {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(0, 240, 255, 0.8),
    transparent
  );
  animation: scanMove 2.5s ease-in-out infinite;
  pointer-events: none;
}

@keyframes scanMove {
  0% {
    top: 0;
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 1;
  }
  100% {
    top: 100%;
    opacity: 0;
  }
}

/* 内容 */
.holo-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.metric-icon {
  font-size: 36px;
  margin-bottom: 5px;
  animation: iconGlow 2s ease-in-out infinite;
}

@keyframes iconGlow {
  0%, 100% {
    transform: scale(1);
    filter: brightness(1);
  }
  50% {
    transform: scale(1.05);
    filter: brightness(1.2);
  }
}

.metric-value {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.value-text {
  font-size: 42px;
  font-weight: 700;
  font-family: 'Orbitron', monospace;
  line-height: 1;
  text-shadow: 0 0 10px currentColor;
  animation: valuePulse 3s ease-in-out infinite;
}

@keyframes valuePulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.02);
  }
}

.value-unit {
  font-size: 14px;
  color: #9ca3af;
  font-weight: 500;
  letter-spacing: 1px;
}

.metric-label {
  font-size: 12px;
  color: #6b7280;
  letter-spacing: 2px;
  text-transform: uppercase;
  font-weight: 600;
}

.metric-trend {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.05);
  transition: all 0.3s;
}

.metric-trend.up {
  color: #00ff9f;
  background: rgba(0, 255, 159, 0.1);
}

.metric-trend.down {
  color: #ff003c;
  background: rgba(255, 0, 60, 0.1);
}

.metric-trend.stable {
  color: #00f0ff;
  background: rgba(0, 240, 255, 0.1);
}

.trend-icon {
  font-size: 10px;
}

.trend-value {
  font-family: 'Orbitron', monospace;
}

/* 全息倒影 */
.holo-reflection {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 50%;
  background: linear-gradient(
    to bottom,
    transparent,
    rgba(0, 240, 255, 0.03)
  );
  pointer-events: none;
  transform: scaleY(-1);
  opacity: 0.3;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .holo-card {
    padding: 20px 15px;
  }

  .metric-icon {
    font-size: 28px;
  }

  .value-text {
    font-size: 32px;
  }

  .value-unit {
    font-size: 12px;
  }

  .metric-label {
    font-size: 10px;
  }
}
</style>
