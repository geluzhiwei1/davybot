/**
 * No Tenant Page — empty state when account belongs to no tenants.
 *
 * Prompt user to contact an admin for an invite, or create a new tenant.
 */
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AlertCircle, Plus, RefreshCw, LogOut } from "lucide-react";
import { useAuthStore } from "@/lib/auth-store";
import { BRAND_NAME } from "@/lib/brand";
import { toastError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/no-tenant")({
  component: NoTenantPage,
});

function NoTenantPage() {
  const { t } = useTranslation("routesB");
  const navigate = useNavigate();
  const { refreshAvailableTenants, switchTenant, logout } = useAuthStore();
  const [checking, setChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState<string>("");

  async function handleRefresh() {
    setChecking(true);
    try {
      const tenants = await refreshAvailableTenants();
      setLastChecked(new Date().toLocaleTimeString());
      if (tenants.length === 0) return;
      if (tenants.length === 1) {
        const ok = await switchTenant(tenants[0].tenant_id);
        if (ok) {
          // 与 select-tenant 一致：全量重载，确保新 JWT 全面生效
          window.location.href = "/";
          return;
        }
        // 切换失败不能静默 — 停在旧身份会造成跨租户串数据
        toastError(t("noTenant.switchFailed"), null);
      } else {
        navigate({ to: "/select-tenant", replace: true });
      }
    } finally {
      setChecking(false);
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
        </div>

        <Card>
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <AlertCircle className="h-7 w-7 text-muted-foreground" />
            </div>
            <CardTitle className="text-xl">{t("noTenant.title")}</CardTitle>
            <CardDescription className="mt-2">
              {t("noTenant.descLine1")}
              <br />
              {t("noTenant.descLine2")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button
              className="w-full"
              onClick={() => {
                /* TODO: 建立租戶流程 */
              }}
            >
              <Plus className="mr-2 h-4 w-4" />
              {t("noTenant.createTenant")}
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={handleRefresh}
              disabled={checking}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${checking ? "animate-spin" : ""}`} />
              {checking ? t("noTenant.checking") : t("noTenant.recheck")}
            </Button>
            <Button variant="ghost" className="w-full" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              {t("noTenant.useOtherAccount")}
            </Button>
            {lastChecked && (
              <p className="pt-2 text-center text-xs text-muted-foreground">
                {t("noTenant.lastChecked", { time: lastChecked })}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
