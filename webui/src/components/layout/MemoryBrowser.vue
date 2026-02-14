/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="memory-browser">
    <!-- Search Bar -->
    <div class="search-bar">
      <el-input
        v-model="searchQueryInput"
        :placeholder="t('memory.searchPlaceholder')"
        :prefix-icon="Search"
        clearable
        @input="handleSearch"
        @clear="handleSearchClear"
      />
      <el-button :icon="Filter" @click="showFilters = !showFilters" circle />
    </div>

    <!-- Filters Panel -->
    <div v-if="showFilters" class="filters-panel">
      <el-form :model="localFilters" label-width="80px" size="small">
        <el-form-item :label="t('memory.type')">
          <el-select v-model="localFilters.type" @change="handleFilterChange">
            <el-option label="All" value="all" />
            <el-option label="Fact" value="fact" />
            <el-option label="Preference" value="preference" />
            <el-option label="Procedure" value="procedure" />
            <el-option label="Strategy" value="strategy" />
            <el-option label="Episode" value="episode" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('memory.minConfidence')">
          <el-slider v-model="localFilters.minConfidence" :min="0" :max="1" :step="0.1" />
        </el-form-item>

        <el-form-item :label="t('memory.minEnergy')">
          <el-slider v-model="localFilters.minEnergy" :min="0" :max="1" :step="0.1" />
        </el-form-item>

        <el-form-item>
          <el-checkbox v-model="localFilters.onlyValid">
            {{ t('memory.onlyValid') }}
          </el-checkbox>
        </el-form-item>
      </el-form>
    </div>

    <!-- View Mode Toggle -->
    <div class="view-mode-toggle">
      <el-radio-group v-model="localViewMode" size="small" @change="handleViewModeChange">
        <el-radio-button value="graph">
          <el-icon><Connection /></el-icon>
          <span>{{ t('memory.graphView') }}</span>
        </el-radio-button>
        <el-radio-button value="list">
          <el-icon><List /></el-icon>
          <span>{{ t('memory.listView') }}</span>
        </el-radio-button>
        <el-radio-button value="timeline">
          <el-icon><Clock /></el-icon>
          <span>{{ t('memory.timelineView') }}</span>
        </el-radio-button>
      </el-radio-group>
    </div>

    <!-- Stats Summary -->
    <div v-if="memoryStore.stats" class="stats-summary">
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item :label="t('memory.total')">
          {{ memoryStore.stats.total }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('memory.valid')">
          {{ memoryStore.validMemories.length }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('memory.archived')">
          {{ memoryStore.archivedMemories.length }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- Content Area -->
    <el-scrollbar class="content-area">
      <div v-loading="memoryStore.loading" class="content-container">
        <!-- Graph View -->
        <MemoryGraph
          v-if="localViewMode === 'graph'"
          :graph-data="memoryStore.graphData"
          :selected-id="memoryStore.selectedId"
          @select-node="handleSelectMemory"
        />

        <!-- List View -->
        <MemoryList
          v-else-if="localViewMode === 'list'"
          :memories="memoryStore.filteredMemories"
          :selected-id="memoryStore.selectedId"
          @select-memory="handleSelectMemory"
          @edit-memory="handleEditMemory"
          @delete-memory="handleDeleteMemory"
        />

        <!-- Timeline View -->
        <MemoryTimeline
          v-else-if="localViewMode === 'timeline'"
          :timeline-data="memoryStore.timelineData"
          @select-memory="handleSelectMemory"
        />

        <!-- Empty State -->
        <el-empty
          v-if="!memoryStore.loading && memoryStore.filteredMemories.length === 0"
          :description="t('memory.noMemories')"
          :image-size="80"
        />
      </div>
    </el-scrollbar>

    <!-- Action Buttons -->
    <div class="action-bar">
      <el-button :icon="Plus" @click="handleAddMemory" type="primary" size="small">
        {{ t('memory.addMemory') }}
      </el-button>
      <el-button :icon="MagicStick" @click="handleExtract" type="success" size="small">
        {{ t('memory.extract') }}
      </el-button>
      <el-dropdown @command="handleExport">
        <el-button :icon="Download" size="small">
          {{ t('memory.export') }}
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="json">JSON</el-dropdown-item>
            <el-dropdown-item command="csv">CSV</el-dropdown-item>
            <el-dropdown-item command="ndjson">NDJSON</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :icon="Refresh" @click="handleRefresh" size="small" />
    </div>

    <!-- Memory Details Drawer -->
    <el-drawer
      v-model="showDetails"
      :title="t('memory.memoryDetails')"
      direction="rtl"
      size="500px"
    >
      <MemoryNodeDetails
        v-if="memoryStore.selectedMemory"
        :memory="memoryStore.selectedMemory"
        :editable="true"
        @save="handleSaveMemory"
        @delete="handleDeleteMemory"
        @close="showDetails = false"
      />
    </el-drawer>

    <!-- Add Memory Dialog -->
    <el-dialog
      v-model="showAddDialog"
      :title="t('memory.addMemory')"
      width="500px"
    >
      <MemoryForm
        @submit="handleSubmitMemory"
        @cancel="showAddDialog = false"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMemoryStore } from '@/stores/memory'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Filter, Connection, List, Clock, Plus, Download, ArrowDown, Refresh, MagicStick
} from '@element-plus/icons-vue'
import MemoryGraph from './MemoryGraph.vue'
import MemoryList from './MemoryList.vue'
import MemoryTimeline from './MemoryTimeline.vue'
import MemoryNodeDetails from './MemoryNodeDetails.vue'
import MemoryForm from './MemoryForm.vue'
import type { MemoryFilters, ViewMode, CreateMemoryParams, UpdateMemoryParams } from '@/types/memory'

const props = defineProps<{
  workspaceId: string
}>()

const emit = defineEmits<{
  selectMemory: [memory: unknown]
}>()

const { t } = useI18n()
const memoryStore = useMemoryStore()

// Local state
const searchQueryInput = ref('')
const showFilters = ref(false)
const showDetails = ref(false)
const showAddDialog = ref(false)
const localViewMode = ref<ViewMode>('graph')
const localFilters = ref<MemoryFilters>({
  type: 'all',
  minConfidence: 0,
  minEnergy: 0,
  onlyValid: true
})

// Initialize
onMounted(async () => {
  await Promise.all([
    memoryStore.loadMemories(props.workspaceId),
    memoryStore.loadStats(props.workspaceId)
  ])

  // Load view-specific data
  if (localViewMode.value === 'graph') {
    await memoryStore.loadGraphData(props.workspaceId)
  } else if (localViewMode.value === 'timeline') {
    await memoryStore.loadTimelineData(props.workspaceId)
  }
})

// Sync with store
watch(localViewMode, async (newMode) => {
  memoryStore.setViewMode(newMode)

  // Load data based on view mode
  if (newMode === 'graph') {
    await memoryStore.loadGraphData(props.workspaceId)
  } else if (newMode === 'timeline') {
    await memoryStore.loadTimelineData(props.workspaceId)
  }
})

// Handlers
const handleSearch = () => {
  memoryStore.setSearchQuery(searchQueryInput.value)
}

const handleSearchClear = () => {
  searchQueryInput.value = ''
  memoryStore.setSearchQuery('')
}

const handleFilterChange = () => {
  memoryStore.setFilters(localFilters.value)
}

const handleViewModeChange = () => {
  // View mode change is handled by watcher
}

const handleSelectMemory = (memoryId: string) => {
  memoryStore.setSelected(memoryId)
  showDetails.value = true
  emit('selectMemory', memoryId)
}

const handleEditMemory = (memoryId: string) => {
  memoryStore.setSelected(memoryId)
  showDetails.value = true
}

const handleDeleteMemory = async (memoryId: string) => {
  try {
    await ElMessageBox.confirm(
      t('memory.deleteConfirm'),
      t('memory.deleteConfirmTitle'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    const success = await memoryStore.deleteMemory(props.workspaceId, memoryId)

    if (success) {
      ElMessage.success(t('memory.deleteSuccess'))
      showDetails.value = false
    }
  } catch (e: unknown) {
    if (e !== 'cancel') {
      ElMessage.error(e.message || t('memory.deleteError'))
    }
  }
}

const handleSaveMemory = async (updates: UpdateMemoryParams) => {
  if (!memoryStore.selectedId) return

  const success = await memoryStore.updateMemory(
    props.workspaceId,
    memoryStore.selectedId,
    updates
  )

  if (success) {
    ElMessage.success(t('memory.saveSuccess'))
    showDetails.value = false
  }
}

const handleAddMemory = () => {
  showAddDialog.value = true
}

const handleSubmitMemory = async (params: CreateMemoryParams) => {
  const result = await memoryStore.createMemory(props.workspaceId, params)

  if (result) {
    ElMessage.success(t('memory.addSuccess'))
    showAddDialog.value = false
  }
}

const handleExport = async (format: 'json' | 'csv' | 'ndjson') => {
  await memoryStore.exportMemories(props.workspaceId, format)
  ElMessage.success(t('memory.exportSuccess'))
}

const handleRefresh = async () => {
  await Promise.all([
    memoryStore.loadMemories(props.workspaceId),
    memoryStore.loadStats(props.workspaceId),
    memoryStore.loadGraphData(props.workspaceId),
    memoryStore.loadTimelineData(props.workspaceId)
  ])
  ElMessage.success(t('memory.refreshSuccess'))
}

const handleExtract = async () => {
  try {
    const result = await memoryStore.extractMemories(props.workspaceId)

    if (result.success && result.extracted > 0) {
      ElMessage.success(t('memory.extractSuccess', { count: result.extracted, method: result.method }))
    } else {
      ElMessage.warning(result.message || t('memory.extractEmpty'))
    }
  } catch {
    ElMessage.error(t('memory.extractError'))
  }
}
</script>

<style scoped>
.memory-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  gap: 12px;
}

.search-bar {
  display: flex;
  gap: 8px;
}

.search-bar .el-input {
  flex: 1;
}

.filters-panel {
  padding: 12px;
  background-color: var(--el-fill-color-light);
  border-radius: 6px;
}

.view-mode-toggle {
  display: flex;
  justify-content: center;
}

.stats-summary {
  margin-bottom: 8px;
}

.content-area {
  flex: 1;
  overflow: hidden;
}

.content-container {
  min-height: 300px;
}

.action-bar {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-light);
}

.action-bar .el-button {
  flex: 1;
}

.extract-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.extract-tip {
  color: var(--el-text-color-secondary);
  font-size: 14px;
  margin: 0;
}
</style>
