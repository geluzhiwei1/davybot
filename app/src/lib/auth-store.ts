/**
 * Auth Store — Zustand state management for user authentication.
 * Handles login, logout, token refresh, and persistent auth state.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { SUPPORT_API_URL, STORAGE_KEYS, getApiBaseUrl } from "./env";

/**上次登录用户 id(localStorage)— 检测「换账号登录」以清理身份作用域的持久化状态。*/
const LAST_USER_KEY = "normnomos-last-user-id";

/**
 * server 自包含模式的固定本地用户 (server 自包含方案)。
 * 后端无 auth capability 时以 local-user 身份运行, 不走账号体系。
 */
export const LOCAL_USER: AuthUser = {
  id: "local-user",
  nickname: "本地用户",
  token_quota: 0,
  token_used: 0,
  is_active: true,
};

// ── Types ──────────────────────────────────────────────────────────

/**租戶摘要 — 與後端 TenantSummary 對齊。*/
export interface TenantSummary {
  tenant_id: string;
  /**主角色（單值，向後相容）。新代碼應優先使用 ``tenant_roles`` 或 ``allRoles``。*/
  role: string;
  /**v2 多角色：主角色之外的額外角色碼列表。*/
  tenant_roles?: string[];
  joined_at?: string | null;
  last_active_at?: string | null;
  tenant_name: string;
  tenant_slug?: string | null;
  tenant_type: string;
  company_name?: string | null;
  tenant_status: string;
  is_current?: boolean;
}

/**輔助：從 TenantSummary 提取所有角色碼（主角色 + tenant_roles 去重）。*/
export function allRolesOf(t: TenantSummary | null | undefined): string[] {
  if (!t) return [];
  const roles: string[] = [];
  if (t.role) roles.push(t.role);
  for (const r of t.tenant_roles ?? []) {
    if (r && !roles.includes(r)) roles.push(r);
  }
  return roles;
}

/**後端 /auth/login、/auth/refresh、/auth/switch-tenant 共用的 response 結構。*/
export interface AuthLoginResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  user: AuthUser;
  is_tenant_admin?: boolean;
  requires_tenant_selection?: boolean;
  available_tenants?: TenantSummary[];
  /**當前會話可見模塊 key 列表（空 = 全量；前端降級為 null 不過濾） */
  effective_modules?: string[];
}

export interface AuthUser {
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
  created_at?: string;
  updated_at?: string;
  // 多租戶
  available_tenants?: TenantSummary[];
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  authenticated: boolean;
  initialized: boolean; // true once startup validation completes
  /**server 自包含模式 (后端无 auth capability): 本地身份, 无账号体系。*/
  localMode: boolean;

  // ── 多租戶 state ──
  /**當前用戶所有可用租戶（已過濾 ACTIVE）。*/
  availableTenants: TenantSummary[];
  /**登入時是否需要進入選擇租戶頁。*/
  requiresTenantSelection: boolean;
  /**
   * 當前會話可見模塊 key 列表。
   * - 非空數組 → sidebar 按此過濾
   * - null → 未載入或後端未返回，降級為全量顯示（兼容老後端）
   */
  effectiveModules: string[] | null;

  // Actions
  login: (
    identifier: string,
    password: string,
    loginType?: "email" | "phone",
  ) => Promise<AuthLoginResponse>;
  /**
   * server 自包含模式进入 (server 自包含方案): 固定 local-user 身份。
   * 密码为服务器 DAWEI_SERVER_PASSWORD (未设置则传空串), 存 localStorage
   * 供 client/ws 附着 Bearer。
   */
  enterLocalMode: (password?: string) => void;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
  loadFromStorage: () => Promise<void>;
  /**切換會話租戶 — 取得新的 access/refresh token。*/
  switchTenant: (tenantId: string) => Promise<boolean>;
  /**切換到個人身份 — 取得不帶 tid 的 access/refresh token。*/
  switchToPersonal: () => Promise<boolean>;
  /**重新拉取可用租戶清單。*/
  refreshAvailableTenants: () => Promise<TenantSummary[]>;
  /**當前會話租戶（派生值）。*/
  currentTenant: () => TenantSummary | null;
}

