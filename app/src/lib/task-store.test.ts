/**
 * Task store tests — incremental WS ingestion for §6.3 UI-F.
 *
 * 后端契约（engine/agent/dawei/websocket/protocol.py）：
 * - task_status_update: { task_id, graph_id, old_status, new_status, timestamp }
 * - task_graph_update: { graph_id, update_type, data, timestamp }
 *
 * UI-F 调研结论（2026-08-24）：这两类协议当前在 MessageType 枚举中已声明
 * 且 validator 注册完毕，但 backend 全仓**零生产发射点**（仅 protocol.py
 * 类定义、import、validator 注册三处）。前端补齐 task-store 增量入口后，
 * 一旦 backend P3-6 在 engine 状态变更处 fire-and-forget 广播即自动接入。
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useTaskStore } from "./task-store";

const WS = "ws-1";

function resetStore(): void {
  useTaskStore.setState({
    workspaceCurrentTaskId: {},
    workspaceTaskGraphData: {},
    workspaceTaskGraphStats: {},
    workspaceActiveNodes: {},
    workspaceCompletedNodes: {},
  });
}

// ── markNodeStatus（task_status_update 入口） ──────────────────────────

describe("task-store: markNodeStatus", () => {
  beforeEach(resetStore);

  it("active 状态（running/pending/in_progress）→ 加入 active 桶（idempotent）", () => {
    const store = useTaskStore.getState();
    store.markNodeStatus(WS, "node-1", "running");
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual(["node-1"]);

    // 再次标记 running 不应重复加入
    store.markNodeStatus(WS, "node-1", "running");
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual(["node-1"]);

    // 大小写不敏感 + in_progress 别名
    store.markNodeStatus(WS, "node-2", "In_Progress");
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual(["node-1", "node-2"]);
  });

  it("终态（completed/failed/success/done）→ 从 active 移到 completed 桶", () => {
    const store = useTaskStore.getState();
    store.markNodeStatus(WS, "node-1", "running");
    store.markNodeStatus(WS, "node-1", "completed");

    const state = useTaskStore.getState();
    expect(state.workspaceActiveNodes[WS]).toEqual([]);
    expect(state.workspaceCompletedNodes[WS]).toEqual(["node-1"]);
  });

  it("未入 active 直接进 completed 终态：仍记入 completed 桶", () => {
    useTaskStore.getState().markNodeStatus(WS, "node-1", "failed");
    expect(useTaskStore.getState().workspaceCompletedNodes[WS]).toEqual(["node-1"]);
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual([]);
  });

  it("非 active 非终态（cancelled/skipped/paused）→ 仅从 active 移除，不入 completed", () => {
    const store = useTaskStore.getState();
    store.markNodeStatus(WS, "node-1", "running");
    store.markNodeStatus(WS, "node-2", "running");
    store.markNodeStatus(WS, "node-1", "cancelled");

    const state = useTaskStore.getState();
    expect(state.workspaceActiveNodes[WS]).toEqual(["node-2"]);
    // 与既有 getCompletedNodes(... ?? []) 约定一致：未初始化的桶视作空
    expect(state.workspaceCompletedNodes[WS] ?? []).toEqual([]);
  });

  it("跨工作区隔离：另一工作区桶不受影响", () => {
    const store = useTaskStore.getState();
    store.markNodeStatus("ws-1", "node-a", "running");
    store.markNodeStatus("ws-2", "node-b", "running");

    expect(useTaskStore.getState().workspaceActiveNodes["ws-1"]).toEqual(["node-a"]);
    expect(useTaskStore.getState().workspaceActiveNodes["ws-2"]).toEqual(["node-b"]);
  });
});

// ── applyGraphUpdate（task_graph_update 入口） ─────────────────────────

describe("task-store: applyGraphUpdate", () => {
  beforeEach(resetStore);

  it("update_type=node_added + status=running → 加入 active 桶", () => {
    useTaskStore.getState().applyGraphUpdate(WS, "node_added", {
      task_id: "node-1",
      status: "running",
    });
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual(["node-1"]);
  });

  it("update_type=node_added + status=completed → 直接入 completed 桶", () => {
    useTaskStore.getState().applyGraphUpdate(WS, "node_added", {
      task_id: "node-1",
      status: "completed",
    });
    expect(useTaskStore.getState().workspaceCompletedNodes[WS]).toEqual(["node-1"]);
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual([]);
  });

  it("update_type=node_updated 状态迁移：active → completed", () => {
    const store = useTaskStore.getState();
    store.applyGraphUpdate(WS, "node_added", { task_id: "node-1", status: "running" });
    store.applyGraphUpdate(WS, "node_updated", { task_id: "node-1", status: "completed" });

    const state = useTaskStore.getState();
    expect(state.workspaceActiveNodes[WS]).toEqual([]);
    expect(state.workspaceCompletedNodes[WS]).toEqual(["node-1"]);
  });

  it("update_type=node_removed → 同时从 active 与 completed 移除", () => {
    const store = useTaskStore.getState();
    store.applyGraphUpdate(WS, "node_added", { task_id: "node-1", status: "running" });
    store.applyGraphUpdate(WS, "node_added", { task_id: "node-2", status: "completed" });
    store.applyGraphUpdate(WS, "node_removed", { task_id: "node-1" });

    const state = useTaskStore.getState();
    expect(state.workspaceActiveNodes[WS]).toEqual([]);
    expect(state.workspaceCompletedNodes[WS]).toEqual(["node-2"]);

    // 再移除 node-2 也得清空
    store.applyGraphUpdate(WS, "node_removed", { task_id: "node-2" });
    expect(useTaskStore.getState().workspaceCompletedNodes[WS]).toEqual([]);
  });

  it("未知 update_type → no-op，不抛错", () => {
    const store = useTaskStore.getState();
    store.applyGraphUpdate(WS, "node_added", { task_id: "node-1", status: "running" });
    const before = useTaskStore.getState().workspaceActiveNodes[WS];

    // 不识别的事件 → 不动状态
    store.applyGraphUpdate(WS, "graph_renamed", { new_name: "foo" });
    expect(useTaskStore.getState().workspaceActiveNodes[WS]).toEqual(before);
  });

  it("data 缺 task_id / status → no-op（静默跳过）", () => {
    const store = useTaskStore.getState();
    store.applyGraphUpdate(WS, "node_added", { status: "running" }); // 缺 task_id
    store.applyGraphUpdate(WS, "node_added", { task_id: "node-1" }); // 缺 status（→ 默认 pending，但需补全）
    store.applyGraphUpdate(WS, "node_updated", { task_id: "node-2" }); // 缺 status

    const state = useTaskStore.getState();
    // node-1 缺 status 时以默认 pending 视为 active；其余无 task_id 的全跳过
    expect(state.workspaceActiveNodes[WS]).toContain("node-1");
  });
});
