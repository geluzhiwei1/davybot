<template>
  <div class="knowledge-base-manager">
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-button type="primary" :icon="Plus" @click="handleCreate">新建知识库</el-button>
      <el-button :icon="Refresh" @click="loadBases" :loading="loading">刷新</el-button>
    </div>

    <!-- 知识库列表 -->
    <el-table :data="knowledgeBases" v-loading="loading" stripe>
      <el-table-column prop="name" label="名称" min-width="200">
        <template #default="{ row }">
          <div class="base-name">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_default" type="success" size="small" style="margin-left: 8px">
              默认
            </el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="description" label="描述" min-width="250" show-overflow-tooltip />

      <el-table-column label="领域" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.settings.domain" type="info" size="small">
            {{ getDomainLabel(row.settings.domain) }}
          </el-tag>
          <span v-else style="color: var(--el-text-color-placeholder); font-size: 12px">未设置</span>
        </template>
      </el-table-column>

      <el-table-column label="统计" width="200">
        <template #default="{ row }">
          <div class="stats">
            <div>{{ row.stats.total_documents }} 文档</div>
            <div>{{ row.stats.total_chunks }} 文档块</div>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column prop="updated_at" label="更新时间" width="180">
        <template #default="{ row }">
          {{ formatDate(row.updated_at) }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :icon="Upload" @click="handleUpload(row)">
            上传
          </el-button>
          <el-button v-if="!row.is_default" link type="primary" size="small" @click="handleSetDefault(row)">
            设为默认
          </el-button>
          <el-button link type="primary" size="small" @click="handleEdit(row)">
            设置
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog id="knowledge-base-create-edit" v-model="showCreateDialog" :title="editingBase ? '知识库设置' : '创建知识库'"
      width="720px" top="5vh">
      <el-form :model="formData" label-width="130px" label-position="right">
        <el-form-item label="名称" required>
          <el-input v-model="formData.name" placeholder="输入知识库名称" maxlength="100" show-word-limit />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="formData.description" type="textarea" placeholder="输入知识库描述" :rows="2" maxlength="500"
            show-word-limit />
        </el-form-item>

        <el-form-item label="知识领域">
          <el-select v-model="formData.settings!.domain" style="width: 100%" placeholder="选择知识领域（可选）" clearable>
            <el-option v-for="domain in domainOptions" :key="domain.value" :label="domain.label" :value="domain.value">
              <span>{{ domain.label }}</span>
              <span v-if="domain.description"
                style="color: var(--el-text-color-secondary); font-size: 12px; margin-left: 8px">
                {{ domain.description }}
              </span>
            </el-option>
          </el-select>
          <div class="form-item-tip">选择知识领域将启用领域特定的知识图谱和实体抽取</div>
        </el-form-item>

        <el-form-item v-if="!editingBase" label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>

        <el-divider content-position="left">检索模式</el-divider>

        <el-form-item label="默认检索模式">
          <el-select v-model="formData.settings!.default_mode" style="width: 100%">
            <el-option label="混合检索 (推荐)" value="hybrid" />
            <el-option label="仅向量检索" value="vector" />
            <el-option label="仅全文检索" value="fulltext" />
            <el-option label="仅图谱检索" value="graph" />
          </el-select>
        </el-form-item>

        <!-- 分类设置 Tabs -->
        <el-tabs v-model="settingsTab" type="border-card" class="settings-tabs">
          <!-- 文件目录设置 (在通用设置之前) -->
          <el-tab-pane label="文件目录" name="directory">
            <el-form-item label="文档目录路径">
              <div style="display: flex; gap: 8px; width: 100%">
                <el-input v-model="formData.settings!.watch_dir" placeholder="输入或粘贴目录路径, 如 /home/user/docs" />
                <el-button @click="handleScanDir" :loading="scanning" :disabled="!formData.settings!.watch_dir">
                  扫描
                </el-button>
              </div>
              <div class="form-item-tip">监视此目录, 开启"启用目录监视"后, 服务端每60秒自动同步新文件</div>
            </el-form-item>

            <el-form-item label="启用目录监视">
              <el-switch v-model="formData.settings!.watch_enabled" />
              <div class="form-item-tip">启用后, 目录中的新文件将自动同步到知识库 (服务端每60秒轮询一次)</div>
            </el-form-item>

            <el-form-item label="包含子目录">
              <el-switch v-model="formData.settings!.watch_recursive" />
              <div class="form-item-tip">是否递归监视子目录中的文件</div>
            </el-form-item>

            <el-form-item label="监视文件类型">
              <el-select v-model="formData.settings!.watch_extensions" multiple style="width: 100%"
                placeholder="选择要监视的文件类型">
                <el-option label="Markdown (.md)" value=".md" />
                <el-option label="Markdown (.markdown)" value=".markdown" />
              </el-select>
              <div class="form-item-tip">仅同步所选类型的文件到知识库</div>
            </el-form-item>

            <!-- 扫描结果 -->
            <div v-if="scanResult" class="scan-result-section">
              <el-divider content-position="left">
                扫描结果
                <el-tag size="small" style="margin-left: 8px">{{ scanResult.total }} 个文件</el-tag>
              </el-divider>

              <div v-if="scanResult.dir_path" class="scan-summary">
                <el-tag type="info" size="small">{{ scanResult.dir_path }}</el-tag>
                <el-tag type="success" size="small" style="margin-left: 8px">已入库: {{ scanResult.existing_count
                }}</el-tag>
                <el-tag type="warning" size="small" style="margin-left: 8px">待同步: {{ scanResult.new_count }}</el-tag>
              </div>

              <el-table v-if="scanResult.files.length > 0" :data="scanResult.files" stripe size="small" max-height="300"
                style="margin-top: 12px">
                <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip />
                <el-table-column prop="extension" label="类型" width="80">
                  <template #default="{ row }">
                    <el-tag size="small">{{ row.extension?.toUpperCase() }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="size" label="大小" width="100">
                  <template #default="{ row }">
                    {{ formatFileSize(row.size) }}
                  </template>
                </el-table-column>
                <el-table-column label="相对路径" min-width="200" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="file-path">{{ row.relative_path }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.exists_in_kb ? 'success' : 'warning'" size="small">
                      {{ row.exists_in_kb ? '已入库' : '待同步' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>

              <div v-if="scanResult.files.length > 0 && editingBase" class="scan-actions">
                <el-button type="primary" @click="handleSyncFromDir(false)" :loading="syncing"
                  :disabled="scanResult.new_count === 0">
                  同步新文件 ({{ scanResult.new_count }})
                </el-button>
                <el-button type="danger" @click="handleSyncFromDir(true)" :loading="syncing">
                  重建全部
                </el-button>
                <span v-if="syncing" class="sync-progress-text" style="margin-left: 12px; font-size: 13px; color: #909399;">
                  {{ syncProgress.toFixed(0) }}% ({{ syncProcessedFiles }}/{{ syncTotalFiles }})
                  <span v-if="syncCurrentFile"> - {{ syncCurrentFile }}</span>
                </span>
              </div>
              <div v-if="scanResult.files.length > 0 && !editingBase" class="scan-actions">
                <el-tag type="info">创建知识库后将自动同步这些文件</el-tag>
              </div>
            </div>
          </el-tab-pane>

          <!-- 通用/分块设置 -->
          <el-tab-pane label="通用设置" name="general">
            <el-form-item label="分块策略">
              <el-select v-model="formData.settings!.chunk_strategy" style="width: 100%">
                <el-option label="递归分块 (推荐)" value="recursive" />
                <el-option label="固定大小" value="fixed_size" />
                <el-option label="语义分块" value="semantic" />
                <el-option label="Markdown" value="markdown" />
              </el-select>
            </el-form-item>

            <el-form-item label="分块大小">
              <el-input-number v-model="formData.settings!.chunk_size" :min="100" :max="10000" :step="100"
                style="width: 100%" />
              <div class="form-item-tip">每个文档块的字符数 (100-10000)</div>
            </el-form-item>

            <el-form-item label="分块重叠">
              <el-input-number v-model="formData.settings!.chunk_overlap" :min="0" :max="1000" :step="50"
                style="width: 100%" />
              <div class="form-item-tip">相邻块之间的重叠字符数</div>
            </el-form-item>

            <el-form-item label="默认返回数量">
              <el-input-number v-model="formData.settings!.default_top_k" :min="1" :max="50" :step="1"
                style="width: 100%" />
              <div class="form-item-tip">检索时默认返回的结果数量</div>
            </el-form-item>

            <el-form-item label="自动重建索引">
              <el-switch v-model="formData.settings!.auto_reindex" />
              <div class="form-item-tip">文档变更时自动重建索引</div>
            </el-form-item>
          </el-tab-pane>

          <!-- 向量检索设置 -->
          <el-tab-pane label="向量检索" name="vector">
            <el-form-item label="嵌入模型">
              <el-select v-model="formData.settings!.embedding_model" style="width: 100%" @change="handleModelChange">
                <el-option label="Qwen3-Embedding (默认, 1024维)" value="qwen3-embedding" />
                <el-option label="MiniLM (快速, 384维)" value="minilm" />
                <el-option label="BGE-M3 (高质量, 1024维)" value="bge-m3" />
                <el-option label="BGE-Large-zh (中文优化, 1024维)" value="bge-large-zh" />
                <el-option label="Jina-V4 (多语言, 768维)" value="jina-v4" />
                <el-option label="OpenAI Ada-3 (API, 3072维)" value="text-embedding-3-large" />
              </el-select>
            </el-form-item>

            <el-form-item label="向量维度">
              <el-input-number v-model="formData.settings!.embedding_dimension" :min="128" :max="4096" :step="64"
                style="width: 100%" disabled />
              <div class="form-item-tip">由嵌入模型自动决定</div>
            </el-form-item>

            <el-form-item label="向量检索权重">
              <el-slider v-model="formData.settings!.vector_weight" :min="0" :max="1" :step="0.05"
                :format-tooltip="(val: number) => (val * 100).toFixed(0) + '%'" show-input :show-input-controls="false"
                input-size="small" />
              <div class="form-item-tip">混合检索时向量检索的权重占比</div>
            </el-form-item>
          </el-tab-pane>

          <!-- 全文检索设置 -->
          <el-tab-pane label="全文检索" name="fulltext">
            <el-form-item label="启用全文检索">
              <el-switch v-model="formData.settings!.enable_fulltext" />
              <div class="form-item-tip">基于关键词的全文搜索引擎</div>
            </el-form-item>

            <el-form-item label="全文检索权重">
              <el-slider v-model="formData.settings!.fulltext_weight" :min="0" :max="1" :step="0.05"
                :format-tooltip="(val: number) => (val * 100).toFixed(0) + '%'" show-input :show-input-controls="false"
                input-size="small" :disabled="!formData.settings!.enable_fulltext" />
              <div class="form-item-tip">混合检索时全文检索的权重占比</div>
            </el-form-item>
          </el-tab-pane>

          <!-- 知识图谱设置 -->
          <el-tab-pane label="知识图谱" name="graph">
            <el-form-item label="启用知识图谱">
              <el-switch v-model="formData.settings!.enable_graph" />
              <div class="form-item-tip">从文档中抽取实体和关系, 构建知识图谱</div>
            </el-form-item>

            <el-form-item label="知识抽取策略">
              <el-select v-model="formData.settings!.extraction_strategy" style="width: 100%"
                :disabled="!formData.settings!.enable_graph">
                <el-option label="基于规则 (快速)" value="rule_based" />
                <el-option label="LLM (高质量)" value="llm" />
                <el-option label="NER模型" value="ner_model" />
                <el-option label="自动选择" value="auto" />
              </el-select>
              <div class="form-item-tip">从文本中抽取实体和关系的策略</div>
            </el-form-item>

            <el-form-item v-if="formData.settings!.extraction_strategy === 'llm'" label="抽取LLM配置">
              <el-select v-model="formData.settings!.extraction_llm_config" style="width: 100%"
                :disabled="!formData.settings!.enable_graph" clearable
                placeholder="使用默认LLM配置">
                <el-option v-for="cfg in llmConfigOptions" :key="cfg.llm_id" :label="`${cfg.llm_id} (${cfg.model_id})`" :value="cfg.llm_id" />
              </el-select>
              <div class="form-item-tip">选择用于知识抽取的LLM配置，留空则使用系统默认配置</div>
            </el-form-item>

            <el-form-item label="图谱检索权重">
              <el-slider v-model="formData.settings!.graph_weight" :min="0" :max="1" :step="0.05"
                :format-tooltip="(val: number) => (val * 100).toFixed(0) + '%'" show-input :show-input-controls="false"
                input-size="small" :disabled="!formData.settings!.enable_graph" />
              <div class="form-item-tip">混合检索时知识图谱的权重占比</div>
            </el-form-item>
          </el-tab-pane>
        </el-tabs>

        <!-- 权重提示 -->
        <div v-if="showWeightWarning" class="weight-warning">
          <el-alert type="warning" :closable="false" show-icon>
            <template #title>
              检索权重总和为 {{ weightSumDisplay }}, 建议调整为 100%
            </template>
          </el-alert>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          {{ editingBase ? '保存设置' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 上传文档对话框 -->
    <el-dialog v-model="uploadDialogVisible" :title="'上传文档 - ' + uploadBaseName" width="600px">
      <el-upload ref="uploadRef" class="upload-demo" drag :action="uploadActionUrl" :on-success="handleUploadSuccess"
        :on-error="handleUploadError" :before-upload="beforeUpload" :file-list="uploadFileList" multiple>
        <el-icon class="el-icon--upload">
          <UploadFilled />
        </el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或点击上传
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 Markdown (.md) 文件，单文件不超过 100MB
          </div>
        </template>
      </el-upload>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, UploadFilled, Plus, Refresh } from '@element-plus/icons-vue'
import { knowledgeBasesApi, knowledgeApi } from '@/services/api/knowledge'
import type {
  KnowledgeBase,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KnowledgeBaseStatus,
  KnowledgeBaseSettings,
  DomainOption
} from '@/types/knowledge'

interface ScanFileInfo {
  name: string
  path: string
  relative_path: string
  size: number
  extension: string
  modified_at: number
  exists_in_kb: boolean
}

interface ScanResult {
  files: ScanFileInfo[]
  total: number
  dir_path: string
  existing_count: number
  new_count: number
  message?: string
}

const emit = defineEmits<{
  'documents-changed': []
}>()

const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreateDialog = ref(false)
const editingBase = ref<KnowledgeBase | null>(null)
const settingsTab = ref('general')
const domainOptions = ref<DomainOption[]>([])
const llmConfigOptions = ref<Array<{ llm_id: string; model_id: string }>>([])

// 文件目录状态
const scanning = ref(false)
const syncing = ref(false)
const syncProgress = ref(0)
const syncCurrentFile = ref('')
const syncTotalFiles = ref(0)
const syncProcessedFiles = ref(0)
let syncPollTimer: ReturnType<typeof setInterval> | null = null
const scanResult = ref<ScanResult | null>(null)

// 上传状态
const uploadDialogVisible = ref(false)
const uploadBaseId = ref('')
const uploadBaseName = ref('')
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const uploadFileList = ref<any[]>([])

const uploadActionUrl = computed(() => {
  if (uploadBaseId.value) {
    return `/api/knowledge/bases/by-id/${uploadBaseId.value}/documents/upload`
  }
  return '/api/knowledge/documents/upload'
})

// 嵌入模型 → 向量维度映射
const MODEL_DIMENSION_MAP: Record<string, number> = {
  'qwen3-embedding': 1024,
  'minilm': 384,
  'bge-m3': 1024,
  'bge-large-zh': 1024,
  'jina-v4': 768,
  'text-embedding-3-large': 3072,
}

const handleModelChange = (model: string) => {
  if (formData.value.settings) {
    formData.value.settings.embedding_dimension = MODEL_DIMENSION_MAP[model] ?? 1024
  }
}

const formData = ref<KnowledgeBaseCreate & { settings?: KnowledgeBaseSettings }>({
  name: '',
  description: '',
  settings: {
    watch_dir: '',
    watch_enabled: false,
    watch_recursive: true,
    watch_extensions: ['.md', '.markdown'],
    chunk_size: 1000,
    chunk_overlap: 200,
    chunk_strategy: 'recursive',
    embedding_model: 'qwen3-embedding',
    embedding_dimension: 1024,
    default_top_k: 5,
    default_mode: 'hybrid',
    vector_weight: 0.5,
    graph_weight: 0.3,
    fulltext_weight: 0.2,
    extraction_strategy: 'llm',
    extraction_llm_config: '',
    enable_graph: true,
    enable_fulltext: true,
    auto_reindex: false,
    domain: undefined,
  },
  is_default: false
})

// 权重总和计算
const weightSum = computed(() => {
  const s = formData.value.settings
  if (!s) return 0
  return Math.round((s.vector_weight + s.graph_weight + s.fulltext_weight) * 100) / 100
})

const weightSumDisplay = computed(() => {
  return (weightSum.value * 100).toFixed(0) + '%'
})

const showWeightWarning = computed(() => {
  return Math.abs(weightSum.value - 1.0) > 0.05
})

const loadBases = async () => {
  loading.value = true
  try {
    const response = await knowledgeBasesApi.listBases()
    knowledgeBases.value = response.items
  } catch (error) {
    ElMessage.error('加载知识库列表失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const loadDomains = async () => {
  try {
    const domains = await knowledgeApi.listDomains()
    domainOptions.value = domains
  } catch (error) {
    console.error('Failed to load domains:', error)
  }
}

const loadLLMConfigs = async () => {
  try {
    const result = await knowledgeApi.listLLMConfigs()
    llmConfigOptions.value = result.configs || []
  } catch (error) {
    console.error('Failed to load LLM configs:', error)
    llmConfigOptions.value = []
  }
}

const getDomainLabel = (domainValue: string | undefined) => {
  if (!domainValue) return '未设置'
  const domain = domainOptions.value.find(d => d.value === domainValue)
  return domain?.label || domainValue
}

// 文件目录操作
const handleScanDir = async () => {
  if (!formData.value.settings?.watch_dir) {
    ElMessage.warning('请先输入文档目录路径')
    return
  }

  scanning.value = true
  try {
    let result: ScanResult
    if (editingBase.value) {
      // 编辑已有知识库 — 用 base_id 相关的扫描 API
      result = await knowledgeBasesApi.scanDir(editingBase.value.id, formData.value.settings.watch_dir)
    } else {
      // 创建新知识库 — 用独立扫描 API（不需要 base_id)
      result = await knowledgeBasesApi.scanDirStandalone(
        formData.value.settings.watch_dir,
        formData.value.settings.watch_recursive,
      )
    }
    scanResult.value = result
    if (result.total === 0) {
      ElMessage.info(result.message || '目录中没有找到支持的文件')
    } else if (editingBase.value && formData.value.settings?.watch_enabled && result.new_count > 0) {
      // Auto-sync when watch_enabled and there are new files
      await handleSyncFromDir(false)
      return
    }
  } catch (error: unknown) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const err = error as any
    ElMessage.error(err.response?.data?.detail || '扫描目录失败')
    scanResult.value = null
  } finally {
    scanning.value = false
  }
}

const handleSyncFromDir = async (forceRebuild: boolean) => {
  if (!editingBase.value) return

  const action = forceRebuild ? '重建全部' : '同步新文件'
  try {
    await ElMessageBox.confirm(
      forceRebuild
        ? '确定要重建全部索引吗? 这将清除现有数据并重新导入目录中的所有文件。'
        : `确定要同步 ${scanResult.value?.new_count || 0} 个新文件到知识库吗?`,
      '确认操作',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: forceRebuild ? 'warning' : 'info',
      }
    )
  } catch {
    return // 用户取消
  }

  syncing.value = true
  syncProgress.value = 0
  syncCurrentFile.value = ''
  syncTotalFiles.value = 0
  syncProcessedFiles.value = 0

  try {
    // Start background task
    await knowledgeBasesApi.syncFromDir(editingBase.value.id, {
      dir_path: formData.value.settings?.watch_dir,
      force_rebuild: forceRebuild,
    })

    // Poll for progress
    const baseId = editingBase.value.id
    syncPollTimer = setInterval(async () => {
      try {
        const status = await knowledgeBasesApi.getSyncStatus(baseId)
        if (status.status === 'idle') return

        syncProgress.value = status.progress ?? 0
        syncCurrentFile.value = status.current_file ?? ''
        syncTotalFiles.value = status.total_files ?? 0
        syncProcessedFiles.value = status.processed_files ?? 0

        if (status.status === 'completed') {
          stopPolling()
          syncing.value = false
          const result = status.result as { success?: boolean; stats?: { total_documents: number; total_chunks: number }; errors?: unknown[] } | undefined
          if (result?.success) {
            ElMessage.success(`${action}完成: ${result.stats?.total_documents ?? 0} 文档, ${result.stats?.total_chunks ?? 0} 文档块`)
            emit('documents-changed')
            await loadBases()
            // 重新扫描以更新状态
            if (formData.value.settings?.watch_dir) {
              const newScan = await knowledgeBasesApi.scanDir(baseId, formData.value.settings.watch_dir)
              scanResult.value = newScan
            }
          }
          if (result?.errors?.length) {
            ElMessage.warning(`${(result.errors as unknown[]).length} 个文件导入失败`)
          }
        } else if (status.status === 'failed') {
          stopPolling()
          syncing.value = false
          ElMessage.error(status.error || `${action}失败`)
        }
      } catch {
        // Poll error — stop polling
        stopPolling()
        syncing.value = false
        ElMessage.error('获取同步状态失败')
      }
    }, 2000)
  } catch (error: unknown) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const err = error as any
    // 409 = already running, show as info
    if (err.response?.status === 409) {
      ElMessage.warning('该知识库已有同步任务正在运行')
      syncing.value = false
      return
    }
    ElMessage.error(err.response?.data?.detail || `${action}失败`)
    syncing.value = false
  }
}

const stopPolling = () => {
  if (syncPollTimer) {
    clearInterval(syncPollTimer)
    syncPollTimer = null
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// 上传操作
const handleUpload = (base: KnowledgeBase) => {
  uploadBaseId.value = base.id
  uploadBaseName.value = base.name
  uploadFileList.value = []
  uploadDialogVisible.value = true
}

const beforeUpload = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase()
  const isValidType = ext === 'md' || ext === 'markdown'

  if (!isValidType) {
    ElMessage.error('不支持的文件类型')
    return false
  }

  const isValidSize = file.size / 1024 / 1024 < 100
  if (!isValidSize) {
    ElMessage.error('文件大小不能超过 100MB')
    return false
  }

  return true
}

const handleUploadSuccess = () => {
  ElMessage.success('上传成功')
  uploadFileList.value = []
  emit('documents-changed')
  loadBases()
}

const handleUploadError = () => {
  ElMessage.error('上传失败')
}

const handleCreate = () => {
  editingBase.value = null
  scanResult.value = null
  formData.value = {
    name: '',
    description: '',
    settings: {
      watch_dir: '',
      watch_enabled: false,
      watch_recursive: true,
      watch_extensions: ['.md', '.markdown'],
      chunk_size: 1000,
      chunk_overlap: 200,
      chunk_strategy: 'recursive',
      embedding_model: 'qwen3-embedding',
      embedding_dimension: 1024,
      default_top_k: 5,
      default_mode: 'hybrid',
      vector_weight: 0.5,
      graph_weight: 0.3,
      fulltext_weight: 0.2,
      extraction_strategy: 'llm',
      extraction_llm_config: '',
      enable_graph: true,
      enable_fulltext: true,
      auto_reindex: false,
      domain: undefined,
    },
    is_default: false
  }
  settingsTab.value = 'directory'
  showCreateDialog.value = true
}

const handleEdit = (base: KnowledgeBase) => {
  editingBase.value = base
  const settings = { ...base.settings }
  // Ensure dimension matches model
  settings.embedding_dimension = MODEL_DIMENSION_MAP[settings.embedding_model] ?? settings.embedding_dimension
  // Ensure extraction_llm_config exists
  if (settings.extraction_llm_config === undefined) {
    settings.extraction_llm_config = ''
  }
  formData.value = {
    name: base.name,
    description: base.description,
    settings,
    is_default: base.is_default
  }
  // Reset scan result when switching bases
  scanResult.value = null
  settingsTab.value = 'directory'
  showCreateDialog.value = true
}

const handleSave = async () => {
  if (!formData.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }

  saving.value = true
  try {
    if (editingBase.value) {
      // 更新
      const updateData: KnowledgeBaseUpdate = {
        name: formData.value.name,
        description: formData.value.description,
        settings: formData.value.settings
      }
      await knowledgeBasesApi.updateBase(editingBase.value.id, updateData)
      ElMessage.success('知识库更新成功')
    } else {
      // 创建
      await knowledgeBasesApi.createBase(formData.value as KnowledgeBaseCreate)
      ElMessage.success('知识库创建成功')
    }

    showCreateDialog.value = false
    editingBase.value = null
    scanResult.value = null
    await loadBases()
  } catch (error: unknown) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const err = error as any
    ElMessage.error(err.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

const handleSetDefault = async (base: KnowledgeBase) => {
  try {
    await knowledgeBasesApi.setDefaultBase(base.id)
    ElMessage.success('已设为默认知识库')
    await loadBases()
  } catch (error: unknown) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const err = error as any
    ElMessage.error(err.response?.data?.detail || '操作失败')
  }
}

const handleDelete = async (base: KnowledgeBase) => {
  if (base.is_default) {
    ElMessage.warning('无法删除默认知识库')
    return
  }

  if (base.stats.total_documents > 0) {
    try {
      await ElMessageBox.confirm(
        `知识库"${base.name}"包含 ${base.stats.total_documents} 个文档,确定要删除吗?`,
        '警告',
        {
          confirmButtonText: '强制删除',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
      await knowledgeBasesApi.deleteBase(base.id, true)
    } catch {
      return // 用户取消
    }
  } else {
    try {
      await ElMessageBox.confirm(
        `确定要删除知识库"${base.name}"吗?`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
      await knowledgeBasesApi.deleteBase(base.id, false)
    } catch {
      return // 用户取消
    }
  }

  ElMessage.success('知识库已删除')
  await loadBases()
}

const getStatusType = (status: KnowledgeBaseStatus) => {
  const types = {
    active: 'success',
    archived: 'info',
    deleting: 'danger'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status: KnowledgeBaseStatus) => {
  const labels = {
    active: '活跃',
    archived: '已归档',
    deleting: '删除中'
  }
  return labels[status] || status
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

onMounted(() => {
  loadBases()
  loadDomains()
  loadLLMConfigs()
})

onBeforeUnmount(() => {
  stopPolling()
})

defineExpose({
  loadBases
})
</script>

<style scoped>
.knowledge-base-manager {
  padding: 20px;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h2 {
  margin: 0;
}

.base-name {
  display: flex;
  align-items: center;
}

.stats {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.upload-demo {
  text-align: center;
}

.settings-tabs {
  margin-top: 12px;
}

.settings-tabs :deep(.el-tabs__content) {
  padding: 16px;
}

.form-item-tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  line-height: 1.4;
  margin-top: 4px;
}

.weight-warning {
  margin-top: 12px;
}

.scan-result-section {
  margin-top: 12px;
}

.scan-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.scan-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  justify-content: center;
}

.file-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
