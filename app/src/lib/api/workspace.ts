/**
 * Workspace + Collection API — workspace CRUD, collections, workspace config.
 */
import { request, type ApiResponse } from "./client";

// ── Workspace Config types ──────────────────────────────────────────

export interface AgentConfig {
  mode?: "orchestrator" | "pdca";
  plan_mode_confirm_required?: boolean;
  enable_auto_mode_switch?: boolean;
  auto_approve_tools?: boolean;
  max_concurrent_subtasks?: number;
}

export interface CheckpointConfig {
  checkpoint_interval?: number;
  max_checkpoints?: number;
  enable_compression?: boolean;
}

export interface CompressionConfig {
  enabled?: boolean;
  preserve_recent?: number;
  max_tokens?: number;
  summary_model?: string;
}

export interface MemoryConfig {
  enabled?: boolean;
  virtual_page_size?: number;
  max_active_pages?: number;
  default_energy?: number;
  energy_decay_rate?: number;
  min_energy_threshold?: number;
}

export interface KnowledgeConfig {
  enabled?: boolean;
  vector_store_type?: string;
  embedding_model?: string;
  dimension?: number;
  chunk_size?: number;
  chunk_overlap?: number;
  default_top_k?: number;
  retrieval_mode?: string;
  rag_context_length?: number;
}

export interface SkillsConfig {
  enabled?: boolean;
  auto_discovery?: boolean;
}

export interface ToolsConfig {
  builtin_tools_enabled?: boolean;
  system_tools_enabled?: boolean;
  allowed_tools?: string[];
  denied_tools?: string[];
}

export interface WorkspaceConfig {
  agent?: AgentConfig;
  checkpoint?: CheckpointConfig;
  compression?: CompressionConfig;
  memory?: MemoryConfig;
  knowledge?: KnowledgeConfig;
  skills?: SkillsConfig;
  tools?: ToolsConfig;
}

// ── Workspace Resources ────────────────────────────────────────────

export interface WorkspaceResources {
  skills: Array<{ slug: string; name: string }>;
  modes: Array<{ slug: string; name: string; description: string; source: string }>;
  mcp_servers: Array<{ name: string; command?: string; url?: string }>;
  /** agent slug → mode slugs（安装时各 agent 的 modes.yaml 归属，供专家下拉按 agent 过滤） */
  agent_modes?: Record<string, string[]>;
  team: {
    team_id: string;
    slug: string;
    name?: string;
    skills?: string[];
    agents?: string[];
    mcps?: string[];
    knowledges?: string[];
  } | null;
}

// ── Workspace API ───────────────────────────────────────────────────

