/**
* Copyright (c) 2025 格律至微
* SPDX-License-Identifier: AGPL-3.0
*/

<template>
  <el-dialog v-model="visible" :title="isEditMode ? '编辑工作区' : '创建工作区'" width="700px" :close-on-click-modal="false"
    @close="handleClose">
    <el-form ref="formRef" :model="formData" :rules="formRules" label-width="140px" @submit.prevent="handleSubmit">
      <!-- 工作区路径（仅创建时显示） -->
      <el-form-item label="工作区路径" prop="path" v-if="!isEditMode">
        <el-input v-model="formData.path" placeholder="~/my-project" @blur="validatePath">
          <template #prepend>
            <el-icon>
              <Folder />
            </el-icon>
          </template>
          <template #append>
            <el-button v-if="isTauri" :icon="FolderOpened" @click="selectDirectory" :disabled="selectingDirectory">
              {{ selectingDirectory ? '选择中...' : '选择目录' }}
            </el-button>
          </template>
        </el-input>
        <div class="form-tip">
          工作区的完整路径，将在此路径下创建 .dawei 配置目录
          <el-tag v-if="!isTauri" type="info" size="small" style="margin-left: 8px">
            Web 模式：请手动输入路径
          </el-tag>
        </div>

        <!-- 路径验证状态 -->
        <el-alert v-if="pathValidation.status" :type="pathValidation.status" :closable="false" style="margin-top: 10px">
          {{ pathValidation.message }}
        </el-alert>
      </el-form-item>

      <!-- 显示名称 -->
      <el-form-item label="显示名称" prop="display_name">
        <el-input v-model="formData.display_name" placeholder="我的项目">
          <template #prepend>
            <el-icon>
              <FolderOpened />
            </el-icon>
          </template>
        </el-input>
      </el-form-item>

      <!-- 描述 -->
      <el-form-item label="描述" prop="description">
        <el-input v-model="formData.description" type="textarea" :rows="3" placeholder="简单描述这个工作区的用途..." />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" @click="handleSubmit" :loading="submitting" :disabled="!isValidPath">
        {{ isEditMode ? '保存' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Folder, FolderOpened } from '@element-plus/icons-vue'
import { invoke } from '@tauri-apps/api/core'
import { isTauri } from '@/utils/platform'
import { workspaceService, type CreateWorkspaceRequest, type UpdateWorkspaceRequest } from '@/services/workspace'

interface Props {
  modelValue: boolean
  workspace?: unknown
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', workspace: unknown): void
  (e: 'updated', workspace: unknown): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const formRef = ref()
const submitting = ref(false)
const selectingDirectory = ref(false)

// 是否为编辑模式
const isEditMode = computed(() => !!props.workspace)

// 表单数据
const formData = reactive({
  path: '',
  name: '',
  display_name: '',
  description: ''
})

// 路径验证状态
const pathValidation = reactive({
  status: '' as 'success' | 'warning' | 'error' | 'info' | '',
  message: ''
})

// 路径是否有效
const isValidPath = computed(() => {
  // 编辑模式下不需要验证路径
  if (isEditMode.value) return true
  // 创建模式下，路径必须验证通过（包括已有工作区的情况）
  return pathValidation.status === 'success' || pathValidation.status === 'warning' || pathValidation.status === 'info'
})

// 表单验证规则
const formRules = {
  path: [
    { required: true, message: '请输入工作区路径', trigger: 'blur' }
  ],
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' }
  ]
}

// 对话框显示状态
const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

// 选择目录（仅 Tauri 模式支持）
const selectDirectory = async () => {
  if (!isTauri()) {
    ElMessage.warning('目录选择功能仅在桌面应用中可用')
    return
  }

  try {
    selectingDirectory.value = true

    // 调用 Tauri 命令选择目录
    const selected = await invoke<string | null>('select_directory')

    if (selected) {
      formData.path = selected
      // 触发路径验证
      await validatePath()
    }
  } catch (error) {
    console.error('Directory selection error:', error)
    ElMessage.error('选择目录失败')
  } finally {
    selectingDirectory.value = false
  }
}

// 验证路径
let validatePathTimer: unknown = null
const validatePath = async () => {
  if (!formData.path || isEditMode.value) {
    pathValidation.status = ''
    pathValidation.message = ''
    return
  }

  // 防抖
  if (validatePathTimer) {
    clearTimeout(validatePathTimer)
  }

  validatePathTimer = setTimeout(async () => {
    try {
      const response = await workspaceService.validatePath({
        path: formData.path
      })

      if (response.valid) {
        // 如果是已有工作区，显示 info 状态
        if (response.is_workspace) {
          pathValidation.status = 'info'
          pathValidation.message = response.message
        } else {
          pathValidation.status = 'success'
          pathValidation.message = response.message
        }
      } else {
        pathValidation.status = 'error'
        pathValidation.message = response.message || '路径无效'
      }
    } catch (error: unknown) {
      pathValidation.status = 'error'
      pathValidation.message = error.response?.data?.detail || '路径验证失败'
    }
  }, 500)
}

// 重置表单
const resetForm = () => {
  formRef.value?.resetFields()
  formData.path = ''
  formData.name = ''
  formData.display_name = ''
  formData.description = ''
  pathValidation.status = ''
  pathValidation.message = ''
}

// 加载工作区数据（编辑模式）
const loadWorkspace = () => {
  if (props.workspace) {
    formData.display_name = props.workspace.display_name || ''
    formData.description = props.workspace.description || ''
  }
}

// 提交表单
const handleSubmit = async () => {
  try {
    await formRef.value?.validate()

    submitting.value = true

    if (isEditMode.value) {
      // 编辑模式
      const updateData: UpdateWorkspaceRequest = {
        display_name: formData.display_name,
        description: formData.description
      }

      const response = await workspaceService.updateWorkspace(
        props.workspace.id,
        updateData
      )

      if (response.success) {
        ElMessage.success('工作区更新成功')
        emit('updated', response.workspace)
        handleClose()
      } else {
        ElMessage.error(response.error || '更新失败')
      }
    } else {
      // 创建模式
      const createData: CreateWorkspaceRequest = {
        path: formData.path,
        name: formData.name || undefined,
        display_name: formData.display_name,
        description: formData.description || undefined
      }

      const response = await workspaceService.createWorkspace(createData)

      if (response.success) {
        ElMessage.success('工作区创建成功')
        emit('created', response.workspace)
        handleClose()
      } else {
        ElMessage.error(response.error || '创建失败')
      }
    }
  } catch (error: unknown) {
    console.error('Form submission error:', error)
    ElMessage.error(error.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

// 关闭对话框
const handleClose = () => {
  resetForm()
  emit('update:modelValue', false)
}

// 监听 workspace 变化
watch(() => props.workspace, () => {
  loadWorkspace()
})

// 监听对话框打开
watch(visible, (val) => {
  if (val) {
    loadWorkspace()
  }
})
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

:deep(.el-input-group__prepend) {
  background-color: #f5f7fa;
  color: #909399;
}
</style>
