/**
 * 生图模型选择通用件(拆库方案 §5.2 解倒挂)——核心 ⇄ biz 共享。
 *
 * modelOptions/ImageModelOption 原定义于 lib/social/images.ts(B3 后迁入 biz/social);
 * 核心 hooks/use-llm-providers.ts 依赖它们(文字/生图模型目录属跨域 LLM 能力),
 * 故下沉核心,biz 侧 re-export 维持旧出口。
 */

export interface ImageModelOption {
  /** llmApi 服务商名(sidecar provider 参数原样传回) */
  name: string;
  /** 展示:model id */
  model: string;
  source: string;
}

/** llmApi.listUserProviders() 响应的最小结构(user+workspace 合并,去重同名;容忍 null 畸形条目) */
export function modelOptions(settings: {
  current_config?: string | null;
  user?: Array<{ name: string; config?: { config?: { openAiModelId?: string } } } | null>;
  workspace?: Array<{ name: string; config?: { config?: { openAiModelId?: string } } } | null>;
}): ImageModelOption[] {
  const out = new Map<string, ImageModelOption>();
  for (const item of [...(settings.workspace ?? []), ...(settings.user ?? [])]) {
    if (!item?.name || out.has(item.name)) continue;
    out.set(item.name, {
      name: item.name,
      model: item.config?.config?.openAiModelId ?? "",
      source: "provider",
    });
  }
  return [...out.values()];
}
