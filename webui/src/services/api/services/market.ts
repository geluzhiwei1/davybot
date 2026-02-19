/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Market API Service
 *
 * Provides methods to interact with the Market API endpoints
 * for searching, installing, and managing skills, agents, and plugins.
 */

import { httpClient } from '../http';

// ============================================================================
// Type Definitions
// ============================================================================

export type ResourceType = 'skill' | 'agent' | 'plugin';

export interface SearchResult {
  id: string;
  name: string;
  type: ResourceType;
  description: string;
  author?: string;
  version?: string;
  tags: string[];
  downloads: number;
  rating?: number;
  created_at?: string;
  updated_at?: string;
}

export interface ResourceInfo extends SearchResult {
  readme?: string;
  license?: string;
  python_version?: string;
  dependencies: string[];
  install_path?: string;
  similar_resources: SearchResult[];
}

export interface InstallResult {
  success: boolean;
  resource_type: ResourceType;
  resource_name: string;
  install_path?: string;
  version?: string;
  message: string;
  error?: string;
  installed_files: string[];
  requires_restart: boolean;
}

export interface InstalledResource {
  name: string;
  type: ResourceType;
  version?: string;
  install_path: string;
  installed_at?: string;
  enabled: boolean;
  metadata: Record<string, unknown>;
}

// ============================================================================
// Request/Response Types
// ============================================================================

export interface SearchRequest {
  query: string;
  type: ResourceType;
  limit?: number;
}

export interface SearchResponse {
  success: boolean;
  query: string;
  type: string;
  total: number;
  results: SearchResult[];
}

export interface InstallRequest {
  resource_type: ResourceType;
  resource_name: string;
  workspace: string;
  force?: boolean;
}

export interface InstallResponse {
  success: boolean;
  result: InstallResult;
}

export interface InfoResponse {
  success: boolean;
  resource?: ResourceInfo;
  error?: string;
}

export interface ListInstalledResponse {
  success: boolean;
  type: string;
  total: number;
  resources: InstalledResource[];
}

export interface UninstallResponse {
  success: boolean;
  message: string;
  plugin_name?: string;
}

export interface FeaturedResponse {
  success: boolean;
  type: string;
  total: number;
  resources: SearchResult[];
}

export interface CategoryResponse {
  success: boolean;
  categories: Array<{
    value: string;
    label: string;
    description: string;
  }>;
}

// ============================================================================
// API Service Class
// ============================================================================

export class MarketApiService {
  private readonly basePath = '/market';

  /**
   * Search for resources in the market
   *
   * @param query - Search query string
   * @param type - Resource type (skill, agent, plugin)
   * @param limit - Maximum number of results
   * @returns Promise with search results
   */
  async searchResources(
    query: string,
    type: ResourceType = 'skill',
    limit: number = 20
  ): Promise<SearchResponse> {
    return httpClient.post<SearchResponse>(`${this.basePath}/search`, {
      query,
      type,
      limit
    });
  }

  /**
   * GET endpoint for search (for browser compatibility)
   *
   * @param query - Search query string
   * @param type - Resource type
   * @param limit - Maximum results
   * @returns Promise with search results
   */
  async searchResourcesGet(
    query: string,
    type: ResourceType = 'skill',
    limit: number = 20
  ): Promise<SearchResponse> {
    const params = new URLSearchParams({
      q: query,
      type,
      limit: limit.toString()
    });
    return httpClient.get<SearchResponse>(`${this.basePath}/search?${params}`);
  }

  /**
   * Get detailed information about a resource
   *
   * @param type - Resource type
   * @param name - Resource name or ID
   * @returns Promise with resource details
   */
  async getResourceInfo(
    type: ResourceType,
    name: string
  ): Promise<InfoResponse> {
    return httpClient.get<InfoResponse>(`${this.basePath}/info/${type}/${name}`);
  }

  /**
   * Install a resource from the market
   *
   * @param type - Resource type
   * @param name - Resource name or URI
   * @param workspace - Workspace path
   * @param force - Force reinstall if already exists
   * @returns Promise with installation result
   */
  async installResource(
    type: ResourceType,
    name: string,
    workspace: string,
    force: boolean = false
  ): Promise<InstallResponse> {
    return httpClient.post<InstallResponse>(`${this.basePath}/install`, {
      resource_type: type,
      resource_name: name,
      workspace,
      force
    });
  }

  /**
   * List installed resources in workspace
   *
   * @param type - Resource type
   * @param workspaceId - Workspace ID
   * @returns Promise with installed resources list
   */
  async listInstalled(
    type: ResourceType,
    workspaceId: string
  ): Promise<ListInstalledResponse> {
    const params = new URLSearchParams({ workspace_id: workspaceId });
    return httpClient.get<ListInstalledResponse>(
      `${this.basePath}/installed/${type}?${params}`
    );
  }

