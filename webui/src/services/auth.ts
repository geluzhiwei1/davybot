/**
 * Copyright (c) 2025 格律至微
 * SPDX-License-Identifier: AGPL-3.0
 */

/**
 * Authentication Service
 * 认证服务 - 处理OAuth2登录流程和用户会话管理
 */

import { invoke } from '@tauri-apps/api/core';

// 配置
const SUPPORT_SYSTEM_URL = import.meta.env.VITE_SUPPORT_SYSTEM_URL || 'http://www.davybot.com';
const OAUTH_CLIENT_ID = import.meta.env.VITE_OAUTH_CLIENT_ID || 'davybot';
const OAUTH_REDIRECT_URI = import.meta.env.VITE_OAUTH_REDIRECT_URI || 'http://localhost:8465/api/auth/callback';

// 用户信息接口
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

// 认证状态接口
export interface AuthState {
  authenticated: boolean;
  user: UserInfo | null;
}

// 用户信息响应接口
interface UserResponse {
  authenticated: boolean;
  user?: UserInfo;
}

/**
 * 认证服务类
 */
class AuthService {
  private pollTimer: number | null = null;
  private readonly POLL_INTERVAL = 2000; // 2秒轮询一次
  private readonly MAX_POLL_TIME = 120000; // 最多轮询2分钟

  /**
   * 发起OAuth2登录
   */
  async login(): Promise<void> {
    // 生成state参数（防CSRF）
    const state = this.generateState();

    // 保存state到localStorage
    localStorage.setItem('oauth_state', state);

    // 构建OAuth授权URL
    const authUrl = new URL(`${SUPPORT_SYSTEM_URL}/support/auth/oauth/authorize`);
    authUrl.searchParams.set('client_id', OAUTH_CLIENT_ID);
    authUrl.searchParams.set('redirect_uri', OAUTH_REDIRECT_URI);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('scope', 'profile email token_quota');

    // 使用系统浏览器打开授权页面
    try {
      await invoke('open_by_system_browser', { url: authUrl.toString() });
    } catch (error) {
      console.error('Failed to open browser:', error);
      throw new Error('无法打开浏览器，请手动访问授权页面');
    }
  }

  /**
   * 开始轮询检查登录状态
   * @param onLoginSuccess 登录成功回调
   */
  startPolling(onLoginSuccess: (user: UserInfo) => void): void {
    const startTime = Date.now();

    this.pollTimer = window.setInterval(async () => {
      // 检查是否超时
      if (Date.now() - startTime > this.MAX_POLL_TIME) {
        this.stopPolling();
        return;
      }

      try {
        const authState = await this.checkAuthStatus();

        if (authState.authenticated && authState.user) {
          this.stopPolling();
          onLoginSuccess(authState.user);
        }
      } catch (error) {
        console.error('Error checking auth status:', error);
      }
    }, this.POLL_INTERVAL);
  }

  /**
   * 停止轮询
   */
  stopPolling(): void {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /**
   * 检查当前认证状态
   */
  async checkAuthStatus(): Promise<AuthState> {
    try {
      const response = await fetch('/api/auth/user', {
        method: 'GET',
        credentials: 'include', // 包含cookie
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: UserResponse = await response.json();

      return {
        authenticated: data.authenticated,
        user: data.user || null,
      };
    } catch (error) {
      console.error('Failed to check auth status:', error);
      return {
        authenticated: false,
        user: null,
      };
    }
  }

  /**
   * 登出
   */
  async logout(): Promise<void> {
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // 清除本地存储的state
      localStorage.removeItem('oauth_state');
    } catch (error) {
      console.error('Failed to logout:', error);
      throw new Error('登出失败');
    }
  }

  /**
   * 生成随机state字符串（防CSRF）
   */
  private generateState(): string {
    const array = new Uint8Array(16);
    crypto.getRandomValues(array);
    return Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('');
  }

  /**
   * 验证OAuth回调的state参数
   */
  validateState(state: string): boolean {
    const savedState = localStorage.getItem('oauth_state');
    return savedState === state;
  }
}

// 导出单例
export const authService = new AuthService();
