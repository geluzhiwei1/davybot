/**
 * Subtask card extraction tests — UI-B 子任务卡片（§6.3）。
 *
 * 对应后端契约（第五批工具结果增强）：
 * - new_task 成功：{ type:"new_task", mode, mode_name, message, subtask_id, agent,
 *                    conversation_id:null, initial_todos, status:"created", note }
 * - run_task 成功：{ type:"run_task", status:"completed"|<终态>, subtask_id,
 *                    conversation_id, agent, mode, result }
 * - 失败：status:"error"（可能带/不带 subtask_id）
 */
import { describe, it, expect } from "vitest";
import {
  extractSubtaskCard,
  findSubtaskNode,
  findSubtaskWorkspace,
  toSubtaskStatus,
} from "./subtask-card";
import type { SubtaskNode } from "./types/subtask";

const NEW_TASK_JSON = JSON.stringify({
  type: "new_task",
  mode: "pdca",
  mode_name: "PDCA 模式",
  message: "调研竞品定价",
  subtask_id: "sub-1",
  agent: "worker",
  conversation_id: null,
  initial_todos: ["Start subtask in pdca mode"],
  status: "created",
  note: "…",
});

const RUN_TASK_OBJ = {
  type: "run_task",
  status: "completed",
  subtask_id: "sub-2",
  conversation_id: "conv-2",
  agent: "explorer",
  mode: "pdca",
  result: "42",
};

describe("extractSubtaskCard", () => {
  it("new_task JSON 字符串 → 卡片信息（created → pending）", () => {
    const card = extractSubtaskCard("new_task", NEW_TASK_JSON);
    expect(card).not.toBeNull();
    expect(card!.subtaskId).toBe("sub-1");
    expect(card!.toolName).toBe("new_task");
    expect(card!.agent).toBe("worker");
    expect(card!.conversationId).toBeNull();
    expect(card!.initialStatus).toBe("pending");
    expect(card!.message).toBe("调研竞品定价");
    expect(card!.mode).toBe("pdca");
    expect(card!.isError).toBe(false);
  });

  it("run_task 对象结果 → completed + conversationId", () => {
    const card = extractSubtaskCard("run_task", RUN_TASK_OBJ);
    expect(card).not.toBeNull();
    expect(card!.subtaskId).toBe("sub-2");
    expect(card!.initialStatus).toBe("completed");
    expect(card!.conversationId).toBe("conv-2");
    expect(card!.agent).toBe("explorer");
  });

  it("run_task 失败终态 JSON 字符串 → failed", () => {
    const card = extractSubtaskCard(
      "run_task",
      JSON.stringify({ ...RUN_TASK_OBJ, status: "failed" }),
    );
    expect(card!.initialStatus).toBe("failed");
  });

  it("非子任务工具 → null（即使 payload 带 subtask_id）", () => {
    expect(extractSubtaskCard("read_file", NEW_TASK_JSON)).toBeNull();
    expect(extractSubtaskCard("attempt_completion", RUN_TASK_OBJ)).toBeNull();
  });

  it("new_task 失败（status=error 且无 subtask_id）→ null", () => {
    const card = extractSubtaskCard(
      "new_task",
      JSON.stringify({ type: "new_task", status: "error", error: "No root task found" }),
    );
    expect(card).toBeNull();
  });

  it("run_task 失败但带 subtask_id → isError 卡片（可渲染失败态）", () => {
    const card = extractSubtaskCard(
      "run_task",
      JSON.stringify({ status: "error", subtask_id: "sub-3", message: "Subtask execution error" }),
    );
    expect(card).not.toBeNull();
    expect(card!.subtaskId).toBe("sub-3");
    expect(card!.isError).toBe(true);
    expect(card!.initialStatus).toBeNull();
  });

  it("无效 JSON 字符串 → null 不抛异常", () => {
    expect(extractSubtaskCard("new_task", "{not json")).toBeNull();
  });

  it("null/undefined/原始类型 result → null", () => {
    expect(extractSubtaskCard("new_task", null)).toBeNull();
    expect(extractSubtaskCard("new_task", undefined)).toBeNull();
    expect(extractSubtaskCard("run_task", 42)).toBeNull();
  });

  it("未知 status 值 → initialStatus null（渲染端回落）", () => {
    const card = extractSubtaskCard(
      "run_task",
      JSON.stringify({ status: "weird_state", subtask_id: "sub-4" }),
    );
    expect(card!.initialStatus).toBeNull();
  });

  it("run_task 无 message 字段 → message null（由 tool_input 补）", () => {
    const card = extractSubtaskCard(
      "run_task",
      JSON.stringify({ status: "completed", subtask_id: "s", result: "ok" }),
    );
    expect(card!.message).toBeNull();
  });
});

describe("findSubtaskNode", () => {
  const node = (id: string): SubtaskNode => ({
    task_id: id,
    parent_id: "root",
    status: "running",
    agent: "worker",
    model: null,
    mode: "pdca",
    depth: 1,
    conversation_id: "conv-x",
    description: "任务 " + id,
    lastEvent: "started",
    steerMessages: [],
    createdAt: 1,
    updatedAt: 2,
  });

  it("跨工作区桶查找命中", () => {
    const buckets = {
      "ws-1": { a: node("a") },
      "ws-2": { b: node("b") },
    };
    expect(findSubtaskNode(buckets, "b")?.task_id).toBe("b");
  });

  it("未命中 → undefined", () => {
    expect(findSubtaskNode({ "ws-1": { a: node("a") } }, "zzz")).toBeUndefined();
    expect(findSubtaskNode({}, "a")).toBeUndefined();
  });
});

describe("findSubtaskWorkspace", () => {
  const node = (id: string): SubtaskNode => ({
    task_id: id,
    parent_id: null,
    status: "pending",
    agent: null,
    model: null,
    mode: null,
    depth: 1,
    conversation_id: null,
    description: "",
    lastEvent: "created",
    steerMessages: [],
    createdAt: 1,
    updatedAt: 1,
  });

  it("命中桶 → 返回归属工作区 id（卡片点击打开抽屉用）", () => {
    const buckets = {
      "ws-1": { a: node("a") },
      "ws-2": { b: node("b") },
    };
    expect(findSubtaskWorkspace(buckets, "b")).toBe("ws-2");
  });

  it("未命中 / 空桶 → null", () => {
    expect(findSubtaskWorkspace({ "ws-1": {} }, "a")).toBeNull();
    expect(findSubtaskWorkspace({}, "a")).toBeNull();
  });
});

describe("toSubtaskStatus", () => {
  it("已知值直通（含大小写不敏感）", () => {
    expect(toSubtaskStatus("completed", "pending")).toBe("completed");
    expect(toSubtaskStatus("Running", "pending")).toBe("running");
  });

  it("未知/空值回落 fallback（卡片渲染端状态归一）", () => {
    expect(toSubtaskStatus("weird_state", "failed")).toBe("failed");
    expect(toSubtaskStatus(null, "pending")).toBe("pending");
    expect(toSubtaskStatus(undefined, "pending")).toBe("pending");
  });
});
