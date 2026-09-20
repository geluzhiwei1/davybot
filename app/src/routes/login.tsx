/**
 * Login Page — dual form by runtime capability (多模式统一方案 §L4).
 * - auth capability present (saas/desktop): email/phone + password via
 *   nn-user-system (SUPPORT_API_URL).
 * - no auth capability (server/tui 自包含): single access-password gate
 *   (DAWEI_SERVER_PASSWORD on the server; unset → leave empty and enter).
 * caps not yet loaded / old backend → account form (维持现状, FAST FAIL).
 */
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import { useCaps } from "@/lib/stores/runtime-store";
import { getApiBaseUrl } from "@/lib/env";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

function LoginPage() {
  const { t } = useTranslation("routesA");
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const enterLocalMode = useAuthStore((s) => s.enterLocalMode);

  // 运行期能力 (唯一判定口, 禁止按 mode 字符串分支): 无 auth cap → 访问密码门
  const { caps } = useCaps();
  const accountMode = caps === null || caps.includes("auth");

  const [loginType, setLoginType] = useState<"email" | "phone">("email");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [accessPassword, setAccessPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await login(identifier, password, loginType);
      // 身份选择分发：
      //   有租户 membership → /select-tenant（让用户选个人身份 or 租户身份）
      //   无租户 membership  → 直接进入个人模式（系统原生支持,不阻断）
      const tenants = Array.isArray(data.available_tenants) ? data.available_tenants : [];
      if (tenants.length > 0) {
        navigate({ to: "/select-tenant", replace: true });
      } else {
        navigate({ to: "/", replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  /**
   * server 自包含访问密码门: 用裸 fetch 探测一个受保护端点校验密码
   * (不走 request() — 其 401 处理会强制登出+整页跳转, 吞掉本页错误提示)。
   */
  async function handleAccessSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/workspaces/v2/workspaces`, {
        headers: accessPassword ? { Authorization: `Bearer ${accessPassword}` } : {},
      });
      if (res.status === 401) {
        setError(t("login.accessWrong"));
        return;
      }
      enterLocalMode(accessPassword || undefined);
      navigate({ to: "/", replace: true });
    } catch {
      setError(t("login.failed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        {/* Brand header */}
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-gradient-brand">NormNomos</h1>
          <p className="mt-2 text-sm text-muted-foreground">{t("login.tagline")}</p>
        </div>

        {accountMode ? (
          <Card>
            <CardHeader className="space-y-1 pb-4">
              <CardTitle className="text-xl">{t("login.title")}</CardTitle>
              <CardDescription>{t("login.subtitle")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <Tabs
                  value={loginType}
                  onValueChange={(v) => {
                    setLoginType(v as "email" | "phone");
                    setIdentifier("");
                    setError(null);
                  }}
                >
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="email">{t("login.email")}</TabsTrigger>
                    <TabsTrigger value="phone">{t("login.phone")}</TabsTrigger>
                  </TabsList>

                  <TabsContent value="email" className="mt-4 space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="email">{t("login.emailAddress")}</Label>
                      <Input
                        id="email"
                        type="email"
                        placeholder="user@example.com"
                        value={loginType === "email" ? identifier : ""}
                        onChange={(e) => setIdentifier(e.target.value)}
                        autoComplete="email"
                        required
                      />
                    </div>
                  </TabsContent>

                  <TabsContent value="phone" className="mt-4 space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="phone">{t("login.phoneNumber")}</Label>
                      <Input
                        id="phone"
                        type="tel"
                        placeholder="13800138000"
                        value={loginType === "phone" ? identifier : ""}
                        onChange={(e) => setIdentifier(e.target.value)}
                        autoComplete="tel"
                        required
                      />
                    </div>
                  </TabsContent>
                </Tabs>

                <div className="space-y-2">
                  <Label htmlFor="password">{t("login.password")}</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder={t("login.passwordPlaceholder")}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                  />
                </div>

                <Button
                  type="submit"
                  className="w-full bg-gradient-brand text-brand-foreground shadow-brand"
                  disabled={loading || !identifier || !password}
                >
                  {loading ? t("login.signingIn") : t("login.submit")}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="space-y-1 pb-4">
              <CardTitle className="text-xl">{t("login.accessTitle")}</CardTitle>
              <CardDescription>{t("login.accessSubtitle")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleAccessSubmit} className="space-y-4">
                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <div className="space-y-2">
                  <Label htmlFor="access-password">{t("login.accessPassword")}</Label>
                  <Input
                    id="access-password"
                    type="password"
                    placeholder={t("login.accessPlaceholder")}
                    value={accessPassword}
                    onChange={(e) => setAccessPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                </div>

                <Button
                  type="submit"
                  className="w-full bg-gradient-brand text-brand-foreground shadow-brand"
                  disabled={loading}
                >
                  {loading ? t("login.accessChecking") : t("login.accessSubmit")}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}

        <p className="mt-4 text-center text-xs text-muted-foreground">{t("login.terms")}</p>
      </div>
    </div>
  );
}
