/**
 * 简单的事件总线 —— 用于 Store 间解耦。
 * 基于 EventTarget，各 Store 通过 type 订阅感兴趣的 WS 消息。
 *
 * 用法:
 *   import { emit, on } from "./event-bus"
 *   emit("ws:agent_start", { wsId, mode, taskId })
 *   const unsub = on("ws:agent_start", (detail) => { ... })
 */

export type EventPayload = Record<string, unknown>;

const bus = new EventTarget();

export function emit(type: string, detail?: EventPayload): void {
  bus.dispatchEvent(new CustomEvent(type, { detail }));
}

export function on(type: string, handler: (detail: EventPayload) => void): () => void {
  const listener = (e: Event) => handler((e as CustomEvent).detail);
  bus.addEventListener(type, listener);
  return () => bus.removeEventListener(type, listener);
}
