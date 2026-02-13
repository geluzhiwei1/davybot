/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <teleport to="body">
    <el-dialog
      v-model="visible"
      :title="title"
      width="600px"
      @close="handleClose"
      :z-index="99999"
    >
    <div class="upload-dialog">
      <!-- 显示父目录信息 -->
      <div class="parent-directory-info">
        <el-icon><Folder /></el-icon>
        <span class="info-text">
          上传到: <strong>{{ parentDirectoryName }}</strong>
        </span>
        <span class="info-path">{{ parentDirectoryPath }}</span>
      </div>

      <!-- 上传选项 -->
      <div class="upload-options">
        <el-radio-group v-model="uploadType">
          <el-radio-button value="file">上传文件</el-radio-button>
          <el-radio-button value="folder">上传文件夹</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 文件选择区域 -->
      <div class="upload-area">
        <el-upload
          ref="uploadRef"
          :action="uploadUrl"
          :headers="uploadHeaders"
          :data="uploadData"
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :file-list="fileList"
          :multiple="true"
          drag
          class="upload-component"
        >
          <template v-if="uploadType === 'file'">
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">
              <div>拖拽文件到此处或 <em>点击上传</em></div>
              <div class="upload-hint">支持多文件上传</div>
            </div>
          </template>
        </el-upload>

        <!-- 文件夹上传 -->
        <div v-if="uploadType === 'folder'" class="folder-upload-area">
          <input
            ref="folderInputRef"
            type="file"
            webkitdirectory
            directory
            multiple
            @change="handleFolderSelect"
            style="display: none"
          />
          <el-button type="primary" @click="selectFolder">
            <el-icon><FolderOpened /></el-icon>
            选择文件夹
          </el-button>
          <div class="folder-info" v-if="selectedFolderInfo">
            已选择: {{ selectedFolderInfo.fileCount }} 个文件
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button
          type="primary"
          @click="handleUpload"
          :loading="uploading"
          :disabled="fileList.length === 0 && !selectedFolderInfo"
        >
          开始上传
        </el-button>
      </div>
    </template>
  </el-dialog>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { UploadFilled, Folder, FolderOpened } from '@element-plus/icons-vue';
import type { UploadInstance, UploadUserFile, UploadProps } from 'element-plus';

interface Props {
  modelValue: boolean;
  parentPath: string;
  parentName: string;
  workspaceId?: string;
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void;
  (e: 'success'): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

const title = computed(() => {
  return props.parentName ? `上传到 ${props.parentName}` : '上传到根目录';
});

const parentDirectoryName = computed(() => {
  return props.parentName || '根目录';
});

const parentDirectoryPath = computed(() => {
  return props.parentPath || '/';
});

const uploadType = ref<'file' | 'folder'>('file');
const uploading = ref(false);
const fileList = ref<UploadUserFile[]>([]);
const selectedFolderInfo = ref<unknown>(null);
const uploadRef = ref<UploadInstance>();
const folderInputRef = ref<HTMLInputElement>();

// 上传URL
const uploadUrl = computed(() => {
  if (!props.workspaceId) {
    return '';
  }
  return `/api/workspaces/${props.workspaceId}/files/upload`;
});

// 上传头部
const uploadHeaders = computed(() => {
  return {
    // 如果需要认证，可以在这里添加token
  };
});

// 上传附加数据
const uploadData = computed(() => {
  return {
    parent_path: props.parentPath || ''
  };
});

// 处理文件选择
const handleFileChange: UploadProps['onChange'] = (uploadFile, uploadFiles) => {
  fileList.value = uploadFiles;
};

// 处理文件移除
const handleFileRemove: UploadProps['onRemove'] = (file, uploadFiles) => {
  fileList.value = uploadFiles;
};

// 选择文件夹
const selectFolder = () => {
  folderInputRef.value?.click();
};

// 处理文件夹选择
const handleFolderSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = target.files;

  if (files && files.length > 0) {
    selectedFolderInfo.value = {
      fileCount: files.length,
      files: Array.from(files)
    };
    ElMessage.success(`已选择 ${files.length} 个文件`);
  }
};

// 处理上传成功
const handleUploadSuccess = (response: unknown, file: UploadUserFile) => {
  ElMessage.success(`${file.name} 上传成功`);
};

// 处理上传错误
const handleUploadError = (error: Error, file: UploadUserFile) => {
  ElMessage.error(`${file.name} 上传失败`);
};

// 执行上传
const handleUpload = async () => {
  if (uploadType.value === 'folder') {
    await uploadFolder();
  } else {
    await uploadFiles();
  }
};

// 上传文件
const uploadFiles = async () => {
  if (!props.workspaceId) {
    ElMessage.error('工作区ID不存在，无法上传文件');
    return;
  }

  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择文件');
    return;
  }

  uploading.value = true;

  try {
    await uploadRef.value?.submit();

    // 等待所有文件上传完成
    setTimeout(() => {
      ElMessage.success('文件上传完成');
      handleClose();
      emit('success');
    }, 1000);
  } catch {
    ElMessage.error('文件上传失败');
  } finally {
    uploading.value = false;
  }
};

// 上传文件夹
const uploadFolder = async () => {
  if (!props.workspaceId) {
    ElMessage.error('工作区ID不存在，无法上传文件夹');
    return;
  }

  if (!selectedFolderInfo.value) {
    ElMessage.warning('请先选择文件夹');
    return;
  }

  uploading.value = true;

  try {
    const files = selectedFolderInfo.value.files;
    const formData = new FormData();

    // 添加父目录路径
    formData.append('parent_path', props.parentPath || '');

    // 添加所有文件，保持文件夹结构
    for (const file of files) {
      // 获取文件的相对路径
      const relativePath = file.webkitRelativePath || file.name;
      formData.append('files', file, relativePath);
    }

    const response = await fetch(`/api/workspaces/${props.workspaceId}/files/upload-folder`, {
      method: 'POST',
      body: formData
    });

    if (response.ok) {
      ElMessage.success('文件夹上传完成');
      handleClose();
      emit('success');
    } else {
      throw new Error('Upload failed');
    }
  } catch {
    ElMessage.error('文件夹上传失败');
  } finally {
    uploading.value = false;
  }
};

// 关闭对话框
const handleClose = () => {
  visible.value = false;
  fileList.value = [];
  selectedFolderInfo.value = null;
  uploadType.value = 'file';
};
</script>

<style scoped>
.upload-dialog {
  padding: 10px 0;
}

.parent-directory-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 15px;
  background-color: var(--el-bg-color-page);
  border-radius: 8px;
  margin-bottom: 20px;
}

.info-text {
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.info-path {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.upload-options {
  margin-bottom: 20px;
  text-align: center;
}

.upload-area {
  min-height: 200px;
}

.upload-component {
  width: 100%;
}

.upload-icon {
  font-size: 48px;
  color: var(--el-color-primary);
}

.upload-text {
  font-size: 14px;
  color: var(--el-text-color-regular);
  margin-top: 10px;
}

.upload-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 5px;
}

.folder-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  border: 2px dashed var(--el-border-color);
  border-radius: 8px;
  padding: 20px;
}

.folder-info {
  margin-top: 15px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
