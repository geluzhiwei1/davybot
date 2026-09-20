import { Outlet, createRootRoute, useRouterState } from "@tanstack/react-router";
import { Suspense, lazy, useEffect } from "react";
import { toast } from "sonner";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { Toaster } from "@/components/ui/sonner";
import { useBackendConnection } from "@/lib/use-backend";
import { initMonitoringWs } from "@/lib/monitoring-ws";
import { AppDrawers } from "@/components/drawers";
import { ErrorBoundary } from "@/components/error-boundary";
import { TabBar } from "@/components/tab-bar";
import { MobileTabBar } from "@/components/mobile-shell/mobile-tab-bar";
import { useAuthStore } from "@/lib/auth-store";
import { useRuntimeStore } from "@/lib/stores/runtime-store";
import { UpdateNotification } from "@/components/ui/update-notification";
import { BIZ_ROOT_DOCKS } from "@/lib/biz-registry";
// biz 域 Dock(如 FirmAgentDock)静态导入会把整个聊天栈(chat-view→file-content-area
// →xlsx/codemirror/docx-preview 等重编辑器,合计 ~1.1MB min)拖进首屏主 chunk。
// 故注册表只持有 loader,此处统一 lazy 化:首屏与非命中模块零负载,分包不回退。
const BIZ_DOCK_LAZIES = BIZ_ROOT_DOCKS.map((e) => ({ match: e.match, Dock: lazy(e.load) }));
import { getBasepath } from "@/router";
import { isCoreModuleKey, routeToModuleKey } from "@/lib/sidebar-config";
import { useTranslation } from "react-i18next";
// Initialize i18n (default export used for non-component lookups)
import i18n from "@/lib/i18n";
// Apply saved theme on mount
import "@/lib/theme";

import appCss from "../styles.css?url";

function NotFoundComponent() {
  const { t } = useTranslation("routesB");
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-gradient-brand">404</h1>
        <h2 className="mt-4 text-xl font-semibold">{t("root.notFoundTitle")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("root.notFoundDesc")}</p>
        <a
          href="/"
          className="mt-6 inline-flex items-center rounded-md bg-gradient-brand text-brand-foreground px-4 py-2 text-sm font-medium shadow-brand"
        >
          {t("root.backHome")}
        </a>
      </div>
    </div>
  );
}

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      // keep in sync with index.html (viewport-fit=cover for notch/safe-area)
      { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
      { title: i18n.t("routesB:root.metaTitle") },
      {
        name: "description",
        content: i18n.t("routesB:root.metaDescription"),
      },
      { property: "og:title", content: i18n.t("routesB:root.metaTitle") },
      {
        property: "og:description",
        content: i18n.t("routesB:root.metaDescription"),
      },
      { property: "og:type", content: "website" },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});

