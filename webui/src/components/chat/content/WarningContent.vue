/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="warning-content compact-content">
    <div class="warning-header compact-header">
      <div class="header-left">
        <el-icon class="warning-icon"><Warning /></el-icon>
        <span class="compact-title">警告</span>
        <el-tag v-if="block.code" size="small" type="warning" effect="light" class="compact-tag">
          {{ block.code }}
        </el-tag>
      </div>
      <div class="header-right">
        <el-button
          size="small"
          text
          @click="dismissWarning"
          :icon="Close"
          class="compact-btn"
        >
          关闭
        </el-button>
      </div>
    </div>

    <div class="warning-body compact-body">
      <div class="warning-message">{{ block.message }}</div>

      <!-- 详细信息 -->
      <el-collapse v-if="block.details && Object.keys(block.details).length > 0" class="details-collapse compact-collapse">
        <el-collapse-item name="details" title="详细信息">
          <div class="details-content">
            <pre class="compact-pre">{{ JSON.stringify(block.details, null, 2) }}</pre>
            <el-button
              size="small"
              @click="copyDetails"
              :icon="DocumentCopy"
              class="compact-btn"
            >
              复制详情
            </el-button>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- 建议操作 -->
      <div v-if="suggestions.length > 0" class="suggestions compact-detail-block">
        <div class="suggestions-title compact-detail-title">建议操作:</div>
        <ul class="suggestions-list">
          <li v-for="(suggestion, index) in suggestions" :key="index" class="suggestion-item">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ suggestion }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Warning, Close, DocumentCopy, InfoFilled } from '@element-plus/icons-vue'
import { ElIcon, ElTag, ElButton, ElCollapse, ElCollapseItem, ElMessage } from 'element-plus'
import { copyToClipboard } from '@/utils/clipboard'

// 定义警告内容块类型
interface WarningContentBlock {
  type: 'warning'
  code?: string
  message: string
  details?: Record<string, unknown>
}

const props = defineProps<{
  block: WarningContentBlock
}>()

const emit = defineEmits<{
  contentAction: [action: string, data: unknown]
}>()

// 根据警告代码生成建议
const suggestions = computed(() => {
  const code = props.block.code?.toLowerCase() || ''
  const message = props.block.message.toLowerCase()

  const suggestionMap: Record<string, string[]> = {
    'timeout': [
      '检查网络连接',
      '减少请求的数据量',
      '稍后重试'
    ],
    'rate_limit': [
      '降低请求频率',
      '等待一段时间后重试',
      '联系管理员增加配额'
    ],
    'deprecated': [
      '更新到最新的API版本',
      '查看迁移指南',
      '联系技术支持'
    ],
    'experimental': [
      '谨慎使用此功能',
      '备份重要数据',
      '在生产环境使用前充分测试'
    ]
  }

  // 根据代码匹配
  for (const [key, suggestions] of Object.entries(suggestionMap)) {
    if (code.includes(key) || message.includes(key)) {
      return suggestions
    }
  }

  // 默认建议
  return [
    '检查相关配置',
    '查看文档获取更多信息',
    '如果问题持续存在，请联系支持团队'
  ]
})

// 关闭警告
const dismissWarning = () => {
  emit('contentAction', 'dismiss', {
    warningCode: props.block.code,
    message: props.block.message
  })
}

// 复制详情
const copyDetails = async () => {
  const text = `警告信息:\n代码: ${props.block.code || 'N/A'}\n消息: ${props.block.message}\n详情: ${JSON.stringify(props.block.details, null, 2)}`

  const success = await copyToClipboard(text)
  if (success) {
    ElMessage.success('警告详情已复制到剪贴板')
  } else {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
/* 导入紧凑样式系统 */
@import './compact-styles.css';

/* ============================================================================
   Warning Content - 使用统一紧凑样式系统 + 警告风格
   ============================================================================ */

/* 警告内容 - 保留警告特色样式 */
.warning-content {
  /* 警告风格背景 - 特殊样式，保留 */
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 1px solid var(--el-color-warning-light-7, #fde68a);
}

/* 警告头部 - 使用紧凑样式，保留警告风格 */
.warning-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-bottom: 1px solid var(--el-color-warning-light-7, #fde68a);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: var(--modern-spacing-sm, 8px);
}

/* 警告图标 - 功能性样式，保留 */
.warning-icon {
  font-size: 18px;
  color: var(--modern-color-warning, #d97706);
}

/* 警告消息 */
.warning-message {
  font-size: var(--modern-font-md, 14px);
  line-height: 1.6;
  color: #78716c;
  margin-bottom: var(--modern-spacing-md, 12px);
}

/* 详情折叠 */
.details-collapse {
  margin-bottom: var(--modern-spacing-md, 12px);
}

.details-content {
  display: flex;
  flex-direction: column;
  gap: var(--modern-spacing-md, 12px);
}

/* 建议操作 - 使用紧凑样式 */
.suggestions {
  background-color: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--el-color-warning-light-7, #fde68a);
}

.suggestions-title {
  /* 使用紧凑样式变量 */
  font-size: var(--modern-font-sm, 13px);
  font-weight: 600;
  color: #92400e;
  margin-bottom: var(--modern-spacing-sm, 8px);
}

.suggestions-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: var(--modern-spacing-sm, 8px);
  padding: var(--modern-spacing-xs, 6px) 0;
  font-size: var(--modern-font-sm, 13px);
  color: #78716c;
}

.suggestion-item .el-icon {
  font-size: 14px;
  color: var(--modern-color-warning, #d97706);
  margin-top: 2px;
  flex-shrink: 0;
}
</style>
