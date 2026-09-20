/**
 * RuntimeInfo store — 运行模式与能力 (多模式统一方案 §L4)
 *
 * boot 时拉一次 (RootComponent); 拉取失败回退最小安全集 (FAST FAIL):
 * - 老后端 (无 /api/runtime-info, 404) → 降级读旧 /api/system/deployment-mode,
 *   capabilities 取保底集 (维持现状, 不隐藏既有入口);
 * - 完全失联 → info=null, 仅 caps:[] 的区块可见。
 * 不持久化: capabilities 非用户偏好。
 */
import { create } from "zustand";
import { runtimeApi, type RuntimeInfo } from "@/lib/api/runtime";
import { sandboxProviderApi } from "@/lib/api/sandbox";

// 老后端保底集: 维持现状 (sandbox/market/relay 可见), 不因降级隐藏入口
const FALLBACK_CAPS = ["sandbox", "market", "relay"];

interface RuntimeStoreState {
  info: RuntimeInfo | null;
  loaded: boolean;
  load: () => Promise<void>;
}

export const useRuntimeStore = create<RuntimeStoreState>((set) => ({
  info: null,
  loaded: false,
  load: async () => {
    try {
      const info = await runtimeApi.getRuntimeInfo();
      set({ info, loaded: true });
      return;
    } catch {
      // 降级链: 老后端无 runtime-info → 旧 deployment-mode 端点
    }
    try {
      const { mode } = await sandboxProviderApi.getDeploymentMode();
      set({
        info: {
          mode: mode === "saas" ? "saas" : "desktop",
          deployment_class: mode,
          capabilities: FALLBACK_CAPS,
        },
        loaded: true,
      });
    } catch {
      // 完全失联 → 最小安全集 (info=null: 仅无 caps 要求的区块可见)
      set({ info: null, loaded: true });
    }
  },
}));

/** useCaps() — 能力查询 hook (SECTIONS 表的唯一消费口) */
export function useCaps() {
  const info = useRuntimeStore((s) => s.info);
  const loaded = useRuntimeStore((s) => s.loaded);
  return {
    loaded,
    mode: info?.mode ?? null,
    caps: info?.capabilities ?? null,
    hasCap: (cap: string) => (info ? info.capabilities.includes(cap) : false),
  };
}
