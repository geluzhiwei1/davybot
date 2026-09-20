/**
 * UI-C 子代理线程抽屉 — 纯逻辑测试。
 *
 * 契约对齐：
 * - REST GET /subtasks/{id}/conversation → conversation.to_dict()：
 *   { messages: [{ role: "user"|"assistant"|"system"|"tool", content, timestamp, id, … }], … }
 *   content 形态（dawei/entity/lm_messages.py）：字符串 或 分片数组
 *   （{type:"text",text} / image / audio …）
 * - REST GET /agents/profiles → { profiles: [{ agent, description, builtin, … }] }
 */
import { describe, expect, it } from "vitest";
import {
  availableSubtaskActions,
  countSubtaskAgents,
  describeActionResult,
  describeRerunResult,
  extractConversationMessages,
  findAgentProfile,
} from "./subtask-thread";

// ── extractConversationMessages ──────────────────────────────────────

describe("extractConversationMessages", () => {
  it("content 为字符串：role/text/timestamp 直通", () => {
    const conv = {
      messages: [
        { role: "user", content: "检索劳动合规要点", timestamp: "2026-08-24T10:00:00Z" },
        { role: "assistant", content: "已开始处理", timestamp: "2026-08-24T10:00:05Z" },
      ],
    };
    expect(extractConversationMessages(conv)).toEqual([
      { role: "user", text: "检索劳动合规要点", timestamp: "2026-08-24T10:00:00Z" },
      { role: "assistant", text: "已开始处理", timestamp: "2026-08-24T10:00:05Z" },
    ]);
  });

  it("content 为 text 分片数组：按换行拼接", () => {
    const conv = {
      messages: [
        {
          role: "assistant",
          content: [
            { type: "text", text: "第一段" },
            { type: "text", text: "第二段" },
          ],
        },
      ],
    };
    expect(extractConversationMessages(conv)).toEqual([
      { role: "assistant", text: "第一段\n第二段", timestamp: undefined },
    ]);
  });

  it("content 数组含非 text 分片（image 等）：仅提取 text 分片", () => {
    const conv = {
      messages: [
        {
          role: "user",
          content: [
            { type: "image", image: "data:…" },
            { type: "text", text: "附图说明" },
          ],
        },
      ],
    };
    expect(extractConversationMessages(conv)).toEqual([{ role: "user", text: "附图说明" }]);
  });

  it("空文本消息（content 缺失/空白/全非 text）被过滤", () => {
    const conv = {
      messages: [
        { role: "assistant", content: "" },
        { role: "assistant", content: "   " },
        { role: "user", content: [{ type: "image", image: "data:…" }] },
        { role: "user", content: "有效消息" },
      ],
    };
    expect(extractConversationMessages(conv)).toEqual([{ role: "user", text: "有效消息" }]);
  });

  it("未知 role 原样透传（不猜映射）", () => {
    const conv = { messages: [{ role: "custom_agent", content: "hi" }] };
    expect(extractConversationMessages(conv)).toEqual([{ role: "custom_agent", text: "hi" }]);
  });

  it("conversation 为 null / 缺 messages / messages 非数组 → []", () => {
    expect(extractConversationMessages(null)).toEqual([]);
    expect(extractConversationMessages({})).toEqual([]);
    expect(extractConversationMessages({ messages: "oops" })).toEqual([]);
  });
});

// ── findAgentProfile ─────────────────────────────────────────────────

describe("findAgentProfile", () => {
  const profiles = [
    { agent: "labor-compliance", description: "劳动合规专家", builtin: true },
    { agent: "contract-reviewer", description: "合同审查", builtin: false, model: "gpt-4o" },
  ];

  it("精确命中返回 profile", () => {
    expect(findAgentProfile(profiles, "labor-compliance")?.description).toBe("劳动合规专家");
  });

  it("大小写不敏感命中", () => {
    expect(findAgentProfile(profiles, "Contract-Reviewer")?.model).toBe("gpt-4o");
  });

  it("未命中 / agent 为空 / profiles 为空 → null", () => {
    expect(findAgentProfile(profiles, "nonexistent")).toBeNull();
    expect(findAgentProfile(profiles, null)).toBeNull();
    expect(findAgentProfile(undefined, "labor-compliance")).toBeNull();
    expect(findAgentProfile([], "labor-compliance")).toBeNull();
  });
});

// ── UI-D steer/abort 动作可用性与结果文案 ─────────────────────────────

