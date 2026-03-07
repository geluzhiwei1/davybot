/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * LLM Provider 类型定义
 */
export type LLMProvider =
  | 'openai'
  | 'deepseek'
  | 'moonshot'
  | 'qwen'
  | 'glm'
  | 'gemini'
  | 'claude'
  | 'minimax'
  | 'openrouter'
  | 'ollama';

/**
 * Element Plus Tag 类型
 */
export type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info';

/**
 * Provider 分类
 */
export type ProviderCategory = 'domestic' | 'international' | 'local';

/**
 * Provider API 配置
 */
export interface ProviderApiConfig {
  baseUrl: string;
  modelId: string;
  headers?: Record<string, string>;
}

/**
 * Provider 显示配置
 */
export interface ProviderDisplayConfig {
  displayName: string;
  tagType: TagType;
  dividerTitle: string;
}

/**
 * Provider 完整配置（内部使用）
 */
interface ProviderFullConfig {
  api: ProviderApiConfig;
  display: ProviderDisplayConfig;
  docsUrl: string;
  models: string[];
  category: ProviderCategory;
}

/**
 * Provider 推荐配置（对外暴露，保持向后兼容）
 */
export interface ProviderConfig {
  baseUrl: string;
  modelId: string;
  headers?: Record<string, string>;
  docsUrl: string;
}

/**
 * Provider 显示信息（对外暴露，保持向后兼容）
 */
export interface ProviderDisplayInfo {
  displayName: string;
  tagType: TagType;
  dividerTitle: string;
  docsUrl: string;
}

/**
 * Provider 完整信息（对外暴露，保持向后兼容）
 */
export interface ProviderInfo {
  config: ProviderConfig;
  display: ProviderDisplayInfo;
  models: string[];
}

/**
 * 所有 LLM Provider 的完整配置
 * 统一管理，方便维护和扩展
 */