function RootComponent() {
  const { t } = useTranslation("routesB");
  useBackendConnection();
  const routerState = useRouterState();
  // TanStack Router's pathname is relative to basepath (e.g. "/login", not "/app-ui/login")
  const currentPath = routerState.location.pathname;
  const isLoginPage = currentPath === "/login";
  // 公开页面（免登录 + 免租户/模块守卫）: 登录页 + 报告分享页（PRD §10 #5）
  const isPublicPage = isLoginPage || currentPath.startsWith("/shared-report/");

  // Full login URL including runtime basepath (e.g. "/app-ui/login")
  const loginHref = (getBasepath() + "/login").replace(/\/+/g, "/");

  // Auth guard — use specific selectors to avoid subscribing to entire store
  const authenticated = useAuthStore((s) => s.authenticated);
  const initialized = useAuthStore((s) => s.initialized);
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const effectiveModules = useAuthStore((s) => s.effectiveModules);
  // const availableTenants = useAuthStore((s) => s.availableTenants);

  // All hooks MUST be called before any conditional returns (Rules of Hooks)

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  // 运行模式与能力 (多模式统一方案 §L4): boot 拉一次; 失败回退最小安全集
  useEffect(() => {
    void useRuntimeStore.getState().load();
  }, []);

  // Initialize monitoring WS listener (live agent/task tracking)
  useEffect(() => {
    initMonitoringWs();
  }, []);

  // WS 鉴权失败(后端以 1008 关闭,见 nn-bot websocket.py _authenticate_ws)时,
  // ws-client 会停止重连并派发 "ws:auth-error"。此处统一收口:
  // 提示并跳转登录页,替代旧的"无限重连转圈"死路。
  useEffect(() => {
    const onWsAuthError = () => {
      toast.error(t("root.sessionExpired"));
      window.location.href = loginHref;
    };
    window.addEventListener("ws:auth-error", onWsAuthError);
    return () => window.removeEventListener("ws:auth-error", onWsAuthError);
  }, [t, loginHref]);

  useEffect(() => {
    // Only redirect after initialization completes
    if (initialized && !authenticated && !isPublicPage) {
      // Not authenticated and not on a public page — redirect
      window.location.href = loginHref;
    }
  }, [authenticated, initialized, isPublicPage, loginHref]);

  // ── 无租户守卫(已移除)──
  // 个人用户(无租户)是系统原生支持的模式:JWT 无 tid → market-flow/social-flow
  // 自动使用 u-{sub} 命名空间。不再全局阻断;nn-flow 等需要租户的功能由各自
  // 页面内的错误处理兜底(403 → 提示切换租户),而非阻止整个 app 的使用。

  // ── 模塊權限守衛 ──
  // 訪問未啟用模塊時 toast + 重定向到首頁。
  // F2: effectiveModules === null 表示無模組管控（自包含 server/tui 本地態）
  // → 僅放行核心模塊（home/explore/system），業務路由彈回首頁。
  const moduleKey = routeToModuleKey(currentPath);
  useEffect(() => {
    if (!initialized || !authenticated || isPublicPage) return;
    if (moduleKey === null) return; // 非業務路由（如 /select-tenant）放行
    const allowed =
      effectiveModules == null ? isCoreModuleKey(moduleKey) : effectiveModules.includes(moduleKey);
    if (!allowed) {
      toast.warning(t("root.moduleNotAllowed"));
      // 用 replace 避免產生歷史記錄
      window.location.href = (getBasepath() + "/").replace(/\/+/g, "/");
    }
  }, [currentPath, effectiveModules, initialized, authenticated, isPublicPage, moduleKey]);

  // biz 域 Dock 按模塊鍵命中顯示（如 FirmAgentDock ↔ smart-law-firm 模塊）；
  // 模塊級功能，不是全局功能。

  // Show public pages (login / shared report) without sidebar/tab layout
  if (isPublicPage) {
    return (
      <ErrorBoundary>
        <Outlet />
        <Toaster />
      </ErrorBoundary>
    );
  }

  // Waiting for token validation to complete — show loading
  if (!initialized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">{t("root.verifying")}</p>
        </div>
      </div>
    );
  }

  // Not authenticated — show minimal loading while redirect triggers
  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="w-8 h-8 border-2 border-brand/30 border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <SidebarProvider>
        <div className="min-h-screen flex w-full bg-background">
          <AppSidebar />
          {/* h-dvh:动态视口高度,移动端地址栏收放不跳版;pb-safe-area 避让 iPhone 底部横条 */}
          <div className="flex-1 flex flex-col min-w-0 h-dvh">
            <TabBar />
            <main className="flex-1 min-h-0 overflow-y-auto flex flex-col relative pb-[env(safe-area-inset-bottom)]">
              <Outlet />
            </main>
            {/* 移动端底部导航(方案 Phase 2):根节点 md:hidden,桌面端不渲染不占位 */}
            <MobileTabBar />
          </div>
          <Toaster />
          <AppDrawers />
          <UpdateNotification />
          {/* biz 域浮动 Dock(如 FirmAgentDock)：模块键命中页面显示(chunk 按需加载,加载完成前不占位) */}
          {moduleKey !== null &&
            BIZ_DOCK_LAZIES.map(({ match, Dock }, i) =>
              match(moduleKey) ? (
                <Suspense key={i} fallback={null}>
                  <Dock />
                </Suspense>
              ) : null,
            )}
        </div>
      </SidebarProvider>
    </ErrorBoundary>
  );
}
