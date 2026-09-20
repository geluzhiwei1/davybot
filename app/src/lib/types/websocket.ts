/**
 * WebSocket type definitions — migrated from legalbot/webui/src/services/websocket/types.ts
 */

export type ConnectionState =
  "disconnected" | "connecting" | "connected" | "reconnecting" | "error";

export interface WebSocketConfig {
  url: string;
  reconnectAttempts?: number;
  reconnectDelay?: number;
  heartbeatInterval?: number;
  messageTimeout?: number;
  connectionTimeout?: number;
}

export interface WebSocketMessage<T = unknown> {
  id: string;
  type: string;
  timestamp: string;
  session_id: string;
  payload?: T;
}

export type MessageHandler<T = unknown> = (message: WebSocketMessage<T>) => void;
export type Unsubscribe = () => void;

export interface WebSocketEventMap {
  connect: void;
  disconnect: void;
  stateChange: ConnectionState;
  message: WebSocketMessage;
  error: Error;
}

export type WebSocketEventHandler<K extends keyof WebSocketEventMap> = (
  data: WebSocketEventMap[K],
) => void;

// Message types from backend
export enum WsMessageType {
  // Connection
  CONNECT = "connect",
  DISCONNECT = "disconnect",
  HEARTBEAT = "heartbeat",
  HEARTBEAT_ACK = "heartbeat_ack",

  // Chat
  CHAT_MESSAGE = "chat_message",
  CHAT_RESPONSE = "chat_response",
  CHAT_STREAM = "chat_stream",
  CHAT_COMPLETE = "chat_complete",
  CHAT_ERROR = "chat_error",

  // Task
  TASK_START = "task_start",
  TASK_PROGRESS = "task_progress",
  TASK_COMPLETE = "task_complete",
  TASK_ERROR = "task_error",

  // File
  FILE_CHANGED = "file_changed",
  FILE_CREATED = "file_created",
  FILE_DELETED = "file_deleted",
  FILE_SAVED = "file_saved",

  // Workspace
  WORKSPACE_CHANGED = "workspace_changed",

  // Agent
  AGENT_STATUS = "agent_status",
  AGENT_THINKING = "agent_thinking",
  AGENT_TOOL_CALL = "agent_tool_call",
  AGENT_TOOL_RESULT = "agent_tool_result",

  // System
  SYSTEM_NOTIFICATION = "system_notification",
  SYSTEM_ERROR = "system_error",
}

// Stream chunk for chat streaming
export interface ChatStreamChunk {
  conversation_id: string;
  message_id: string;
  chunk: string;
  index: number;
  is_final: boolean;
}

export interface ChatCompletePayload {
  conversation_id: string;
  message_id: string;
  content: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
}
