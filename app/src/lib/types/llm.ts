/**
 * LLM provider type definitions — migrated from legalbot/webui/src/types/llm.ts
 */

export interface LLMProvider {
  name: string;
  source: "user" | "workspace";
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

export interface LLMConfig {
  provider: string;
  model: string;
  baseUrl?: string;
  apiKey?: string;
  temperature?: number;
  maxTokens?: number;
  topP?: number;
}

export interface LLMUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  cost?: number;
}
