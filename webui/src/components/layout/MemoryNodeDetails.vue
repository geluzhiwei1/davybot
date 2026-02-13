/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div v-if="memory" class="memory-node-details">
    <!-- Header -->
    <div class="details-header">
      <el-tag :type="getTypeTagType(memory.memory_type)" size="large">
        {{ memory.memory_type }}
      </el-tag>
      <div class="energy-indicator">
        <el-icon><Lightning /></el-icon>
        <span>{{ (memory.energy * 100).toFixed(0) }}%</span>
      </div>
    </div>

    <!-- Triple -->
    <div class="triple-display">
      <div class="triple-subject">
        <label>{{ t('memory.subject') }}</label>
        <el-input v-if="editable" v-model="localMemory.subject" />
        <div v-else class="triple-value">{{ memory.subject }}</div>
      </div>

      <div class="triple-predicate">
        <label>{{ t('memory.predicate') }}</label>
        <el-input v-if="editable" v-model="localMemory.predicate" />
        <div v-else class="triple-value">{{ memory.predicate }}</div>
      </div>

      <div class="triple-object">
        <label>{{ t('memory.object') }}</label>
        <el-input v-if="editable" v-model="localMemory.object" />
        <div v-else class="triple-value">{{ memory.object }}</div>
      </div>
    </div>

    <!-- Details Form -->
    <el-form v-if="editable" label-width="100px" class="details-form">
      <el-form-item :label="t('memory.confidence')">
        <el-slider v-model="localMemory.confidence" :min="0" :max="1" :step="0.1" />
        <span class="value-display">{{ (localMemory.confidence * 100).toFixed(0) }}%</span>
      </el-form-item>

      <el-form-item :label="t('memory.energy')">
        <el-slider v-model="localMemory.energy" :min="0" :max="1" :step="0.1" />
        <span class="value-display">{{ (localMemory.energy * 100).toFixed(0) }}%</span>
      </el-form-item>

      <el-form-item :label="t('memory.validFrom')">
        <el-date-picker
          v-model="validStartDate"
          type="datetime"
          :placeholder="t('memory.selectDate')"
        />
      </el-form-item>

      <el-form-item :label="t('memory.validTo')">
        <el-date-picker
          v-model="validEndDate"
          type="datetime"
          :placeholder="t('memory.optional')"
          clearable
        />
        <el-checkbox v-model="isValidIndefinitely" style="margin-left: 12px">
          {{ t('memory.indefinitely') }}
        </el-checkbox>
      </el-form-item>

      <el-form-item :label="t('memory.keywords')">
        <el-select
          v-model="localMemory.keywords"
          multiple
          filterable
          allow-create
          :placeholder="t('memory.addKeywords')"
        >
        </el-select>
      </el-form-item>
    </el-form>

    <!-- Read-only Details -->
    <el-descriptions v-else :column="1" border class="details-display">
      <el-descriptions-item :label="t('memory.confidence')">
        <el-progress :percentage="memory.confidence * 100" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.energy')">
        <el-progress :percentage="memory.energy * 100" :color="getEnergyColor(memory.energy)" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.accessCount')">
        {{ memory.access_count }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.validFrom')">
        {{ formatDateTime(memory.valid_start) }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.validTo')">
        {{ memory.valid_end ? formatDateTime(memory.valid_end) : t('memory.present') }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.keywords')">
        <el-tag v-for="keyword in memory.keywords" :key="keyword" size="small" style="margin-right: 4px">
          {{ keyword }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.source')">
        {{ memory.source_event_id || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('memory.createdAt')">
        {{ formatDateTime(memory.created_at) }}
      </el-descriptions-item>
    </el-descriptions>

    <!-- Actions -->
    <div v-if="editable" class="details-actions">
      <el-button type="primary" @click="handleSave" :loading="saving">
        {{ t('common.save') }}
      </el-button>
      <el-button @click="handleDelete" type="danger" :icon="Delete">
        {{ t('common.delete') }}
      </el-button>
      <el-button @click="handleClose">
        {{ t('common.cancel') }}
      </el-button>
    </div>

    <!-- History -->
    <div class="memory-history">
      <el-divider />
      <h4>{{ t('memory.history') }}</h4>
      <el-button text @click="showHistory = !showHistory">
        {{ showHistory ? t('common.hide') : t('common.show') }}
      </el-button>
      <div v-if="showHistory" class="history-content">
        <el-empty :description="t('memory.noHistory')" :image-size="40" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Lightning, Delete } from '@element-plus/icons-vue'
import type { MemoryEntry, UpdateMemoryParams } from '@/types/memory'
import { MemoryType } from '@/types/memory'

const props = defineProps<{
  memory: MemoryEntry | null
  editable: boolean
}>()

const emit = defineEmits<{
  save: [updates: UpdateMemoryParams]
  delete: []
  close: []
}>()

const localMemory = ref<MemoryEntry>({ ...props.memory } as MemoryEntry)
const saving = ref(false)
const showHistory = ref(false)
const isValidIndefinitely = ref(!props.memory?.valid_end)

const validStartDate = ref(props.memory?.valid_start ? new Date(props.memory.valid_start) : new Date())
const validEndDate = ref(props.memory?.valid_end ? new Date(props.memory.valid_end) : null)

watch(() => props.memory, (newMemory) => {
  if (newMemory) {
    localMemory.value = { ...newMemory }
    isValidIndefinitely.value = !newMemory.valid_end
    validStartDate.value = new Date(newMemory.valid_start)
    validEndDate.value = newMemory.valid_end ? new Date(newMemory.valid_end) : null
  }
}, { deep: true })

function getTypeTagType(type: MemoryType) {
  const types: Record<MemoryType, unknown> = {
    [MemoryType.FACT]: 'primary',
    [MemoryType.PREFERENCE]: 'success',
    [MemoryType.PROCEDURE]: 'warning',
    [MemoryType.CONTEXT]: 'info',
    [MemoryType.STRATEGY]: 'danger',
    [MemoryType.EPISODE]: ''
  }
  return types[type] || ''
}

function getEnergyColor(energy: number): string {
  if (energy > 0.7) return '#67C23A'
  if (energy > 0.4) return '#E6A23C'
  return '#F56C6C'
}

function formatDateTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function handleSave() {
  const updates: UpdateMemoryParams = {
    predicate: localMemory.value.predicate,
    object: localMemory.value.object,
    confidence: localMemory.value.confidence,
    energy: localMemory.value.energy,
    valid_end: isValidIndefinitely.value ? undefined : validEndDate.value?.toISOString(),
    keywords: localMemory.value.keywords
  }

  emit('save', updates)
}

function handleDelete() {
  emit('delete')
}

function handleClose() {
  emit('close')
}
</script>

<style scoped>
.memory-node-details {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.details-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.energy-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  color: var(--el-color-success);
}

.triple-display {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background-color: var(--el-fill-color-light);
  border-radius: 6px;
}

.triple-subject,
.triple-predicate,
.triple-object {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.triple-subject label,
.triple-predicate label,
.triple-object label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.triple-value {
  font-size: 14px;
  font-weight: 500;
  padding: 8px;
  background-color: var(--el-bg-color);
  border-radius: 4px;
}

.details-form {
  margin-top: 16px;
}

.value-display {
  margin-left: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.details-display {
  margin-top: 16px;
}

.details-actions {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-light);
}

.memory-history h4 {
  margin-bottom: 8px;
}

.history-content {
  margin-top: 12px;
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>
