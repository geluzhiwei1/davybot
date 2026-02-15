/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Plugin API Service
 *
 * API client for plugin management in workspaces
 */

import { httpClient } from './http'
import type { PluginInfo, PluginSettings } from '@/types/plugins'

const BASE_URL = '/workspaces'

export interface PluginListOptions {
  plugin_type?: string
  activated_only?: boolean
}

export interface PluginActionRequest {
  action: 'enable' | 'disable' | 'activate' | 'deactivate' | 'reload'
}

export interface JSONSchemaDefinition {
  type: string
  properties?: Record<string, unknown>
  required?: string[]
  [key: string]: unknown
}

export interface UISchemaDefinition {
  type?: string
  properties?: Record<string, unknown>
  [key: string]: unknown
}

export interface PluginConfigSchema {
  success: boolean
  schema: JSONSchemaDefinition // Raw JSON schema from config_schema.json
  config: Record<string, unknown>
  existing_config?: Record<string, unknown>
  form_config?: Record<string, unknown> | null
  message?: string | null
}

export interface ValidateConfigRequest {
  config: Record<string, unknown>
}

export interface ValidateConfigResponse {
  valid: boolean
  errors: string[]
}

export interface SaveConfigRequest {
  config: Record<string, unknown>
}

export interface SaveConfigResponse {
  success: boolean
  plugin_id: string
  activated: boolean
  message: string
}

/**
 * Plugin API
 */
export const pluginsApi = {
  /**
   * List all plugins in workspace
   */
  async listPlugins(workspaceId: string, options?: PluginListOptions): Promise<PluginInfo[]> {
    const params = new URLSearchParams()

    if (options?.plugin_type) {
      params.append('plugin_type', options.plugin_type)
    }

    if (options?.activated_only) {
      params.append('activated_only', 'true')
    }

    const response = await httpClient.get<{ plugins: PluginInfo[] }>(
      `${BASE_URL}/${workspaceId}/plugins`,
      params
    )

    return response.plugins
  },

  /**
   * Get plugin information
   */
  async getPlugin(workspaceId: string, pluginId: string): Promise<PluginInfo> {
    const response = await httpClient.get<PluginInfo>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}`
    )

    return response
  },

  /**
   * Get plugin settings
   */
  async getPluginSettings(
    workspaceId: string,
    pluginId: string
  ): Promise<PluginSettings> {
    const response = await httpClient.get<PluginSettings>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/settings`
    )

    return response
  },

  /**
   * Update plugin settings
   */
  async updatePluginSettings(
    workspaceId: string,
    pluginId: string,
    settings: Partial<PluginSettings>
  ): Promise<{ success: boolean; settings: PluginSettings }> {
    const response = await httpClient.put<{ success: boolean; settings: PluginSettings }>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/settings`,
      settings
    )

    return response
  },

  /**
   * Perform action on plugin
   */
  async pluginAction(
    workspaceId: string,
    pluginId: string,
    action: PluginActionRequest['action']
  ): Promise<{ success: boolean; action: string; plugin_id: string }> {
    const response = await httpClient.post<{ success: boolean; action: string; plugin_id: string }>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/action`,
      { action }
    )

    return response
  },

  /**
   * Enable plugin
   */
  async enablePlugin(workspaceId: string, pluginId: string): Promise<void> {
    await this.pluginAction(workspaceId, pluginId, 'enable')
  },

  /**
   * Disable plugin
   */
  async disablePlugin(workspaceId: string, pluginId: string): Promise<void> {
    await this.pluginAction(workspaceId, pluginId, 'disable')
  },

  /**
   * Activate plugin
   */
  async activatePlugin(workspaceId: string, pluginId: string): Promise<void> {
    await this.pluginAction(workspaceId, pluginId, 'activate')
  },

  /**
   * Deactivate plugin
   */
  async deactivatePlugin(workspaceId: string, pluginId: string): Promise<void> {
    await this.pluginAction(workspaceId, pluginId, 'deactivate')
  },

  /**
   * Reload plugin
   */
  async reloadPlugin(workspaceId: string, pluginId: string): Promise<void> {
    await this.pluginAction(workspaceId, pluginId, 'reload')
  },

  /**
   * Get plugin statistics
   */
  async getStatistics(workspaceId: string): Promise<{
    total_plugins: number
    activated_plugins: number
    by_type: Record<string, number>
    discovery_paths: string[]
  }> {
    const response = await httpClient.get<{
      total_plugins: number
      activated_plugins: number
      by_type: Record<string, number>
      discovery_paths: string[]
    }>(`${BASE_URL}/${workspaceId}/plugins/statistics`)

    return response
  },

  /**
   * Get plugin configuration schema
   */
  async getConfigSchema(workspaceId: string, pluginId: string): Promise<PluginConfigSchema> {
    const response = await httpClient.get<PluginConfigSchema>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/schema`
    )

    return response
  },

  /**
   * Save and apply plugin configuration
   */
  async saveConfig(
    workspaceId: string,
    pluginId: string,
    config: Record<string, unknown>
  ): Promise<SaveConfigResponse> {
    const response = await httpClient.post<SaveConfigResponse>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/config`,
      { config }
    )

    return response
  },

  /**
   * Uninstall a plugin
   */
  async uninstallPlugin(
    workspaceId: string,
    pluginId: string
  ): Promise<{ success: boolean; plugin_id: string; message: string }> {
    const response = await httpClient.delete<{
      success: boolean;
      plugin_id: string;
      message: string;
    }>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}`
    )

    return response
  },

  /**
   * Test Feishu plugin connection status
   */
  async testFeishuConnection(
    workspaceId: string,
    pluginId: string
  ): Promise<{
    success: boolean
    plugin_id: string
    connection_status?: {
      plugin_activated: boolean
      event_server_running: boolean
      health_check_passed: boolean
      event_port: number
      event_host: string
    }
    health_status?: Record<string, unknown>
    message?: string
    error?: string
  }> {
    const response = await httpClient.post<{
      success: boolean
      plugin_id: string
      connection_status?: {
        plugin_activated: boolean
        event_server_running: boolean
        health_check_passed: boolean
        event_port: number
        event_host: string
      }
      health_status?: Record<string, unknown>
      message?: string
      error?: string
    }>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/test-connection`,
      {}
    )

    return response
  },

  /**
   * Send test message to Feishu
   */
  async sendFeishuTestMessage(
    workspaceId: string,
    pluginId: string,
    message?: string
  ): Promise<{
    success: boolean
    plugin_id: string
    message: string
    sent_content?: string
    receive_id?: string
    error?: string
  }> {
    const response = await httpClient.post<{
      success: boolean
      plugin_id: string
      message: string
      sent_content?: string
      receive_id?: string
      error?: string
    }>(
      `${BASE_URL}/${workspaceId}/plugins/${pluginId}/send-test-message`,
      { message: message || '这是一条测试消息' }
    )

    return response
  }
}
