/**
 * SECTIONS 可见性表 (多模式统一方案 §L4)
 *
 * 前端禁止按 mode 字符串分支逻辑 (硬规则 §6-1); 可见性只查本表:
 * - desktop: true  → 构建期能力 (Tauri 壳, __APP_TARGET__)
 * - caps: [...]    → 运行期能力 (GET /api/runtime-info)
 * 前端隐藏 ≠ 安全: 后端守卫才是权威, 无能力操作照常 4xx。
 */
import { IS_DESKTOP, isTauri } from "@/lib/platform";

export interface SectionDef {
  /** 需 Tauri 壳: desktop 构建, 或 web 构建运行于壳内 (light-app, isTauri 兜底) */
  desktop?: boolean;
  /** 运行期能力要求 (全部满足才可见; 空数组 = 任何模式可见) */
  caps?: readonly string[];
}

export const SECTIONS = {
  // ── 用户设置抽屉 tab ──
  llm: { caps: [] },
  mcp: { caps: [] },
  skills: { caps: [] },
  memory: { caps: [] },
  knowledge: { caps: [] },
  security: { caps: [] },
  preferences: { caps: [] },
  about: { caps: [] },
  // ── 功能区块 / 路由页 ──
  localMcp: { desktop: true, caps: [] }, // 本机私有 MCP, 需 Tauri 壳
  sandbox: { caps: ["sandbox"] }, // server/tui 无此 cap → 整块隐藏
  modules: { caps: ["market"] }, // 模块订阅
  devices: { caps: ["relay"] }, // 我的设备
} as const satisfies Record<string, SectionDef>;

export type SectionKey = keyof typeof SECTIONS;

export function isSectionVisible(key: SectionKey, caps: readonly string[] | null): boolean {
  const def = SECTIONS[key] as SectionDef;
  // desktop 段需 Tauri 壳: desktop 构建恒可见; web 构建跑在壳内(light-app 加载 saas
  // bundle)亦可见 —— 运行时 isTauri() 兜底,纯浏览器才隐藏。对位 LocalMcpSection 自检。
  if (def.desktop && !IS_DESKTOP && !isTauri()) return false;
  const required = def.caps ?? [];
  if (required.length === 0) return true;
  // caps=null (未加载/失联) → 按 FAST FAIL 最小安全集处理: 隐藏
  return !!caps && required.every((c) => caps.includes(c));
}
