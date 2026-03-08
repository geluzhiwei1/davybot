import { ref, computed } from 'vue';
import { apiManager } from '@/services/api';
import { ElMessage } from 'element-plus';
import type { LLMProvider } from '@/types/llm';

interface ProviderConfig {
  apiProvider?: string;
  openAiBaseUrl?: string;
  openAiApiKey?: string;
  openAiModelId?: string;
  openAiLegacyFormat?: boolean;
  openAiHeaders?: Record<string, string>;
  diffEnabled?: boolean;
  todoListEnabled?: boolean;
  fuzzyMatchThreshold?: number;
  rateLimitSeconds?: number;
  consecutiveMistakeLimit?: number;
  enableReasoningEffort?: boolean;
  toolChoice?: string | null;
  temperature?: number | null;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
  source?: string;
  config?: ProviderConfig;
}

export function useLLMProviders(workspaceId: string) {
  const llmSettings = ref({
    currentApiConfigName: null as string | null,
    allConfigs: {} as Record<string, ProviderConfig>,
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
    openAiModelId: 'gpt-4o-mini',
    openAiLegacyFormat: false,
    openAiHeaders: {} as Record<string, string>,
    diffEnabled: true,
    todoListEnabled: true,
    fuzzyMatchThreshold: 1,
    rateLimitSeconds: 0,
    consecutiveMistakeLimit: 3,
    enableReasoningEffort: true,
    toolChoice: 'required' as string | null,
    temperature: 1.0 as number | null,
    timeout: 600 as number,
    maxRetries: 3 as number,
    retryDelay: 2.0 as number,
    saveLocation: 'user' as 'user' | 'workspace'
  });

  // Provider 列表 - 合并用户级和工作区级配置
  const providerList = computed(() => {
    const providers: LLMProvider[] = [];

    // 添加用户级配置
    Object.entries(llmSettings.value.allConfigs).forEach(([name, config]: [string, ProviderConfig]) => {
      // 处理嵌套的config结构：如果是嵌套格式则提取内部config
      const extractedConfig = config && typeof config === 'object' && 'config' in config
        ? (config as { config?: ProviderConfig }).config
        : config;

      // 确保extractedConfig不为undefined
      const providerConfig: ProviderConfig = extractedConfig || {};

      providers.push({
        name,
        source: config.source || 'user',
        is_default: name === llmSettings.value.currentApiConfigName,
        apiProvider: providerConfig.apiProvider || 'openai',
        modelId: providerConfig.openAiModelId || 'N/A',
        baseUrl: providerConfig.openAiBaseUrl || 'N/A',
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
        allConfigs: {} as Record<string, ProviderConfig>,
        modeApiConfigs: response.settings.mode_configs || {}
      };

      // 合并用户级和工作区级配置到 allConfigs
      const userConfigs = response.settings.user || [];
      const workspaceConfigs = response.settings.workspace || [];

      for (const item of userConfigs) {
        // 处理嵌套的config结构：item.config.config 或 item.config
        const configData = item.config && typeof item.config === 'object' && 'config' in item.config
          ? (item.config as { config?: ProviderConfig }).config
          : item.config;

        llmSettings.value.allConfigs[item.name] = {
          ...(configData || {}),
          source: 'user'
        };
      }

      for (const item of workspaceConfigs) {
        // 处理嵌套的config结构：item.config.config 或 item.config
        const configData = item.config && typeof item.config === 'object' && 'config' in item.config
          ? (item.config as { config?: ProviderConfig }).config
          : item.config;

        llmSettings.value.allConfigs[item.name] = {
          ...(configData || {}),
          source: 'workspace'
        };
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      ElMessage.error(err.response?.data?.detail || '加载LLM配置失败');
      console.error('Failed to load LLM settings:', error);
    } finally {
      loading.value = false;
    }
  };

  // 获取Provider显示名称
  const getProviderDisplayName = (apiProvider: string) => {
    const names: Record<string, string> = {
      openai: 'OpenAI兼容',
      glm: 'GLM (智谱)',
      ollama: 'Ollama (本地)'
    };
    return names[apiProvider] || apiProvider;
  };

  // 获取Provider标签类型
  const getProviderTagType = (apiProvider: string) => {
    const types: Record<string, string> = {
      openai: 'primary',
      glm: 'success',
      ollama: 'info'
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
    getProviderDisplayName,
    getProviderTagType
  };
}
