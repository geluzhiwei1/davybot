/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div v-if="showHelp" class="keyboard-help-overlay" @click.self="close">
    <div class="keyboard-help-modal">
      <div class="help-header">
        <h2>> 键盘快捷键</h2>
        <button @click="close" class="close-btn">[×]</button>
      </div>

      <div class="help-body">
        <div class="help-section">
          <h3>模式切换</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>i</kbd>
              <span>进入插入模式（编辑）</span>
            </div>
            <div class="shortcut-item">
              <kbd>Esc</kbd>
              <span>返回正常模式</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>导航</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>j</kbd>
              <span>向下滚动</span>
            </div>
            <div class="shortcut-item">
              <kbd>k</kbd>
              <span>向上滚动</span>
            </div>
            <div class="shortcut-item">
              <kbd>gg</kbd>
              <span>跳转到顶部</span>
            </div>
            <div class="shortcut-item">
              <kbd>G</kbd>
              <span>跳转到底部</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>操作</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>Enter</kbd>
              <span>发送消息（插入模式）</span>
            </div>
            <div class="shortcut-item">
              <kbd>/</kbd>
              <span>搜索</span>
            </div>
            <div class="shortcut-item">
              <kbd>n</kbd>
              <span>下一个搜索结果</span>
            </div>
            <div class="shortcut-item">
              <kbd>N</kbd>
              <span>上一个搜索结果</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>内容操作</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>yy</kbd>
              <span>复制当前消息</span>
            </div>
            <div class="shortcut-item">
              <kbd>Ctrl+C</kbd>
              <span>复制选中内容</span>
            </div>
            <div class="shortcut-item">
              <kbd>Ctrl+V</kbd>
              <span>粘贴</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>折叠控制</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>fold</kbd>
              <span>折叠所有内容</span>
            </div>
            <div class="shortcut-item">
              <kbd>unfold</kbd>
              <span>展开所有内容</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>工具操作</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>r</kbd>
              <span>重试工具</span>
            </div>
            <div class="shortcut-item">
              <kbd>v</kbd>
              <span>查看详情</span>
            </div>
          </div>
        </div>

        <div class="help-section">
          <h3>其他</h3>
          <div class="shortcut-list">
            <div class="shortcut-item">
              <kbd>?</kbd>
              <span>显示/隐藏此帮助</span>
            </div>
          </div>
        </div>
      </div>

      <div class="help-footer">
        <span>当前模式: [{{ mode.toUpperCase() }}]</span>
        <span>按 [?] 或 [Esc] 关闭</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { VimMode } from '@/composables/useKeyboardShortcuts'

interface Props {
  showHelp: boolean
  mode: VimMode
}

defineProps<Props>()

const emit = defineEmits<{
  close: []
}>()

const close = () => {
  emit('close')
}
</script>

<style scoped>
.keyboard-help-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}

.keyboard-help-modal {
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  background: #ffffff;
  border: 2px solid #000000;
  display: flex;
  flex-direction: column;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 12px;
}

.help-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f5f5f5;
  border-bottom: 2px solid #000000;
}

.help-header h2 {
  margin: 0;
  font-size: 14px;
  font-weight: bold;
  color: #000000;
}

.close-btn {
  background: transparent;
  border: 1px solid #d0d0d0;
  padding: 2px 6px;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}

.close-btn:hover {
  background: #e8e8e8;
}

.help-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.help-section {
  border: 1px solid #e8e8e8;
  padding: 8px;
  background: #fafafa;
}

.help-section h3 {
  margin: 0 0 8px 0;
  font-size: 11px;
  font-weight: bold;
  color: #000000;
  border-bottom: 1px dashed #d0d0d0;
  padding-bottom: 4px;
}

.shortcut-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.shortcut-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

kbd {
  background: #ffffff;
  border: 1px solid #000000;
  padding: 1px 4px;
  font-family: inherit;
  font-size: 10px;
  font-weight: bold;
  min-width: 60px;
  text-align: center;
  display: inline-block;
}

.shortcut-item span {
  color: #666666;
}

.help-footer {
  display: flex;
  justify-content: space-between;
  padding: 6px 12px;
  background: #f5f5f5;
  border-top: 1px solid #d0d0d0;
  font-size: 10px;
  color: #666666;
}

/* 响应式 */
@media (max-width: 640px) {
  .help-body {
    grid-template-columns: 1fr;
  }

  .keyboard-help-modal {
    width: 95%;
    max-height: 90vh;
  }
}
</style>
