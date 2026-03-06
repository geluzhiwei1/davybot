<template>
  <div class="knowledge-base-manager">
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

      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!row.is_default" link type="primary" size="small" @click="handleSetDefault(row)">
            设为默认
          </el-button>
          <el-button link type="primary" size="small" @click="handleEdit(row)">
            编辑
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="showCreateDialog" :title="editingBase ? '编辑知识库' : '创建知识库'" width="600px">
      <el-form :model="formData" label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="formData.name" placeholder="输入知识库名称" maxlength="100" show-word-limit />
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="formData.description" type="textarea" placeholder="输入知识库描述" :rows="3" maxlength="500"
            show-word-limit />
        </el-form-item>

        <el-divider content-position="left">高级设置</el-divider>

        <el-form-item label="分块大小">
          <el-input-number v-model="formData.settings!.chunk_size" :min="100" :max="10000" :step="100" />
        </el-form-item>

        <el-form-item label="分块重叠">
          <el-input-number v-model="formData.settings!.chunk_overlap" :min="0" :max="1000" :step="50" />
        </el-form-item>

        <el-form-item label="嵌入模型">
          <el-select v-model="formData.settings!.embedding_model">
            <el-option label="MiniLM (快速)" value="minilm" />
            <el-option label="BGE-M3 (高质量)" value="bge-m3" />
            <el-option label="Jina-V4 (多语言)" value="jina-v4" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="!editingBase" label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          {{ editingBase ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { knowledgeBasesApi } from '@/services/api/knowledge'
import type {
  KnowledgeBase,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  KnowledgeBaseStatus,
  KnowledgeBaseSettings
} from '@/types/knowledge'

const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreateDialog = ref(false)
const editingBase = ref<KnowledgeBase | null>(null)

const formData = ref<KnowledgeBaseCreate & { settings?: KnowledgeBaseSettings }>({
  name: '',
  description: '',
  settings: {
    chunk_size: 1000,
    chunk_overlap: 200,
    chunk_strategy: 'recursive',
    embedding_model: 'minilm',
    embedding_dimension: 384,
    default_top_k: 5,
    default_mode: 'hybrid',
    vector_weight: 0.5,
    graph_weight: 0.3,
    fulltext_weight: 0.2,
    enable_graph: true,
    enable_fulltext: true,
    auto_reindex: false,
  },
  is_default: false
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

const handleEdit = (base: KnowledgeBase) => {
  editingBase.value = base
  formData.value = {
    name: base.name,
    description: base.description,
    settings: { ...base.settings },
    is_default: base.is_default
  }
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
    await loadBases()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

const handleSetDefault = async (base: KnowledgeBase) => {
  try {
    await knowledgeBasesApi.setDefaultBase(base.id)
    ElMessage.success('已设为默认知识库')
    await loadBases()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
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
})

defineExpose({
  loadBases
})
</script>

<style scoped>
.knowledge-base-manager {
  padding: 20px;
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
</style>
