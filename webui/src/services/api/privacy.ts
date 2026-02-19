/**
 * 隐私配置 API Client
 *
 * 提供隐私配置的读取和更新接口
 */

import { httpClient } from './http';

class PrivacyConfigClient {
  private baseUrl = '/privacy';

  /**
   * 获取隐私配置
   */
  async getPrivacyConfig(): Promise<{
    success: boolean;
    config: {
      enabled: boolean;
      retention_days: number;
      sampling_rate: number;
      anonymize_enabled: boolean;
    } | null;
    message?: string;
  }> {
    return httpClient.get(`${this.baseUrl}/config`);
  }

  /**
   * 更新隐私配置
   */
  async updatePrivacyConfig(config: {
    enabled: boolean;
    retention_days: number;
    sampling_rate: number;
    anonymize_enabled: boolean;
  }): Promise<{
    success: boolean;
    config: {
      enabled: boolean;
      retention_days: number;
      sampling_rate: number;
      anonymize_enabled: boolean;
    } | null;
    message?: string;
  }> {
    return httpClient.put(`${this.baseUrl}/config`, config);
  }
}

// 导出单例
export const privacyConfigClient = new PrivacyConfigClient();
