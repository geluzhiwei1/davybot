/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="llm-api-request-content compact-content">
    <div class="request-header compact-header">
      <div class="header-left">
        <el-icon class="api-icon"><Cloudy /></el-icon>
        <span class="request-title compact-title">LLM API 请求</span>
        <el-tag size="small" type="primary" effect="light" class="compact-tag">
          {{ request.provider }}
        </el-tag>
        <el-tag size="small" type="info" effect="light" class="compact-tag">
          {{ request.model }}
        </el-tag>
        <el-tag size="small" :type="getRequestTypeTag(request.request_type)" effect="light" class="compact-tag">
          {{ request.request_type }}
        </el-tag>
      </div>
      <div class="header-right">
        <el-icon class="loading-icon is-loading"><Loading /></el-icon>
      </div>
    </div>

    <div class="request-body compact-body">
      <!-- 请求信息 -->
      <div class="request-info compact-stats">
        <div class="info-item" v-if="request.input_tokens !== undefined">
          <el-icon><Document /></el-icon>
          <div class="info-content">
            <div class="info-label">输入 Tokens</div>
            <div class="info-value">{{ request.input_tokens }}</div>
          </div>
        </div>
        <div class="info-item">
          <el-icon><Timer /></el-icon>
          <div class="info-content">
            <div class="info-label">开始时间</div>
            <div class="info-value">{{ formatTimestamp(timestamp, 'time') }}</div>
          </div>
        </div>
        <div class="info-item">
          <el-icon><InfoFilled /></el-icon>
          <div class="info-content">
            <div class="info-label">请求类型</div>
            <div class="info-value">{{ request.request_type }}</div>
          </div>
        </div>
      </div>

      <!-- 元数据 -->
      <el-collapse v-if="request.metadata && Object.keys(request.metadata).length > 0" class="metadata-collapse compact-collapse">
        <el-collapse-item name="metadata" title="详细信息">
          <pre class="metadata-json compact-pre">{{ JSON.stringify(request.metadata, null, 2) }}</pre>
        </el-collapse-item>
      </el-collapse>

      <!-- 成本估算 -->
      <div class="cost-estimate compact-detail-block" v-if="estimatedCost > 0">
        <el-icon><Coin /></el-icon>
        <span class="cost-text">预估成本: ${{ estimatedCost.toFixed(4) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatTimestamp } from '@/utils/formatters'
import { computed } from 'vue'
import { Cloudy, Loading, Coin, Document, Timer, InfoFilled } from '@element-plus/icons-vue'
import { ElTag, ElIcon, ElCollapse, ElCollapseItem } from 'element-plus'

// 定义LLM API请求消息类型（临时定义，应该从types中导入）
interface LLMApiRequestBlock {
  type: 'llm_api_request'
  provider: string
  model: string
  request_type: string
  input_tokens?: number
  metadata?: Record<string, unknown>
}

const props = defineProps<{
  block: LLMApiRequestBlock
}>()

const request = computed(() => props.block)
const timestamp = computed(() => new Date().toISOString())

// 估算成本（简化版本，基于输入tokens）
const estimatedCost = computed(() => {
  const inputTokens = request.value.input_tokens
  if (!inputTokens) return 0

  // 简化的成本计算
  const promptPrice = 0.0001 // $0.0001 per 1K tokens
  return (inputTokens / 1000) * promptPrice
})

// 获取请求类型标签颜色
const getRequestTypeTag = (type: string) => {
  switch (type) {
    case 'chat':
      return 'success'
    case 'completion':
      return 'warning'
    case 'embedding':
      return 'info'
    default:
      return 'info'
  }
}
</script>

<style scoped>
/* 导入紧凑样式 */
@import './compact-styles.css';

/* 组件特定样式 */
.llm-api-request-content {
  animation: pulse-border 2s infinite;
}

@keyframes pulse-border {
  0%, 100% {
    border-color: var(--modern-border-light);
  }
  50% {
    border-color: var(--modern-color-primary);
  }
}

.request-header {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
}

.api-icon {
  font-size: 16px;
  color: var(--modern-color-info);
}

.loading-icon {
  font-size: 16px;
  color: var(--modern-color-warning);
}

/* 请求信息 */
.request-info {
  margin-bottom: var(--modern-spacing-md);
}

.info-item {
  flex-direction: column;
  align-items: flex-start;
  gap: var(--modern-spacing-xs);
  padding: var(--modern-spacing-sm);
}

.info-item .el-icon {
  font-size: 14px;
  color: var(--modern-color-info);
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}

.info-label {
  font-size: var(--modern-font-xs);
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.info-value {
  font-size: var(--modern-font-sm);
  color: var(--el-text-color-primary);
  font-weight: 600;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

/* 元数据 */
.metadata-collapse {
  margin-bottom: var(--modern-spacing-md);
}

.metadata-json {
  margin: 0;
}

/* 成本估算 */
.cost-estimate {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm);
  padding: var(--modern-spacing-md);
  background: linear-gradient(135deg, var(--modern-color-warning-light) 0%, #fef3c7 100%);
  border: 1px solid var(--modern-color-warning);
}

.cost-estimate .el-icon {
  font-size: 16px;
  color: var(--modern-color-warning);
}

.cost-text {
  font-size: var(--modern-font-sm);
  font-weight: 500;
  color: #92400e;
}
</style>
