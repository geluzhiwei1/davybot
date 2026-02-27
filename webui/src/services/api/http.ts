/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

import axios from 'axios';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';
import type { ApiResponse, HttpConfig } from './types';
import { logger } from '@/utils/logger';
import { NetworkError } from '@/utils/errors';
import { getApiBaseUrl } from '@/utils/platform';
import { appConfig } from '@/config/app.config';

// HTTP客户端类
export class HttpClient {
  private instance: AxiosInstance;
  private config: HttpConfig;

  constructor(config: HttpConfig) {
    this.config = config;
    this.instance = axios.create({
      baseURL: config.baseURL,
      timeout: config.timeout || 10000,
      headers: {
        'Content-Type': 'application/json',
        ...config.headers
      }
    });

    this.setupInterceptors();
  }

  // 设置请求和响应拦截器
  private setupInterceptors(): void {
    // 请求拦截器
    this.instance.interceptors.request.use(
      (config) => {
        // 添加请求时间戳
        config.metadata = { startTime: new Date() };
        
        // 添加认证token（如果存在）
        const token = this.getAuthToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }

        return config;
      },
      (error) => {
        logger.error('HTTP request error', error);
        return Promise.reject(this.handleError(error));
      }
    );

    // 响应拦截器
    this.instance.interceptors.response.use(
      (response: AxiosResponse) => {
        const apiResponse = response.data as ApiResponse;

        if (apiResponse && typeof apiResponse.success === 'boolean') {
          if (apiResponse.success) {
            // 后端返回成功，直接返回解包后的数据
            // @ts-expect-error Unwrapping backend API response
            response.data = apiResponse;
            return response;
          } else {
            // 后端返回业务失败
            const error: ApiError = {
              code: apiResponse.code || 400,
              message: apiResponse.message || 'API request failed',
              details: apiResponse,
              timestamp: new Date().toISOString(),
              type: 'API_BUSINESS_ERROR'
            };
            return Promise.reject(error);
          }
        }

        // 对于非标准格式的响应（例如文件下载），直接返回
        return response;
      },
      (error: AxiosError) => {
        // Network error - fast fail with original error preserved
        if (!error.response) {
          logger.error('Network request failed', error)
          const networkError = new NetworkError(
            'Network request failed: Unable to connect to server',
            { url: error.config?.url, method: error.config?.method }
          )
          ;(networkError as unknown).cause = error
          return Promise.reject(networkError)
        }

        // Server errors (5xx) - preserve original error context
        if (error.response.status >= 500) {
          logger.error('Server error', error, { status: error.response.status })
          // Don't wrap server errors - let them propagate with full context
          return Promise.reject(error)
        }

        // Client errors (4xx) - wrap with additional context
        logger.warn('Client error', error, { status: error.response.status })
        return Promise.reject(this.handleError(error))
      }
    );
  }

  // GET请求
  async get<T>(url: string, params?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.get<ApiResponse<T>>(url, {
        params,
        ...config
      });
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // POST请求
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.post<ApiResponse<T>>(url, data, config);
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // PUT请求
  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.put<ApiResponse<T>>(url, data, config);
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // DELETE请求
  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.delete<ApiResponse<T>>(url, config);
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // PATCH请求
  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.patch<ApiResponse<T>>(url, data, config);
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // 文件上传
  async upload<T>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await this.instance.post<ApiResponse<T>>(url, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        ...config
      });
      return response.data as unknown as T;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // 文件下载
  async download(url: string, config?: AxiosRequestConfig): Promise<Blob> {
    try {
      const response = await this.instance.get(url, {
        responseType: 'blob',
        ...config
      });
      return response.data;
    } catch (error) {
      throw error; // 拦截器已经处理过错误
    }
  }

  // 错误处理
  private handleError(error: unknown): ApiError {
    if (error.response) {
      // 服务器响应错误
      const { status, data } = error.response;
      return {
        code: status,
        message: data?.message || error.message,
        details: data?.details || data,
        timestamp: new Date().toISOString(),
        type: this.getErrorType(status)
      };
    } else if (error.request) {
      // 网络错误
      return {
        code: 0,
        message: 'Network error: Unable to connect to server',
        details: error.message,
        timestamp: new Date().toISOString(),
        type: 'NETWORK_ERROR'
      };
    } else {
      // 其他错误
      return {
        code: -1,
        message: error.message || 'Unknown error occurred',
        details: error,
        timestamp: new Date().toISOString(),
        type: 'UNKNOWN_ERROR'
      };
    }
  }

  // 根据状态码获取错误类型
  private getErrorType(status: number): string {
    if (status >= 400 && status < 500) {
      switch (status) {
        case 400:
          return 'BAD_REQUEST';
        case 401:
          return 'UNAUTHORIZED';
        case 403:
          return 'FORBIDDEN';
        case 404:
          return 'NOT_FOUND';
        case 422:
          return 'VALIDATION_ERROR';
        default:
          return 'CLIENT_ERROR';
      }
    } else if (status >= 500) {
      return 'SERVER_ERROR';
    }
    return 'UNKNOWN_ERROR';
  }

  // 获取认证token
  private getAuthToken(): string | null {
    // 从localStorage或cookie中获取token
    return localStorage.getItem('auth_token') || null;
  }

  // 设置认证token
  setAuthToken(token: string): void {
    localStorage.setItem('auth_token', token);
  }

  // 清除认证token
  clearAuthToken(): void {
    localStorage.removeItem('auth_token');
  }

  // 获取Axios实例（用于高级用法）
  getInstance(): AxiosInstance {
    return this.instance;
  }

  // 更新配置
  updateConfig(newConfig: Partial<HttpConfig>): void {
    this.config = { ...this.config, ...newConfig };
    
    // 更新axios实例配置
    if (newConfig.baseURL) {
      this.instance.defaults.baseURL = newConfig.baseURL;
    }
    if (newConfig.timeout) {
      this.instance.defaults.timeout = newConfig.timeout;
    }
    if (newConfig.headers) {
      this.instance.defaults.headers = {
        ...this.instance.defaults.headers,
        ...newConfig.headers
      };
    }
  }
}

// 扩展AxiosRequestConfig以支持metadata
declare module 'axios' {
  interface AxiosRequestConfig {
    metadata?: {
      startTime?: Date;
    };
  }
}

// 创建默认HTTP客户端实例
export const createHttpClient = (config?: Partial<HttpConfig>): HttpClient => {
  const defaultConfig: HttpConfig = {
    baseURL: getApiBaseUrl(), // 使用平台检测获取正确的API基础URL
    timeout: appConfig.api.timeout,
    headers: {
      'Content-Type': 'application/json'
    },
    logRequests: appConfig.api.logRequests,
    logResponses: appConfig.api.logResponses
  };

  return new HttpClient({ ...defaultConfig, ...config });
};

// 导出默认实例
export const httpClient = createHttpClient();