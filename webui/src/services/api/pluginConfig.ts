/**
 * 插件配置 API Client
 *
 * 提供统一的插件配置管理 API 调用
 */

import { HttpClient } from './http';
import type {
  PluginConfigResponse,
  PluginListResponse,
  UpdatePluginConfigRequest,
  GetPluginConfigRequest,
  ResetPluginConfigRequest,
} from './types';

class PluginConfigClient {
  /**
   * 获取所有插件的配置
   */
  async listAllPlugins(request: { workspace_id: string }): Promise<PluginListResponse> {
    return HttpClient.get(`/plugin-config/plugins`, { params: request });
  }

  /**
   * 获取插件的配置 schema
   */
  async getPluginSchema(request: { workspace_id: string; plugin_id: string }): Promise<PluginConfigResponse> {
    return HttpClient.get(`/plugin-config/schema`, { params: request });
  }

  /**
   * 获取插件的当前配置
   */
  async getPluginConfig(request: { workspace_id: string; plugin_id: string }): Promise<PluginConfigResponse> {
    return HttpClient.get(`/plugin-config/config`, { params: request });
  }

  /**
   * 更新插件配置
   */
  async updatePluginConfig(request: { workspace_id: string } & UpdatePluginConfigRequest): Promise<PluginConfigResponse> {
    return HttpClient.put(`/plugin-config/config`, request);
  }

  /**
   * 重置插件配置为默认值
   */
  async resetPluginConfig(request: { workspace_id: string } & ResetPluginConfigRequest): Promise<PluginConfigResponse> {
    return HttpClient.post(`/plugin-config/config/reset`, request);
  }
}

// 导出单例
export const pluginConfigClient = new PluginConfigClient();