export const LLM_PROVIDERS: Record<LLMProvider, ProviderFullConfig> = {
  openai: {
    api: {
      baseUrl: 'https://api.openai.com/v1',
      modelId: 'gpt-4o-mini'
    },
    display: {
      displayName: 'OpenAI兼容',
      tagType: 'primary',
      dividerTitle: 'OpenAI兼容 配置'
    },
    docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#openai',
    models: [
      // OpenAI兼容模式不提供预定义模型，用户可以自由输入
    ],
    category: 'international'
  },

  // deepseek: {
  //   api: {
  //     baseUrl: 'https://api.deepseek.com',
  //     modelId: 'deepseek-chat'
  //   },
  //   display: {
  //     displayName: 'DeepSeek',
  //     tagType: 'success',
  //     dividerTitle: 'DeepSeek 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#deepseek',
  //   models: [
  //     'deepseek-chat',
  //     'deepseek-coder',
  //     'deepseek-reasoner'
  //   ],
  //   category: 'domestic'
  // },

  // moonshot: {
  //   api: {
  //     baseUrl: 'https://api.moonshot.cn/v1',
  //     modelId: 'moonshot-v1-8k'
  //   },
  //   display: {
  //     displayName: 'Moonshot (Kimi)',
  //     tagType: 'success',
  //     dividerTitle: 'Moonshot 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#moonshot',
  //   models: [
  //     'moonshot-v1-8k',
  //     'moonshot-v1-32k',
  //     'moonshot-v1-128k'
  //   ],
  //   category: 'domestic'
  // },

  // qwen: {
  //   api: {
  //     baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  //     modelId: 'qwen-turbo'
  //   },
  //   display: {
  //     displayName: 'Qwen (通义千问)',
  //     tagType: 'success',
  //     dividerTitle: 'Qwen 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#qwen',
  //   models: [
  //     'qwen-turbo',
  //     'qwen-plus',
  //     'qwen-max',
  //     'qwen-long',
  //     'qwq-32b-preview'
  //   ],
  //   category: 'domestic'
  // },

  glm: {
    api: {
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      modelId: 'glm-4.7'
    },
    display: {
      displayName: 'GLM (智谱)',
      tagType: 'success',
      dividerTitle: 'GLM 配置'
    },
    docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#glm',
    models: [
      'glm-5',
      'glm-4.7',
      'GLM-4.7-FlashX',
      'glm-4.6',
    ],
    category: 'domestic'
  },

  // gemini: {
  //   api: {
  //     baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
  //     modelId: 'gemini-2.0-flash-exp'
  //   },
  //   display: {
  //     displayName: 'Gemini',
  //     tagType: 'warning',
  //     dividerTitle: 'Gemini 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#gemini',
  //   models: [
  //     'gemini-2.0-flash-exp',
  //     'gemini-1.5-pro',
  //     'gemini-1.5-flash',
  //     'gemini-1.5-flash-8b'
  //   ],
  //   category: 'international'
  // },

  // claude: {
  //   api: {
  //     baseUrl: 'https://api.anthropic.com/v1',
  //     modelId: 'claude-3-5-sonnet-20241022'
  //   },
  //   display: {
  //     displayName: 'Claude',
  //     tagType: 'danger',
  //     dividerTitle: 'Claude 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#claude',
  //   models: [
  //     'claude-3-5-sonnet-20241022',
  //     'claude-3-5-haiku-20241022',
  //     'claude-3-opus-20240229',
  //     'claude-3-sonnet-20240229',
  //     'claude-3-haiku-20240307'
  //   ],
  //   category: 'international'
  // },

  // minimax: {
  //   api: {
  //     baseUrl: 'https://api.minimax.chat/v1',
  //     modelId: 'MiniMax-M2.1'
  //   },
  //   display: {
  //     displayName: 'MiniMax',
  //     tagType: 'info',
  //     dividerTitle: 'MiniMax 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#minimax',
  //   models: [
  //     'MiniMax-M2.5',
  //     'MiniMax-M2.5-highspeed',
  //     'MiniMax-M2.1',
  //     'MiniMax-M2.1-highspeed',
  //   ],
  //   category: 'domestic'
  // // },

  // openrouter: {
  //   api: {
  //     baseUrl: 'https://openrouter.ai/api/v1',
  //     modelId: 'openai/gpt-4o'
  //   },
  //   display: {
  //     displayName: 'OpenRouter',
  //     tagType: 'primary',
  //     dividerTitle: 'OpenRouter 配置'
  //   },
  //   docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#openrouter',
  //   models: [
  //     'openai/gpt-4o',
  //     'openai/gpt-4o-mini',
  //     'openai/gpt-4-turbo',
  //     'openai/gpt-3.5-turbo',
  //     'anthropic/claude-3.5-sonnet',
  //     'anthropic/claude-3-opus',
  //     'google/gemini-pro-1.5'
  //   ],
  //   category: 'international'
  // },

  ollama: {
    api: {
      baseUrl: 'http://localhost:11434/v1',
      modelId: 'qwen3.5:9b'
    },
    display: {
      displayName: 'Ollama (本地)',
      tagType: 'info',
      dividerTitle: 'Ollama 配置'
    },
    docsUrl: 'http://www.davybot.com/books/book/providers/llm.html#ollama',
    models: [
      'qwen3.5:9b',
      'llama3.1',
      'llama3.2',
      'qwen2.5:7b',
      'deepseek-coder:6.7b',
    ],
    category: 'local'
  }
};

// ==================== 向后兼容的导出（已弃用，建议直接使用 LLM_PROVIDERS）====================

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].api 替代
 */
export const PROVIDER_CONFIGS: Record<LLMProvider, ProviderConfig> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = {
      baseUrl: value.api.baseUrl,
      modelId: value.api.modelId,
      headers: value.api.headers,
      docsUrl: value.docsUrl
    };
    return acc;
  },
  {} as Record<LLMProvider, ProviderConfig>
);

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].models 替代
 */
export const PROVIDER_MODELS: Record<LLMProvider, string[]> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = value.models;
    return acc;
  },
  {} as Record<LLMProvider, string[]>
);

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].display.displayName 替代
 */
export const PROVIDER_DISPLAY_NAMES: Record<LLMProvider, string> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = value.display.displayName;
    return acc;
  },
  {} as Record<LLMProvider, string>
);

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].display.tagType 替代
 */
export const PROVIDER_TAG_TYPES: Record<LLMProvider, TagType> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = value.display.tagType;
    return acc;
  },
  {} as Record<LLMProvider, TagType>
);

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].display.dividerTitle 替代
 */
export const PROVIDER_DIVIDER_TITLES: Record<LLMProvider, string> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = value.display.dividerTitle;
    return acc;
  },
  {} as Record<LLMProvider, string>
);

/**
 * @deprecated 使用 LLM_PROVIDERS[provider].docsUrl 替代
 */
export const PROVIDER_DOCS_URLS: Record<LLMProvider, string> = Object.entries(LLM_PROVIDERS).reduce(
  (acc, [key, value]) => {
    acc[key as LLMProvider] = value.docsUrl;
    return acc;
  },
  {} as Record<LLMProvider, string>
);

// ==================== 工具函数 ====================

/**
 * 获取 Provider 显示名称
 */
