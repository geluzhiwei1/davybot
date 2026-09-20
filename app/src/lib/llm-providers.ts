/**
 * LLM provider presets — 用户级与工作区级 LLM 配置面板共享。
 *
 * 每个预设携带官方 OpenAI 兼容端点（defaultBaseUrl），选择供应商时自动回填，
 * 减少手填出错。默认值与后端 config/settings.py 的 *_base_url 对齐；
 * 其余按各厂商官方 OpenAI 兼容端点填写。
 */

export interface ApiProviderPreset {
  /** 写入 config.apiProvider 的值；后端据此分流（仅 "ollama" 特判，其余走 OpenAI 兼容）。 */
  value: string;
  /** 下拉显示名。 */
  label: string;
  /** 官方 OpenAI 兼容 base_url（不含末尾斜杠）。留空表示自定义、不自动回填。 */
  defaultBaseUrl?: string;
}

export const API_PROVIDERS: ApiProviderPreset[] = [
  // 通用类别：不绑定具体供应商，base_url 完全由用户填写
  { value: "openai-compatible", label: "OpenAI 兼容（自定义）" },
  { value: "openai", label: "OpenAI", defaultBaseUrl: "https://api.openai.com/v1" },
  { value: "deepseek", label: "DeepSeek", defaultBaseUrl: "https://api.deepseek.com/v1" },
  { value: "ollama", label: "Ollama", defaultBaseUrl: "http://localhost:11434" },
  { value: "zhipu", label: "智谱 (GLM)", defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4" },
  {
    value: "qwen",
    label: "通义千问",
    defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  },
  { value: "moonshot", label: "Moonshot (Kimi)", defaultBaseUrl: "https://api.moonshot.cn/v1" },
  {
    value: "anthropic",
    label: "Anthropic (Claude)",
    defaultBaseUrl: "https://api.anthropic.com/v1",
  },
  { value: "openrouter", label: "OpenRouter", defaultBaseUrl: "https://openrouter.ai/api/v1" },
];

/**
 * 切换供应商后应使用的 base_url。
 *
 * 仅当当前 URL 为空、或仍是某个预设默认值时，才切换到新供应商的默认——
 * 这样用户已手填的自定义地址不会被误覆盖。选「OpenAI 兼容」时无默认，
 * 若当前仍是预设值则清空，交给用户填写。
 */
export function resolveBaseUrlOnProviderChange(
  provider: string,
  currentBaseUrl?: string,
  presets: ApiProviderPreset[] = API_PROVIDERS,
): string | undefined {
  const next = presets.find((p) => p.value === provider)?.defaultBaseUrl;
  const knownUrls = new Set(presets.map((p) => p.defaultBaseUrl).filter((u): u is string => !!u));
  const pristine = !currentBaseUrl || knownUrls.has(currentBaseUrl);
  return pristine ? next : currentBaseUrl;
}

/**
 * 从后端加载 provider 目录并转换为下拉预设。
 * 后端是单一数据源；本地 API_PROVIDERS 仅在后端不可用时兜底。
 */
export async function fetchProviderPresets(workspaceId: string): Promise<ApiProviderPreset[]> {
  if (!workspaceId) return API_PROVIDERS;
  try {
    const { llmApi } = await import("./api/llm");
    const res = await llmApi.listProviderCatalog(workspaceId);
    const catalog = res.providers ?? [];
    if (catalog.length === 0) return API_PROVIDERS;
    // 合并：后端目录在前，静态列表兜底补充未覆盖的条目（如 openai-compatible）
    const covered = new Set(catalog.map((c) => c.id));
    return [
      ...catalog.map((c) => ({ value: c.id, label: c.label, defaultBaseUrl: c.baseUrl })),
      ...API_PROVIDERS.filter((p) => !covered.has(p.value)),
    ];
  } catch {
    return API_PROVIDERS;
  }
}
