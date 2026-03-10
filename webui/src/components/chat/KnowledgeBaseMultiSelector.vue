<template>
  <div class="kb-multi-selector">
    <el-select
      v-model="selectedBaseIds"
      multiple
      collapse-tags
      collapse-tags-tooltip
      :placeholder="t('knowledge.selector.placeholder')"
      @change="handleSelectionChange"
      :loading="loading"
      class="kb-select"
      clearable
    >
      <el-option
        v-for="base in knowledgeBases"
        :key="base.id"
        :label="base.name"
        :value="base.id"
      >
        <div class="kb-option">
          <span class="kb-name">{{ base.name }}</span>
          <div class="kb-meta">
            <el-tag v-if="base.is_default" type="success" size="small">{{ t('knowledge.selector.default') }}</el-tag>
            <el-tag size="small" type="info">{{ t('knowledge.selector.documentCount', { count: base.stats.total_documents }) }}</el-tag>
          </div>
        </div>
      </el-option>
      <template #footer>
        <div class="kb-footer">
          <el-button text @click="handleManageKnowledgeBases" size="small">
            <el-icon><Setting /></el-icon>
            {{ t('knowledge.selector.manageBases') }}
          </el-button>
          <el-button text @click="handleRefresh" size="small" :loading="loading">
            <el-icon><Refresh /></el-icon>
            {{ t('knowledge.selector.refresh') }}
          </el-button>
        </div>
      </template>
    </el-select>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Setting, Refresh } from '@element-plus/icons-vue'
import { knowledgeBasesApi } from '@/services/api/knowledge'
import type { KnowledgeBase } from '@/types/knowledge'

const { t } = useI18n()

const props = defineProps<{
  modelValue?: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  'change': [bases: KnowledgeBase[]]
}>()

const selectedBaseIds = ref<string[]>(props.modelValue || [])
const knowledgeBases = ref<KnowledgeBase[]>([])
const loading = ref(false)

// 加载知识库列表
const loadBases = async () => {
  loading.value = true
  try {
    const response = await knowledgeBasesApi.listBases()
    knowledgeBases.value = response.items
  } catch (error) {
    ElMessage.error(t('knowledge.selector.loadFailed'))
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 处理选择变化
const handleSelectionChange = (baseIds: string[]) => {
  emit('update:modelValue', baseIds)

  // 找到选中的知识库对象
  const selectedBases = knowledgeBases.value.filter(b => baseIds.includes(b.id))
  emit('change', selectedBases)
}

// 管理知识库
const handleManageKnowledgeBases = () => {
  // 触发打开知识库管理面板的事件
  window.dispatchEvent(new CustomEvent('open-knowledge-drawer'))
}

// 刷新列表
const handleRefresh = () => {
  loadBases()
}

// 监听 modelValue 变化
watch(() => props.modelValue, (newValue) => {
  if (newValue !== undefined) {
    selectedBaseIds.value = newValue
  }
}, { deep: true })

onMounted(() => {
  loadBases()
})

// 暴露刷新方法
defineExpose({
  loadBases,
  refresh: handleRefresh
})
</script>

<style scoped>
.kb-multi-selector {
  width: 100%;
}

.kb-select {
  width: 100%;
}

.kb-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
}

.kb-name {
  flex: 1;
  font-weight: 500;
}

.kb-meta {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kb-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 优化多选标签样式 */
:deep(.el-select__tags) {
  max-width: calc(100% - 32px);
}

:deep(.el-tag) {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 下拉选项样式优化 */
:deep(.el-select-dropdown__item) {
  padding: 8px 12px;
  height: auto;
  line-height: 1.5;
}
</style>