export function getProviderDisplayName(provider: string): string {
  return LLM_PROVIDERS[provider as LLMProvider]?.display.displayName || provider;
}

/**
 * 获取 Provider Tag 类型
 */
export function getProviderTagType(provider: string): TagType {
  return LLM_PROVIDERS[provider as LLMProvider]?.display.tagType || 'info';
}

/**
 * 获取 Provider 分隔标题
 */
export function getProviderDividerTitle(provider: string): string {
  return LLM_PROVIDERS[provider as LLMProvider]?.display.dividerTitle || 'API 配置';
}

/**
 * 获取 Provider 文档 URL
 */
export function getProviderDocsUrl(provider: string): string {
  return LLM_PROVIDERS[provider as LLMProvider]?.docsUrl || '';
}

/**
 * 获取 Provider 推荐配置
 */
export function getProviderConfig(provider: string): ProviderConfig | undefined {
  const providerConfig = LLM_PROVIDERS[provider as LLMProvider];
  if (!providerConfig) {
    return undefined;
  }

  return {
    baseUrl: providerConfig.api.baseUrl,
    modelId: providerConfig.api.modelId,
    headers: providerConfig.api.headers,
    docsUrl: providerConfig.docsUrl
  };
}

/**
 * 获取 Provider API 配置
 */
export function getProviderApiConfig(provider: string): ProviderApiConfig | undefined {
  return LLM_PROVIDERS[provider as LLMProvider]?.api;
}

/**
 * 判断是否为 Ollama Provider
 */
export function isOllamaProvider(provider: string): boolean {
  return provider === 'ollama';
}

/**
 * 获取 Provider 模型列表
 */
export function getProviderModels(provider: string): string[] {
  return LLM_PROVIDERS[provider as LLMProvider]?.models || [];
}

/**
 * 获取 Provider 分类
 */
export function getProviderCategory(provider: string): ProviderCategory {
  return LLM_PROVIDERS[provider as LLMProvider]?.category || 'international';
}

/**
 * 获取 Provider 完整显示信息
 */
export function getProviderDisplayInfo(provider: string): ProviderDisplayInfo | undefined {
  const providerConfig = LLM_PROVIDERS[provider as LLMProvider];
  if (!providerConfig) {
    return undefined;
  }

  return {
    displayName: providerConfig.display.displayName,
    tagType: providerConfig.display.tagType,
    dividerTitle: providerConfig.display.dividerTitle,
    docsUrl: providerConfig.docsUrl
  };
}

/**
 * 获取 Provider 完整信息（包括配置、显示、模型）
 */
export function getProviderInfo(provider: string): ProviderInfo | undefined {
  const providerConfig = LLM_PROVIDERS[provider as LLMProvider];
  if (!providerConfig) {
    return undefined;
  }

  return {
    config: {
      baseUrl: providerConfig.api.baseUrl,
      modelId: providerConfig.api.modelId,
      headers: providerConfig.api.headers,
      docsUrl: providerConfig.docsUrl
    },
    display: {
      displayName: providerConfig.display.displayName,
      tagType: providerConfig.display.tagType,
      dividerTitle: providerConfig.display.dividerTitle,
      docsUrl: providerConfig.docsUrl
    },
    models: providerConfig.models
  };
}

// ==================== Provider 分类列表 ====================

/**
 * 所有 Provider 类型列表（从 LLM_PROVIDERS 动态生成）
 */
export const ALL_PROVIDERS: LLMProvider[] = Object.keys(LLM_PROVIDERS) as LLMProvider[];

/**
 * 国内提供商（不需要代理）
 * 从 LLM_PROVIDERS 中动态筛选 category === 'domestic' 的 Provider
 */
export const DOMESTIC_PROVIDERS: LLMProvider[] = Object.entries(LLM_PROVIDERS)
  .filter(([_, config]) => config.category === 'domestic')
  .map(([key]) => key as LLMProvider);

/**
 * 国际提供商（可能需要代理）
 * 从 LLM_PROVIDERS 中动态筛选 category === 'international' 的 Provider
 */
export const INTERNATIONAL_PROVIDERS: LLMProvider[] = Object.entries(LLM_PROVIDERS)
  .filter(([_, config]) => config.category === 'international')
  .map(([key]) => key as LLMProvider);

/**
 * 本地提供商
 * 从 LLM_PROVIDERS 中动态筛选 category === 'local' 的 Provider
 */
export const LOCAL_PROVIDERS: LLMProvider[] = Object.entries(LLM_PROVIDERS)
  .filter(([_, config]) => config.category === 'local')
  .map(([key]) => key as LLMProvider);