  /**
   * List all installed resources (all types)
   *
   * @param workspace - Workspace path
   * @returns Promise with all installed resources grouped by type
   */
  async listAllInstalled(workspace: string): Promise<Record<ResourceType, InstalledResource[]>> {
    const [skills, agents, plugins] = await Promise.all([
      this.listInstalled('skill', workspace),
      this.listInstalled('agent', workspace),
      this.listInstalled('plugin', workspace)
    ]);

    return {
      skill: skills.resources || [],
      agent: agents.resources || [],
      plugin: plugins.resources || []
    };
  }

  /**
   * Uninstall a plugin from workspace
   *
   * @param name - Plugin name
   * @param workspaceId - Workspace ID
   * @returns Promise with uninstall result
   */
  async uninstallPlugin(
    name: string,
    workspaceId: string
  ): Promise<UninstallResponse> {
    const params = new URLSearchParams({ workspace_id: workspaceId });
    return httpClient.delete<UninstallResponse>(
      `${this.basePath}/installed/plugin/${name}?${params}`
    );
  }

  /**
   * Get featured/popular resources
   *
   * @param type - Resource type filter
   * @param limit - Number of results
   * @param skip - Number of results to skip (for pagination)
   * @returns Promise with featured resources
   */
  async getFeatured(
    type: ResourceType = 'skill',
    limit: number = 10,
    skip: number = 0
  ): Promise<FeaturedResponse> {
    const params = new URLSearchParams({
      type,
      limit: limit.toString(),
      skip: skip.toString()
    });
    return httpClient.get<FeaturedResponse>(`${this.basePath}/featured?${params}`);
  }

  /**
   * Get available resource categories
   *
   * @returns Promise with categories list
   */
  async getCategories(): Promise<CategoryResponse> {
    return httpClient.get<CategoryResponse>(`${this.basePath}/categories`);
  }

  /**
   * Check Market API health
   *
   * @returns Promise with health status
   */
  async healthCheck(): Promise<{ status: string; database?: string; error?: string }> {
    return httpClient.get(`${this.basePath}/health`);
  }

  // ========================================================================
  // Convenience Methods for Specific Resource Types
  // ========================================================================

  /**
   * Search for skills
   */
  async searchSkills(query: string, limit = 20): Promise<SearchResponse> {
    return this.searchResources(query, 'skill', limit);
  }

  /**
   * Search for agents
   */
  async searchAgents(query: string, limit = 20): Promise<SearchResponse> {
    return this.searchResources(query, 'agent', limit);
  }

  /**
   * Search for plugins
   */
  async searchPlugins(query: string, limit = 20): Promise<SearchResponse> {
    return this.searchResources(query, 'plugin', limit);
  }

  /**
   * Install a skill
   */
  async installSkill(name: string, workspace: string, force = false): Promise<InstallResponse> {
    return this.installResource('skill', name, workspace, force);
  }

  /**
   * Install an agent
   */
  async installAgent(name: string, workspace: string, force = false): Promise<InstallResponse> {
    return this.installResource('agent', name, workspace, force);
  }

  /**
   * Install a plugin
   */
  async installPlugin(name: string, workspace: string, force = false): Promise<InstallResponse> {
    return this.installResource('plugin', name, workspace, force);
  }

  /**
   * List installed skills
   */
  async listInstalledSkills(workspace: string): Promise<InstalledResource[]> {
    const response = await this.listInstalled('skill', workspace);
    return response.resources || [];
  }

  /**
   * List installed agents
   */
  async listInstalledAgents(workspace: string): Promise<InstalledResource[]> {
    const response = await this.listInstalled('agent', workspace);
    return response.resources || [];
  }

  /**
   * List installed plugins
   */
  async listInstalledPlugins(workspace: string): Promise<InstalledResource[]> {
    const response = await this.listInstalled('plugin', workspace);
    return response.resources || [];
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

export const marketApi = new MarketApiService();

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Search resources in the market
 */
export async function searchMarketResources(
  query: string,
  type: ResourceType = 'skill',
  limit = 20
): Promise<SearchResponse> {
  return marketApi.searchResources(query, type, limit);
}

/**
 * Get resource information
 */
export async function getMarketResourceInfo(
  type: ResourceType,
  name: string
): Promise<InfoResponse> {
  return marketApi.getResourceInfo(type, name);
}

/**
 * Install a resource from market
 */
export async function installMarketResource(
  type: ResourceType,
  name: string,
  workspace: string,
  force = false
): Promise<InstallResponse> {
  return marketApi.installResource(type, name, workspace, force);
}

/**
 * List installed resources
 */
export async function listInstalledMarketResources(
  type: ResourceType,
  workspace: string
): Promise<ListInstalledResponse> {
  return marketApi.listInstalled(type, workspace);
}

/**
 * Uninstall a plugin
 */
export async function uninstallMarketPlugin(
  name: string,
  workspace: string
): Promise<UninstallResponse> {
  return marketApi.uninstallPlugin(name, workspace);
}

/**
 * Get featured resources
 */
export async function getFeaturedMarketResources(
  type: ResourceType = 'skill',
  limit = 10
): Promise<FeaturedResponse> {
  return marketApi.getFeatured(type, limit);
}
