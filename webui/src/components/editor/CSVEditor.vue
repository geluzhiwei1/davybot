/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="csv-editor-container">
    <div class="csv-header">
      <div class="csv-info">
        <el-icon><Grid /></el-icon>
        <span class="row-count">{{ tableData.length }} 行</span>
        <el-divider direction="vertical" />
        <span class="column-count">{{ columns.length }} 列</span>
        <el-divider direction="vertical" />
        <el-tag v-if="isLargeFile" type="warning" size="small">大文件模式</el-tag>
      </div>
      <div class="csv-actions">
        <el-button size="small" @click="addRow" :icon="Plus">
          添加行
        </el-button>
        <el-button size="small" @click="exportCSV" :icon="Download">
          导出
        </el-button>
      </div>
    </div>

    <div class="csv-table-wrapper">
      <el-table
        :data="paginatedData"
        border
        stripe
        style="width: 100%"
        height="100%"
        :default-sort="{ prop: columns[0] || '', order: 'ascending' }"
        @cell-click="handleCellClick"
      >
      <el-table-column
        type="index"
        label="#"
        width="60"
        fixed
      />
      <el-table-column
        v-for="col in columns"
        :key="col"
        :prop="col"
        :label="col"
        sortable
        :width="120"
        show-overflow-tooltip
      >
        <template #default="{ row, $index }">
          <!-- 只在编辑模式显示输入框 -->
          <el-input
            v-if="isEditingCell($index, col)"
            v-model="row[col]"
            size="small"
            @blur="finishEditing"
            @keyup.enter="finishEditing"
            @keyup.esc="cancelEditing"
            ref="editInput"
            placeholder="输入内容"
          />
          <!-- 否则显示纯文本 -->
          <span v-else class="cell-content" @click="startEditing($index, col)">
            {{ row[col] || '' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        label="操作"
        width="80"
        fixed="right"
      >
        <template #default="{ $index }">
          <el-button
            size="small"
            type="danger"
            text
            @click="deleteRow($index)"
            :icon="Delete"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
      </el-table>

      <!-- 分页器 -->
      <div v-if="isLargeFile" class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[100, 500, 1000]"
          :total="tableData.length"
          layout="total, sizes, prev, pager, next, jumper"
          small
        />
      </div>
    </div>

    <div v-if="tableData.length === 0" class="empty-state">
      <el-empty description="CSV 文件为空或格式无效">
        <el-button type="primary" @click="addRow">添加第一行数据</el-button>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue'
import { ElTable, ElTableColumn, ElButton, ElInput, ElEmpty, ElIcon, ElDivider, ElMessage, ElPagination, ElTag } from 'element-plus'
import { Grid, Plus, Download, Delete } from '@element-plus/icons-vue'
import Papa from 'papaparse'

interface Props {
  modelValue: string
}

interface Emits {
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

interface TableRow {
  [key: string]: string
}

// 数据
const tableData = ref<TableRow[]>([])
const columns = ref<string[]>([])

// 编辑状态
const editingCell = ref<{ rowIndex: number; colName: string } | null>(null)
const editInput = ref<InstanceType<typeof ElInput>[]>([])

// 分页
const LARGE_FILE_THRESHOLD = 500 // 大文件阈值
const isLargeFile = computed(() => tableData.value.length > LARGE_FILE_THRESHOLD)
const currentPage = ref(1)
const pageSize = ref(100)

// 分页数据
const paginatedData = computed(() => {
  if (!isLargeFile.value) {
    return tableData.value
  }
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return tableData.value.slice(start, end)
})

// 使用 PapaParse 解析 CSV（带性能监控）
const parseCSV = (csvText: string) => {
  if (!csvText.trim()) {
    tableData.value = []
    columns.value = []
    return
  }

  const startTime = performance.now()

  Papa.parse(csvText, {
    header: true,
    skipEmptyLines: true,
    transformHeader: (header) => header.trim(),
    complete: (results) => {
      // 直接赋值，避免额外的map操作
      tableData.value = results.data as TableRow[]
      columns.value = results.meta.fields || []

      // 如果是大文件，自动启用分页
      if (isLargeFile.value) {
        ElMessage.info({
          message: `大文件已自动分页，共 ${tableData.value.length} 行`,
          duration: 2000
        })
      }
    },
    error: (error) => {
      console.error('[CSVEditor] Parse error:', error)
      ElMessage.error('CSV 解析失败: ' + error.message)
    }
  })
}

// 监听 modelValue 变化（添加防抖）
let parseTimer: number | null = null
watch(() => props.modelValue, (newValue) => {
  if (parseTimer) {
    clearTimeout(parseTimer)
  }
  parseTimer = window.setTimeout(() => {
    parseCSV(newValue)
  }, 100) // 100ms 防抖
}, { immediate: true })

// 判断单元格是否正在编辑
const isEditingCell = (rowIndex: number, colName: string): boolean => {
  return editingCell.value?.rowIndex === rowIndex && editingCell.value?.colName === colName
}

// 开始编辑单元格
const startEditing = async (rowIndex: number, colName: string) => {
  editingCell.value = { rowIndex, colName }
  await nextTick()
  // 自动聚焦输入框
  if (editInput.value && editInput.value[0]) {
    editInput.value[0].focus()
  }
}

// 完成编辑
const finishEditing = () => {
  if (editingCell.value) {
    // 使用防抖保存
    if (parseTimer) {
      clearTimeout(parseTimer)
    }
    parseTimer = window.setTimeout(() => {
      saveChanges()
    }, 300) // 300ms 防抖
  }
  editingCell.value = null
}

// 取消编辑
const cancelEditing = () => {
  editingCell.value = null
}

// 保存更改
const saveChanges = () => {
  const csv = unparseCSV()
  emit('update:modelValue', csv)
  emit('change', csv)
}

// 将表格数据转换为 CSV
const unparseCSV = (): string => {
  if (tableData.value.length === 0) return ''

  const startTime = performance.now()
  const csv = Papa.unparse(tableData.value, {
    quotes: false,  // 只在必要时加引号，提升性能
    delimiter: ',',
    header: true,
    newline: '\n'
  })
  return csv
}

// 添加新行
const addRow = () => {
  const newRow: TableRow = {}
  columns.value.forEach(col => {
    newRow[col] = ''
  })
  tableData.value.push(newRow)

  // 自动滚动到最后一行
  if (isLargeFile.value) {
    const totalPages = Math.ceil(tableData.value.length / pageSize.value)
    currentPage.value = totalPages
  }

  saveChanges()
  ElMessage.success('已添加新行')
}

// 删除行
const deleteRow = (index: number) => {
  // 如果是分页模式，需要计算实际索引
  const actualIndex = isLargeFile.value
    ? (currentPage.value - 1) * pageSize.value + index
    : index

  tableData.value.splice(actualIndex, 1)
  saveChanges()
  ElMessage.success('已删除行')
}

// 导出 CSV
const exportCSV = () => {
  const csv = unparseCSV()
  if (!csv) {
    ElMessage.warning('没有数据可导出')
    return
  }

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)
  link.setAttribute('href', url)
  link.setAttribute('download', `export_${Date.now()}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  ElMessage.success('CSV 导出成功')
}

// 处理单元格点击（已废弃，改用startEditing）
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const handleCellClick = (_row: TableRow, _column: unknown) => {
  // 点击事件现在由单元格内的span处理
}
</script>

<style scoped>
.csv-editor-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.csv-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color-light);
  flex-shrink: 0;
}

.csv-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.csv-info .el-icon {
  font-size: 16px;
}

.csv-actions {
  display: flex;
  gap: 8px;
}

.csv-table-wrapper {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

/* 单元格内容样式 */
.cell-content {
  display: block;
  width: 100%;
  height: 100%;
  padding: 8px 12px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background-color 0.2s;
}

.cell-content:hover {
  background-color: var(--el-fill-color-light);
}

/* 分页器容器 */
.pagination-container {
  padding: 8px 16px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-fill-color-lighter);
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

/* 表格样式优化 */
:deep(.el-table) {
  font-size: 13px;
  flex: 1;
}

:deep(.el-table th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

:deep(.el-table__body-wrapper) {
  overflow-y: auto;
}

:deep(.el-input__wrapper) {
  padding: 0;
}

:deep(.el-input__inner) {
  text-align: left;
}
</style>
