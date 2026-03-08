export interface LLMProvider {
  name: string;
  source: 'user' | 'workspace';
  is_default: boolean;
  apiProvider: string;
  modelId: string;
  baseUrl: string;
  config: {
    source?: string;
    config?: {
      apiProvider?: string;
      openAiBaseUrl?: string;
      openAiModelId?: string;
      diffEnabled?: boolean;
      todoListEnabled?: boolean;
      enableReasoningEffort?: boolean;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
}
