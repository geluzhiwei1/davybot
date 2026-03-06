<template>
  <div class="knowledge-base-selector">
    <el-select
      v-model="selectedBaseId"
      placeholder="选择知识库"
      @change="handleBaseChange"
      :loading="loading"
    >
      <el-option
        v-for="base in knowledgeBases"
        :key="base.id"
        :label="base.name"
        :value="base.id"
      >
        <div class="kb-option">
          <span class="kb-name">{{ base.name }}</span>
          <el-tag v-if="base.is_default" type="success" size="small">默认</el-tag>
          <span class="kb-stats">{{ base.stats.total_documents }} 文档</span>
        </div>
      </el-option>
      <template #footer>
        <el-button text @click="showCreateDialog = true" size="small">
          <el-icon><Plus /></el-icon>
          创建新知识库
        </el-button>
      </template>
    </el-select>

    <!-- 创建知识库对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="创建知识库"
      width="500px"
    >
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            placeholder="输入知识库描述"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="createForm.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreateBase" :loading="creating">
          创建
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { knowledgeBasesApi } from '@/services/api/knowledge'
import type { KnowledgeBase } from '@/types/knowledge'

const props = defineProps<{
  modelValue?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [base: KnowledgeBase]
}>()

const selectedBaseId = ref(props.modelValue || '')
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)
const creating = ref(false)
const showCreateDialog = ref(false)

const createForm = ref({
  name: '',
  description: '',
  is_default: false
})

const loadBases = async () => {
  loading.value = true
  try {
    const response = await knowledgeBasesApi.listBases()
    knowledgeBases.value = response.items

    // 如果没有选中且有默认知识库,自动选中
    if (!selectedBaseId.value && response.default_base_id) {
      selectedBaseId.value = response.default_base_id
      emit('update:modelValue', selectedBaseId.value)
    }
  } catch (error) {
    ElMessage.error('加载知识库列表失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const handleBaseChange = (baseId: string) => {
  emit('update:modelValue', baseId)
  const base = knowledgeBases.value.find(b => b.id === baseId)
  if (base) {
    emit('change', base)
  }
}

const handleCreateBase = async () => {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }

  creating.value = true
  try {
    const newBase = await knowledgeBasesApi.createBase(createForm.value)
    ElMessage.success('知识库创建成功')

    // 添加到列表
    knowledgeBases.value.push(newBase)

    // 选中新创建的知识库
    selectedBaseId.value = newBase.id
    emit('update:modelValue', newBase.id)
    emit('change', newBase)

    // 重置表单并关闭对话框
    createForm.value = { name: '', description: '', is_default: false }
    showCreateDialog.value = false
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '创建知识库失败')
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadBases()
})

defineExpose({
  loadBases
})
</script>

<style scoped>
.knowledge-base-selector {
  width: 100%;
}

.kb-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.kb-name {
  flex: 1;
}

.kb-stats {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
