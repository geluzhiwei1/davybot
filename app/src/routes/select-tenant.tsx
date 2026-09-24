/**
 * Select Identity Page — Feishu-style identity picker.
 *
 * Every account has a "personal" identity by default (JWT without tid).
 * Accounts that belong to tenants also show tenant identities.
 * The user picks which identity to use; we call the appropriate API
 * to obtain a new session-scoped token pair and navigate to home.
 */
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Building2, User as UserIcon, ChevronRight, LogOut } from "lucide-react";
import { useAuthStore, type TenantSummary } from "@/lib/auth-store";
import { BRAND_NAME } from "@/lib/brand";
import { toastError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/select-tenant")({
  component: SelectTenantPage,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function roleLabel(t: any, role: string): string {
  return t(`selectTenant.role.${role}`) || role;
}

/**v2 多角色：顯示所有角色（主角色 + tenant_roles 去重）。*/
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function rolesLabel(t: any, tenant: { role: string; tenant_roles?: string[] }): string {
  const roles = [tenant.role, ...(tenant.tenant_roles ?? [])].filter(
    (r, i, arr) => r && arr.indexOf(r) === i,
  );
  return roles.map((r) => roleLabel(t, r)).join(" · ");
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function lastActiveLabel(t: any, ts?: string | null): string {
  if (!ts) return "";
  const parsed = Date.parse(ts);
  if (isNaN(parsed)) return "";
  const diff = Date.now() - parsed;
  const min = Math.floor(diff / 60000);
  if (min < 1) return t("selectTenant.activeNow");
  if (min < 60) return t("selectTenant.minutesAgo", { count: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("selectTenant.hoursAgo", { count: hr });
  const day = Math.floor(hr / 24);
  if (day < 30) return t("selectTenant.daysAgo", { count: day });
  return new Date(parsed).toLocaleDateString();
}

function SelectTenantPage() {
  const { t: tr } = useTranslation("routesB");
  const navigate = useNavigate();
  const {
    availableTenants,
    switchTenant,
    switchToPersonal,
    refreshAvailableTenants,
    logout,
    user,
    currentTenant,
  } = useAuthStore();
  const [loading, setLoading] = useState<string | null>(null);

  const activeTenant = currentTenant();
  const isPersonal = !activeTenant;

  // 若进入此页时 tenants 为空（如刷新），尝试重新拉取
  useEffect(() => {
    refreshAvailableTenants();
  }, [refreshAvailableTenants]);

  async function handleSelectPersonal() {
    if (isPersonal) {
      navigate({ to: "/", replace: true });
      return;
    }
    setLoading("__personal__");
    try {
      const ok = await switchToPersonal();
      if (ok) {
        // 强制完整重载 — 确保所有组件/hook/缓存从零初始化,新 JWT 生效
        window.location.href = "/";
        return;
      }
      // 切换失败不能静默 — 用户会停留在旧身份，造成跨租户串数据
      toastError(tr("selectTenant.switchPersonalFailed"), null);
    } finally {
      setLoading(null);
    }
  }

  async function handleSelectTenant(t: TenantSummary) {
    if (t.is_current) {
      navigate({ to: "/", replace: true });
      return;
    }
    setLoading(t.tenant_id);
    try {
      const ok = await switchTenant(t.tenant_id);
      if (ok) {
        // 强制完整重载 — 确保所有组件/hook/缓存从零初始化,新 JWT 生效
        window.location.href = "/";
        return;
      }
      // 切换失败不能静默 — 用户会停留在旧身份，造成跨租户串数据
      toastError(
        tr("selectTenant.switchFailed", { name: t.tenant_name || t.company_name || t.tenant_id }),
        null,
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleLogout() {
    await logout();
    navigate({ to: "/login", replace: true });
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-gradient-brand">{BRAND_NAME}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{tr("selectTenant.subtitle")}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{tr("selectTenant.title")}</CardTitle>
            <CardDescription>{tr("selectTenant.desc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {/* 个人身份 */}
            <button
              onClick={handleSelectPersonal}
              disabled={!!loading}
              className="group flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left transition-colors hover:border-primary hover:bg-accent disabled:opacity-50"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-md bg-gradient-brand text-brand-foreground">
                <UserIcon className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium">
                    {user?.nickname || user?.email || tr("selectTenant.personalIdentity")}
                  </span>
                  <Badge variant="secondary" className="text-xs">
                    {tr("selectTenant.badgePersonal")}
                  </Badge>
                  {isPersonal && (
                    <Badge variant="default" className="text-xs">
                      {tr("selectTenant.badgeCurrent")}
                    </Badge>
                  )}
                </div>
                <div className="mt-0.5 truncate text-xs text-muted-foreground">{user?.email}</div>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </button>

            {/* 分隔线（仅当有租户时显示） */}
            {availableTenants.length > 0 && (
              <div className="flex items-center gap-2 py-1">
                <div className="h-px flex-1 bg-border" />
                <span className="text-[10px] text-muted-foreground">
                  {tr("selectTenant.tenantIdentities")}
                </span>
                <div className="h-px flex-1 bg-border" />
              </div>
            )}

            {/* 租户身份列表 */}
            {availableTenants.length === 0 && (
              <div className="py-4 text-center text-sm text-muted-foreground">
                {tr("selectTenant.noTenants")}
              </div>
            )}
            {availableTenants.map((t) => (
              <button
                key={t.tenant_id}
                onClick={() => handleSelectTenant(t)}
                disabled={!!loading}
                className="group flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left transition-colors hover:border-primary hover:bg-accent disabled:opacity-50"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <Building2 className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">
                      {t.tenant_name || t.company_name || tr("selectTenant.unnamedTenant")}
                    </span>
                    {t.is_current && (
                      <Badge variant="default" className="text-xs">
                        {tr("selectTenant.badgeCurrent")}
                      </Badge>
                    )}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {rolesLabel(tr, t)}
                    {t.tenant_type ? ` · ${t.tenant_type}` : ""}
                    {lastActiveLabel(tr, t.last_active_at)
                      ? ` · ${lastActiveLabel(tr, t.last_active_at)}`
                      : ""}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            ))}

            <div className="pt-4">
              <Button variant="ghost" size="sm" onClick={handleLogout} className="w-full">
                <LogOut className="mr-2 h-4 w-4" />
                {tr("selectTenant.useOtherAccount")}
              </Button>
            </div>
          </CardContent>
        </Card>

        {user?.email && (
          <p className="mt-4 text-center text-xs text-muted-foreground">
            {tr("selectTenant.currentAccount", { email: user.email })}
          </p>
        )}
      </div>
    </div>
  );
}
