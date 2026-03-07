/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * 支持系统 API 服务
 * 提供用户认证、验证码、Token统计、用户资料、市场等功能
 */

import { httpClient } from '../http';
import type { ApiResponse } from '../types';

// ==================== 类型定义 ====================

/**
 * 登录请求
 */
export interface LoginRequest {
  identifier: string; // 邮箱或手机号
  password: string;
  identifier_type: 'email' | 'phone';
}

/**
 * 登录响应
 */
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserInfo;
}

/**
 * 注册请求
 */
export interface RegisterRequest {
  email?: string;
  phone?: string;
  password: string;
  nickname?: string;
  verification_code: string;
}

/**
 * 注册响应
 */
export interface RegisterResponse {
  user: UserInfo;
  access_token: string;
  refresh_token: string;
}

/**
 * 刷新令牌请求
 */
export interface RefreshTokenRequest {
  refresh_token: string;
}

/**
 * 刷新令牌响应
 */
export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * 用户信息
 */
export interface UserInfo {
  id: string;
  email?: string;
  phone?: string;
  nickname: string;
  avatar?: string;
  token_quota: number;
  token_used: number;
  is_active: boolean;
  email_verified?: boolean;
  phone_verified?: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * 发送验证码请求
 */
export interface SendVerificationCodeRequest {
  identifier: string; // 邮箱或手机号
  identifier_type: 'email' | 'phone';
  purpose: 'register' | 'login' | 'reset_password' | 'verify_identity';
}

/**
 * 发送验证码响应
 */
export interface SendVerificationCodeResponse {
  message: string;
  expires_in: number; // 验证码有效期（秒）
  cooldown_until?: string; // 冷却时间
}

/**
 * 验证验证码请求
 */
export interface VerifyCodeRequest {
  identifier: string;
  identifier_type: 'email' | 'phone';
  code: string;
  purpose?: string;
}

/**
 * Token 统计信息
 */
export interface TokenStats {
  total_quota: number;
  used: number;
  remaining: number;
  reset_date: string;
  usage_history: TokenUsageEntry[];
}

/**
 * Token 使用记录
 */
export interface TokenUsageEntry {
  date: string;
  tokens_used: number;
  action: string;
}

/**
 * 用户资料
 */
export interface UserProfile extends UserInfo {
  bio?: string;
  location?: string;
  website?: string;
  preferences?: {
    language: string;
    theme: string;
    notifications_enabled: boolean;
  };
}

/**
 * 更新用户资料请求
 */
export interface UpdateProfileRequest {
  nickname?: string;
  bio?: string;
  avatar?: string;
  location?: string;
  website?: string;
  preferences?: {
    language?: string;
    theme?: string;
    notifications_enabled?: boolean;
  };
}

/**
 * 健康检查响应
 */
export interface HealthCheckResponse {
  status: 'healthy' | 'unhealthy';
  version: string;
  timestamp: string;
}

/**
 * 服务信息响应
 */
export interface ServiceInfoResponse {
  name: string;
  version: string;
  description: string;
  features: string[];
}

// ==================== API 服务类 ====================

/**
 * 支持系统 API 服务类
 */
export class SupportApiService {
  private readonly baseUrl = '/support/api';

  // ==================== 认证相关 ====================

  /**
   * 登录
   */
  async login(data: LoginRequest): Promise<LoginResponse> {
    return httpClient.post(`${this.baseUrl}/auth/login`, data);
  }

  /**
   * 邮箱注册
   */
  async registerWithEmail(data: RegisterRequest): Promise<RegisterResponse> {
    return httpClient.post(`${this.baseUrl}/auth/register/email`, data);
  }

  /**
   * 手机注册
   */
  async registerWithPhone(data: RegisterRequest): Promise<RegisterResponse> {
    return httpClient.post(`${this.baseUrl}/auth/register/phone`, data);
  }

  /**
   * 刷新令牌
   */
  async refreshToken(data: RefreshTokenRequest): Promise<RefreshTokenResponse> {
    return httpClient.post(`${this.baseUrl}/auth/refresh`, data);
  }

  /**
   * 登出
   */
  async logout(): Promise<void> {
    return httpClient.post(`${this.baseUrl}/auth/logout`);
  }

  /**
   * 获取当前用户信息
   */
  async getCurrentUser(): Promise<UserInfo> {
    return httpClient.get(`${this.baseUrl}/auth/me`);
  }

  // ==================== 验证码相关 ====================

  /**
   * 发送邮箱验证码
   */
  async sendEmailVerification(data: SendVerificationCodeRequest): Promise<SendVerificationCodeResponse> {
    return httpClient.post(`${this.baseUrl}/verify/email/send`, data);
  }

  /**
   * 验证邮箱验证码
   */
  async verifyEmailCode(data: VerifyCodeRequest): Promise<{ message: string }> {
    return httpClient.post(`${this.baseUrl}/verify/email/verify`, data);
  }

  /**
   * 发送短信验证码
   */
  async sendSmsVerification(data: SendVerificationCodeRequest): Promise<SendVerificationCodeResponse> {
    return httpClient.post(`${this.baseUrl}/verify/sms/send`, data);
  }

  /**
   * 验证短信验证码
   */
  async verifySmsCode(data: VerifyCodeRequest): Promise<{ message: string }> {
    return httpClient.post(`${this.baseUrl}/verify/sms/verify`, data);
  }

  // ==================== Token 统计 ====================

  /**
   * 获取 Token 统计
   */
  async getTokenStats(): Promise<TokenStats> {
    return httpClient.get(`${this.baseUrl}/tokens/stats`);
  }

  // ==================== 用户资料 ====================

  /**
   * 获取用户资料
   */
  async getUserProfile(): Promise<UserProfile> {
    return httpClient.get(`${this.baseUrl}/users/profile`);
  }

  /**
   * 更新用户资料
   */
  async updateUserProfile(data: UpdateProfileRequest): Promise<UserProfile> {
    return httpClient.put(`${this.baseUrl}/users/profile`, data);
  }

  // ==================== 系统信息 ====================

  /**
   * 健康检查
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    return httpClient.get(`${this.baseUrl.replace('/api', '')}/health`);
  }

  /**
   * 获取服务信息
   */
  async getServiceInfo(): Promise<ServiceInfoResponse> {
    return httpClient.get(`${this.baseUrl.replace('/api', '')}/`);
  }
}

// ==================== 导出 ====================

/**
 * 支持系统 API 服务单例
 */
export const supportApi = new SupportApiService();

// 导出类型
export type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  RefreshTokenRequest,
  RefreshTokenResponse,
  UserInfo,
  SendVerificationCodeRequest,
  SendVerificationCodeResponse,
  VerifyCodeRequest,
  TokenStats,
  TokenUsageEntry,
  UserProfile,
  UpdateProfileRequest,
  HealthCheckResponse,
  ServiceInfoResponse
};
