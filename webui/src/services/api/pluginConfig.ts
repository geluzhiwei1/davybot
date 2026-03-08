/**
 * 插件配置 API Client
 *
 * 提供统一的插件配置管理 API 调用
 */

import { httpClient } from './http';
import type {
  PluginConfigResponse,
  PluginListResponse,
  UpdatePluginConfigRequest,
  ResetPluginConfigRequest,
} from './types';

class PluginConfigClient {
  private baseUrl = '/workspaces';

  /**
   * 获取所有插件的配置
   */
  async listAllPlugins(request: { workspace_id: string }): Promise<PluginListResponse> {
    const { workspace_id, ...params } = request;
    return httpClient.get(`${this.baseUrl}/${workspace_id}/plugin-config/plugins`, { params });
  }

  /**
   * 获取插件的配置 schema
   */
  async getPluginSchema(request: { workspace_id: string; plugin_id: string }): Promise<PluginConfigResponse> {
    const { workspace_id, ...params } = request;
    return httpClient.get(`${this.baseUrl}/${workspace_id}/plugin-config/schema`, { params });
  }

  /**
   * 获取插件的当前配置
   */
  async getPluginConfig(request: { workspace_id: string; plugin_id: string }): Promise<PluginConfigResponse> {
    const { workspace_id, ...params } = request;
    return httpClient.get(`${this.baseUrl}/${workspace_id}/plugin-config/config`, { params });
  }

  /**
   * 更新插件配置
   */
  async updatePluginConfig(request: { workspace_id: string } & UpdatePluginConfigRequest): Promise<PluginConfigResponse> {
    const { workspace_id, plugin_id, config } = request;
    return httpClient.put(`${this.baseUrl}/${workspace_id}/plugin-config/config`, {
      plugin_id,
      config
    });
  }

  /**
   * 重置插件配置为默认值
   */
  async resetPluginConfig(request: { workspace_id: string } & ResetPluginConfigRequest): Promise<PluginConfigResponse> {
    const { workspace_id, plugin_id } = request;
    return httpClient.post(`${this.baseUrl}/${workspace_id}/plugin-config/config/reset`, {
      plugin_id
    });
  }
}

// 导出单例
export const pluginConfigClient = new PluginConfigClient();