describe("availableSubtaskActions", () => {
  it("pending：steer（追加描述）+ abort 可用，rerun 不可用", () => {
    expect(availableSubtaskActions("pending")).toEqual({
      canSteer: true,
      canAbort: true,
      canRerun: false,
    });
  });

  it("running：steer（注入会话）+ abort 可用，rerun 不可用", () => {
    expect(availableSubtaskActions("running")).toEqual({
      canSteer: true,
      canAbort: true,
      canRerun: false,
    });
  });

  it("completed：steer（续跑）+ rerun（从头重跑）可用，abort 不可用", () => {
    expect(availableSubtaskActions("completed")).toEqual({
      canSteer: true,
      canAbort: false,
      canRerun: true,
    });
  });

  it("failed/aborted 终态：仅 rerun 可用（原位重置，不要求会话存活）", () => {
    expect(availableSubtaskActions("failed")).toEqual({
      canSteer: false,
      canAbort: false,
      canRerun: true,
    });
    expect(availableSubtaskActions("aborted")).toEqual({
      canSteer: false,
      canAbort: false,
      canRerun: true,
    });
  });
});

describe("describeActionResult", () => {
  it("steer：delivery=description → 追加描述文案", () => {
    expect(
      describeActionResult("steer", {
        success: true,
        source: "user",
        result: { status: "steered", delivery: "description" },
      }),
    ).toContain("任务描述");
  });

  it("steer：delivery=conversation → 注入会话文案", () => {
    expect(
      describeActionResult("steer", {
        success: true,
        source: "user",
        result: { status: "steered", delivery: "conversation" },
      }),
    ).toContain("会话");
  });

  it("steer：status=resumed → 续跑文案", () => {
    expect(
      describeActionResult("steer", {
        success: true,
        source: "user",
        result: { status: "resumed", delivery: "conversation" },
      }),
    ).toContain("续跑");
  });

  it("steer/abort：失败 → 透出后端 message", () => {
    expect(
      describeActionResult("steer", {
        success: false,
        source: "user",
        result: { status: "error", message: "terminal state" },
      }),
    ).toContain("terminal state");
    expect(
      describeActionResult("abort", {
        success: false,
        source: "user",
        result: { status: "error", message: "root task" },
      }),
    ).toContain("root task");
  });

  it("abort：成功 → 级联中止文案", () => {
    expect(
      describeActionResult("abort", {
        success: true,
        source: "user",
        result: { status: "aborted" },
      }),
    ).toContain("中止");
  });
});

// ── P2-D rerun 结果文案 ──────────────────────────────────────────────

describe("describeRerunResult", () => {
  it("成功（未带重跑指令）→ 重置待启动文案，无指令后缀", () => {
    const s = describeRerunResult({
      success: true,
      task_node_id: "sub1",
      status: "pending",
      steer: null,
    });
    expect(s).toContain("待启动");
    expect(s).not.toContain("重跑指令");
  });

  it("成功（带重跑指令）→ 追加重跑指令文案", () => {
    const s = describeRerunResult({
      success: true,
      task_node_id: "sub1",
      status: "pending",
      steer: { status: "steered", delivery: "description" },
    });
    expect(s).toContain("重跑指令");
  });

  it("失败 → 重跑失败文案", () => {
    expect(
      describeRerunResult({ success: false, task_node_id: "sub1", status: "", steer: null }),
    ).toBe("重跑失败");
  });
});

// ── UI-E Agent Profile 使用计数 ──────────────────────────────────────

describe("countSubtaskAgents", () => {
  it("空工作区桶 → {}", () => {
    expect(countSubtaskAgents({}, "ws-1")).toEqual({});
  });

  it("按 agent 分桶累加；null/缺失 agent 跳过", () => {
    const buckets = {
      "ws-1": {
        a: { agent: "worker" },
        b: { agent: "worker" },
        c: { agent: "explorer" },
        d: { agent: null },
        e: { agent: "worker" },
      },
      // 其他工作区应被忽略
      "ws-2": { f: { agent: "worker" } },
    };
    expect(countSubtaskAgents(buckets, "ws-1")).toEqual({ worker: 3, explorer: 1 });
  });

  it("指定工作区无桶 → {}", () => {
    expect(countSubtaskAgents({ "ws-2": { a: { agent: "x" } } }, "ws-1")).toEqual({});
  });
});
