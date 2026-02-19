/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <el-dialog
    v-model="visible"
    title="删除工作区"
    width="500px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="delete-confirmation">
      <!-- 警告图标 -->
      <el-icon class="warning-icon" :size="48" color="#E6A23C">
        <WarningFilled />
      </el-icon>

      <!-- 标题 -->
      <h3>确定要删除工作区吗？</h3>

      <p class="workspace-info">
        <strong>{{ workspace?.display_name || workspace?.name }}</strong>
        <br />
        <span class="workspace-path">{{ workspace?.path }}</span>
      </p>

      <!-- 警告文本 -->
      <p class="warning-text">
        此操作将删除工作区的配置和数据：
      </p>

      <!-- 删除项列表 -->
      <ul class="data-list">
        <li>工作区配置（.dawei 目录）</li>
        <li>对话历史</li>
        <li>任务图和检查点</li>
        <li>{{ t('workspaceSettings.title') }}</li>
      </ul>

      <!-- 删除选项 -->
      <div class="delete-options">
        <el-checkbox v-model="deleteConfig">
          删除配置目录（.dawei）
        </el-checkbox>

        <el-checkbox v-model="deleteFiles" style="margin-top: 10px">
          同时删除整个工作区目录（包括用户文件）
        </el-checkbox>
      </div>

      <!-- 危险警告 -->
      <el-alert
        v-if="deleteFiles"
        type="error"
        :closable="false"
        show-icon
        style="margin-top: 20px"
      >
        <template #title>
          <strong>危险操作</strong>
        </template>
        <template #default>
          删除整个目录将永久删除所有文件，此操作不可撤销！
        </template>
      </el-alert>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="danger"
        @click="handleDelete"
        :loading="deleting"
      >
        确认删除
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { workspaceService } from '@/services/workspace'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  modelValue: boolean
  workspace?: unknown
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'deleted', workspaceId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const deleting = ref(false)
const deleteConfig = ref(true)
const deleteFiles = ref(false)

// 对话框显示状态
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 删除工作区
const handleDelete = async () => {
  if (!props.workspace) {
    return
  }

  try {
    deleting.value = true

    const response = await workspaceService.deleteWorkspace(
      props.workspace.id,
      deleteConfig.value,
      deleteFiles.value
    )

    if (response.success) {
      // 触发 deleted 事件，让父组件处理消息和刷新
      emit('deleted', props.workspace.id)
      handleClose()
    } else {
      ElMessage.error(response.error || '删除失败')
    }
  } catch (error: unknown) {
    console.error('Delete workspace error:', error)
    // 如果是 404 错误，说明工作区已经被删除了，不算失败
    if (error.response?.status === 404) {
      ElMessage.success('工作区已删除')
      emit('deleted', props.workspace.id)
      handleClose()
    } else {
      ElMessage.error(error.response?.data?.detail || '删除失败')
    }
  } finally {
    deleting.value = false
  }
}

// 关闭对话框
const handleClose = () => {
  deleteConfig.value = true
  deleteFiles.value = false
  emit('update:modelValue', false)
}
</script>

<style scoped>
.delete-confirmation {
  text-align: center;
  padding: 20px 0;
}

.warning-icon {
  margin-bottom: 20px;
}

h3 {
  font-size: 20px;
  margin-bottom: 15px;
  color: #303133;
}

.workspace-info {
  margin-bottom: 20px;
  color: #606266;
}

.workspace-path {
  font-size: 13px;
  color: #909399;
}

.warning-text {
  text-align: left;
  margin: 20px 0;
  color: #E6A23C;
  font-weight: 500;
}

.data-list {
  text-align: left;
  margin: 15px 0 20px 20px;
  padding: 0;
  color: #606266;
}

.data-list li {
  margin: 8px 0;
  list-style-type: disc;
}

.delete-options {
  text-align: left;
  margin: 20px 0;
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
}
</style>
