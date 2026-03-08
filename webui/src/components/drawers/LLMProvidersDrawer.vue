<template>
  <div class="llm-providers-drawer">
    <div class="drawer-content" v-loading="loading">
      <!-- Provider Header -->
      <div class="provider-header">
        <el-alert title="Provider 管理" type="info" :closable="false" show-icon>
          <template #default>
            <p style="margin: 0; font-size: 13px;">
              管理用户和工作区的 LLM Provider 配置。所有配置保存在 <code>settings.json</code>
            </p>
          </template>
        </el-alert>

        <div class="provider-actions" style="margin-top: 16px; display: flex; gap: 8px;">
          <el-button type="primary" @click="showCreateProviderDialog">
            <el-icon>
              <Plus />
            </el-icon>
            添加 Provider
          </el-button>
          <el-button @click="loadLLMSettings" :loading="loading">
            <el-icon>
              <Refresh />
            </el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <!-- Provider 列表 -->
      <el-table :data="providerList" style="width: 100%; margin-top: 16px;" border>
        <el-table-column prop="name" label="名称" width="200">
          <template #default="scope">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>{{ scope.row.name }}</span>
              <el-tag v-if="scope.row.name === llmSettings.currentApiConfigName" type="success" size="small">默认</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="source" label="来源" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.source === 'user' ? 'warning' : 'success'" size="small">
              {{ scope.row.source === 'user' ? '用户级' : '工作区级' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="apiProvider" label="类型" width="150">
          <template #default="scope">
            <el-tag :type="getProviderTagType(scope.row.apiProvider)" size="small">
              {{ getProviderDisplayName(scope.row.apiProvider) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="modelId" label="模型 ID" width="200" show-overflow-tooltip />

        <el-table-column prop="baseUrl" label="Base URL" show-overflow-tooltip />

        <el-table-column label="高级设置" width="180">
          <template #default="scope">
            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
              <el-tag v-if="scope.row.config.config?.diffEnabled || scope.row.config.diffEnabled" size="small"
                type="info">Diff</el-tag>
              <el-tag v-if="scope.row.config.config?.todoListEnabled || scope.row.config.todoListEnabled" size="small"
                type="info">TODO</el-tag>
              <el-tag v-if="scope.row.config.config?.enableReasoningEffort || scope.row.config.enableReasoningEffort"
                size="small" type="warning">推理</el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" align="center" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="viewProvider(scope.row)">查看</el-button>
            <el-button size="small" type="primary" @click="editProvider(scope.row)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteProvider(scope.row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Provider 编辑/创建对话框 -->
    <el-dialog v-model="showProviderDialog" :title="editingProvider ? '编辑 Provider' : '添加 Provider'" width="800px">
      <el-form :model="providerForm" label-width="160px">
        <el-form-item label="配置名称" required>
          <el-input v-model="providerForm.name" placeholder="例如：ali-qwen-3.0" :disabled="editingProvider !== null" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            本配置的唯一名称,创建后不可修改
          </div>
        </el-form-item>

        <el-form-item label="保存位置" required v-if="editingProvider === null">
          <el-radio-group v-model="providerForm.saveLocation">
            <el-radio value="user">用户级（默认）</el-radio>
            <el-radio value="workspace">工作区级</el-radio>
          </el-radio-group>
          <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
            用户级配置对所有工作区可用，工作区级配置仅对当前工作区有效
          </div>
        </el-form-item>

        <el-form-item label="API 厂家" required>
          <el-select v-model="providerForm.apiProvider" placeholder="选择 API 类型" style="width: 100%"
            @change="onApiProviderChange">
            <el-option label="OpenAI兼容" value="openai" />
            <el-option label="GLM (智谱)" value="glm" />
            <el-option label="Ollama (本地)" value="ollama" />
          </el-select>
        </el-form-item>

        <!-- OpenAI/GLM 配置 -->
        <template v-if="providerForm.apiProvider === 'openai' || providerForm.apiProvider === 'glm'">
          <el-form-item label="Base URL" required>
            <el-input v-model="providerForm.openAiBaseUrl" placeholder="https://api.openai.com/v1" />
          </el-form-item>

          <el-form-item label="API Key">
            <el-input v-model="providerForm.openAiApiKey" type="password" placeholder="sk-..." show-password />
          </el-form-item>

          <el-form-item label="模型 ID" required>
            <el-input v-model="providerForm.openAiModelId" placeholder="gpt-4o-mini" />
          </el-form-item>

          <el-form-item label="自定义 Headers (JSON)">
            <el-input v-model="customHeadersText" type="textarea" :rows="3"
              placeholder='{"Authorization": "Bearer token"}' />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              可选。使用 JSON 格式添加自定义 HTTP headers
            </div>
          </el-form-item>

          <el-form-item v-if="providerForm.apiProvider === 'openai'" label="兼容格式">
            <el-switch v-model="providerForm.openAiLegacyFormat" />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              启用旧版 API 格式（某些第三方兼容 API 可能需要）
            </div>
          </el-form-item>
        </template>

        <!-- Ollama 配置 (使用 OpenAI 兼容字段) -->
        <template v-if="providerForm.apiProvider === 'ollama'">
          <el-form-item label="Base URL" required>
            <el-input v-model="providerForm.openAiBaseUrl" placeholder="http://localhost:11434/v1" />
            <div style="font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px;">
              Ollama 使用 OpenAI 兼容接口 (/v1/chat/completions)
            </div>
          </el-form-item>

          <el-form-item label="模型 ID" required>
            <el-input v-model="providerForm.openAiModelId" placeholder="qwen2.5:7b" />
          </el-form-item>

          <el-form-item label="API Key">
            <el-input v-model="providerForm.openAiApiKey" type="password" placeholder="ollama (可选)" show-password />
          </el-form-item>
        </template>

        <!-- 高级设置 -->
        <el-divider content-position="left">高级设置</el-divider>

        <el-form-item label="模糊匹配阈值">
          <el-input-number v-model="providerForm.fuzzyMatchThreshold" :min="0" :max="1" :step="0.1" :precision="2"
            style="width: 200px;" />
        </el-form-item>

        <el-form-item label="速率限制（秒）">
          <el-input-number v-model="providerForm.rateLimitSeconds" :min="0" :max="60" :step="1" style="width: 200px;" />
        </el-form-item>

        <el-form-item label="连续错误限制">
          <el-input-number v-model="providerForm.consecutiveMistakeLimit" :min="1" :max="20" :step="1"
            style="width: 200px;" />
        </el-form-item>

        <el-form-item label="Tool Choice">
          <el-select v-model="providerForm.toolChoice" placeholder="Tool Choice" style="width: 200px;">
            <el-option label="Required" value="required" />
            <el-option label="Auto" value="auto" />
            <el-option label="None" value="none" />
          </el-select>
        </el-form-item>

        <el-form-item label="Temperature">
          <el-input-number v-model="providerForm.temperature" :min="0" :max="2" :step="0.1" :precision="1"
            style="width: 200px;" />
        </el-form-item>
      </el-form>

      <template #footer>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span v-if="providerTestResult" style="display: flex; align-items: center;">
            <el-tag :type="providerTestResult.supported ? 'success' : 'danger'" size="small">
              {{ providerTestResult.supported ? '支持' : '不支持' }}
            </el-tag>
          </span>
          <div style="display: flex; gap: 8px; margin-left: auto;">
            <el-button @click="testProvider" :loading="testingProvider" :disabled="!providerForm.openAiModelId">
              <el-icon>
                <Document />
              </el-icon>
              测试
            </el-button>
            <el-button @click="showProviderDialog = false">取消</el-button>
            <el-button type="primary" @click="saveProvider" :loading="saving">
              保存
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- Provider 查看对话框 -->
    <el-dialog v-model="showViewProviderDialog" title="Provider 详情" width="700px">
      <el-descriptions :column="2" border v-if="viewingProvider">
        <el-descriptions-item label="Provider 名称">
          {{ viewingProvider.name }}
        </el-descriptions-item>
        <el-descriptions-item label="API 类型">
          <el-tag :type="getProviderTagType(viewingProvider.apiProvider)">
            {{ getProviderDisplayName(viewingProvider.apiProvider) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型 ID">
          {{ viewingProvider.modelId }}
        </el-descriptions-item>
        <el-descriptions-item label="Base URL">
          {{ viewingProvider.baseUrl }}
        </el-descriptions-item>

        <el-descriptions-item label="启用差异编辑" :span="2">
          <el-tag :type="viewingProvider.config.diffEnabled ? 'success' : 'info'" size="small">
            {{ viewingProvider.config.diffEnabled ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="启用 TODO 列表" :span="2">
          <el-tag :type="viewingProvider.config.todoListEnabled ? 'success' : 'info'" size="small">
            {{ viewingProvider.config.todoListEnabled ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="启用推理增强" :span="2">
          <el-tag :type="viewingProvider.config.enableReasoningEffort ? 'warning' : 'info'" size="small">
            {{ viewingProvider.config.enableReasoningEffort ? '启用' : '禁用' }}
          </el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="模糊匹配阈值" :span="2">
          {{ viewingProvider.config.fuzzyMatchThreshold || 1 }}
        </el-descriptions-item>

        <el-descriptions-item label="速率限制（秒）" :span="2">
          {{ viewingProvider.config.rateLimitSeconds || 0 }}
        </el-descriptions-item>

        <el-descriptions-item label="连续错误限制" :span="2">
          {{ viewingProvider.config.consecutiveMistakeLimit || 3 }}
        </el-descriptions-item>

        <el-descriptions-item label="Tool Choice" :span="2">
          {{ viewingProvider.config.toolChoice || 'required' }}
        </el-descriptions-item>

        <el-descriptions-item label="Temperature" :span="2">
          {{ viewingProvider.config.temperature || 1.0 }}
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button type="primary" @click="showViewProviderDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh, Document } from '@element-plus/icons-vue';
import { ref, onMounted, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useLLMProviders } from '@/composables/llm/useLLMProviders';
import { apiManager } from '@/services/api';
import { getProviderConfig, getProviderDisplayName, getProviderTagType } from '@/config/llm-provider-config';

const props = defineProps<{
  workspaceId?: string;
}>();

const {
  llmSettings,
  loading,
  showProviderDialog,
  showViewProviderDialog,
  editingProvider,
  viewingProvider,
  saving,
  customHeadersText,
  providerForm,
  providerList,
  loadLLMSettings
} = useLLMProviders(props.workspaceId || '');

// Provider 测试相关
const testingProvider = ref(false);
const providerTestResult = ref<{ success: boolean; supported: boolean; message: string } | null>(null);

// 显示创建Provider对话框
const showCreateProviderDialog = () => {
  editingProvider.value = null;
  providerForm.value = {
    name: '',
    apiProvider: 'openai',
    openAiBaseUrl: 'https://api.openai.com/v1',
    openAiApiKey: '',
    openAiModelId: 'gpt-4o-mini',
    openAiLegacyFormat: false,
    openAiHeaders: {},
    diffEnabled: true,
    todoListEnabled: true,
    fuzzyMatchThreshold: 1,
    rateLimitSeconds: 0,
    consecutiveMistakeLimit: 3,
    enableReasoningEffort: true,
    toolChoice: 'required',
    temperature: 1.0,
    saveLocation: 'user' as 'user' | 'workspace'
  };
  customHeadersText.value = '';
  showProviderDialog.value = true;
};

// 当切换 API 类型时自动填充推荐的配置
const onApiProviderChange = () => {
  const provider = providerForm.value.apiProvider;
  const config = getProviderConfig(provider);
  if (config) {
    // 所有 OpenAI 兼容提供商统一使用 openAi* 字段
    providerForm.value.openAiBaseUrl = config.baseUrl;
    providerForm.value.openAiModelId = config.modelId;
    providerForm.value.openAiApiKey = '';

    // 处理自定义 headers
    if (config.headers) {
      providerForm.value.openAiHeaders = config.headers;
      customHeadersText.value = JSON.stringify(config.headers, null, 2);
    } else {
      providerForm.value.openAiHeaders = {};
      customHeadersText.value = '';
    }
  }
};

// 查看Provider
const viewProvider = (provider: LLMProvider) => {
  viewingProvider.value = provider;
  showViewProviderDialog.value = true;
};

// 编辑Provider
const editProvider = (provider: LLMProvider) => {
  editingProvider.value = provider.name;
  const config = llmSettings.value.allConfigs[provider.name];

  providerForm.value = {
    name: provider.name,
    apiProvider: config.apiProvider,
    openAiBaseUrl: config.openAiBaseUrl || '',
    openAiApiKey: config.openAiApiKey || '',
    openAiModelId: config.openAiModelId || '',
    openAiLegacyFormat: config.openAiLegacyFormat || false,
    openAiHeaders: config.openAiHeaders || {},
    diffEnabled: config.diffEnabled ?? true,
    todoListEnabled: config.todoListEnabled ?? true,
    fuzzyMatchThreshold: config.fuzzyMatchThreshold ?? 1,
    rateLimitSeconds: config.rateLimitSeconds ?? 0,
    consecutiveMistakeLimit: config.consecutiveMistakeLimit ?? 3,
    enableReasoningEffort: config.enableReasoningEffort ?? true,
    toolChoice: config.toolChoice ?? 'required',
    temperature: config.temperature ?? 1.0,
    saveLocation: 'user' as 'user' | 'workspace'
  };

  // 序列化 headers 到文本
  customHeadersText.value = Object.keys(providerForm.value.openAiHeaders).length > 0
    ? JSON.stringify(providerForm.value.openAiHeaders, null, 2)
    : '';

  showProviderDialog.value = true;
  // Reset test result
  providerTestResult.value = null;
};

// Test provider Tool Call support
const testProvider = async () => {
  if (!props.workspaceId) return;
  if (!providerForm.value.openAiModelId) {
    ElMessage.error('请填写模型 ID');
    return;
  }

  testingProvider.value = true;
  providerTestResult.value = null;

  try {
    // 解析自定义 Headers
    let headers: Record<string, string> = {};
    if (customHeadersText.value.trim()) {
      try {
        headers = JSON.parse(customHeadersText.value);
      } catch {
        ElMessage.error('自定义 Headers 格式错误，请输入有效的 JSON');
        testingProvider.value = false;
        return;
      }
    }

    const providerData = {
      ...providerForm.value,
      openAiHeaders: headers
    };

    const response = await apiManager.getWorkspacesApi().testLLMProvider(
      props.workspaceId,
      providerData
    );

    providerTestResult.value = response;

    if (response.supported) {
      ElMessage.success(response.message || '测试通过');
    } else {
      ElMessage.warning(response.message || '测试失败');
    }
  } catch (error: unknown) {
    const errMsg = error.response?.data?.detail || error.message || '测试失败';
    ElMessage.error(errMsg);
    providerTestResult.value = {
      success: false,
      supported: false,
      message: errMsg
    };
  } finally {
    testingProvider.value = false;
  }
};

// 保存Provider
const saveProvider = async () => {
  if (!props.workspaceId) return;
  if (!providerForm.value.name) {
    ElMessage.error('请输入 Provider 名称');
    return;
  }

  saving.value = true;
  try {
    // 解析自定义 Headers
    let headers: Record<string, string> = {};
    if (customHeadersText.value.trim()) {
      try {
        headers = JSON.parse(customHeadersText.value);
        if (typeof headers !== 'object' || headers === null) {
          throw new Error('Headers 必须是对象');
        }
      } catch {
        ElMessage.error('自定义 Headers 格式错误，请输入有效的 JSON');
        return;
      }
    }

    // 准备保存的数据
    const providerData = {
      ...providerForm.value,
      openAiHeaders: headers
    };

    if (editingProvider.value) {
      // 更新现有 Provider（编辑时不包含 saveLocation）
      const { saveLocation: _saveLocation, ...updateData } = providerData;
      await apiManager.getWorkspacesApi().updateLLMProvider(
        props.workspaceId,
        editingProvider.value,
        updateData
      );
      ElMessage.success('Provider 更新成功');
    } else {
      // 创建新 Provider（包含 saveLocation）
      await apiManager.getWorkspacesApi().createLLMProvider(
        props.workspaceId,
        providerData
      );
      ElMessage.success('Provider 创建成功');
    }

    showProviderDialog.value = false;
    await loadLLMSettings(); // 重新加载配置
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } } };
    ElMessage.error(err.response?.data?.detail || '操作失败');
    console.error('Failed to save provider:', error);
  } finally {
    saving.value = false;
  }
};

// 删除Provider
const deleteProvider = async (providerName: string) => {
  if (!props.workspaceId) return;

  try {
    await ElMessageBox.confirm(
      `确定要删除 Provider "${providerName}" 吗?此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    );

    saving.value = true;
    await apiManager.getWorkspacesApi().deleteLLMProvider(props.workspaceId, providerName);
    ElMessage.success('Provider 删除成功');
    await loadLLMSettings(); // 重新加载配置
  } catch (error: unknown) {
    if (error !== 'cancel') {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '删除失败');
      console.error('Failed to delete provider:', error);
    }
  } finally {
    saving.value = false;
  }
};

// Load settings on mount
onMounted(() => {
  if (props.workspaceId) {
    loadLLMSettings();
  }
});

// Reload when workspaceId changes
watch(() => props.workspaceId, (newId) => {
  if (newId) {
    loadLLMSettings();
  }
});
</script>

<style scoped>
.llm-providers-drawer {
  height: 100%;
  padding: 20px;
}

.drawer-content {
  padding: 0;
}
</style>
