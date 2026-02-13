/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="export-panel">
    <el-card class="export-card" header="数据导出">
      <template #extra>
        <div class="export-status">
          <el-tag 
            v-if="exportStatus.type" 
            :type="exportStatus.type" 
            size="small"
          >
            {{ exportStatus.text }}
          </el-tag>
        </div>
      </template>

      <!-- 导出配置 -->
      <div class="export-config">
        <el-form :model="exportForm" :rules="exportRules" ref="exportFormRef" label-width="120px">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="导出格式" prop="format">
                <el-select v-model="exportForm.format" placeholder="选择导出格式">
                  <el-option label="JSON" value="json" />
                  <el-option label="CSV" value="csv" />
                  <el-option label="Excel (XLSX)" value="xlsx" />
                  <el-option label="PDF" value="pdf" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="导出类型" prop="exportType">
                <el-select v-model="exportForm.exportType" placeholder="选择导出类型">
                  <el-option label="完整报告" value="full" />
                  <el-option label="监控数据" value="metrics" />
                  <el-option label="执行记录" value="executions" />
                  <el-option label="告警记录" value="alerts" />
                  <el-option label="日志数据" value="logs" />
                  <el-option label="自定义" value="custom" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="24">
              <el-form-item label="时间范围" prop="timeRange">
                <el-date-picker
                  v-model="exportForm.timeRange"
                  type="datetimerange"
                  range-separator="至"
                  start-placeholder="开始时间"
                  end-placeholder="结束时间"
                  format="YYYY-MM-DD HH:mm:ss"
                  value-format="YYYY-MM-DD HH:mm:ss"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="包含数据">
                <el-checkbox-group v-model="exportForm.includeData">
                  <el-checkbox label="metrics">系统指标</el-checkbox>
                  <el-checkbox label="executions">执行记录</el-checkbox>
                  <el-checkbox label="logs">日志数据</el-checkbox>
                  <el-checkbox label="alerts">告警记录</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="图表类型">
                <el-checkbox-group v-model="exportForm.chartTypes">
                  <el-checkbox label="trend">趋势图</el-checkbox>
                  <el-checkbox label="performance">性能图</el-checkbox>
                  <el-checkbox label="error">错误分析图</el-checkbox>
                  <el-checkbox label="success">成功率图</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </el-col>
          </el-row>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="文件名前缀">
                <el-input 
                  v-model="exportForm.filenamePrefix" 
                  placeholder="导出文件名前缀"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="压缩选项">
                <el-select v-model="exportForm.compression" placeholder="选择压缩选项">
                  <el-option label="不压缩" value="none" />
                  <el-option label="ZIP压缩" value="zip" />
                  <el-option label="GZIP压缩" value="gzip" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          
          <!-- 自定义字段选择 -->
          <el-form-item v-if="exportForm.exportType === 'custom'" label="自定义字段">
            <el-transfer
              v-model="exportForm.customFields"
              :data="availableFields"
              :titles="['可用字段', '已选字段']"
              :props="{ key: 'key', label: 'label' }"
            />
          </el-form-item>
          
          <!-- 高级选项 -->
          <el-form-item>
            <el-collapse v-model="advancedOptions">
              <el-collapse-item title="高级选项" name="advanced">
                <el-row :gutter="20">
                  <el-col :span="8">
                    <el-form-item label="数据分片">
                      <el-input-number 
                        v-model="exportForm.chunkSize" 
                        :min="100"
                        :max="10000"
                        placeholder="每片数据量"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="并发数">
                      <el-input-number 
                        v-model="exportForm.concurrency" 
                        :min="1"
                        :max="10"
                        placeholder="并发导出数"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="超时时间">
                      <el-input-number 
                        v-model="exportForm.timeout" 
                        :min="30"
                        :max="600"
                        placeholder="超时时间(秒)"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>
                
                <el-row :gutter="20">
                  <el-col :span="12">
                    <el-form-item label="数据过滤">
                      <el-input 
                        v-model="exportForm.dataFilter" 
                        type="textarea"
                        :rows="3"
                        placeholder="JSON格式的过滤条件"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="排序字段">
                      <el-select v-model="exportForm.sortBy" placeholder="选择排序字段">
                        <el-option label="时间" value="timestamp" />
                        <el-option label="级别" value="level" />
                        <el-option label="状态" value="status" />
                        <el-option label="执行时长" value="duration" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                </el-row>
              </el-collapse-item>
            </el-collapse>
          </el-form-item>
        </el-form>
      </div>

      <!-- 导出预览 -->
      <div class="export-preview" v-if="previewData.length > 0">
        <h3 class="preview-title">数据预览 (前10条)</h3>
        <el-table :data="previewData" stripe max-height="200">
          <el-table-column
            v-for="column in previewColumns"
            :key="column.prop"
            :prop="column.prop"
            :label="column.label"
            :width="column.width"
          />
        </el-table>
      </div>

      <!-- 导出操作 -->
      <div class="export-actions">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-button 
              @click="previewExport"
              :disabled="!canPreview"
            >
              预览
            </el-button>
          </el-col>
          <el-col :span="8">
            <el-button 
              type="primary"
              @click="startExport"
              :disabled="!canExport || exporting"
              :loading="exporting"
            >
              {{ exporting ? '导出中...' : '开始导出' }}
            </el-button>
          </el-col>
          <el-col :span="8">
            <el-button 
              @click="saveTemplate"
              :disabled="!canSaveTemplate"
            >
              保存模板
            </el-button>
          </el-col>
        </el-row>
      </div>

      <!-- 导出进度 -->
      <div class="export-progress" v-if="exporting || exportProgress.total > 0">
        <el-progress 
          :percentage="exportProgress.percentage"
          :status="exportProgress.status"
        />
        <div class="progress-info">
          <p>{{ exportProgress.message }}</p>
          <p v-if="exportProgress.estimatedTime">
            预计剩余时间: {{ exportProgress.estimatedTime }}秒
          </p>
        </div>
      </div>

      <!-- 导出历史 -->
      <div class="export-history">
        <h3 class="history-title">导出历史</h3>
        <el-table :data="exportHistory" stripe max-height="200">
          <el-table-column prop="timestamp" label="导出时间" width="180">
            <template #default="{ row }">
              {{ formatTimestamp(row.timestamp, 'time') }}
            </template>
          </el-table-column>
          <el-table-column prop="format" label="格式" width="80" />
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="filename" label="文件名" />
          <el-table-column prop="size" label="大小" width="100">
            <template #default="{ row }">
              {{ formatFileSize(row.size) }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getExportStatusType(row.status)" size="small">
                {{ getExportStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button 
                v-if="row.status === 'completed'"
                size="small" 
                type="primary"
                @click="downloadExport(row)"
              >
                下载
              </el-button>
              <el-button 
                size="small" 
                type="danger"
                @click="deleteExport(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { formatTimestamp } from '@/utils/formatters'

// 状态
const exporting = ref(false)
// const showTemplateDialog = ref(false)
const previewData = ref<unknown[]>([])
const exportHistory = ref<Array<{
  id: string
  timestamp: string
  format: string
  type: string
  filename: string
  size: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  downloadUrl?: string
}>>([])

// 导出表单
const exportForm = ref({
  format: 'xlsx',
  exportType: 'full',
  timeRange: [] as string[],
  includeData: ['metrics', 'executions'],
  chartTypes: ['trend', 'performance'],
  filenamePrefix: `monitoring-export-${new Date().toISOString().split('T')[0]}`,
  compression: 'none',
  customFields: [] as string[],
  chunkSize: 1000,
  concurrency: 3,
  timeout: 300,
  dataFilter: '',
  sortBy: 'timestamp'
})

// 高级选项
const advancedOptions = ref(['advanced'])

// 导出进度
const exportProgress = ref({
  percentage: 0,
  status: 'success' as 'success' | 'exception' | 'warning',
  message: '',
  estimatedTime: 0,
  total: 0,
  current: 0
})

// 可用字段
const availableFields = ref([
  { key: 'timestamp', label: '时间戳' },
  { key: 'level', label: '级别' },
  { key: 'source', label: '来源' },
  { key: 'message', label: '消息' },
  { key: 'executionId', label: '执行ID' },
  { key: 'nodeId', label: '节点ID' },
  { key: 'duration', label: '执行时长' },
  { key: 'status', label: '状态' },
  { key: 'error', label: '错误信息' }
])

// 预览列
const previewColumns = computed(() => {
  if (previewData.value.length === 0) return []
  
  const firstRow = previewData.value[0]
  return Object.keys(firstRow).map(key => ({
    prop: key,
    label: availableFields.value.find(field => field.key === key)?.label || key,
    width: 150
  }))
})

// 导出状态
const exportStatus = computed(() => {
  if (exporting.value) {
    return { type: 'warning', text: '导出中' }
  }
  return { type: 'success', text: '就绪' }
})

// 是否可以预览
const canPreview = computed(() => {
  return exportForm.value.exportType && exportForm.value.timeRange.length === 2
})

// 是否可以导出
const canExport = computed(() => {
  return exportForm.value.format && 
         exportForm.value.exportType && 
         exportForm.value.timeRange.length === 2 &&
         exportForm.value.includeData.length > 0
})

// 是否可以保存模板
const canSaveTemplate = computed(() => {
  return exportForm.value.exportType === 'custom' && exportForm.value.customFields.length > 0
})

// 表单验证规则
const exportRules = {
  format: [
    { required: true, message: '请选择导出格式', trigger: 'change' }
  ],
  exportType: [
    { required: true, message: '请选择导出类型', trigger: 'change' }
  ],
  timeRange: [
    { required: true, message: '请选择时间范围', trigger: 'change' }
  ],
  includeData: [
    { required: true, message: '请至少选择一种数据类型', trigger: 'change' }
  ]
}

const exportFormRef = ref()

// 使用统一的格式化函数（从 @/utils/formatters 导入）

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 获取导出状态类型
const getExportStatusType = (status: string): string => {
  const types: Record<string, string> = {
    pending: 'info',
    processing: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return types[status] || 'info'
}

// 获取导出状态文本
const getExportStatusText = (status: string): string => {
  const texts: Record<string, string> = {
    pending: '等待中',
    processing: '处理中',
    completed: '已完成',
    failed: '失败'
  }
  return texts[status] || '未知'
}

// 预览导出
const previewExport = async () => {
  try {
    // 模拟预览数据
    previewData.value = [
      {
        timestamp: new Date().toISOString(),
        level: 'info',
        source: 'system',
        message: '系统启动完成',
        executionId: 'exec-001',
        nodeId: 'node-001',
        duration: 1500,
        status: 'completed'
      },
      {
        timestamp: new Date(Date.now() - 60000).toISOString(),
        level: 'warning',
        source: 'task',
        message: '任务执行超时',
        executionId: 'exec-002',
        nodeId: 'node-002',
        duration: 30000,
        status: 'failed'
      },
      {
        timestamp: new Date(Date.now() - 120000).toISOString(),
        level: 'error',
        source: 'node',
        message: '节点处理失败',
        executionId: 'exec-003',
        nodeId: 'node-003',
        duration: 5000,
        status: 'failed',
        error: 'Connection timeout'
      }
    ]
    
    ElMessage.success('预览数据已生成')
  } catch {
    ElMessage.error('预览失败')
  }
}

// 开始导出
const startExport = async () => {
  if (!exportFormRef.value) return
  
  try {
    await exportFormRef.value.validate()
    
    exporting.value = true
    exportProgress.value = {
      percentage: 0,
      status: 'success',
      message: '准备导出数据...',
      estimatedTime: 0,
      total: 100,
      current: 0
    }

    
    // 模拟导出过程
    const startTime = Date.now()
    const totalSteps = 100
    
    for (let i = 0; i <= totalSteps; i += 10) {
      await new Promise(resolve => setTimeout(resolve, 100))
      
      exportProgress.value = {
        percentage: i,
        status: 'success',
        message: `导出进度: ${i}%`,
        estimatedTime: Math.round((totalSteps - i) * (Date.now() - startTime) / 1000 / i),
        total: totalSteps,
        current: i
      }
    }
    
    // 模拟完成
    const fileSize = Math.floor(Math.random() * 10000000) + 1000000
    const downloadUrl = URL.createObjectURL(new Blob(['mock data']))
    
    // 添加到历史记录
    exportHistory.value.unshift({
      id: `export-${Date.now()}`,
      timestamp: new Date().toISOString(),
      format: exportForm.value.format,
      type: exportForm.value.exportType,
      filename: `${exportForm.value.filenamePrefix}.${exportForm.value.format}`,
      size: fileSize,
      status: 'completed',
      downloadUrl
    })
    
    // 限制历史记录数量
    if (exportHistory.value.length > 50) {
      exportHistory.value = exportHistory.value.slice(0, 50)
    }
    
    exportProgress.value = {
      percentage: 100,
      status: 'success',
      message: '导出完成！',
      estimatedTime: 0,
      total: totalSteps,
      current: totalSteps
    }
    
    ElMessage.success('数据导出完成')
    
    // 自动下载
    const a = document.createElement('a')
    a.href = downloadUrl
    a.download = `${exportForm.value.filenamePrefix}.${exportForm.value.format}`
    a.click()
    URL.revokeObjectURL(downloadUrl)
    
    exporting.value = false
  } catch {
    exporting.value = false
    exportProgress.value = {
      percentage: 0,
      status: 'exception',
      message: '导出失败',
      estimatedTime: 0,
      total: 0,
      current: 0
    }
    ElMessage.error('导出失败')
  }
}

// 保存模板
const saveTemplate = async () => {
  try {
    const template = {
      name: exportForm.value.filenamePrefix,
      format: exportForm.value.format,
      exportType: exportForm.value.exportType,
      includeData: exportForm.value.includeData,
      chartTypes: exportForm.value.chartTypes,
      customFields: exportForm.value.customFields,
      compression: exportForm.value.compression,
      chunkSize: exportForm.value.chunkSize,
      concurrency: exportForm.value.concurrency,
      timeout: exportForm.value.timeout,
      dataFilter: exportForm.value.dataFilter,
      sortBy: exportForm.value.sortBy,
      createdAt: new Date().toISOString()
    }
    
    // 保存到本地存储
    const templates = JSON.parse(localStorage.getItem('export-templates') || '[]')
    templates.push(template)
    localStorage.setItem('export-templates', JSON.stringify(templates))
    
    ElMessage.success('模板已保存')
  } catch {
    ElMessage.error('保存模板失败')
  }
}

// 下载导出
const downloadExport = (exportRecord: unknown) => {
  if (exportRecord.downloadUrl) {
    const a = document.createElement('a')
    a.href = exportRecord.downloadUrl
    a.download = exportRecord.filename
    a.click()
  }
}

// 删除导出记录
const deleteExport = async (exportRecord: unknown) => {
  try {
    await ElMessageBox.confirm('确定要删除此导出记录吗？', '确认删除', {
      type: 'warning'
    })
    
    const index = exportHistory.value.findIndex(item => item.id === exportRecord.id)
    if (index !== -1) {
      exportHistory.value.splice(index, 1)
    }
    
    ElMessage.success('导出记录已删除')
  } catch {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  // 加载导出历史
  const savedHistory = localStorage.getItem('export-history')
  if (savedHistory) {
    exportHistory.value = JSON.parse(savedHistory)
  }
})
</script>

<style scoped>
.export-panel {
  height: 100%;
}

.export-card {
  height: 100%;
}

.export-status {
  display: flex;
  align-items: center;
}

.export-config {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f8f9fa;
  border-radius: 4px;
}

.export-preview {
  margin-bottom: 20px;
}

.preview-title {
  margin: 0 0 15px 0;
  font-size: 16px;
  font-weight: bold;
  color: #303133;
}

.export-actions {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.export-progress {
  margin-bottom: 20px;
  padding: 20px;
  background-color: #f0f9ff;
  border-radius: 4px;
}

.progress-info {
  margin-top: 10px;
  font-size: 14px;
  color: #606266;
}

.progress-info p {
  margin: 5px 0;
}

.export-history {
  padding: 20px;
}

.history-title {
  margin: 0 0 15px 0;
  font-size: 16px;
  font-weight: bold;
  color: #303133;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .export-config .el-col {
    margin-bottom: 15px;
  }
  
  .export-actions .el-col {
    margin-bottom: 15px;
  }
  
  .export-preview {
    margin-bottom: 15px;
  }
  
  .export-progress {
    margin-bottom: 15px;
  }
}
</style>