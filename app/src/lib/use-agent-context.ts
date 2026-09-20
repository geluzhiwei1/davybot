/**
 * useAgentContext · §9.3.2 页面上下文注入 hook
 *
 * 在路由组件顶层调用一次，将当前页的语义写入 `agent-context-store`。
 * `<FirmAgentDock />` 全局订阅此 store，在 Sheet header 展示上下文摘要 +
 * 建议动作（除 `module === "firm-agent"` 外，那是 FirmAgent 自己的主场，Dock 隐藏）。
 *
 * 调用契约：
 *   - **每页只在一处调用**（顶层路由组件）。多组件同时调用时 last-write-wins，
 *     但子组件卸载不会让父组件的 effect 重跑，会留 stale。
 *   - **传入对象必须引用稳定**（用 useMemo 包裹）。本 hook 用引用比较 dep。
 *   - **支持 null**：当上下文尚未就绪（如 task/workspace 未加载）时传 null，
 *     hook 会跳过 setContext 但**仍保留 clearContext 清理**，确保导航离开时
 *     不会留 stale。这样可以在「早返回」之前无副作用地调用，遵守 Rules of Hooks。
 *
 * @example
 *   // 在 routes/smart-firm.cases.$caseId.tsx 顶层
 *   const ctx = useMemo(
 *     () => ({
 *       module: "case",
 *       entityType: "case",
 *       entityId: caseId,
 *       summary: `${caseData.case_name} · ${caseData.status}`,
 *       suggestedActions: [
 *         { label: "分析证据链", prompt: `分析案件 ${caseData.case_name} 的证据链` },
 *       ],
 *     }),
 *     [caseId, caseData],
 *   );
 *   useAgentContext(ctx);
 *
 * 详见 project/docs/FirmAgent终极版.md §9.3.2 / §13.3。
 */
import { useEffect } from "react";
import { useAgentContextStore, type AgentContextSummary } from "./agent-context-store";

export function useAgentContext(ctx: AgentContextSummary | null): void {
  useEffect(() => {
    if (ctx) {
      useAgentContextStore.getState().setContext(ctx);
    }
    return () => {
      useAgentContextStore.getState().clearContext();
    };
  }, [ctx]);
}
