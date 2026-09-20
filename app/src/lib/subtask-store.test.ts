/**
 * Subtask store tests — applyLifecycle 状态机 / 树组装 / bootstrap 恢复。
 *
 * 对应后端契约（dawei §6.2）：
 * - WS subtask_lifecycle 载荷（exclude_none）：subtask_id/event/status/parent_id/
 *   agent/depth/conversation_id/metadata 均可缺省
 * - REST GET /subtasks bootstrap item：task_id/parent_id/status/mode/agent/model/
 *   depth/conversation_id/description/child_ids
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useSubtaskStore, selectSubtaskTree } from "./subtask-store";
import type { SubtaskLifecyclePayload, SubtaskInfo } from "./types/subtask";

const WS = "ws-1";

function msg(
  partial: Partial<SubtaskLifecyclePayload> & { subtask_id: string },
): SubtaskLifecyclePayload {
  return { type: "subtask_lifecycle", event: "created", ...partial };
}

describe("subtask-store: applyLifecycle 状态机", () => {
  beforeEach(() => {
    useSubtaskStore.setState({ workspaceSubtasks: {} });
  });

  it("created → 插入 pending 节点，记录 parent/agent/depth", () => {
    useSubtaskStore.getState().applyLifecycle(
      WS,
      msg({
        subtask_id: "sub1",
        event: "created",
        status: "pending",
        parent_id: "root",
        agent: "worker",
        depth: 1,
      }),
    );

    const node = useSubtaskStore.getState().getSubtask(WS, "sub1");
    expect(node).toBeDefined();
    expect(node!.status).toBe("pending");
    expect(node!.parent_id).toBe("root");
    expect(node!.agent).toBe("worker");
    expect(node!.depth).toBe(1);
    expect(node!.lastEvent).toBe("created");
  });

  it("created → started → running 且补记 conversation_id", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(
      WS,
      msg({ subtask_id: "sub1", event: "created", parent_id: "root", agent: "worker" }),
    );
    store.applyLifecycle(
      WS,
      msg({ subtask_id: "sub1", event: "started", status: "running", conversation_id: "conv-1" }),
    );

    const node = useSubtaskStore.getState().getSubtask(WS, "sub1")!;
    expect(node.status).toBe("running");
    expect(node.conversation_id).toBe("conv-1");
    expect(node.lastEvent).toBe("started");
  });

  it("completed / failed / aborted → 终态落位", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "a", event: "created" }));
    store.applyLifecycle(WS, msg({ subtask_id: "a", event: "started" }));
    store.applyLifecycle(WS, msg({ subtask_id: "a", event: "completed", status: "completed" }));

    store.applyLifecycle(WS, msg({ subtask_id: "b", event: "created" }));
    store.applyLifecycle(WS, msg({ subtask_id: "b", event: "failed", status: "failed" }));

    store.applyLifecycle(WS, msg({ subtask_id: "c", event: "created" }));
    store.applyLifecycle(WS, msg({ subtask_id: "c", event: "aborted", status: "aborted" }));

    const s = useSubtaskStore.getState();
    expect(s.getSubtask(WS, "a")!.status).toBe("completed");
    expect(s.getSubtask(WS, "b")!.status).toBe("failed");
    expect(s.getSubtask(WS, "c")!.status).toBe("aborted");
  });

  it("steered → 状态保持不变，记录 steer 消息", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(
      WS,
      msg({ subtask_id: "sub1", event: "created", status: "pending", parent_id: "root" }),
    );
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "started", status: "running" }));
    store.applyLifecycle(
      WS,
      msg({
        subtask_id: "sub1",
        event: "steered",
        status: "running",
        metadata: { message: "focus on X" },
      }),
    );

    const node = useSubtaskStore.getState().getSubtask(WS, "sub1")!;
    expect(node.status).toBe("running"); // 未被覆盖
    expect(node.lastEvent).toBe("steered");
    expect(node.steerMessages).toEqual(["focus on X"]);
  });

  it("事件缺 status 字段时按 event 推导状态", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "started" }));
    expect(useSubtaskStore.getState().getSubtask(WS, "sub1")!.status).toBe("running");
  });

  it("乱序事件（未见过 created）→ upsert 兜底节点", () => {
    useSubtaskStore.getState().applyLifecycle(
      WS,
      msg({
        subtask_id: "sub1",
        event: "started",
        status: "running",
        parent_id: "root",
        agent: "explorer",
        depth: 2,
      }),
    );

    const node = useSubtaskStore.getState().getSubtask(WS, "sub1")!;
    expect(node.status).toBe("running");
    expect(node.agent).toBe("explorer");
    expect(node.depth).toBe(2);
  });

  it("缺 subtask_id → no-op 不抛异常", () => {
    const before = useSubtaskStore.getState().workspaceSubtasks;
    useSubtaskStore.getState().applyLifecycle(WS, {} as SubtaskLifecyclePayload);
    expect(useSubtaskStore.getState().workspaceSubtasks).toBe(before);
  });

  it("后续事件不回退已记录的 conversation_id / agent（缺省字段不覆盖）", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(
      WS,
      msg({ subtask_id: "sub1", event: "started", conversation_id: "conv-1", agent: "worker" }),
    );
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "completed", status: "completed" }));

    const node = useSubtaskStore.getState().getSubtask(WS, "sub1")!;
    expect(node.conversation_id).toBe("conv-1");
    expect(node.agent).toBe("worker");
  });

  it("工作区隔离：互不污染", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "created" }));
    store.applyLifecycle("ws-2", msg({ subtask_id: "sub2", event: "created" }));

    const s = useSubtaskStore.getState();
    expect(s.getSubtasks(WS).map((n) => n.task_id)).toEqual(["sub1"]);
    expect(s.getSubtasks("ws-2").map((n) => n.task_id)).toEqual(["sub2"]);
  });
});

describe("subtask-store: restoreFromBootstrap", () => {
  beforeEach(() => {
    useSubtaskStore.setState({ workspaceSubtasks: {} });
  });

  const items: SubtaskInfo[] = [
    {
      task_id: "sub1",
      parent_id: "root",
      status: "completed",
      mode: "pdca",
      agent: "worker",
      model: null,
      depth: 1,
      conversation_id: "conv-1",
      description: "调研竞品",
      child_ids: ["sub2"],
    },
    {
      task_id: "sub2",
      parent_id: "sub1",
      status: "running",
      mode: "pdca",
      agent: "worker",
      model: null,
      depth: 2,
      conversation_id: null,
      description: "写报告",
      child_ids: [],
    },
  ];

  it("REST bootstrap → 全量重建节点", () => {
    useSubtaskStore.getState().restoreFromBootstrap(WS, items);

    const s = useSubtaskStore.getState();
    expect(s.getSubtasks(WS)).toHaveLength(2);
    const sub1 = s.getSubtask(WS, "sub1")!;
    expect(sub1.status).toBe("completed");
    expect(sub1.agent).toBe("worker");
    expect(sub1.description).toBe("调研竞品");
    expect(sub1.conversation_id).toBe("conv-1");
    expect(sub1.lastEvent).toBeNull();
  });

  it("bootstrap 整体替换旧桶（不留陈旧节点）", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "stale", event: "created" }));
    store.restoreFromBootstrap(WS, items);

    const s = useSubtaskStore.getState();
    expect(s.getSubtask(WS, "stale")).toBeUndefined();
    expect(s.getSubtasks(WS)).toHaveLength(2);
  });

  it("bootstrap 空列表 → 空桶", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "created" }));
    store.restoreFromBootstrap(WS, []);

    expect(useSubtaskStore.getState().getSubtasks(WS)).toEqual([]);
  });

  it("clearWorkspace 清空指定工作区", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "created" }));
    store.applyLifecycle("ws-2", msg({ subtask_id: "sub2", event: "created" }));
    store.clearWorkspace(WS);

    const s = useSubtaskStore.getState();
    expect(s.getSubtasks(WS)).toEqual([]);
    expect(s.getSubtasks("ws-2")).toHaveLength(1);
  });
});

describe("subtask-store: selectSubtaskTree 树组装", () => {
  beforeEach(() => {
    useSubtaskStore.setState({ workspaceSubtasks: {} });
  });

  it("parent 不在图中（= 根任务）→ 成为树根，子节点按创建顺序排列", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "sub1", event: "created", parent_id: "root" }));
    store.applyLifecycle(WS, msg({ subtask_id: "sub2", event: "created", parent_id: "root" }));
    store.applyLifecycle(WS, msg({ subtask_id: "sub3", event: "created", parent_id: "sub1" }));

    const tree = selectSubtaskTree(useSubtaskStore.getState().workspaceSubtasks[WS]);
    expect(tree).toHaveLength(2); // sub1、sub2 挂根；sub3 是 sub1 的孩子
    const sub1 = tree.find((n) => n.task_id === "sub1")!;
    expect(sub1.children.map((c) => c.task_id)).toEqual(["sub3"]);
    expect(tree.find((n) => n.task_id === "sub2")!.children).toEqual([]);
  });

  it("深层嵌套链正确递归", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "a", event: "created", parent_id: "root" }));
    store.applyLifecycle(WS, msg({ subtask_id: "b", event: "created", parent_id: "a" }));
    store.applyLifecycle(WS, msg({ subtask_id: "c", event: "created", parent_id: "b" }));

    const tree = selectSubtaskTree(useSubtaskStore.getState().workspaceSubtasks[WS]);
    expect(tree[0].task_id).toBe("a");
    expect(tree[0].children[0].task_id).toBe("b");
    expect(tree[0].children[0].children[0].task_id).toBe("c");
  });

  it("环引用不死循环（孤儿全部上提为根）", () => {
    const store = useSubtaskStore.getState();
    store.applyLifecycle(WS, msg({ subtask_id: "x", event: "created", parent_id: "y" }));
    store.applyLifecycle(WS, msg({ subtask_id: "y", event: "created", parent_id: "x" }));

    const tree = selectSubtaskTree(useSubtaskStore.getState().workspaceSubtasks[WS]);
    // x、y 互为父且都不在根可达路径 → 各自作为根出现（2 个根，无子节点）
    expect(tree).toHaveLength(2);
    expect(tree.flatMap((n) => n.children)).toEqual([]);
  });

  it("空图 → 空树", () => {
    expect(selectSubtaskTree({})).toEqual([]);
  });
});

describe("subtask-store: threadDrawer 抽屉开合", () => {
  beforeEach(() => {
    useSubtaskStore.setState({ workspaceSubtasks: {}, threadDrawer: null });
  });

  it("openThread 记录工作区 + 子任务 id；closeThread 清空", () => {
    useSubtaskStore.getState().openThread("ws-9", "sub-x");
    expect(useSubtaskStore.getState().threadDrawer).toEqual({
      workspaceId: "ws-9",
      taskNodeId: "sub-x",
    });

    // 重复 openThread 切换目标（单抽屉，后开覆盖先开）
    useSubtaskStore.getState().openThread("ws-9", "sub-y");
    expect(useSubtaskStore.getState().threadDrawer?.taskNodeId).toBe("sub-y");

    useSubtaskStore.getState().closeThread();
    expect(useSubtaskStore.getState().threadDrawer).toBeNull();
  });
});

describe("subtask-store: openThread focusSteer（UI-D 树节点 steer 入口）", () => {
  beforeEach(() => {
    useSubtaskStore.setState({ workspaceSubtasks: {}, threadDrawer: null });
  });

  it("focusSteer=true 记录标记；缺省不带该字段", () => {
    useSubtaskStore.getState().openThread("ws-1", "s1", { focusSteer: true });
    expect(useSubtaskStore.getState().threadDrawer).toEqual({
      workspaceId: "ws-1",
      taskNodeId: "s1",
      focusSteer: true,
    });

    useSubtaskStore.getState().openThread("ws-1", "s2");
    expect(useSubtaskStore.getState().threadDrawer).toEqual({
      workspaceId: "ws-1",
      taskNodeId: "s2",
    });
  });
});