// ── Store ──────────────────────────────────────────────────────────

/** Redirect to login page — clears auth state and navigates via window.location.
 *  await logout():整页跳转会中断未完成的异步清理链(tabs/持久化 token 残留)。 */
export async function redirectToLogin() {
  await useAuthStore.getState().logout();
  const base = (import.meta.env.BASE_URL || "/").replace(/\/+$/, "");
  window.location.href = `${base}/login`.replace(/\/+/g, "/");
}

// ── Global refresh mutex ────────────────────────────────────────────
// Ensures only one refresh request is in-flight at a time across ALL
// callers (client.ts, market-api.ts, proactive timer, etc.).
// Without this, concurrent refresh calls with token rotation cause the
// second call to use an already-invalidated refresh token → forced logout.
let _refreshPromise: Promise<boolean> | null = null;

// ── Proactive token refresh ──────────────────────────────────────────
// Refresh the access token before it expires to avoid 401 interruptions.
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

/** Fallback TTL (seconds) when the backend doesn't provide expires_in. */
const FALLBACK_TOKEN_TTL_SECONDS = 55 * 60; // 55 min — safe under the 60 min dev token

/** Refresh this many seconds before the token actually expires. */
const REFRESH_BUFFER_SECONDS = 5 * 60; // 5 minutes

/**
 * Schedule a proactive token refresh.
 * Called after login and after each successful refresh.
 * Refreshes 5 minutes before the access token would expire.
 *
 * @param expiresInSeconds — TTL from the backend's `expires_in` response field.
 *   Falls back to a conservative default if not provided.
 */
function scheduleProactiveRefresh(expiresInSeconds?: number) {
  if (refreshTimer) clearTimeout(refreshTimer);

  const ttl = expiresInSeconds ?? FALLBACK_TOKEN_TTL_SECONDS;
  const delayMs = Math.max((ttl - REFRESH_BUFFER_SECONDS) * 1000, 60_000); // min 1 min

  refreshTimer = setTimeout(async () => {
    const store = useAuthStore.getState();
    if (store.authenticated && store.refreshToken) {
      const ok = await store.refreshAccessToken();
      if (ok) {
        // Schedule next refresh — refreshAccessToken already scheduled it
      } else {
        // Refresh failed — redirectToLogin will be triggered by the 401 handler
        console.warn("[Auth] Proactive refresh failed — session may expire soon");
      }
    }
  }, delayMs);
}

