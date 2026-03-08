import { ref, computed } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { LLMProvider } from '@/types/llm';

export function useLLMProviders(workspaceId: string) {
  const llmSettings = ref({
    currentApiConfigName: null as string | null,
    allConfigs: {} as Record<string, unknown>,
    modeApiConfigs: {
      orchestrator: '',
      plan: '',
      do: '',
      check: '',
      act: ''
    }
  });

  const loading = ref(false);
  const showProviderDialog = ref(false);
  const showViewProviderDialog = ref(false);
  const editingProvider = ref<string | null>(null);
  const viewingProvider = ref<LLMProvider | null>(null);
  const saving = ref(false);
  const customHeadersText = ref('');

  const providerForm = ref({
    name: '',
    apiProvider: 'openai',
    openAiBaseUrl: 'https://api.openai.com/v1',
    openAiApiKey: '',
    openAiModelId: 'gpt-4',
    openAiLegacyFormat: false,
    ollamaBaseUrl: 'http://localhost:11434',
    ollamaModelId: 'llama2',
    ollamaApiKey: '',
    diffEnabled: true,
    todoListEnabled: true,
    fuzzyMatchThreshold: 0.8,
    rateLimitSeconds: 0,
    consecutiveMistakeLimit: 5,
    enableReasoningEffort: false,
    saveLocation: 'user' as 'user' | 'workspace'
  });

  // Provider 列表 - 合并用户级和工作区级配置
  const providerList = computed(() => {
    const providers: LLMProvider[] = [];

    // 添加用户级配置
    Object.entries(llmSettings.value.allConfigs).forEach(([name, config]: [string, unknown]) => {
      const providerConfig = config as { source?: string; config?: unknown };
      providers.push({
        name,
        source: providerConfig.source || 'user',
        is_default: name === llmSettings.value.currentApiConfigName,
        apiProvider: '',
        modelId: '',
        baseUrl: '',
        config: providerConfig
      } as LLMProvider);
    });

    return providers;
  });

  // 加载LLM设置
  const loadLLMSettings = async () => {
    if (!workspaceId) return;
    loading.value = true;
    try {
      const response = await apiManager.getWorkspacesApi().getLLMSettingsAllLevels(workspaceId);
      // 类型转换以适配API响应
      llmSettings.value = {
        currentApiConfigName: response.settings.current_config || '',
        allConfigs: response.settings.user?.concat(response.settings.workspace || []).reduce((acc, item) => {
          acc[item.name] = item;
          return acc;
        }, {} as Record<string, unknown>) || {},
        modeApiConfigs: response.settings.mode_configs || {}
      };
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '加载LLM配置失败');
      console.error('Failed to load LLM settings:', error);
    } finally {
      loading.value = false;
    }
  };

  // 显示创建Provider对话框
  const showCreateProviderDialog = () => {
    editingProvider.value = null;
    providerForm.value = {
      name: '',
      apiProvider: 'openai',
      openAiBaseUrl: 'https://api.openai.com/v1',
      openAiApiKey: '',
      openAiModelId: 'gpt-4',
      openAiLegacyFormat: false,
      ollamaBaseUrl: 'http://localhost:11434',
      ollamaModelId: 'llama2',
      ollamaApiKey: '',
      diffEnabled: true,
      todoListEnabled: true,
      fuzzyMatchThreshold: 0.8,
      rateLimitSeconds: 0,
      consecutiveMistakeLimit: 5,
      enableReasoningEffort: false,
      saveLocation: 'user'
    };
    customHeadersText.value = '';
    showProviderDialog.value = true;
  };

  // 查看Provider
  const viewProvider = (provider: LLMProvider) => {
    viewingProvider.value = provider;
    showViewProviderDialog.value = true;
  };

  // 编辑Provider
  const editProvider = (provider: LLMProvider) => {
    editingProvider.value = provider.name;
    const config = llmSettings.value.allConfigs[provider.name] as {
      config?: Record<string, unknown>;
    };
    const providerConfig = config?.config || {};

    providerForm.value = {
      name: provider.name,
      apiProvider: (providerConfig.apiProvider as string) || 'openai',
      openAiBaseUrl: (providerConfig.openAiBaseUrl as string) || 'https://api.openai.com/v1',
      openAiApiKey: (providerConfig.openAiApiKey as string) || '',
      openAiModelId: (providerConfig.openAiModelId as string) || 'gpt-4',
      openAiLegacyFormat: (providerConfig.openAiLegacyFormat as boolean) || false,
      ollamaBaseUrl: (providerConfig.ollamaBaseUrl as string) || 'http://localhost:11434',
      ollamaModelId: (providerConfig.ollamaModelId as string) || 'llama2',
      ollamaApiKey: (providerConfig.ollamaApiKey as string) || '',
      diffEnabled: (providerConfig.diffEnabled as boolean) !== false,
      todoListEnabled: (providerConfig.todoListEnabled as boolean) !== false,
      fuzzyMatchThreshold: (providerConfig.fuzzyMatchThreshold as number) || 0.8,
      rateLimitSeconds: (providerConfig.rateLimitSeconds as number) || 0,
      consecutiveMistakeLimit: (providerConfig.consecutiveMistakeLimit as number) || 5,
      enableReasoningEffort: (providerConfig.enableReasoningEffort as boolean) || false,
      saveLocation: (providerConfig.saveLocation as 'user' | 'workspace') || 'user'
    };

    // 处理自定义headers
    if (providerConfig.openAiHeaders) {
      try {
        customHeadersText.value = JSON.stringify(providerConfig.openAiHeaders, null, 2);
      } catch {
        customHeadersText.value = '';
      }
    } else {
      customHeadersText.value = '';
    }

    showProviderDialog.value = true;
  };

  // 删除Provider
  const deleteProvider = async (providerName: string) => {
    if (!workspaceId) return;

    try {
      await ElMessageBox.confirm(
        `确定要删除 Provider "${providerName}" 吗?此操作不可恢复。`,
        '确认删除',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning'
        }
      );

      saving.value = true;
      await apiManager.getWorkspacesApi().deleteLLMProvider(workspaceId, providerName);
      ElMessage.success('Provider 删除成功');
      await loadLLMSettings();
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

  // 获取Provider显示名称
  const getProviderDisplayName = (apiProvider: string) => {
    const names: Record<string, string> = {
      openai: 'OpenAI',
      ollama: 'Ollama',
      anthropic: 'Anthropic',
      azure: 'Azure OpenAI'
    };
    return names[apiProvider] || apiProvider;
  };

  // 获取Provider标签类型
  const getProviderTagType = (apiProvider: string) => {
    const types: Record<string, string> = {
      openai: 'primary',
      ollama: 'success',
      anthropic: 'warning',
      azure: 'info'
    };
    return types[apiProvider] || 'default';
  };

  return {
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
    loadLLMSettings,
    showCreateProviderDialog,
    viewProvider,
    editProvider,
    deleteProvider,
    getProviderDisplayName,
    getProviderTagType
  };
}
