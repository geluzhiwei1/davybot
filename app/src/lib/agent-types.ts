/**
 * Agent 通用类型下沉(拆库方案 §5.2 解倒挂)——核心 ⇄ biz 共享的纯类型。
 *
 * ToolCallEntry 原定义于 components/ip/agent-progress.tsx(B2 后迁入 biz/ip);
 * 核心 hooks/use-agent-task.ts 依赖它,故下沉核心,biz 侧 re-export 保持旧出口。
 */
export interface ToolCallEntry {
  name: string;
  status: "running" | "done" | "error";
  preview: string;
}
