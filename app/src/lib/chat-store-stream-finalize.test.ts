/**
 * chat-store 终态复位链路回归测试（bug: 任务页「停止」按钮 UI 卡运行态）。
 *
 * 生产事故时间线（.dev-logs/nn-bot-backend.log 2026-09-17）：
 * - 20:22:53 user_message（继续）→ isStreaming=true
 * - 20:27:01 后端 TASK_COMPLETED → AGENT_COMPLETE ×4
 * - 20:29:49–20:30:23 用户连点停止 ×10，后端每次回 AgentStoppedMessage(already completed)
 * - 前端 busy 始终未复位（停止按钮一直显示）
 *
 * 本测试按真实事件顺序驱动 _handleWsMessage（经 event-bus "ws:message"，与
 * connection-store 的生产入口一致），验证三条复位路径：
 * 1. agent_complete（带 conversation_id）→ isStreaming=false
 * 2. agent_stopped（停止 ack）→ finalizeStaleStreams → isStreaming=false
 * 3. 乐观收尾 finalizeStaleStreams（handleStop 调用）→ isStreaming=false
 * 以及安全网契约：终态事件（agent_complete/agent_stopped）缺 conversation_id
 * 时不再被丢弃，而是收口所有流式会话（后端共享工作区竞态可致 convId=None，
 * 双端已修复：后端回退 _task_to_conv_id_map，前端回退收口全部流式会话）。
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "./chat-store";
import { emit } from "./event-bus";
import type { WsMessage } from "./types";

const CONV = "conv-6ad7710b";
const TASK = "task-abdc115a";

function wsIn(msg: Partial<WsMessage> & { type: string } & Record<string, unknown>): void {
  emit("ws:message", msg as unknown as Record<string, unknown>);
}

function resetConversation(): void {
  useChatStore.setState((s) => {
    const next = new Map(s.conversations);
    next.delete(CONV);
    return { conversations: next };
  });
}

/** 模拟一轮流式输出（handleSend 置位 + stream_content 落缓冲）。 */
function startStreamRound(messageId: string): void {
  const cs = useChatStore.getState();
  if (!cs.conversations.get(CONV)) cs.ensureConversation(CONV);
  cs.setStreaming(CONV, true);
  wsIn({
    type: "stream_content",
    conversation_id: CONV,
    message_id: messageId,
    data: { content: "partial output" },
  } as Partial<WsMessage> & { type: string });
}

describe("chat-store: 终态事件复位 isStreaming（停止按钮卡运行态回归）", () => {
  beforeEach(resetConversation);

  it("路径1: agent_complete(带 conversation_id) 复位 isStreaming", () => {
    startStreamRound("m1");
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(true);

    wsIn({
      type: "agent_complete",
      conversation_id: CONV,
      task_id: TASK,
      result_summary: "done",
    });
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(false);
  });

  it("路径2: agent_stopped(停止 ack) 复位 isStreaming 并收口消息状态", () => {
    startStreamRound("m2");
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(true);

    wsIn({
      type: "agent_stopped",
      conversation_id: CONV,
      task_id: TASK,
      result_summary: "任务已经结束或完成",
      partial: false,
    });
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(false);
    expect(conv?.agentStatus.mode).toBe("idle");
    // 已落盘消息不允许残留 streaming/pending（转圈收口）
    for (const m of conv?.messages ?? []) {
      expect(["complete", "error"]).toContain(m.status);
    }
  });

  it("路径3: 乐观收尾 finalizeStaleStreams（handleStop 无 ack 时的兜底）", () => {
    startStreamRound("m3");
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(true);

    useChatStore.getState().finalizeStaleStreams(CONV);
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(false);
    expect(conv?.agentStatus.mode).toBe("idle");
    expect(conv?.streamBuffer).toBeNull();
  });

  it("迟到 stream_content 不得复活已停止的会话（停止后内容继续增长的回归）", () => {
    startStreamRound("m4");
    useChatStore.getState().finalizeStaleStreams(CONV);
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(false);

    wsIn({
      type: "stream_content",
      conversation_id: CONV,
      message_id: "m4",
      data: { content: "late chunk" },
    } as Partial<WsMessage> & { type: string });
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(false);
  });

  it("迟到 stream_reasoning 不得复活已停止的会话（2026-09-18 08:28 连点停止回归）", () => {
    // 事故链：stop → agent_stopped/agent_complete 复位 → 后端收尾 LLM 流又推
    // 8s reasoning → 无守卫的 stream_reasoning 经 _startStreamBuffer 把
    // isStreaming 复活 → flush 的 isStreaming:!!streamActive 维持忙碌态直到
    // 120s idle 超时，期间停止按钮反复出现、连点全部无效。
    startStreamRound("m7");
    useChatStore.getState().finalizeStaleStreams(CONV);
    expect(useChatStore.getState().conversations.get(CONV)?.isStreaming).toBe(false);

    wsIn({
      type: "stream_reasoning",
      conversation_id: CONV,
      message_id: "m7",
      content: "late reasoning",
    } as Partial<WsMessage> & { type: string } & Record<string, unknown>);
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(false);
    expect(conv?.streamBuffer).toBeNull();
  });

  it("流式进行中 stream_reasoning 正常入缓冲（守卫不得误伤正常流）", () => {
    startStreamRound("m8");
    wsIn({
      type: "stream_reasoning",
      conversation_id: CONV,
      message_id: "m8",
      content: "thinking...",
    } as Partial<WsMessage> & { type: string } & Record<string, unknown>);
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(true);
    expect(conv?.streamBuffer?.reasoning).toBe("thinking...");
  });

  it("安全网: agent_complete 缺 conversation_id 时收口所有流式会话（原卡死根因）", () => {
    startStreamRound("m5");
    // 后端 AgentCompleteMessage.conversation_id 可为 None（chat.py 的
    // _conversation_id 取共享 user_workspace.current_conversation，被其他
    // 标签页切换/清空时为 None；后端已加 _task_to_conv_id_map 回退）。
    // 前端安全网：无 convId 的终态事件不再丢弃，而是收口所有流式会话。
    wsIn({ type: "agent_complete", task_id: TASK, result_summary: "done" });
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(false);
    expect(conv?.agentStatus.mode).toBe("idle");
  });

  it("安全网: agent_stopped 缺 conversation_id 同样收口（停止 ack 丢失 convId 场景）", () => {
    startStreamRound("m6");
    wsIn({
      type: "agent_stopped",
      task_id: TASK,
      result_summary: "already completed",
      partial: false,
    });
    const conv = useChatStore.getState().conversations.get(CONV);
    expect(conv?.isStreaming).toBe(false);
    expect(conv?.streamBuffer).toBeNull();
  });
});
