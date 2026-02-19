/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

<template>
  <div class="workspace-settings-container">
    <el-card class="settings-card">
      <template #header>
        <div class="card-header">
          <h2>{{ t('workspaceSettings.title') }}</h2>
          <el-button type="primary" @click="goBack">返回</el-button>
        </div>
      </template>

      <el-tabs v-model="activeTab" type="border-card">
        <!-- UI 环境信息 Tab -->
        <el-tab-pane label="UI 环境信息" name="environments">
          <el-form :model="uiEnvironments" label-width="120px" class="settings-form">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="浏览器名称">
                  <el-input v-model="uiEnvironments.browser_name" placeholder="Chrome" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="浏览器版本">
                  <el-input v-model="uiEnvironments.browser_version" placeholder="120.0.0.0" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="操作系统">
                  <el-input v-model="uiEnvironments.user_os" placeholder="Windows 11" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="用户语言">
                  <el-input v-model="uiEnvironments.user_language" placeholder="zh-CN" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="时区">
                  <el-input v-model="uiEnvironments.timezone" placeholder="Asia/Shanghai" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="屏幕分辨率">
                  <el-input v-model="uiEnvironments.screen_resolution" placeholder="1920x1080" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item>
              <el-button type="primary" @click="saveUIEnvironments" :loading="saving">
                保存环境信息
              </el-button>
              <el-button @click="loadUIEnvironments">刷新</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- UI 上下文 Tab -->
        <el-tab-pane label="UI 上下文" name="context">
          <el-form :model="uiContext" label-width="140px" class="settings-form">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="当前文件">
                  <el-input v-model="uiContext.current_file" placeholder="src/App.vue" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="当前模式">
                  <el-select v-model="uiContext.current_mode" placeholder="选择模式" clearable>
                    <el-option v-for="mode in modes" :key="mode.slug" :label="mode.name" :value="mode.slug" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="LLM 模型">
                  <el-select v-model="uiContext.current_llm_id" placeholder="选择模型" clearable>
                    <el-option v-for="model in llms" :key="model.model_id" :label="model.name"
                      :value="model.model_id" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="对话 ID">
                  <el-input v-model="uiContext.conversation_id" placeholder="conversation-uuid" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-form-item label="打开的文件">
              <el-select v-model="uiContext.open_files" multiple filterable allow-create default-first-option
                placeholder="打开的文件路径" style="width: 100%">
                <el-option v-for="file in openFilesList" :key="file" :label="file" :value="file" />
              </el-select>
            </el-form-item>

            <el-form-item label="活动应用">
              <el-select v-model="uiContext.active_applications" multiple filterable allow-create default-first-option
                placeholder="活动应用程序" style="width: 100%">
                <el-option v-for="app in activeAppsList" :key="app" :label="app" :value="app" />
              </el-select>
            </el-form-item>

            <el-form-item label="选中内容">
              <el-input v-model="uiContext.current_selected_content" type="textarea" :rows="3" placeholder="当前选中的内容" />
            </el-form-item>

            <el-form-item label="用户偏好">
              <el-input v-model="userPreferencesJson" type="textarea" :rows="5"
                placeholder='{"theme": "dark", "language": "zh-CN"}' @blur="parseUserPreferences" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="saveUIContext" :loading="saving">
                保存上下文信息
              </el-button>
              <el-button @click="loadUIContext">刷新</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { apiManager } from '@/services/api';
import { logger } from '@/utils/logger';
import type { UserUIEnvironments, UserUIContext } from '@/services/api/types';
import { useI18n } from 'vue-i18n';

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const activeTab = ref('environments');
const saving = ref(false);
const workspaceId = ref<string>('');

// UI 环境信息
const uiEnvironments = reactive<UserUIEnvironments>({
  browser_name: '',
  browser_version: '',
  user_os: '',
  user_language: '',
  timezone: '',
  screen_resolution: ''
});

