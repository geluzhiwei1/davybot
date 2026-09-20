/**
 * useAgentTask — 共享的 Agent 任务 WebSocket 进度监听 Hook
 *
 * 所有 IP 模块页面共用，避免在每个页面重复 ~30 行相同的 useEffect。
 * 监听 `ip:task:{taskId}` 事件并更新各页面的本地状态。
 */

import { useEffect, type Dispatch, type SetStateAction } from "react";
import { on } from "@/lib/event-bus";
import i18n from "@/lib/i18n";
import type { ToolCallEntry } from "@/lib/agent-types";

interface AgentProgress {
  current: number;
  total: number;
  phase: string;
}

interface UseAgentTaskOptions {
  /** 当前任务的 taskId，为 null 时跳过监听 */
  taskId: string | null;
  /** 设置进度信息 */
  setProgress: Dispatch<SetStateAction<AgentProgress>>;
  /** 追加流式内容 */
  setStreamContent: Dispatch<SetStateAction<string>>;
  /** 更新工具调用列表 */
  setToolCalls: Dispatch<SetStateAction<ToolCallEntry[]>>;
  /** 设置 Agent 状态 */
  setStatus: Dispatch<SetStateAction<"idle" | "running" | "completed" | "error">>;
  /** 设置错误信息 */
  setError: Dispatch<SetStateAction<string | null>>;
  /** 任务完成时回调（如 - 设置 currentTaskId 为 null） */
  onComplete?: () => void;
}

export function useAgentTask(opts: UseAgentTaskOptions): void {
  const { taskId, setProgress, setStreamContent, setToolCalls, setStatus, setError, onComplete } =
    opts;

  useEffect(() => {
    if (!taskId) return;

    const unsubs = [
      on(`ip:task:${taskId}`, (detail) => {
        const msg = detail as unknown as Record<string, unknown>;
        switch (msg.type) {
          case "task_node_start":
            setProgress({
              current: (msg.nodeIndex as number) ?? 0,
              total: (msg.totalNodes as number) ?? 0,
              phase: (msg.phase as string) ?? "",
            });
            break;
          case "stream_content":
            setStreamContent((prev) => prev + ((msg.chunk as string) ?? ""));
            break;
          case "tool_call_start":
            setToolCalls((prev) => [
              ...prev,
              { name: (msg.name as string) ?? "unknown", status: "running" as const, preview: "" },
            ]);
            break;
          case "tool_call_result":
            setToolCalls((prev) =>
              prev.map((t) =>
                t.status === "running" && t.name === (msg.name as string)
                  ? {
                      ...t,
                      status: "done" as const,
                      preview: String(msg.result ?? "").slice(0, 80),
                    }
                  : t,
              ),
            );
            break;
          case "task_complete":
            setStatus("completed");
            onComplete?.();
            break;
          case "task_error":
            setStatus("error");
            setError((msg.error as string) ?? i18n.t("agentTask.unknownError", { ns: "hooksUi" }));
            break;
        }
      }),
    ];

    return () => unsubs.forEach((u) => u());
  }, [taskId, setProgress, setStreamContent, setToolCalls, setStatus, setError, onComplete]);
}
