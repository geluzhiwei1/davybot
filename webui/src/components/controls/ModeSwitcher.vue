/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="mode-switcher">
    <div class="mode-header">
      <span class="mode-label">PDCA Agent 模式</span>
      <el-tooltip
        content="Orchestrator: 智能协调 | Plan: 规划 | Do: 执行 | Check: 检查 | Act: 改进"
        placement="top"
      >
        <el-icon class="info-icon"><QuestionFilled /></el-icon>
      </el-tooltip>
    </div>

    <!-- 简化模式 -->
    <div class="mode-section">
      <div class="mode-section-title">简化模式</div>
      <div class="mode-buttons">
        <button
          :class="['mode-btn', { active: currentMode === 'orchestrator' }]"
          @click="switchMode('orchestrator')"
          :disabled="isSwitching"
        >
          <span class="mode-icon">🪃</span>
          <span class="mode-name">Orchestrator</span>
          <span class="mode-desc">智能协调</span>
          <span v-if="currentMode === 'orchestrator'" class="mode-badge">推荐</span>
        </button>

        <button
          :class="['mode-btn', { active: currentMode === 'plan' }]"
          @click="switchMode('plan')"
          :disabled="isSwitching"
        >
          <span class="mode-icon">📋</span>
          <span class="mode-name">Plan Only</span>
          <span class="mode-desc">只读分析</span>
          <span v-if="currentMode === 'plan'" class="mode-badge">当前</span>
        </button>
      </div>
    </div>

    <!-- PDCA 完整模式 -->
    <div class="mode-section">
      <div class="mode-section-title">PDCA 循环模式</div>
      <div class="pdca-cycle">
        <button
          :class="['pdca-btn', { active: currentMode === 'plan', active: pdcaPhase === 'plan' }]"
          @click="switchMode('plan')"
          :disabled="isSwitching"
        >
          <span class="pdca-icon">📋</span>
          <span class="pdca-name">Plan</span>
          <span class="pdca-desc">规划</span>
        </button>

        <button
          :class="['pdca-btn', { active: currentMode === 'do' }]"
          @click="switchMode('do')"
          :disabled="isSwitching"
        >
          <span class="pdca-icon">⚙️</span>
          <span class="pdca-name">Do</span>
          <span class="pdca-desc">执行</span>
        </button>

        <button
          :class="['pdca-btn', { active: currentMode === 'check' }]"
          @click="switchMode('check')"
          :disabled="isSwitching"
        >
          <span class="pdca-icon">✓</span>
          <span class="pdca-name">Check</span>
          <span class="pdca-desc">检查</span>
        </button>

        <button
          :class="['pdca-btn', { active: currentMode === 'act' }]"
          @click="switchMode('act')"
          :disabled="isSwitching"
        >
          <span class="pdca-icon">🚀</span>
          <span class="pdca-name">Act</span>
          <span class="pdca-desc">改进</span>
        </button>
      </div>
    </div>

    <div v-if="modeMessage" class="mode-message" :class="messageType">
      {{ modeMessage }}
    </div>

    <!-- PDCA 循环状态 -->
    <div v-if="pdcaStatus" class="pdca-status">
      <div class="pdca-status-header">PDCA 循环状态</div>
      <div class="pdca-progress">
        <div
          v-for="phase in pdcaPhases"
          :key="phase.name"
          :class="['pdca-phase', phase.status]"
        >
          <span class="phase-icon">{{ phase.icon }}</span>
          <span class="phase-name">{{ phase.name }}</span>
          <span class="phase-indicator">{{ phase.indicator }}</span>
        </div>
      </div>
      <div class="pdca-completion">
        完成度: {{ pdcaStatus.completion }}%
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { QuestionFilled } from '@element-plus/icons-vue';
import { useWebSocket } from '@/composables/useWebSocket';
import type { ModeSwitchMessage, ModeSwitchedMessage } from '@/types/websocket';
import { MessageType } from '@/types/websocket';

const { sendMessage, subscribe, sessionId, isConnected } = useWebSocket();

// PDCA Modes 类型
type PDAMode = 'orchestrator' | 'plan' | 'do' | 'check' | 'act';

const currentMode = ref<PDAMode>('orchestrator');
const isSwitching = ref(false);
const modeMessage = ref('');
const messageType = ref<'info' | 'success' | 'error'>('info');
const pdcaPhase = ref<string>('');
const pdcaStatus = ref<unknown>(null);

