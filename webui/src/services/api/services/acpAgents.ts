/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';

// ACP Agent info type
export interface ACPAgentInfo {
  command: string;
  name: string;
  description: string;
  available: boolean;
  manual: boolean;
  disabled: boolean;
}

// Response types
export interface ACPAgentsResponse {
  success: boolean;
  agents: ACPAgentInfo[];
}

export interface ACPAgentResponse {
  success: boolean;
  agent?: ACPAgentInfo | null;
  message: string;
}

export interface ACPScanResponse {
  success: boolean;
  agents: ACPAgentInfo[];
  message: string;
}

export interface ACPAgentAddRequest {
  command: string;
  name?: string;
  description?: string;
}

// ACP Agent API service
export class AcpAgentsApiService {
  private baseUrl = '/workspaces';

  // Get all registered ACP agents
  async getAgents(workspaceId: string): Promise<ACPAgentsResponse> {
    return await httpClient.get<ACPAgentsResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents`
    );
  }

  // Get available (installed + not disabled) ACP agents
  async getAvailableAgents(workspaceId: string): Promise<ACPAgentsResponse> {
    return await httpClient.get<ACPAgentsResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents/available`
    );
  }

  // Scan system PATH for ACP agents and merge with registry
  async scanAgents(workspaceId: string): Promise<ACPScanResponse> {
    return await httpClient.post<ACPScanResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents/scan`,
      {}
    );
  }

  // Manually add an ACP agent
  async addAgent(
    workspaceId: string,
    data: ACPAgentAddRequest
  ): Promise<ACPAgentResponse> {
    return await httpClient.post<ACPAgentResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents`,
      data
    );
  }

  // Remove an ACP agent
  async removeAgent(
    workspaceId: string,
    command: string
  ): Promise<ACPAgentResponse> {
    return await httpClient.delete<ACPAgentResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents/${encodeURIComponent(command)}`
    );
  }

  // Toggle agent enabled/disabled
  async toggleAgent(
    workspaceId: string,
    command: string,
    disabled: boolean
  ): Promise<ACPAgentResponse> {
    return await httpClient.put<ACPAgentResponse>(
      `${this.baseUrl}/${workspaceId}/acp-agents/${encodeURIComponent(command)}/toggle`,
      { disabled }
    );
  }
}

// Service instance
export const acpAgentsApi = new AcpAgentsApiService();
