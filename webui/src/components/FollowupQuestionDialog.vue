/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-dialog
    v-model="dialogVisible"
    title="需要更多信息"
    width="600px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    class="followup-dialog"
  >
    <div class="followup-question">
      <!-- 问题文本 -->
      <div class="question-section">
        <el-icon class="question-icon"><QuestionFilled /></el-icon>
        <div class="question-text">{{ question }}</div>
      </div>

      <!-- 建议答案 -->
      <div class="suggestions-section">
        <div class="section-label">建议答案：</div>
        <div v-if="suggestions && suggestions.length > 0" class="suggestions-list">
          <el-button
            v-for="(suggestion, index) in suggestions"
            :key="index"
            :type="selectedSuggestion === index ? 'primary' : 'default'"
            @click="selectSuggestion(index, suggestion)"
            class="suggestion-btn"
            size="large"
          >
            <span class="suggestion-number">{{ index + 1 }}.</span>
            <span class="suggestion-text">{{ suggestion }}</span>
          </el-button>
        </div>
        <div v-else class="no-suggestions-warning">
          <el-alert
            title="未提供建议答案"
            type="warning"
            :closable="false"
            show-icon
          >
            <template #default>
              <p>LLM 未为此问题提供建议答案，请直接输入您的回答。</p>
              <p class="debug-info">Debug: suggestions 为空或未定义 (长度: {{ suggestions?.length || 0 }})</p>
            </template>
          </el-alert>
        </div>
      </div>

      <!-- 自定义输入 -->
      <div class="custom-response-section">
        <div class="section-label">或者输入自定义答案：</div>
        <el-input
          v-model="customResponse"
          type="textarea"
          :rows="4"
          placeholder="请输入您的回答..."
          @input="onCustomInput"
          :disabled="isSubmitting"
        />
      </div>

      <!-- 字符计数 -->
      <div v-if="customResponse.length > 0" class="char-count">
        {{ customResponse.length }} 个字符
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button
          type="primary"
          @click="submitResponse"
          :disabled="!hasResponse || isSubmitting"
          :loading="isSubmitting"
          size="large"
        >
          提交答案
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { QuestionFilled } from '@element-plus/icons-vue';

interface Props {
  visible: boolean;
  question: string;
  suggestions: string[];
  toolCallId: string;
  taskId: string;
}

interface Emits {
  (e: 'update:visible', value: boolean): void;
  (e: 'response', toolCallId: string, response: string): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// 响应式状态
const dialogVisible = ref(false);
const customResponse = ref('');
const selectedSuggestion = ref<number | null>(null);
const isSubmitting = ref(false);

// 监听 visible prop
watch(() => props.visible, (newVal) => {
  dialogVisible.value = newVal;
  if (newVal) {
    // 重置状态
    customResponse.value = '';
    selectedSuggestion.value = null;
    isSubmitting.value = false;
  }
});

// 监听 dialogVisible 变化，同步到父组件
watch(dialogVisible, (newVal) => {
  emit('update:visible', newVal);
});

// 计算属性
const hasResponse = computed(() => {
  return customResponse.value.trim().length > 0;
});

// 方法
function selectSuggestion(index: number, suggestion: string) {
  selectedSuggestion.value = index;
  customResponse.value = suggestion;
}

function onCustomInput() {
  // 用户手动输入时，清除建议答案的选择
  if (selectedSuggestion.value !== null) {
    selectedSuggestion.value = null;
  }
}

async function submitResponse() {
  if (!hasResponse.value || isSubmitting.value) {
    return;
  }

  isSubmitting.value = true;

  try {
    // 发送响应
    emit('response', props.toolCallId, customResponse.value.trim());

    // 关闭对话框
    dialogVisible.value = false;
  } catch (error) {
    console.error('Failed to submit followup response:', error);
  } finally {
    isSubmitting.value = false;
  }
}

// 暴露方法给父组件
defineExpose({
  reset: () => {
    customResponse.value = '';
    selectedSuggestion.value = null;
    isSubmitting.value = false;
  }
});
</script>

<style scoped>
.followup-dialog :deep(.el-dialog__header) {
  padding: 20px 20px 10px;
  border-bottom: 1px solid #e4e7ed;
}

.followup-dialog :deep(.el-dialog__body) {
  padding: 20px;
}

.followup-dialog :deep(.el-dialog__footer) {
  padding: 10px 20px 20px;
  border-top: 1px solid #e4e7ed;
}

.followup-question {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.question-section {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.question-icon {
  font-size: 24px;
  color: #409eff;
  flex-shrink: 0;
  margin-top: 2px;
}

.question-text {
  flex: 1;
  font-size: 16px;
  font-weight: 500;
  line-height: 1.6;
  color: #303133;
}

.suggestions-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-label {
  font-size: 14px;
  font-weight: 500;
  color: #606266;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggestion-btn {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  text-align: left;
  padding: 12px 16px;
  border-radius: 8px;
  transition: all 0.3s;
}

.suggestion-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.suggestion-number {
  font-weight: 600;
  color: #409eff;
  flex-shrink: 0;
}

.suggestion-text {
  flex: 1;
  line-height: 1.5;
  word-break: break-word;
}

.custom-response-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.custom-response-section :deep(.el-textarea__inner) {
  border-radius: 8px;
  padding: 12px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
}

.char-count {
  text-align: right;
  font-size: 12px;
  color: #909399;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
}

.dialog-footer :deep(.el-button) {
  min-width: 120px;
}

.no-suggestions-warning {
  margin: 10px 0;
}

.no-suggestions-warning .debug-info {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
  font-family: 'Courier New', monospace;
}

/* 动画 */
.followup-question :deep(.el-button) {
  transition: all 0.3s ease;
}
</style>