// PDCA 阶段定义
const pdcaPhases = computed(() => [
  {
    name: 'Plan',
    icon: '📋',
    status: pdcaStatus.value?.phases?.plan === 'completed' ? 'completed' :
           pdcaStatus.value?.phases?.plan === 'in_progress' ? 'in-progress' : 'pending',
    indicator: pdcaStatus.value?.phases?.plan === 'completed' ? '✓' :
                 pdcaStatus.value?.phases?.plan === 'in_progress' ? '→' : '○'
  },
  {
    name: 'Do',
    icon: '⚙️',
    status: pdcaStatus.value?.phases?.do === 'completed' ? 'completed' :
           pdcaStatus.value?.phases?.do === 'in_progress' ? 'in-progress' : 'pending',
    indicator: pdcaStatus.value?.phases?.do === 'completed' ? '✓' :
                 pdcaStatus.value?.phases?.do === 'in_progress' ? '→' : '○'
  },
  {
    name: 'Check',
    icon: '✓',
    status: pdcaStatus.value?.phases?.check === 'completed' ? 'completed' :
           pdcaStatus.value?.phases?.check === 'in_progress' ? 'in-progress' : 'pending',
    indicator: pdcaStatus.value?.phases?.check === 'completed' ? '✓' :
                 pdcaStatus.value?.phases?.check === 'in_progress' ? '→' : '○'
  },
  {
    name: 'Act',
    icon: '🚀',
    status: pdcaStatus.value?.phases?.act === 'completed' ? 'completed' :
           pdcaStatus.value?.phases?.act === 'in_progress' ? 'in-progress' : 'pending',
    indicator: pdcaStatus.value?.phases?.act === 'completed' ? '✓' :
                 pdcaStatus.value?.phases?.act === 'in_progress' ? '→' : '○'
  }
]);

// 订阅模式切换完成消息和 PDCA 状态更新
onMounted(() => {
  subscribe((message: unknown) => {
    if (message.type === MessageType.MODE_SWITCHED) {
      const switchedMessage = message as ModeSwitchedMessage;
      currentMode.value = switchedMessage.current_mode as PDAMode;
      isSwitching.value = false;

      modeMessage.value = switchedMessage.message;
      messageType.value = 'success';

      ElMessage.success(`已切换到 ${switchedMessage.current_mode.toUpperCase()} 模式`);

      // 3秒后清除消息
      setTimeout(() => {
        modeMessage.value = '';
      }, 3000);
    }

    // 监听 PDCA 状态更新
    if (message.type === 'pdca_status_update') {
      pdcaStatus.value = message.data;
    }
  });

  // 从本地存储恢复模式状态
  const savedMode = localStorage.getItem('agent_mode') as PDAMode;
  if (savedMode && ['orchestrator', 'plan', 'do', 'check', 'act'].includes(savedMode)) {
    currentMode.value = savedMode;
  }
});

async function switchMode(mode: PDAMode) {
  if (!isConnected.value) {
    ElMessage.error('WebSocket 未连接，无法切换模式');
    return;
  }

  if (currentMode.value === mode) {
    return; // 已经是目标模式
  }

  isSwitching.value = true;
  modeMessage.value = `正在切换到 ${mode.toUpperCase()} 模式...`;
  messageType.value = 'info';

  try {
    const message: ModeSwitchMessage = {
      id: Date.now().toString(),
      type: MessageType.MODE_SWITCH,
      timestamp: new Date().toISOString(),
      session_id: sessionId.value || '',
      mode,
    };

    sendMessage(message);

    // 保存到本地存储
    localStorage.setItem('agent_mode', mode);
  } catch (error) {
    console.error('切换模式失败:', error);
    isSwitching.value = false;
    modeMessage.value = '切换模式失败';
    messageType.value = 'error';
    ElMessage.error('切换模式失败');
  }
}
</script>

<style scoped>
.mode-switcher {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
}

.mode-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.info-icon {
  font-size: 16px;
  color: var(--el-color-info);
  cursor: help;
}

.mode-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mode-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mode-buttons {
  display: flex;
  gap: 12px;
}

.mode-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 12px;
  border: 2px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
}

.mode-btn:hover:not(:disabled) {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.mode-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.mode-btn.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-7);
}

.mode-icon {
  font-size: 32px;
  line-height: 1;
}

.mode-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.mode-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.mode-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  background: var(--el-color-primary);
  color: white;
  border-radius: 10px;
}

/* PDCA Cycle 样式 */
.pdca-cycle {
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.pdca-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  border: 2px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  transition: all 0.3s ease;
  min-width: 60px;
}

.pdca-btn:hover:not(:disabled) {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  transform: translateY(-2px);
}

.pdca-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pdca-btn.active {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  box-shadow: 0 0 0 2px var(--el-color-success-light-7);
}

.pdca-icon {
  font-size: 24px;
  line-height: 1;
}

.pdca-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.pdca-desc {
  font-size: 10px;
  color: var(--el-text-color-secondary);
}

/* PDCA 状态显示 */
.pdca-status {
  margin-top: 8px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  border: 1px solid var(--el-border-color);
}

.pdca-status-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.pdca-progress {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.pdca-phase {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
  border-radius: 6px;
  font-size: 11px;
  transition: all 0.3s ease;
}

.pdca-phase.pending {
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-placeholder);
}

.pdca-phase.in-progress {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.pdca-phase.completed {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.phase-icon {
  font-size: 18px;
}

.phase-name {
  font-weight: 600;
}

.phase-indicator {
  font-size: 14px;
}

.pdca-completion {
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.mode-message {
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  text-align: center;
  animation: fadeIn 0.3s ease;
}

.mode-message.info {
  background: var(--el-color-info-light-9);
  color: var(--el-color-info);
  border: 1px solid var(--el-color-info-light-5);
}

.mode-message.success {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
  border: 1px solid var(--el-color-success-light-5);
}

.mode-message.error {
  background: var(--el-color-error-light-9);
  color: var(--el-color-error);
  border: 1px solid var(--el-color-error-light-5);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
