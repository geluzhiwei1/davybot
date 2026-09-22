/**
 * Sandbox v2 TypeScript 数据模型 — §14.6
 *
 * 对应后端 TrustedContext + Provider 抽象 + 配额 + 网络策略
 */

// ─── Provider / Isolation ──────────────────────────────────────────────────

export type ProviderType = "auto" | "subprocess" | "docker" | "e2b";

export type IsolationLevel = "none" | "process" | "container" | "hardware";

export type MountMode = "ro" | "rw";

export type SandboxStatus =
  | "uninitialized"
  | "idle"
  | "initializing"
  | "active"
  | "paused"
  | "queued"
  | "reconnecting"
  | "destroyed"
  | "error";

// ─── Capabilities ──────────────────────────────────────────────────────────

export interface SandboxCapabilities {
  isolation_level: IsolationLevel;
  max_timeout_s: number;
  cold_start_ms: number;
  supports_network: boolean;
  supports_filesystem: boolean;
  supports_pause: boolean;
}

// ─── Provider Health ───────────────────────────────────────────────────────

export interface ProviderHealth {
  provider: ProviderType;
  available: boolean;
  latency_ms?: number;
  error?: string;
}

// ─── Quota ─────────────────────────────────────────────────────────────────

export interface QuotaDimension {
  used: number;
  limit: number;
}

export interface QuotaUsage {
  sessions: QuotaDimension;
  memory_mb: QuotaDimension;
  rate_per_min: QuotaDimension;
}

// ─── Network Policy ────────────────────────────────────────────────────────

export interface NetworkPolicy {
  name: string;
  version: number;
  default_action: "allow" | "deny";
  allowed_domains: string[];
  denied_domains: string[];
}

// ─── Sandbox Session ───────────────────────────────────────────────────────

export interface SandboxSessionInfo {
  status: SandboxStatus;
  provider: ProviderType;
  created_at: string;
  last_active: string;
  queue_size: number;
}

// ─── Errors ────────────────────────────────────────────────────────────────

export type SandboxErrorCode =
  | "RO_MODE_WRITE_DENIED"
  | "QUOTA_EXCEEDED"
  | "PATH_OUT_OF_ALLOWLIST"
  | "TMPFS_MASK_FAILED"
  | "TRUSTED_CONTEXT_EXPIRED"
  | "NETWORK_DENIED"
  | "SANDBOX_TIMEOUT"
  | "UNKNOWN";

export type SandboxActionType = "open_settings" | "contact_admin" | "retry" | "upgrade_plan";

export interface SandboxAction {
  type: SandboxActionType;
  target?: string;
}

export interface SandboxError {
  code: SandboxErrorCode;
  message: string;
  exit_code?: number;
  suggested_action?: SandboxAction;
}

// ─── WebSocket Messages (§14.5) ───────────────────────────────────────────

export interface WsSandboxProviderChanged {
  workspace_id: string;
  old: ProviderType;
  new: ProviderType;
  capabilities: SandboxCapabilities;
}

export interface WsSandboxStatusUpdate {
  workspace_id: string;
  status: SandboxStatus;
  reason?: string;
  seq: number;
}

export interface WsSandboxReconnectGrace {
  workspace_id: string;
  deadline: string; // ISO8601
  queue_size: number;
}

export interface WsSandboxQuotaUpdate {
  user_id_hash: string;
  used: number;
  limit: number;
  dimension: "sessions" | "memory" | "rate";
}

export interface WsSandboxCommandRejected {
  workspace_id: string;
  command_hash: string;
  exit_code: number;
  error_code: SandboxErrorCode;
  suggested_action?: SandboxAction;
}

// ─── Test Connection Result ────────────────────────────────────────────────

export interface TestConnectionResult {
  ok: boolean;
  latency_ms?: number;
  error?: string;
}

// ─── UserSecuritySettings 扩展字段 (§14.6 末尾) ────────────────────────────

export interface SandboxUserSettings {
  sandbox_provider: ProviderType; // 默认 'auto'
  workspace_mount_mode: MountMode; // 默认 'ro'
  virtiofs_enabled: boolean; // 默认 false
}
