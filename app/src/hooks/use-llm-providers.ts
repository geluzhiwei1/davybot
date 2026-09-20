/**
 * useLlmProviders —— 模型选择目录 hook(文字/生图共用)。
 *
 * 两个来源合并,网关优先:
 * 1. **LLM Gateway 官方模型**(user-system llm-pricing 管理页配置;
 *    listGatewayModels 经登录态拉取,调用走用户积分,零本地配置)
 * 2. 本地服务商(llmApi 用户级+工作区级,自备 key)
 *
 * 选中值 = 模型 id 或服务商名(引擎三级解析:本地 → 网关注册 → 当前);
 * 记忆在 localStorage(storageKey),默认=记忆>网关目录首个>本地首个;
 * 两源皆空 → failed(界面显示登录/配置引导,不阻断宿主面板其余操作)。
 */
import { useEffect, useState } from "react";

import { llmApi } from "@/lib/api/llm";
import { listGatewayModels } from "@/lib/llm-gateway-service";
import { modelOptions, type ImageModelOption } from "@/lib/image-models";

export interface LlmProvidersState {
  options: ImageModelOption[];
  provider: string;
  setProvider: (name: string) => void;
  failed: boolean;
  loading: boolean;
}

export function useLlmProviders(storageKey: string): LlmProvidersState {
  const [options, setOptions] = useState<ImageModelOption[]>([]);
  const [failed, setFailed] = useState(false);
  const [provider, setProviderRaw] = useState(() => localStorage.getItem(storageKey) || "");

  useEffect(() => {
    let alive = true;
    (async () => {
      // 网关官方模型(登录态;失败静默——未登录/网关不可达时仍可用本地服务商)
      const gateway: ImageModelOption[] = [];
      try {
        const models = await listGatewayModels();
        for (const m of models) {
          if (m.is_active === false) continue;
          gateway.push({
            name: m.id,
            model: m.display_name || m.id,
            source: "gateway",
          });
        }
      } catch {
        /* 未登录或网关不可达 */
      }
      // 本地服务商(自备 key;失败静默)
      let local: ImageModelOption[] = [];
      try {
        const r = await llmApi.listUserProviders();
        local = modelOptions(r.settings ?? {});
      } catch {
        /* 无本地配置 */
      }
      if (!alive) return;
      const merged = [...gateway, ...local.filter((l) => !gateway.some((g) => g.name === l.name))];
      if (!merged.length) {
        setFailed(true);
        return;
      }
      setOptions(merged);
      // 默认:记忆值(仍存在)> 网关目录首个 > 本地首个
      setProviderRaw((p) => (p && merged.some((o) => o.name === p) ? p : merged[0].name));
    })();
    return () => {
      alive = false;
    };
  }, []);

  const setProvider = (name: string) => {
    setProviderRaw(name);
    localStorage.setItem(storageKey, name);
  };

  return { options, provider, setProvider, failed, loading: false };
}