export const workspaceApi = {
  list: () =>
    request<{
      success: boolean;
      workspaces: Array<{
        id: string;
        name: string;
        display_name?: string;
        description?: string;
        /** 业务模块标识（创建时固化，如 research-original）——业务模块列表按它过滤 */
        biz_module?: string;
        created_at: string;
        lifecycle?: string;
        workspace_type?: string;
        /** Task-as-Workspace: deep-research 注册元数据（pipeline = spec.slug） */
        deep_research?: { pipeline?: string };
      }>;
    }>("/api/workspaces/list"),

  // NOTE: 不带 ?lifecycle=temporary —— 后端 lifecycle 查询参数是严格过滤器
  // （只保留 temporary），会把 persistent 工作区全部排除，导致工具页列表
  // 永远看不到自己创建的工作区（createFull 创建的全部是 persistent）。
  // 默认（无参数）返回当前用户全部活跃工作区（persistent + temporary）。
  // 响应为顶层 {success, total, workspaces}（无 data 包裹，与 list() 同构）。
  listWithTemp: () =>
    request<{
      success: boolean;
      total?: number;
      workspaces: Array<{
        id: string;
        name: string;
        display_name?: string;
        description?: string;
        /** 业务模块标识（创建时固化，如 research-original）——业务模块列表按它过滤 */
        biz_module?: string;
        created_at: string;
        lifecycle?: string;
        workspace_type?: string;
        /** Task-as-Workspace: deep-research 注册元数据（pipeline = spec.slug） */
        deep_research?: { pipeline?: string };
      }>;
    }>("/api/workspaces/list"),

  create: (name: string, description?: string) =>
    request<ApiResponse<{ id: string; name: string }>>("/api/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  createTemp: (displayName?: string) =>
    request<{
      success: boolean;
      workspace: {
        id: string;
        name: string;
        display_name: string;
        lifecycle: string;
        workspace_type: string;
      };
      message: string;
    }>("/api/workspaces/create-temp", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName || "[临时] 新聊天" }),
    }),

  /** POST /api/workspaces/create — full workspace creation with all optional params */
  createFull: (data: {
    path?: string;
    name?: string;
    display_name?: string;
    description?: string;
    /** 业务模块标识（如 research-original）：固化进系统索引，业务模块列表按它过滤，与名称解耦 */
    biz_module?: string;
    team_id?: string | null;
    team_meta?: Record<string, unknown> | null;
    skill_ids?: string[];
    agent_ids?: string[];
    mcp_ids?: string[];
    knowledge_ids?: string[];
    compliance_template?: string | null;
    compliance_form_data?: Record<string, unknown> | null;
  }) =>
    request<{
      success: boolean;
      workspace: {
        id: string;
        name: string;
        display_name?: string;
        created_at?: string;
      };
    }>("/api/workspaces/create", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  get: (id: string) =>
    request<ApiResponse<{ id: string; name: string; description?: string }>>(
      `/api/workspaces/${id}`,
    ),

  /** PUT /api/workspaces/{id} — backend UpdateWorkspaceRequest expects display_name (not name) */
  update: (id: string, data: { display_name?: string; description?: string }) =>
    request<ApiResponse>(`/api/workspaces/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) => request<ApiResponse>(`/api/workspaces/${id}`, { method: "DELETE" }),

  /**
   * POST /api/workspaces/{id}/reset — 清空工作区（危险操作）
   * 清除工作区下的任务、日志（执行轨迹）与文件，等同新建状态；工作区 ID 不变。
   * 后端要求 body 携带 { confirm: true } 防误触。
   */
  reset: (id: string) =>
    request<{ success: boolean; message: string; workspace_id: string }>(
      `/api/workspaces/${id}/reset`,
      {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      },
    ),

  // ── Workspace config (agent, memory, knowledge, skills, etc.) ──
  getConfig: (id: string) =>
    request<{ success: boolean; config: WorkspaceConfig }>(`/api/workspaces/${id}/config`),

  updateConfig: (id: string, config: Partial<WorkspaceConfig>) =>
    request<{ success: boolean; config: WorkspaceConfig }>(`/api/workspaces/${id}/config`, {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  /** GET /api/users/me/skills-tools — user-level Skills/Tools defaults (override-or-inherit base) */
  getUserSkillsTools: () =>
    request<{ success?: boolean; skills: Record<string, unknown>; tools: Record<string, unknown> }>(
      "/api/users/me/skills-tools",
    ),

  /** GET /api/users/me/memory — user-level memory defaults (override-or-inherit base) */
  getUserMemory: () => request<Record<string, unknown>>("/api/users/me/memory"),

  /** GET /api/users/me/knowledge — user-level knowledge defaults (override-or-inherit base) */
  getUserKnowledge: () => request<Record<string, unknown>>("/api/users/me/knowledge"),

  /** PUT /api/users/me/skills-tools — 更新用户级 Skills/Tools 默认 */
  updateUserSkillsTools: (data: {
    skills: Record<string, unknown>;
    tools: Record<string, unknown>;
  }) =>
    request<{ skills: Record<string, unknown>; tools: Record<string, unknown> }>(
      "/api/users/me/skills-tools",
      { method: "PUT", body: JSON.stringify(data) },
    ),

  /** PUT /api/users/me/memory — 更新用户级 memory 默认 */
  updateUserMemory: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/users/me/memory", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** PUT /api/users/me/knowledge — 更新用户级 knowledge 默认 */
  updateUserKnowledge: (data: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/users/me/knowledge", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** GET /api/workspaces/{id}/skills-tools/effective — override-or-inherit 合并 */
  getSkillsToolsEffective: (id: string) =>
    request<{
      success: boolean;
      default: { skills: Record<string, unknown>; tools: Record<string, unknown> };
      override: { skills: Record<string, unknown>; tools: Record<string, unknown> };
      effective: { skills: Record<string, unknown>; tools: Record<string, unknown> };
    }>(`/api/workspaces/${id}/skills-tools/effective`),

  /** GET /api/workspaces/{id}/memory/effective — override-or-inherit 合并 */
  getMemoryEffective: (id: string) =>
    request<{
      success: boolean;
      default: Record<string, unknown>;
      override: Record<string, unknown>;
      effective: Record<string, unknown>;
    }>(`/api/workspaces/${id}/memory/effective`),

  /** GET /api/workspaces/{id}/knowledge/effective — override-or-inherit 合并 */
  getKnowledgeEffective: (id: string) =>
    request<{
      success: boolean;
      default: Record<string, unknown>;
      override: Record<string, unknown>;
      effective: Record<string, unknown>;
    }>(`/api/workspaces/${id}/knowledge/effective`),
};

// ── Collection API ───────────────────────────────────────────────────

export interface CollectionItem {
  id: string;
  name: string;
  description: string;
  workspace_ids: string[];
  created_at: string;
  updated_at: string;
}

export const collectionApi = {
  /** GET /api/workspaces/collections — list all collections */
  list: () =>
    request<{ success: boolean; collections: CollectionItem[] }>("/api/workspaces/collections"),

  /** POST /api/workspaces/collections — create a new collection */
  create: (data: { name: string; description?: string; workspace_ids?: string[] }) =>
    request<{ success: boolean; collection: CollectionItem }>("/api/workspaces/collections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  /** PUT /api/workspaces/collections/{id} — update collection metadata */
  update: (id: string, data: { name?: string; description?: string }) =>
    request<{ success: boolean; collection: CollectionItem }>(`/api/workspaces/collections/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** DELETE /api/workspaces/collections/{id} — delete a collection */
  delete: (id: string) =>
    request<ApiResponse>(`/api/workspaces/collections/${id}`, { method: "DELETE" }),

  /** POST /api/workspaces/collections/{id}/workspaces — add workspaces to collection */
  addWorkspaces: (collectionId: string, workspaceIds: string[]) =>
    request<{ success: boolean; collection: CollectionItem }>(
      `/api/workspaces/collections/${collectionId}/workspaces`,
      { method: "POST", body: JSON.stringify({ workspace_ids: workspaceIds }) },
    ),

  /** DELETE /api/workspaces/collections/{id}/workspaces?workspace_ids=... — remove workspaces */
  removeWorkspaces: (collectionId: string, workspaceIds: string[]) =>
    request<{ success: boolean; collection: CollectionItem }>(
      `/api/workspaces/collections/${collectionId}/workspaces?workspace_ids=${encodeURIComponent(workspaceIds.join(","))}`,
      { method: "DELETE" },
    ),
};

// ── Workspace Resources API ────────────────────────────────────────

export const workspaceResourceApi = {
  /** GET /api/workspaces/{id}/resources — installed skills, modes, MCP, team */
  get: (workspaceId: string) =>
    request<{ success: boolean } & WorkspaceResources>(`/api/workspaces/${workspaceId}/resources`),

  /** DELETE /api/skill/{skillName}?workspace_id={id} — uninstall a skill */
  deleteSkill: (workspaceId: string, skillName: string) =>
    request<{ success: boolean; message?: string }>(
      `/api/skill/${encodeURIComponent(skillName)}?workspace_id=${encodeURIComponent(workspaceId)}`,
      { method: "DELETE" },
    ),

  /** DELETE /api/workspaces/{id}/modes/{modeSlug} — delete a workspace mode (agent) */
  deleteMode: (workspaceId: string, modeSlug: string) =>
    request<{ success: boolean; message?: string }>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/modes/${encodeURIComponent(modeSlug)}`,
      { method: "DELETE" },
    ),
};
