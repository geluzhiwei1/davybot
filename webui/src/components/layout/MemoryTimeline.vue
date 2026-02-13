/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="memory-timeline">
    <el-timeline>
      <el-timeline-item
        v-for="entry in timelineData"
        :key="entry.date"
        :timestamp="formatDate(entry.date)"
        placement="top"
        class="timeline-entry"
      >
        <el-card>
          <div class="timeline-date">{{ formatDateFull(entry.date) }}</div>
          <div class="timeline-memories">
            <div
              v-for="memory in entry.memories"
              :key="memory.id"
              class="timeline-memory"
              @click="handleMemoryClick(memory)"
            >
              <el-tag :type="getTypeTagType(memory.memory_type)" size="small">
                {{ memory.memory_type }}
              </el-tag>
              <span class="memory-text">
                <strong>{{ memory.subject }}</strong>
                {{ memory.predicate }}
                {{ memory.object }}
              </span>
              <el-tag
                v-if="memory.valid_end"
                type="info"
                size="small"
                class="expired-tag"
              >
                {{ t('memory.expired') }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>

    <el-empty
      v-if="timelineData.length === 0"
      :description="t('memory.noTimelineData')"
      :image-size="60"
    />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TimelineEntry } from '@/types/memory'
import { MemoryType } from '@/types/memory'

defineProps<{
  timelineData: TimelineEntry[]
}>()

const emit = defineEmits<{
  selectMemory: [memory: unknown]
}>()

const { t } = useI18n()

function handleMemoryClick(memory: unknown) {
  emit('selectMemory', memory.id)
}

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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString()
}

function formatDateFull(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}
</script>

<style scoped>
.memory-timeline {
  padding: 12px 0;
}

.timeline-entry {
  cursor: default;
}

.timeline-date {
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}

.timeline-memories {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline-memory {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.timeline-memory:hover {
  background-color: var(--el-fill-color-light);
}

.memory-text {
  flex: 1;
  font-size: 13px;
}

.expired-tag {
  opacity: 0.7;
}
</style>
