/**
 * External API — sanctions, market resources, health check.
 */
import { request } from "./client";
import { SANCTIONS_API_URL, SUPPORT_API_URL } from "../env";

// ── Sanctions API (direct to sanctions-knowledge :8910) ─────────────

export const sanctionsApi = {
  search: (query: string, limit = 20) =>
    request<{
      results: Array<{
        id: string;
        caption: string;
        schema: string;
        datasets: string[];
        properties: Record<string, unknown>;
      }>;
    }>(`/api/v1/search/all?q=${encodeURIComponent(query)}&limit=${limit}`, {}, SANCTIONS_API_URL),

  getEntity: (entityId: string) =>
    request<{
      id: string;
      caption: string;
      schema: string;
      properties: Record<string, unknown>;
      datasets: string[];
    }>(`/api/v1/entities/${entityId}`, {}, SANCTIONS_API_URL),

  listDatasets: () =>
    request<Array<{ name: string; title: string; count: number }>>(
      "/api/v1/filters",
      {},
      SANCTIONS_API_URL,
    ),
};

// ── Health ──────────────────────────────────────────────────────────

export const healthApi = {
  check: (opts?: RequestInit) =>
    request<{ status: string; version: string }>("/api/health", opts ?? {}),
};

// ── Support System Market Resource API ─────────────────────────────

export interface MarketResource {
  id: string;
  type: string; // "skill" | "agent" | "mcp" | "knowledge" | "plugin" | "team"
  name: string;
  description: string;
  author: string;
  slug?: string;
  tags: string[];
  version: string;
  downloads: number;
  rating_avg: number;
  rating_count: number;
  view_count: number;
  visibility: string;
  status: string;
  extra_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface MarketResourceListResponse {
  items: MarketResource[];
  total: number;
  page: number;
  page_size: number;
}

export const marketApi = {
  /** List resources from support system market, optionally filtered by type */
  listResources: (params?: { type?: string; page?: number; page_size?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.type) searchParams.set("type", params.type);
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.page_size) searchParams.set("page_size", String(params.page_size));
    const qs = searchParams.toString();
    return request<MarketResourceListResponse>(
      `/v1/market/resources${qs ? `?${qs}` : ""}`,
      {},
      SUPPORT_API_URL,
    );
  },
};
