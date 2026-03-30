/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import { httpClient } from '../http';

// Channel capability info
export interface ChannelCapabilityInfo {
  format_type: string;
  max_text_length: number;
  streaming: boolean;
  threading: boolean;
  reactions: boolean;
  typing: boolean;
  media_send: boolean;
  media_receive: boolean;
  voice: boolean;
  groups: boolean;
  mentions: boolean;
  markdown: boolean;
  html: boolean;
  chat_types: string[];
}

// Channel info
export interface ChannelInfo {
  channel_type: string;
  registered: boolean;
  capabilities: ChannelCapabilityInfo;
  config_fields: Record<string, unknown>;
  description: string;
}

// Response types
export interface ChannelsListResponse {
  success: boolean;
  channels: ChannelInfo[];
}

export interface ChannelHealthItem {
  success: boolean;
  channel_type: string;
  healthy: boolean;
  message: string;
  latency_ms: number;
}

export interface ChannelsHealthResponse {
  success: boolean;
  health: Record<string, ChannelHealthItem>;
}

export interface ChannelConfigureRequest {
  enabled?: boolean;
  config: Record<string, unknown>;
}

export interface ChannelConfigureResponse {
  success: boolean;
  message: string;
}

// Channels API service
export class ChannelsApiService {
  private baseUrl = '/workspaces';

  // List all registered channels with capabilities
  async listChannels(workspaceId: string): Promise<ChannelsListResponse> {
    return await httpClient.get<ChannelsListResponse>(
      `${this.baseUrl}/${workspaceId}/channels`
    );
  }

  // Get registered channels (lightweight)
  async getRegisteredChannels(workspaceId: string): Promise<ChannelsListResponse> {
    return await httpClient.get<ChannelsListResponse>(
      `${this.baseUrl}/${workspaceId}/channels/registered`
    );
  }

  // Health check all channels
  async healthCheck(workspaceId: string): Promise<ChannelsHealthResponse> {
    return await httpClient.get<ChannelsHealthResponse>(
      `${this.baseUrl}/${workspaceId}/channels/health`
    );
  }

  // Get single channel detail
  async getChannelDetail(workspaceId: string, channelType: string): Promise<ChannelInfo> {
    return await httpClient.get<ChannelInfo>(
      `${this.baseUrl}/${workspaceId}/channels/${channelType}`
    );
  }

  // Configure channel
  async configureChannel(
    workspaceId: string,
    channelType: string,
    config: Record<string, unknown>
  ): Promise<ChannelConfigureResponse> {
    return await httpClient.put<ChannelConfigureResponse>(
      `${this.baseUrl}/${workspaceId}/channels/${channelType}/config`,
      { config }
    );
  }
}

// Service instance
export const channelsApi = new ChannelsApiService();
