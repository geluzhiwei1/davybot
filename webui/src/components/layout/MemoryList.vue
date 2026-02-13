/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="memory-list">
    <el-table
      :data="memories"
      stripe
      highlight-current-row
      :current-row-key="selectedId"
      @row-click="handleRowClick"
      class="memory-table"
    >
      <el-table-column prop="subject" :label="t('memory.subject')" min-width="80" />
      <el-table-column prop="predicate" :label="t('memory.predicate')" min-width="80" />
      <el-table-column prop="object" :label="t('memory.object')" min-width="100" show-overflow-tooltip />
      <el-table-column :label="t('memory.type')" width="80">
        <template #default="{ row }">
          <el-tag :type="getTypeTagType(row.memory_type)" size="small">
            {{ row.memory_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('memory.energy')" width="70">
        <template #default="{ row }">
          <el-progress
            :percentage="row.energy * 100"
            :color="getEnergyColor(row.energy)"
            :show-text="false"
            :stroke-width="8"
          />
        </template>
      </el-table-column>
      <el-table-column :label="t('memory.confidence')" width="70">
        <template #default="{ row }">
          {{ (row.confidence * 100).toFixed(0) }}%
        </template>
      </el-table-column>
      <el-table-column :label="t('memory.valid')" width="100">
        <template #default="{ row }">
          <span :class="{ 'is-invalid': row.valid_end }">
            {{ formatDate(row.valid_start) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column :label="t('memory.actions')" width="80" fixed="right">
        <template #default="{ row }">
          <el-button
            :icon="Edit"
            type="primary"
            text
            size="small"
            @click.stop="handleEdit(row.id)"
          />
          <el-button
            :icon="Delete"
            type="danger"
            text
            size="small"
            @click.stop="handleDelete(row.id)"
          />
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="memories.length > pageSize"
      v-model:current-page="currentPage"
      :page-size="pageSize"
      :total="memories.length"
      layout="prev, pager, next"
      small
      class="pagination"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Edit, Delete } from '@element-plus/icons-vue'
import type { MemoryEntry } from '@/types/memory'
import { MemoryType } from '@/types/memory'

defineProps<{
  memories: MemoryEntry[]
  selectedId?: string | null
}>()

const emit = defineEmits<{
  selectMemory: [memoryId: string]
  editMemory: [memoryId: string]
  deleteMemory: [memoryId: string]
}>()

const { t } = useI18n()

const currentPage = ref(1)
const pageSize = ref(20)



function handleRowClick(row: MemoryEntry) {
  emit('selectMemory', row.id)
}

function handleEdit(id: string) {
  emit('editMemory', id)
}

function handleDelete(id: string) {
  emit('deleteMemory', id)
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

function getEnergyColor(energy: number): string {
  if (energy > 0.7) return '#67C23A'
  if (energy > 0.4) return '#E6A23C'
  return '#F56C6C'
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString()
}
</script>

<style scoped>
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.memory-table {
  font-size: 13px;
}

.memory-table :deep(.el-table__row) {
  cursor: pointer;
}

.memory-table :deep(.el-table__row.is-invalid) {
  color: var(--el-text-color-disabled);
  text-decoration: line-through;
}

.pagination {
  display: flex;
  justify-content: center;
}
</style>