function cancelProactiveRefresh() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      authenticated: false,
      initialized: false,
      localMode: false,
      availableTenants: [],
      requiresTenantSelection: false,
      effectiveModules: null,

      // ── Helper：從 login/refresh/switch 響應抽取多租戶信號 ──
      // (inline 閉包 — Zustand 不允許在 store 外定義 helper 讀取 set)

      login: async (identifier, password, loginType = "email") => {
        const res = await fetch(`${SUPPORT_API_URL}/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ identifier, password, login_type: loginType }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Login failed" }));
          throw new Error(err.detail || `Login failed (${res.status})`);
        }

        const data: AuthLoginResponse = await res.json();

        // Also store token in localStorage for api-client.ts to pick up
        localStorage.setItem(STORAGE_KEYS.authToken, data.access_token);
        localStorage.setItem(STORAGE_KEYS.refreshToken, data.refresh_token);

        const tenants = Array.isArray(data.available_tenants) ? data.available_tenants : [];
        const requires = !!data.requires_tenant_selection && tenants.length > 1;

        set({
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          user: data.user,
          authenticated: true,
          availableTenants: tenants,
          requiresTenantSelection: requires,
          effectiveModules: data.effective_modules ?? null,
        });
        scheduleProactiveRefresh(data.expires_in);

        // 账号切换隔离:换账号登录时清空上一账号的身份作用域持久化状态
        // (tabs/会话/工作区缓存)。否则残留入口对另一账号是 403 死链。
        // 同账号重新登录(token 过期后)不清理,保留现场。
        const prevUserId = localStorage.getItem(LAST_USER_KEY);
        const newUserId = data.user?.id ?? "";
        if (prevUserId && newUserId && prevUserId !== newUserId) {
          const { resetAllStores } = await import("./reset-stores");
          resetAllStores();
        }
        if (newUserId) localStorage.setItem(LAST_USER_KEY, newUserId);
        return data;
      },

      enterLocalMode: (password) => {
        // 清残留 JWT (同源切换部署形态时可能有旧账号 token; 残留会覆盖密码附着 → 401)
        localStorage.removeItem(STORAGE_KEYS.authToken);
        localStorage.removeItem(STORAGE_KEYS.refreshToken);
        // 访问密码持久化 (client/ws 附着 Bearer; 未设密码传空串 → 清除)
        if (password) {
          localStorage.setItem(STORAGE_KEYS.serverPassword, password);
        } else {
          localStorage.removeItem(STORAGE_KEYS.serverPassword);
        }
        set({
          user: LOCAL_USER,
          accessToken: null,
          refreshToken: null,
          authenticated: true,
          localMode: true,
          availableTenants: [],
          requiresTenantSelection: false,
          effectiveModules: null,
        });
      },

      logout: async () => {
        const { accessToken, localMode } = get();

        // ── 本地清理先行（同步）──
        // redirectToLogin() 会在调用 logout 后立即整页跳转;若清理逻辑排在
        // await 之后,跳转会中断异步链(动态 import 不再 resolve),导致
        // tabs/持久化 token 残留。因此先同步完成全部本地清理。
        localStorage.removeItem(STORAGE_KEYS.authToken);
        localStorage.removeItem(STORAGE_KEYS.refreshToken);
        localStorage.removeItem(STORAGE_KEYS.serverPassword);
        localStorage.removeItem(LAST_USER_KEY);
        cancelProactiveRefresh();

        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          authenticated: false,
          localMode: false,
          availableTenants: [],
          requiresTenantSelection: false,
          effectiveModules: null,
        });

        // 账号切换隔离:登出即清空身份相关持久化状态(含 tabs),防止残留给下一个登录账号
        try {
          const { resetAllStores } = await import("./reset-stores");
          resetAllStores();
        } catch {
          /* noop */
        }

        // ── 服务端撤销(尽力而为,放最后)──
        // 本地模式无 support-system, 无会话可撤销
        if (localMode) return;
        try {
          await fetch(`${SUPPORT_API_URL}/v1/auth/logout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            },
          });
        } catch {
          // Ignore logout API errors
        }
      },

      refreshAccessToken: async () => {
        // ── Global mutex ──
        // If a refresh is already in-flight, piggyback on it instead of
        // sending a second request.  The backend rotates refresh tokens,
        // so a concurrent second call would use an already-invalidated
        // token and force a logout.
        if (_refreshPromise) return _refreshPromise;

        const { refreshToken } = get();
        if (!refreshToken) return false;

        _refreshPromise = (async () => {
          try {
            const res = await fetch(`${SUPPORT_API_URL}/v1/auth/refresh`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ refresh_token: refreshToken }),
            });

            if (!res.ok) return false;

            const data: AuthLoginResponse = await res.json();

            localStorage.setItem(STORAGE_KEYS.authToken, data.access_token);
            localStorage.setItem(STORAGE_KEYS.refreshToken, data.refresh_token);

            // refresh 保留會話租戶；若後端返回 available_tenants 也一併更新
            const tenants = Array.isArray(data.available_tenants) ? data.available_tenants : [];

            set((s) => ({
              accessToken: data.access_token,
              refreshToken: data.refresh_token,
              user: data.user ?? s.user,
              authenticated: true,
              ...(tenants.length > 0 ? { availableTenants: tenants } : {}),
              ...(data.effective_modules ? { effectiveModules: data.effective_modules } : {}),
            }));

            // Schedule the next proactive refresh based on the new token's TTL
            scheduleProactiveRefresh(data.expires_in);

            return true;
          } catch {
            return false;
          }
        })();

        try {
          return await _refreshPromise;
        } finally {
          _refreshPromise = null;
        }
      },

      switchTenant: async (tenantId: string) => {
        const { accessToken } = get();
        if (!accessToken || !tenantId) return false;
        try {
          const res = await fetch(`${SUPPORT_API_URL}/v1/auth/switch-tenant`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ tenant_id: tenantId }),
          });
          if (!res.ok) return false;

          const data: AuthLoginResponse = await res.json();

          localStorage.setItem(STORAGE_KEYS.authToken, data.access_token);
          localStorage.setItem(STORAGE_KEYS.refreshToken, data.refresh_token);

          const tenants = Array.isArray(data.available_tenants) ? data.available_tenants : [];
          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            user: data.user ?? get().user,
            authenticated: true,
            availableTenants: tenants,
            requiresTenantSelection: false,
            effectiveModules: data.effective_modules ?? null,
          });
          scheduleProactiveRefresh(data.expires_in);
          // Reset all identity-scoped stores before the new token takes effect
          const { resetAllStores } = await import("./reset-stores");
          resetAllStores();
          return true;
        } catch {
          return false;
        }
      },

      switchToPersonal: async () => {
        const { accessToken } = get();
        if (!accessToken) return false;
        try {
          const res = await fetch(`${SUPPORT_API_URL}/v1/auth/switch-to-personal`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${accessToken}`,
            },
          });
          if (!res.ok) return false;

          const data: AuthLoginResponse = await res.json();

          localStorage.setItem(STORAGE_KEYS.authToken, data.access_token);
          localStorage.setItem(STORAGE_KEYS.refreshToken, data.refresh_token);

          const tenants = Array.isArray(data.available_tenants) ? data.available_tenants : [];
          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            user: data.user ?? get().user,
            authenticated: true,
            availableTenants: tenants,
            requiresTenantSelection: false,
            effectiveModules: data.effective_modules ?? null,
          });
          scheduleProactiveRefresh(data.expires_in);
          // Reset all identity-scoped stores before the new token takes effect
          const { resetAllStores } = await import("./reset-stores");
          resetAllStores();
          return true;
        } catch {
          return false;
        }
      },

      refreshAvailableTenants: async () => {
        const { accessToken } = get();
        if (!accessToken) return [];
        try {
          const res = await fetch(`${SUPPORT_API_URL}/v1/auth/tenants`, {
            method: "GET",
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (!res.ok) return [];
          const data = await res.json();
          const tenants: TenantSummary[] = Array.isArray(data)
            ? data
            : Array.isArray(data?.tenants)
              ? data.tenants
              : Array.isArray(data?.data)
                ? data.data
                : [];
          set({ availableTenants: tenants });
          return tenants;
        } catch {
          return [];
        }
      },

      currentTenant: () => {
        const { availableTenants } = get();
        // is_current 標記由後端根據 JWT tid 設定；無標記 = 個人身份
        return availableTenants.find((t) => t.is_current) ?? null;
      },

      loadFromStorage: async () => {
        // ── server 自包含模式探测 (server 自包含方案) ──
        // 后端无 auth capability (server/tui) → 固定本地身份, 不走账号体系:
        // 免登录直达; 已存访问密码 (DAWEI_SERVER_PASSWORD) 由 client/ws 附着。
        // 用裸 fetch 探测 (避免引入 runtime-store 循环依赖); 失败/老后端 →
        // 走既有账号体系流程 (FAST FAIL 降级方向: 宁可要登录, 不放匿名)。
        try {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 5_000);
          const res = await fetch(`${getApiBaseUrl()}/api/runtime-info`, {
            signal: controller.signal,
          });
          clearTimeout(timeoutId);
          if (res.ok) {
            const info = await res.json();
            const hasAuth = Array.isArray(info?.capabilities) && info.capabilities.includes("auth");
            if (!hasAuth) {
              const saved = localStorage.getItem(STORAGE_KEYS.serverPassword);
              get().enterLocalMode(saved ?? undefined);
              set({ initialized: true });
              return;
            }
          }
        } catch {
          /* 探测失败 → 账号体系 */
        }

        // Zustand persist already restores state from localStorage.
        // Validate the token against the backend /auth/me endpoint.
        const { accessToken, refreshToken } = get();

        // No token — nothing to validate
        if (!accessToken) {
          set({ initialized: true });
          return;
        }

        localStorage.setItem(STORAGE_KEYS.authToken, accessToken);
        if (refreshToken) {
          localStorage.setItem(STORAGE_KEYS.refreshToken, refreshToken);
        }

        try {
          // Timeout after 10s so a hung backend doesn't block the app permanently
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 10_000);
          const res = await fetch(`${SUPPORT_API_URL}/v1/auth/me`, {
            method: "GET",
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
            signal: controller.signal,
          });
          clearTimeout(timeoutId);

          if (res.ok) {
            // Token is valid — update user info from backend
            const data = await res.json();
            set({
              user: data.user ?? data,
              authenticated: true,
              initialized: true,
              ...(data.effective_modules ? { effectiveModules: data.effective_modules } : {}),
            });
            scheduleProactiveRefresh();
            // 重新整理租戶清單（含 is_current 標記）
            get()
              .refreshAvailableTenants()
              .catch(() => {
                /* 靜默 */
              });
          } else {
            // Token invalid — try refresh before giving up
            const refreshed = await get().refreshAccessToken();
            if (refreshed) {
              // Re-validate with new token
              const newToken = get().accessToken!;
              const controller2 = new AbortController();
              const timeoutId2 = setTimeout(() => controller2.abort(), 10_000);
              const res2 = await fetch(`${SUPPORT_API_URL}/v1/auth/me`, {
                method: "GET",
                headers: { Authorization: `Bearer ${newToken}` },
                signal: controller2.signal,
              });
              clearTimeout(timeoutId2);
              if (res2.ok) {
                const data2 = await res2.json();
                set({
                  user: data2.user ?? data2,
                  authenticated: true,
                  initialized: true,
                  ...(data2.effective_modules ? { effectiveModules: data2.effective_modules } : {}),
                });
                scheduleProactiveRefresh();
                get()
                  .refreshAvailableTenants()
                  .catch(() => {
                    /* 靜默 */
                  });
                return;
              }
            }
            // Both access and refresh failed — clear auth state
            localStorage.removeItem(STORAGE_KEYS.authToken);
            localStorage.removeItem(STORAGE_KEYS.refreshToken);
            cancelProactiveRefresh();
            set({
              user: null,
              accessToken: null,
              refreshToken: null,
              authenticated: false,
              availableTenants: [],
              requiresTenantSelection: false,
              effectiveModules: null,
              initialized: true,
            });
          }
        } catch (err: unknown) {
          // Network error or timeout — keep existing state but set initialized
          if (err instanceof DOMException && err.name === "AbortError") {
            console.warn("Auth token validation timed out — proceeding with cached credentials");
          }
          set({ initialized: true });
        }
      },
    }),
    {
      name: "normomos-auth",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        authenticated: state.authenticated,
        availableTenants: state.availableTenants,
      }),
    },
  ),
);

// ── Cross-tab token sync ────────────────────────────────────────────
// When another tab refreshes the token (writes to localStorage), sync
// the new value into this tab's in-memory store so it doesn't keep using
// a stale token.  The `storage` event only fires in *other* tabs (not the
// one that wrote), which is exactly what we want.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEYS.authToken && e.newValue) {
      const store = useAuthStore.getState();
      if (store.accessToken !== e.newValue) {
        const newRefresh = localStorage.getItem(STORAGE_KEYS.refreshToken);
        useAuthStore.setState({
          accessToken: e.newValue,
          refreshToken: newRefresh ?? store.refreshToken,
        });
        // Re-schedule proactive refresh based on the new token's lifetime
        scheduleProactiveRefresh();
        console.debug("[Auth] Cross-tab token sync: access token updated");
      }
    } else if (e.key === STORAGE_KEYS.authToken && !e.newValue) {
      // Token was removed (another tab logged out) — sync logout
      cancelProactiveRefresh();
      useAuthStore.setState({
        user: null,
        accessToken: null,
        refreshToken: null,
        authenticated: false,
      });
      console.debug("[Auth] Cross-tab sync: logged out from another tab");
    }
  });
}