// UI 上下文信息
const uiContext = reactive<UserUIContext>({
  open_files: [],
  active_applications: [],
  user_preferences: {},
  current_file: null,
  current_selected_content: null,
  current_mode: null,
  current_llm_id: null,
  conversation_id: null
});

// 用户偏好的 JSON 字符串
const userPreferencesJson = ref('');

// 可选择的选项
const modes = ref<Array<{ slug: string; name: string; description?: string }>>([]);
const llms = ref<Array<{ name: string; model_id: string }>>([]);
const openFilesList = ref<string[]>([]);
const activeAppsList = ref<string[]>(['VSCode', 'Chrome', 'Terminal', 'File Explorer']);

// 初始化
onMounted(async () => {
  workspaceId.value = route.params.workspaceId as string || 'default';

  await Promise.all([
    loadUIEnvironments(),
    loadUIContext(),
    loadModes(),
    loadLLMs()
  ]);
});

// 加载 UI 环境信息
const loadUIEnvironments = async () => {
  try {
    const data = await apiManager.getWorkspacesApi().getUIEnvironments(workspaceId.value);
    Object.assign(uiEnvironments, data);
    ElMessage.success('已加载 UI 环境信息');
  } catch (error) {
    console.error('加载 UI 环境信息失败:', error);
    ElMessage.error('加载 UI 环境信息失败');
  }
};

// 保存 UI 环境信息
const saveUIEnvironments = async () => {
  saving.value = true;
  try {
    await apiManager.getWorkspacesApi().updateUIEnvironments(workspaceId.value, uiEnvironments);
    ElMessage.success('UI 环境信息已保存');
  } catch (error) {
    console.error('保存 UI 环境信息失败:', error);
    ElMessage.error('保存 UI 环境信息失败');
  } finally {
    saving.value = false;
  }
};

// 加载 UI 上下文信息
const loadUIContext = async () => {
  try {
    const data = await apiManager.getWorkspacesApi().getUIContext(workspaceId.value);
    Object.assign(uiContext, data);
    userPreferencesJson.value = JSON.stringify(uiContext.user_preferences || {}, null, 2);
    ElMessage.success('已加载 UI 上下文信息');
  } catch (error) {
    console.error('加载 UI 上下文信息失败:', error);
    ElMessage.error('加载 UI 上下文信息失败');
  }
};

// 保存 UI 上下文信息
const saveUIContext = async () => {
  saving.value = true;
  try {
    await apiManager.getWorkspacesApi().updateUIContext(workspaceId.value, uiContext);
    ElMessage.success('UI 上下文信息已保存');
  } catch (error) {
    console.error('保存 UI 上下文信息失败:', error);
    ElMessage.error('保存 UI 上下文信息失败');
  } finally {
    saving.value = false;
  }
};

// 加载模式列表
const loadModes = async () => {
  try {
    // 模式列表功能待实现，当前返回空数组
    modes.value = [];
    logger.debug('Modes loaded (empty - feature not implemented)');
  } catch (error) {
    logger.error('Failed to load modes:', error);
    modes.value = [];
  }
};

// 加载 LLM 列表
const loadLLMs = async () => {
  try {
    // LLM 列表功能待实现，当前返回空数组
    llms.value = [];
    logger.debug('LLMs loaded (empty - feature not implemented)');
  } catch (error) {
    logger.error('Failed to load LLMs:', error);
    llms.value = [];
  }
};

// 解析用户偏好 JSON
const parseUserPreferences = () => {
  try {
    if (userPreferencesJson.value) {
      uiContext.user_preferences = JSON.parse(userPreferencesJson.value);
    }
  } catch {
    ElMessage.error('用户偏好 JSON 格式错误');
  }
};

// 返回上一页
const goBack = () => {
  router.back();
};
</script>

<style scoped>
.workspace-settings-container {
  padding: 20px;
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
}

.settings-card {
  max-width: 1200px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.settings-form {
  padding: 20px 0;
}

.el-form-item {
  margin-bottom: 18px;
}
</style>
