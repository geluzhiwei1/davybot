/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="unknown-content-block">
    <div class="unknown-header">
      <el-icon><Warning /></el-icon>
      <span class="unknown-title">未知消息类型</span>
      <el-tag size="small" type="info">{{ block.type }}</el-tag>
    </div>

    <el-collapse v-model="expanded" class="unknown-details">
      <el-collapse-item title="查看详情" name="details">
        <div class="unknown-content">
          <pre class="json-content">{{ formatContent(block) }}</pre>
        </div>
      </el-collapse-item>
    </el-collapse>

    <div v-if="showRawMessage" class="raw-message-section">
      <el-button size="small" @click="copyRawContent">
        <el-icon><DocumentCopy /></el-icon>
        复制原始内容
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ElIcon, ElTag, ElCollapse, ElCollapseItem, ElButton, ElMessage } from 'element-plus';
import { Warning, DocumentCopy } from '@element-plus/icons-vue';
import type { ContentBlock } from '@/types/websocket';
import { copyToClipboard } from '@/utils/clipboard';

interface Props {
  block: ContentBlock;
}

const props = defineProps<Props>();
const expanded = ref<string[]>([]);
const showRawMessage = ref(true);

const formatContent = (block: ContentBlock): string => {
  try {
    return JSON.stringify(block, null, 2);
  } catch {
    return String(block);
  }
};

const copyRawContent = async () => {
  const content = formatContent(props.block);
  const success = await copyToClipboard(content);
  if (success) {
    ElMessage.success('已复制到剪贴板');
  } else {
    ElMessage.error('复制失败');
  }
};
</script>

<style scoped>
.unknown-content-block {
  margin: 8px 0;
  border: 1px solid #f59e0b;
  border-radius: 4px;
  background: #fffbeb;
}

.unknown-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fef3c7;
  border-bottom: 1px solid #f59e0b;
}

.unknown-header .el-icon {
  color: #f59e0b;
  font-size: 18px;
}

.unknown-title {
  flex: 1;
  font-weight: 500;
  color: #92400e;
}

.unknown-details {
  border: none;
}

.unknown-content {
  padding: 12px;
  background: #ffffff;
}

.json-content {
  margin: 0;
  padding: 12px;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
}

.raw-message-section {
  padding: 8px 12px;
  background: #fef3c7;
  border-top: 1px solid #f59e0b;
  display: flex;
  justify-content: flex-end;
}
</style>
