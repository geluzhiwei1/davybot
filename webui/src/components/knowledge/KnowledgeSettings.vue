/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="knowledge-settings">
    <!-- 顶部提示 -->
    <el-alert :title="t('knowledge.title')" type="info" :closable="false" show-icon style="margin-bottom: 20px">
      <template #default>
        <p style="margin: 0; font-size: 13px;">
          {{ t('knowledge.description') }}
        </p>
      </template>
    </el-alert>

    <!-- 操作按钮 -->
    <div class="knowledge-actions">
      <!-- 知识库选择器 -->
      <KnowledgeBaseSelector
        v-model="selectedBaseId"
        @update:modelValue="handleBaseIdChange"
        @change="handleBaseChange"
        style="width: 300px;"
      />

      <el-button type="primary" :icon="Upload" @click="showUploadDialog">
        {{ t('knowledge.uploadDocument') }}
      </el-button>
      <el-button :icon="Setting" @click="showSettings">
        {{ t('knowledge.settings') }}
      </el-button>
      <el-button :icon="Refresh" @click="loadDocuments" :loading="isLoading">
        {{ t('knowledge.refresh') }}
      </el-button>
      <el-button :icon="Grid" @click="showBaseManager">
        管理知识库
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin: 20px 0;">
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <el-icon :size="28" color="#409EFF"><Document /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalDocuments }}</div>
              <div class="stat-label">{{ t('knowledge.totalDocuments') }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <el-icon :size="28" color="#67C23A"><Grid /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalChunks }}</div>
              <div class="stat-label">{{ t('knowledge.totalChunks') }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <el-icon :size="28" color="#E6A23C"><DataLine /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ stats.avgRelevance }}</div>
              <div class="stat-label">{{ t('knowledge.avgRelevance') }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-content">
            <el-icon :size="28" color="#F56C6C"><Clock /></el-icon>
            <div class="stat-info">
              <div class="stat-value">{{ stats.lastIndexed }}</div>
              <div class="stat-label">{{ t('knowledge.lastIndexed') }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 内部标签页 -->
    <el-tabs v-model="innerTab" type="border-card">
      <!-- 文档列表 -->
      <el-tab-pane :label="t('knowledge.documents')" name="documents">
        <!-- 搜索和过滤 -->
        <div class="search-bar">
          <el-input
            v-model="searchQuery"
            :placeholder="t('knowledge.searchPlaceholder')"
            :prefix-icon="Search"
            clearable
            style="width: 300px;"
          />
          <el-select v-model="filterType" :placeholder="t('knowledge.filterType')" style="width: 150px;">
            <el-option label="全部" value="all" />
            <el-option label="PDF" value="pdf" />
            <el-option label="DOCX" value="docx" />
            <el-option label="Text" value="text" />
            <el-option label="Markdown" value="markdown" />
          </el-select>
        </div>

        <!-- 文档表格 -->
        <el-table
          :data="filteredDocuments"
          v-loading="isLoading"
          :element-loading-text="t('knowledge.loading')"
          stripe
          height="calc(100vh - 500px)"
          style="width: 100%; margin-top: 16px;"
        >
          <el-table-column prop="file_name" :label="t('knowledge.fileName')" min-width="200" show-overflow-tooltip />
          <el-table-column prop="file_type" :label="t('knowledge.fileType')" width="100">
            <template #default="{ row }">
              <el-tag :type="getFileTypeColor(row.file_type)" size="small">
                {{ row.file_type?.toUpperCase() || '-' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_size" :label="t('knowledge.fileSize')" width="120">
            <template #default="{ row }">
              {{ formatFileSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column prop="chunk_count" :label="t('knowledge.chunks')" width="100" />
          <el-table-column prop="indexed_at" :label="t('knowledge.indexedAt')" width="180">
            <template #default="{ row }">
              {{ formatDate(row.indexed_at) }}
            </template>
          </el-table-column>
          <el-table-column :label="t('knowledge.actions')" width="260" fixed="right">
            <template #default="{ row }">
              <el-button size="small" :icon="View" @click="viewDocument(row)">
                {{ t('knowledge.view') }}
              </el-button>
              <el-button size="small" :icon="Refresh" @click="reindexDocument(row)">
                {{ t('knowledge.reindex') }}
              </el-button>
              <el-button size="small" type="danger" :icon="Delete" @click="deleteDocument(row)">
                {{ t('knowledge.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="totalCount"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          style="margin-top: 16px; justify-content: center;"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </el-tab-pane>

      <!-- 智能搜索 -->
      <el-tab-pane :label="t('knowledge.search')" name="search">
        <div class="rag-search">
          <!-- 查询输入 -->
          <div class="search-box">
            <el-input
              v-model="ragQuery"
              type="textarea"
              :rows="3"
              :placeholder="t('knowledge.ragQueryPlaceholder')"
              @keydown.enter.ctrl="handleRAGSearch"
            />
            <div class="search-controls">
              <el-select v-model="searchMode" :placeholder="t('knowledge.searchMode')" style="width: 150px;">
                <el-option label="Hybrid" value="hybrid" />
                <el-option label="Vector" value="vector" />
                <el-option label="Graph" value="graph" />
                <el-option label="Fulltext" value="fulltext" />
              </el-select>
              <el-input-number v-model="topK" :min="1" :max="20" :step="1" />
              <el-button type="primary" :icon="Search" @click="handleRAGSearch" :loading="isSearching">
                {{ t('knowledge.search') }}
              </el-button>
            </div>
          </div>

          <!-- 搜索结果 -->
          <div v-if="searchResults.length > 0" class="search-results">
            <div class="results-header">
              <h4>{{ t('knowledge.searchResults') }} ({{ searchResults.length }})</h4>
              <div class="results-stats">
                <el-tag size="small">Vector: {{ vectorCount }}</el-tag>
                <el-tag size="small" type="success">Graph: {{ graphCount }}</el-tag>
                <el-tag size="small" type="warning">Fulltext: {{ fulltextCount }}</el-tag>
                <el-tag size="small" type="info">{{ latency }}ms</el-tag>
              </div>
            </div>

            <div class="results-list">
              <div v-for="(result, index) in searchResults" :key="result.id" class="result-card">
                <div class="result-header">
                  <span class="result-rank">#{{ index + 1 }}</span>
                  <el-tag :type="getSourceTypeColor(result.source)" size="small">
                    {{ result.source?.toUpperCase() || '-' }}
                  </el-tag>
                  <span class="result-score">{{ (result.score * 100).toFixed(1) }}%</span>
                </div>
                <div class="result-content">
                  {{ result.content }}
                </div>
                <div class="result-actions">
                  <el-button size="small" text @click="copyContent(result)">
                    <el-icon><DocumentCopy /></el-icon>
                    {{ t('knowledge.copy') }}
                  </el-button>
                </div>
              </div>
            </div>
          </div>

          <!-- RAG上下文 -->
          <el-card v-if="ragContext" class="rag-context-card" shadow="never">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>{{ t('knowledge.ragContext') }}</span>
                <el-button size="small" :icon="DocumentCopy" @click="copyContext">
                  {{ t('knowledge.copyContext') }}
                </el-button>
              </div>
            </template>
            <el-input
              :model-value="ragContext"
              type="textarea"
              :rows="10"
              readonly
            />
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 上传文档对话框 -->
    <el-dialog
      v-model="uploadDialogVisible"
      :title="t('knowledge.uploadDocument')"
      width="600px"
    >
      <el-upload
        ref="uploadRef"
        class="upload-demo"
        drag
        :action="uploadActionUrl"
        :on-success="handleUploadSuccess"
        :on-error="handleUploadError"
        :before-upload="beforeUpload"
        :file-list="uploadFileList"
        multiple
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          {{ t('knowledge.uploadText') }}
        </div>
        <template #tip>
          <div class="el-upload__tip">
            {{ t('knowledge.uploadTip') }}
          </div>
        </template>
      </el-upload>
    </el-dialog>

    <!-- 文档预览对话框 -->
    <el-dialog
      v-model="previewDialogVisible"
      :title="previewDocument?.file_name"
      width="700px"
    >
      <div v-if="previewDocument" class="document-preview">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('knowledge.fileType')">
            <el-tag :type="getFileTypeColor(previewDocument.file_type)">
              {{ previewDocument.file_type?.toUpperCase() || '-' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('knowledge.fileSize')">
            {{ formatFileSize(previewDocument.file_size) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('knowledge.chunks')">
            {{ previewDocument.chunk_count }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('knowledge.indexedAt')">
            {{ formatDate(previewDocument.indexed_at) }}
          </el-descriptions-item>
        </el-descriptions>
        <el-divider />
        <el-input
          :model-value="previewContent"
          type="textarea"
          :rows="15"
          readonly
        />
      </div>
    </el-dialog>

    <!-- 设置对话框 -->
    <el-dialog
      v-model="settingsDialogVisible"
      :title="t('knowledge.settings')"
      width="500px"
    >
      <el-form :model="settings" label-width="140px">
        <el-form-item :label="t('knowledge.chunkSize')">
          <el-input-number v-model="settings.chunkSize" :min="100" :max="2000" :step="50" />
        </el-form-item>
        <el-form-item :label="t('knowledge.chunkOverlap')">
          <el-input-number v-model="settings.chunkOverlap" :min="0" :max="500" :step="10" />
        </el-form-item>
        <el-form-item :label="t('knowledge.embeddingModel')">
          <el-select v-model="settings.embeddingModel" style="width: 100%;">
            <el-option label="all-MiniLM-L6-v2 (384维)" value="minilm" />
            <el-option label="BGE-M3 (1024维)" value="bge-m3" />
            <el-option label="jina-embeddings-v4 (768维)" value="jina-v4" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('knowledge.chunkStrategy')">
          <el-select v-model="settings.chunkStrategy" style="width: 100%;">
            <el-option label="Fixed Size" value="fixed_size" />
            <el-option label="Recursive" value="recursive" />
            <el-option label="Semantic" value="semantic" />
            <el-option label="Markdown" value="markdown" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="settingsDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button type="primary" @click="saveSettings">
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 知识库管理对话框 -->
    <el-dialog
      v-model="baseManagerDialogVisible"
      title="知识库管理"
      width="90%"
      :close-on-click-modal="false"
    >
      <KnowledgeBaseManager @close="baseManagerDialogVisible = false" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload,
  Setting,
  Refresh,
  Search,
  View,
  Delete,
  DocumentCopy,
  Document,
  Grid,
  DataLine,
  Clock,
  UploadFilled
} from '@element-plus/icons-vue'
import { knowledgeApi, knowledgeBasesApi } from '@/services/api/knowledge'
import type { DocumentInfo, SearchResult, Stats, KnowledgeBase } from '@/types/knowledge'
import { logger } from '@/utils/logger'
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue'
import KnowledgeBaseManager from './KnowledgeBaseManager.vue'

const { t } = useI18n()

// Props
const props = defineProps<{
  workspaceId?: string
}>()

// 状态
const innerTab = ref('documents')
const isLoading = ref(false)
const searchQuery = ref('')
const filterType = ref('all')
const currentPage = ref(1)
const pageSize = ref(10)
const totalCount = ref(0)
const documents = ref<DocumentInfo[]>([])

// 知识库状态
const selectedBaseId = ref<string>('')
const currentBase = ref<KnowledgeBase | null>(null)
const uploadBaseId = ref<string>('')

// RAG搜索
const ragQuery = ref('')
const searchMode = ref('hybrid')
const topK = ref(5)
const isSearching = ref(false)
const searchResults = ref<SearchResult[]>([])
const vectorCount = ref(0)
const graphCount = ref(0)
const fulltextCount = ref(0)
const latency = ref(0)
const ragContext = ref('')

// 统计
const stats = ref<Stats>({
  totalDocuments: 0,
  totalChunks: 0,
  totalEntities: 0,
  avgRelevance: 0,
  lastIndexed: '-'
})

// 对话框
const uploadDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const settingsDialogVisible = ref(false)
const baseManagerDialogVisible = ref(false)
const previewDocument = ref<DocumentInfo | null>(null)
const previewContent = ref('')
const uploadFileList = ref([])

// 设置
const settings = ref({
  chunkSize: 512,
  chunkOverlap: 50,
  embeddingModel: 'minilm',
  chunkStrategy: 'recursive'
})

// 计算属性
const filteredDocuments = computed(() => {
  let filtered = documents.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(doc =>
      doc.file_name.toLowerCase().includes(query)
    )
  }

  if (filterType.value !== 'all') {
    filtered = filtered.filter(doc => doc.file_type === filterType.value)
  }

  return filtered
})

// 上传URL (根据选择的知识库动态变化)
const uploadActionUrl = computed(() => {
  if (uploadBaseId.value) {
    return `/api/knowledge/bases/${uploadBaseId.value}/documents/upload`
  }
  return '/api/knowledge/documents/upload'
})

// 方法
const loadDocuments = async () => {
  try {
    isLoading.value = true

    // 使用选中的知识库ID获取文档
    const response = await knowledgeApi.listDocuments(
      {
        skip: (currentPage.value - 1) * pageSize.value,
        limit: pageSize.value
      },
      selectedBaseId.value // 传递选中的知识库ID
    )

    documents.value = response.documents
    totalCount.value = response.total
  } catch (error) {
    logger.error('Failed to load documents:', error)
    ElMessage.error(t('knowledge.loadFailed'))
  } finally {
    isLoading.value = false
  }
}

const handleSizeChange = () => {
  currentPage.value = 1
  loadDocuments()
}

const handlePageChange = () => {
  loadDocuments()
}

const showUploadDialog = () => {
  // 初始化上传知识库ID为当前选择的知识库
  uploadBaseId.value = selectedBaseId.value
  uploadDialogVisible.value = true
}

const showSettings = () => {
  settingsDialogVisible.value = true
}

const showBaseManager = () => {
  baseManagerDialogVisible.value = true
}

const beforeUpload = (file: File) => {
  const isValidType = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'text/markdown'
  ].includes(file.type)

  if (!isValidType) {
    ElMessage.error(t('knowledge.invalidFileType'))
    return false
  }

  const isValidSize = file.size / 1024 / 1024 < 100
  if (!isValidSize) {
    ElMessage.error(t('knowledge.fileTooLarge'))
    return false
  }

  return true
}

const handleUploadSuccess = () => {
  ElMessage.success(t('knowledge.uploadSuccess'))
  loadDocuments()
}

const handleUploadError = () => {
  ElMessage.error(t('knowledge.uploadFailed'))
}

const viewDocument = async (doc: DocumentInfo) => {
  try {
    previewDocument.value = doc
    const response = await knowledgeApi.getDocument(doc.id, selectedBaseId.value)
    previewContent.value = response.content
    previewDialogVisible.value = true
  } catch (error) {
    logger.error('Failed to load document:', error)
    ElMessage.error(t('knowledge.loadDocumentFailed'))
  }
}

const reindexDocument = async (doc: DocumentInfo) => {
  try {
    await ElMessageBox.confirm(
      t('knowledge.reindexConfirm', { name: doc.file_name }),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    await knowledgeApi.reindexDocument(doc.id, selectedBaseId.value)
    ElMessage.success(t('knowledge.reindexSuccess'))
    loadDocuments()
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('Failed to reindex document:', error)
      ElMessage.error(t('knowledge.reindexFailed'))
    }
  }
}

const deleteDocument = async (doc: DocumentInfo) => {
  try {
    await ElMessageBox.confirm(
      t('knowledge.deleteConfirm', { name: doc.file_name }),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    await knowledgeApi.deleteDocument(doc.id, selectedBaseId.value)
    ElMessage.success(t('knowledge.deleteSuccess'))
    loadDocuments()
  } catch (error) {
    if (error !== 'cancel') {
      logger.error('Failed to delete document:', error)
      ElMessage.error(t('knowledge.deleteFailed'))
    }
  }
}

const handleRAGSearch = async () => {
  if (!ragQuery.value.trim()) {
    ElMessage.warning(t('knowledge.enterQuery'))
    return
  }

  try {
    isSearching.value = true
    const startTime = Date.now()

    const response = await knowledgeApi.search({
      query: ragQuery.value,
      mode: searchMode.value,
      top_k: topK.value
    })

    latency.value = Date.now() - startTime
    searchResults.value = response.results
    vectorCount.value = response.vector_count
    graphCount.value = response.graph_count
    fulltextCount.value = response.fulltext_count
  } catch (error) {
    logger.error('Search failed:', error)
    ElMessage.error(t('knowledge.searchFailed'))
  } finally {
    isSearching.value = false
  }
}

const copyContent = async (result: SearchResult) => {
  try {
    await navigator.clipboard.writeText(result.content)
    ElMessage.success(t('knowledge.copySuccess'))
  } catch (error) {
    ElMessage.error(t('knowledge.copyFailed'))
  }
}

const copyContext = async () => {
  try {
    await navigator.clipboard.writeText(ragContext.value)
    ElMessage.success(t('knowledge.copySuccess'))
  } catch (error) {
    ElMessage.error(t('knowledge.copyFailed'))
  }
}

const saveSettings = async () => {
  try {
    await knowledgeApi.updateSettings(settings.value)
    ElMessage.success(t('knowledge.settingsSaved'))
    settingsDialogVisible.value = false
  } catch (error) {
    logger.error('Failed to save settings:', error)
    ElMessage.error(t('knowledge.saveSettingsFailed'))
  }
}

// 工具函数
const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

const formatDate = (date: string | null) => {
  if (!date) return '-'
  return new Date(date).toLocaleString()
}

const getFileTypeColor = (type: string) => {
  const colors: Record<string, string> = {
    pdf: 'danger',
    docx: 'warning',
    text: 'success',
    markdown: 'info'
  }
  return colors[type] || ''
}

const getSourceTypeColor = (source: string) => {
  const colors: Record<string, string> = {
    vector: 'primary',
    graph: 'success',
    fulltext: 'warning',
    hybrid: 'info'
  }
  return colors[source] || ''
}

// 知识库切换处理
const handleBaseIdChange = async (baseId: string) => {
  logger.info('Knowledge base ID changed:', baseId)
  // 当知识库ID改变时，获取完整信息并重新加载文档
  if (baseId) {
    try {
      const base = await knowledgeBasesApi.getBase(baseId)
      currentBase.value = base
      await loadDocuments()
    } catch (error) {
      logger.error('Failed to load knowledge base:', error)
    }
  }
}

const handleBaseChange = async (base: KnowledgeBase) => {
  logger.info('Knowledge base changed:', base)
  currentBase.value = base
  // 重新加载文档列表
  await loadDocuments()
  ElMessage.success(`已切换到知识库: ${base.name}`)
}

// 生命周期
onMounted(() => {
  // 不在这里加载文档，等待知识库选择器自动选中默认知识库
  // 文档会在 handleBaseIdChange 中加载
})
</script>

<style scoped>
.knowledge-settings {
  padding: 20px;
}

.knowledge-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  cursor: pointer;
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-info {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.stat-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.search-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.rag-search {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.search-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.search-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.results-stats {
  display: flex;
  gap: 8px;
}

.result-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-fill-color-blank);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.result-rank {
  font-weight: 600;
  font-size: 14px;
}

.result-score {
  margin-left: auto;
  font-weight: 600;
  color: var(--el-color-primary);
}

.result-content {
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  margin-bottom: 12px;
  line-height: 1.6;
  font-size: 14px;
  max-height: 150px;
  overflow-y: auto;
}

.result-actions {
  display: flex;
  gap: 8px;
}

.rag-context-card {
  margin-top: 20px;
}

.upload-demo {
  text-align: center;
}
</style>
