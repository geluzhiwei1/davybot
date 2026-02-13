/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="cost-tracker-panel">
    <div class="panel-header">
      <h4>💰 成本追踪</h4>
      <div class="header-actions">
        <el-select
          v-model="detailLevel"
          size="small"
          @change="fetchCostData"
        >
          <el-option label="概览" value="summary" />
          <el-option label="详细" value="detailed" />
          <el-option label="建议" value="suggestions" />
        </el-select>
        <el-button
          size="small"
          :icon="RefreshRight"
          @click="fetchCostData"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- Summary View -->
    <div v-if="detailLevel === 'summary' && costData" class="summary-view">
      <div class="cost-cards">
        <div class="cost-card primary">
          <div class="card-icon">💵</div>
          <div class="card-content">
            <div class="card-label">总成本</div>
            <div class="card-value">${{ costData.total_cost }}</div>
          </div>
        </div>

        <div class="cost-card success">
          <div class="card-icon">📞</div>
          <div class="card-content">
            <div class="card-label">调用次数</div>
            <div class="card-value">{{ costData.total_calls }}</div>
          </div>
        </div>

        <div class="cost-card info">
          <div class="card-icon">📊</div>
          <div class="card-content">
            <div class="card-label">Token 总数</div>
            <div class="card-value">{{ formatNumber(costData.total_tokens) }}</div>
          </div>
        </div>

        <div class="cost-card warning">
          <div class="card-icon">⏱️</div>
          <div class="card-content">
            <div class="card-label">会话时长</div>
            <div class="card-value">{{ costData.session_duration }}</div>
          </div>
        </div>
      </div>

      <div class="cost-details">
        <div class="detail-row">
          <span class="detail-label">输入 Tokens:</span>
          <span class="detail-value">{{ formatNumber(costData.input_tokens) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">输出 Tokens:</span>
          <span class="detail-value">{{ formatNumber(costData.output_tokens) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">主要模型:</span>
          <span class="detail-value">{{ costData.top_model }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">平均成本/次:</span>
          <span class="detail-value">{{ costData.average_cost_per_call }}</span>
        </div>
      </div>
    </div>

    <!-- Detailed View -->
    <div v-else-if="detailLevel === 'detailed' && costData" class="detailed-view">
      <div class="section">
        <h5>📊 按模型统计</h5>
        <div class="model-breakdown">
          <div
            v-for="(model, name) in costData.by_model"
            :key="name"
            class="model-item"
          >
            <div class="model-header">
              <span class="model-name">{{ name }}</span>
              <span class="model-cost">{{ model.cost }}</span>
            </div>
            <div class="model-stats">
              <span class="stat">{{ model.calls }} 次调用</span>
              <span class="stat">{{ formatNumber(model.tokens) }} tokens</span>
              <span class="stat percentage">{{ model.percentage }}</span>
            </div>
            <el-progress
              :percentage="parseFloat(model.percentage)"
              :color="getProgressColor(parseFloat(model.percentage))"
            />
          </div>
        </div>
      </div>

      <div class="section">
        <h5>📋 按任务类型统计</h5>
        <div class="task-breakdown">
          <div
            v-for="(task, type) in costData.by_task_type"
            :key="type"
            class="task-item"
          >
            <div class="task-header">
              <span class="task-name">{{ formatTaskType(type) }}</span>
              <span class="task-cost">{{ task.cost }}</span>
            </div>
            <div class="task-stats">
              <span class="stat">{{ task.calls }} 次调用</span>
              <span class="stat percentage">{{ task.percentage }}</span>
            </div>
            <el-progress
              :percentage="parseFloat(task.percentage)"
              :color="getProgressColor(parseFloat(task.percentage))"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Suggestions View -->
    <div v-else-if="detailLevel === 'suggestions' && costData" class="suggestions-view">
      <div v-if="costData.suggestions && costData.suggestions.length > 0" class="suggestions-list">
        <div
          v-for="(suggestion, index) in costData.suggestions"
          :key="index"
          class="suggestion-item"
        >
          <span class="suggestion-icon">💡</span>
          <span class="suggestion-text">{{ suggestion }}</span>
        </div>
      </div>

      <div v-if="costData.quick_wins && costData.quick_wins.length > 0" class="quick-wins">
        <h5>🚀 快速优化</h5>
        <div
          v-for="(win, index) in costData.quick_wins"
          :key="'win-' + index"
          class="win-item"
        >
          <div class="win-header">
            <span class="win-title">{{ win.description }}</span>
            <el-tag size="small" type="success">
              节省 {{ win.potential_savings }}
            </el-tag>
          </div>
        </div>
      </div>

      <el-empty
        v-if="(!costData.suggestions || costData.suggestions.length === 0) &&
                  (!costData.quick_wins || costData.quick_wins.length === 0)"
        description="暂无优化建议，成本控制良好！"
        :image-size="100"
      />
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="3" animated />
    </div>

    <!-- Error State -->
    <div v-if="error" class="error-state">
      <el-result
        icon="error"
        title="加载失败"
        :sub-title="error"
      >
        <template #extra>
          <el-button type="primary" @click="fetchCostData">重试</el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { RefreshRight } from '@element-plus/icons-vue';
import { useWebSocket } from '@/composables/useWebSocket';
import type { CostUpdateMessage } from '@/types/websocket';

const { subscribe, unsubscribe } = useWebSocket();

// State
const detailLevel = ref<'summary' | 'detailed' | 'suggestions'>('summary');
const costData = ref<unknown>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// WebSocket subscription
let costUpdateHandler: ((message: unknown) => void) | null = null;

// Fetch cost data
async function fetchCostData() {
  loading.value = true;
  error.value = null;

  try {
    // TODO: Implement actual API call
    // For now, simulate data
    await new Promise(resolve => setTimeout(resolve, 500));

    costData.value = {
      // Summary data
      total_cost: '0.1234',
      total_calls: 42,
      total_tokens: 125000,
      input_tokens: 80000,
      output_tokens: 45000,
      session_duration: '2.50 hours',
      top_model: 'deepseek-chat ($0.0850)',
      average_cost_per_call: '$0.0029',

      // Detailed data
      by_model: {
        'deepseek-chat': {
          calls: 35,
          tokens: 100000,
          cost: '0.0850',
          percentage: '68.9%'
        },
        'anthropic/claude-opus-4': {
          calls: 5,
          tokens: 20000,
          cost: '0.0320',
          percentage: '25.9%'
        },
        'local/qwen2.5-coder:7b': {
          calls: 2,
          tokens: 5000,
          cost: '0.0064',
          percentage: '5.2%'
        }
      },

      by_task_type: {
        'daily_chat': {
          calls: 30,
          cost: '0.0720',
          percentage: '58.4%'
        },
        'complex_reasoning': {
          calls: 8,
          cost: '0.0380',
          percentage: '30.8%'
        },
        'code_completion': {
          calls: 4,
          cost: '0.0134',
          percentage: '10.8%'
        }
      },

      // Suggestions data
      suggestions: [
        '高成本模型 anthropic/claude-opus-4 占用了 25.9% 成本，考虑为日常任务切换到 DeepSeek Chat',
        '代码补全已调用 4 次，建议使用本地 Qwen 模型以节省 $0.0134'
      ],
      quick_wins: [
        {
          type: 'model_substitution',
          description: 'Consider using cheaper alternatives for anthropic/claude-opus-4',
          potential_savings: '~$0.0224'
        }
      ]
    };
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch cost data';
  } finally {
    loading.value = false;
  }
}

// Format number with commas
function formatNumber(num: number): string {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format task type for display
function formatTaskType(type: string): string {
  const typeMap: Record<string, string> = {
    'daily_chat': '日常对话',
    'complex_reasoning': '复杂推理',
    'code_completion': '代码补全',
    'long_context': '长上下文',
    'critical_output': '关键输出'
  };
  return typeMap[type] || type;
}

// Get progress bar color based on percentage
function getProgressColor(percentage: number): string {
  if (percentage > 60) return '#f56c6c';  // Red
  if (percentage > 30) return '#e6a23c';  // Orange
  return '#67c23a';  // Green
}

// Lifecycle
onMounted(() => {
  fetchCostData();

  // Subscribe to cost updates via WebSocket
  costUpdateHandler = (message: unknown) => {
    if (message.type === 'cost_update') {
      const updateMessage = message as CostUpdateMessage;
      // Update cost data
      if (updateMessage.data) {
        costData.value = {
          ...costData.value,
          ...updateMessage.data
        };
      }
    }
  };

  subscribe(costUpdateHandler);
});

onUnmounted(() => {
  if (costUpdateHandler) {
    unsubscribe(costUpdateHandler);
  }
});
</script>

<style scoped>
.cost-tracker-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--el-bg-color);
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

/* Summary View */
.cost-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.cost-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  border-left: 4px solid;
  transition: all 0.2s;
}

.cost-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.cost-card.primary {
  border-left-color: var(--el-color-primary);
}

.cost-card.success {
  border-left-color: var(--el-color-success);
}

.cost-card.info {
  border-left-color: var(--el-color-info);
}

.cost-card.warning {
  border-left-color: var(--el-color-warning);
}

.card-icon {
  font-size: 24px;
}

.card-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.card-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.card-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.cost-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.detail-label {
  color: var(--el-text-color-secondary);
}

.detail-value {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* Detailed View */
.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.section h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.model-breakdown,
.task-breakdown {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.model-item,
.task-item {
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  transition: all 0.2s;
}

.model-item:hover,
.task-item:hover {
  background: var(--el-fill-color);
}

.model-header,
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.model-name,
.task-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.model-cost,
.task-cost {
  font-weight: 700;
  color: var(--el-color-danger);
}

.model-stats,
.task-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}

.stat {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.percentage {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

/* Suggestions View */
.suggestions-list,
.quick-wins {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-item,
.win-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: var(--el-color-info-light-9);
  border-left: 3px solid var(--el-color-info);
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.suggestion-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.suggestion-text {
  flex: 1;
  line-height: 1.5;
}

.win-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.win-title {
  flex: 1;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

/* Loading & Error States */
.loading-state,
.error-state {
  padding: 20px;
}
</style>
