/**
 * Memory API — workspace-scoped memory CRUD via nn-bot.
 * Endpoints: /api/workspaces/{workspaceId}/memory/*
 */
import { httpClient } from "./http-client";

// ─── Types ─────────────────────────────────────────────────────────

export interface MemoryEntry {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  memory_type: string;
  confidence: number;
  energy: number;
  access_count?: number;
  valid_start?: string;
  valid_end?: string | null;
  keywords?: string[];
  source_event_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface CreateMemoryParams {
  subject: string;
  predicate: string;
  object: string;
  memory_type: string;
  confidence: number;
  energy: number;
  keywords?: string[];
}

export interface MemoryListResponse {
  items: MemoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface MemoryStatsResponse {
  total: number;
  by_type: Record<string, number>;
  avg_confidence: number;
  avg_energy: number;
}

export interface MemoryGraphNode {
  id: string;
  label: string;
  type: string;
  energy: number;
}

export interface MemoryGraphLink {
  source: string;
  target: string;
  label: string;
  confidence?: number;
}

export interface MemoryGraphResponse {
  nodes: MemoryGraphNode[];
  links: MemoryGraphLink[];
}

export interface TimelineEntry {
  date: string;
  memories: MemoryEntry[];
}

// ─── Auto Memory Types ───────────────────────────────────────────

export interface AutoMemoryStats {
  total_entries: number;
  index_lines: number;
  index_near_limit: boolean;
  topics: Record<string, number>;
}

export interface AutoMemoryResponse {
  index: string;
  topics: Record<string, string>;
  topic_counts: Record<string, number>;
  stats: AutoMemoryStats;
  path: string;
}

// ─── Service ───────────────────────────────────────────────────────

class MemoryApiService {
  private base(workspaceId: string) {
    return `/api/workspaces/${workspaceId}/memory`;
  }

  /** List memories with optional filters. */
  async getMemories(
    workspaceId: string,
    params?: {
      type?: string;
      min_confidence?: number;
      min_energy?: number;
      subject?: string;
      only_valid?: boolean;
      page?: number;
      page_size?: number;
    },
  ): Promise<MemoryListResponse> {
    return httpClient.get<MemoryListResponse>(this.base(workspaceId), params);
  }

  /** Create a new memory. */
  async createMemory(workspaceId: string, data: CreateMemoryParams): Promise<MemoryEntry> {
    return httpClient.post<MemoryEntry>(this.base(workspaceId), data);
  }

  /** Get a single memory by ID. */
  async getMemory(workspaceId: string, memoryId: string): Promise<MemoryEntry> {
    return httpClient.get<MemoryEntry>(`${this.base(workspaceId)}/${memoryId}`);
  }

  /** Update a memory. */
  async updateMemory(
    workspaceId: string,
    memoryId: string,
    data: Partial<CreateMemoryParams & { valid_end?: string }>,
  ): Promise<MemoryEntry> {
    return httpClient.patch<MemoryEntry>(`${this.base(workspaceId)}/${memoryId}`, data);
  }

  /** Delete a memory. */
  async deleteMemory(workspaceId: string, memoryId: string): Promise<void> {
    return httpClient.delete<void>(`${this.base(workspaceId)}/${memoryId}`);
  }

  /** Get memory statistics. */
  async getStats(workspaceId: string): Promise<MemoryStatsResponse> {
    return httpClient.get<MemoryStatsResponse>(`${this.base(workspaceId)}/stats`);
  }

  /** Get graph data for visualization. */
  async getGraph(
    workspaceId: string,
    params?: { type?: string; min_energy?: number },
  ): Promise<MemoryGraphResponse> {
    return httpClient.get<MemoryGraphResponse>(`${this.base(workspaceId)}/graph`, params);
  }

  /** Search memories by keyword. */
  async searchMemories(
    workspaceId: string,
    params: { query: string; limit?: number },
  ): Promise<MemoryEntry[]> {
    return httpClient.get<MemoryEntry[]>(`${this.base(workspaceId)}/search`, params);
  }

  /** Get timeline data grouped by date. */
  async getTimeline(workspaceId: string): Promise<TimelineEntry[]> {
    return httpClient.get<TimelineEntry[]>(`${this.base(workspaceId)}/timeline`);
  }

  // ─── Markdown memory file (Codex-inspired, no retrieval) ─────────

  /** Get user-level memory.md content. */
  async getUserMemoryMd(): Promise<{ content: string; path: string }> {
    return httpClient.get<{ content: string; path: string }>("/api/users/me/memory/md");
  }

  /** Update user-level memory.md content. */
  async updateUserMemoryMd(content: string): Promise<{ content: string; path: string }> {
    return httpClient.put<{ content: string; path: string }>("/api/users/me/memory/md", {
      content,
    });
  }

  // ─── Auto Memory (Agent 自动写) ──────────────────────────────

  /** Get user-level auto-memory. */
  async getUserAutoMemory(): Promise<AutoMemoryResponse> {
    return httpClient.get<AutoMemoryResponse>("/api/users/me/memory/auto");
  }

  /** Clear user-level auto-memory. */
  async clearUserAutoMemory(): Promise<void> {
    return httpClient.delete<void>("/api/users/me/memory/auto");
  }

  /** Get workspace-level auto-memory. */
  async getWorkspaceAutoMemory(workspaceId: string): Promise<AutoMemoryResponse> {
    return httpClient.get<AutoMemoryResponse>(`${this.base(workspaceId)}/memory/auto`);
  }

  /** Clear workspace-level auto-memory. */
  async clearWorkspaceAutoMemory(workspaceId: string): Promise<void> {
    return httpClient.delete<void>(`${this.base(workspaceId)}/memory/auto`);
  }

  /** Get workspace-level memory.md content. */
  async getWorkspaceMemoryMd(workspaceId: string): Promise<{ content: string; path: string }> {
    return httpClient.get<{ content: string; path: string }>(`${this.base(workspaceId)}/md`);
  }

  /** Update workspace-level memory.md content. */
  async updateWorkspaceMemoryMd(
    workspaceId: string,
    content: string,
  ): Promise<{ content: string; path: string }> {
    return httpClient.put<{ content: string; path: string }>(`${this.base(workspaceId)}/md`, {
      content,
    });
  }

  // ─── User-level memory (跨工作区共享, 不需要 workspaceId) ──────────

  /** List user-level memories (cross-workspace). */
  async getUserMemories(params?: {
    type?: string;
    min_confidence?: number;
    page?: number;
    page_size?: number;
  }): Promise<MemoryListResponse> {
    return httpClient.get<MemoryListResponse>("/api/users/me/memory/entries", params);
  }

  /** Create a user-level memory. */
  async createUserMemory(data: CreateMemoryParams): Promise<MemoryEntry> {
    return httpClient.post<MemoryEntry>("/api/users/me/memory/entries", data);
  }

  /** Get a single user-level memory by ID. */
  async getUserMemory(memoryId: string): Promise<MemoryEntry> {
    return httpClient.get<MemoryEntry>(`/api/users/me/memory/entries/${memoryId}`);
  }

  /** Update a user-level memory. */
  async updateUserMemory(
    memoryId: string,
    data: Partial<CreateMemoryParams & { valid_end?: string }>,
  ): Promise<MemoryEntry> {
    return httpClient.patch<MemoryEntry>(`/api/users/me/memory/entries/${memoryId}`, data);
  }

  /** Delete a user-level memory. */
  async deleteUserMemory(memoryId: string): Promise<void> {
    return httpClient.delete<void>(`/api/users/me/memory/entries/${memoryId}`);
  }
}

export const memoryApi = new MemoryApiService();
