/**
 * agent-context-store · §9.3.2 页面上下文契约
 *
 * 全局唯一实例，承载「当前页面正在做什么」的语义，供 `<FirmAgentDock />` 在
 * 任何路由下展示上下文摘要 + 建议动作。Page → Page 导航会自动清空（上一个
 * useAgentContext 卸载时 clearContext，下一个挂载时 setContext）。
 *
 * 与 `firm-agent-context-store.ts` 区别：
 *   - 那个是 FirmAgent **内部** fleet 状态（子 Agent status）
 *   - 这个是 **外部页面** 对 FirmAgent 的输入（我在看什么、想做什么）
 *
 * 设计约束（KISS）：
 *   - 单一 current，last-write-wins。多组件同时 setContext 时子组件覆盖父组件，
 *     但子组件卸载时父组件的 effect 不会重跑 → 可能 stale。MVP 不解决，调用方
 *     自行保证「每页只在一处调用」。详见 project/docs/FirmAgent终极版.md §9.3.2。
 */
import { create } from "zustand";

export interface AgentContextSuggestedAction {
  /** 按钮文案，如「分析此案证据链」 */
  label: string;
  /** 点击后填入 FirmAgent 输入框的提示词（不自动发送） */
  prompt: string;
}

export interface AgentContextSummary {
  /** 页面模块标识：`firm-agent` | `case` | `contract` | `dashboard` | ... */
  module: string;
  /** 实体类型（可选）：`case` | `contract` | `task` | ... */
  entityType?: string;
  /** 实体 ID（可选，跳转/溯源用） */
  entityId?: string;
  /** 一句话摘要：人类可读，如「环球科技案 · 待答辩」 */
  summary: string;
  /** 建议动作（≤ 4 个，太多会撑爆 Sheet header） */
  suggestedActions?: AgentContextSuggestedAction[];
}

interface State {
  current: AgentContextSummary | null;
  setContext: (ctx: AgentContextSummary) => void;
  clearContext: () => void;
}

export const useAgentContextStore = create<State>((set) => ({
  current: null,
  setContext: (ctx) => set({ current: ctx }),
  clearContext: () => set((s) => (s.current === null ? {} : { current: null })),
}));
