/**
 * Result Governance — types, API client, and helpers.
 * Ported from Vue webui src/services/api/governance.ts + src/utils/toolHelpers.ts
 */

import { request } from "./api";
import type { GovernanceMeta } from "./types";

// Re-export for convenience
export type { GovernanceMeta } from "./types";

// ── Config Types ────────────────────────────────────────────────────

export interface ToolPolicy {
  output_type: string;
  max_output_tokens: number;
  blob_max_lines?: number;
  blob_head_ratio?: number;
  list_max_items?: number;
  list_item_max_chars?: number;
  list_summary_threshold?: number;
  echo_max_input_chars?: number;
  pagination_enabled?: boolean;
}

export interface GovernanceConfig {
  default_policy: ToolPolicy;
  tool_policies: Record<string, ToolPolicy>;
  snapshot_ttl_hours: number;
  progressive_disclosure: {
    enabled: boolean;
    schema_compression: boolean;
    max_activated_tools: number;
  };
}

export interface GovernanceMetrics {
  total_calls: number;
  truncated_count: number;
  tokens_saved: number;
  truncation_rate: number;
}

// ── API ─────────────────────────────────────────────────────────────

const BASE = "/api/tools";

export async function expandSnapshot(snapshotId: string): Promise<unknown> {
  return request<unknown>(`${BASE}/snapshots/${snapshotId}`);
}

export async function getGovernanceConfig(): Promise<GovernanceConfig> {
  return request<GovernanceConfig>(`${BASE}/governance/config`);
}

export async function updateGovernanceConfig(
  update: Partial<GovernanceConfig>,
): Promise<GovernanceConfig> {
  return request<GovernanceConfig>(`${BASE}/governance/config`, {
    method: "PUT",
    body: JSON.stringify(update),
  });
}

export async function getGovernanceMetrics(): Promise<GovernanceMetrics> {
  return request<GovernanceMetrics>(`${BASE}/governance/metrics`);
}

// ── Helpers ─────────────────────────────────────────────────────────

export function isResultTruncated(governance?: GovernanceMeta | null): boolean {
  return !!governance?.was_truncated;
}

export function formatByteSize(size: number): string {
  if (size < 1024) return `${size}B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)}KB`;
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
}

export function formatGovernanceInfo(g: GovernanceMeta): string {
  const saved = g.original_size - g.governed_size;
  return `已截断 ${formatByteSize(g.original_size)} → ${formatByteSize(g.governed_size)} (节省 ${formatByteSize(saved)}, ${g.format_type})`;
}

/** Detect structured result format type from a tool result object. */
export function detectResultFormat(result: unknown): "blob_window" | "list_page" | "plain" {
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const type = (result as Record<string, unknown>).type;
    if (type === "blob_window") return "blob_window";
    if (type === "list_page") return "list_page";
  }
  return "plain";
}

/** Format a tool result for display as text. */
export function formatToolResult(result: unknown): string {
  if (result === null || result === undefined) return "(无输出)";
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}
