/**
 * Sandbox 高级配置子页 — §14.2.2
 *
 * 路由: /settings/security/sandbox
 *
 * 三段式布局 (Tabs):
 * 1. Provider — radio + capabilities + test connection
 * 2. 工作区挂载 — mount_mode + virtiofs + path preview
 * 3. 网络与配额 — network policy summary + quota + grace period
 */
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { useSandboxStore } from "@/lib/stores/sandbox-store";
import { CapabilityGate } from "@/components/capability-gate";
import { sandboxPolicyApi, sandboxSettingsApi } from "@/lib/api/sandbox";

import { ProviderSelector } from "@/components/sandbox/provider-selector";
import { SandboxTestButton } from "@/components/sandbox/sandbox-test-button";
import { MountModeSelector } from "@/components/sandbox/mount-mode-selector";
import { VirtiofsToggle } from "@/components/sandbox/virtiofs-toggle";
import { NetworkPolicyViewer } from "@/components/sandbox/network-policy-viewer";
import { QuotaIndicator } from "@/components/sandbox/quota-indicator";

import type { ProviderType, MountMode, NetworkPolicy } from "@/lib/types/sandbox";
import { useTranslation } from "react-i18next";
import i18n from "@/lib/i18n";

export const Route = createFileRoute("/settings/security/sandbox")({
  head: () => ({ meta: [{ title: i18n.t("routesB:settingsSandbox.metaTitle") }] }),
  component: SandboxConfigPage,
});

// 能力门 (多模式统一方案 §L4): server/tui 无 sandbox capability → 显式空态
function SandboxConfigPage() {
  return (
    <CapabilityGate section="sandbox">
      <SandboxConfigPageInner />
    </CapabilityGate>
  );
}

function SandboxConfigPageInner() {
  const { t } = useTranslation("routesB");
  const { selectedProvider, capabilities, loadInitial, setProvider, quotaUsage, actualProvider } =
    useSandboxStore();

  const [mountMode, setMountMode] = useState<MountMode>("ro");
  const [virtiofs, setVirtiofs] = useState(false);
  const [policy, setPolicy] = useState<NetworkPolicy | null>(null);

  useEffect(() => {
    loadInitial();
    sandboxPolicyApi
      .getPolicy()
      .then((res) => setPolicy(res.policy))
      .catch(() => {});
    sandboxSettingsApi
      .get()
      .then((res) => {
        if (res.settings?.workspace_mount_mode) {
          setMountMode(res.settings.workspace_mount_mode as MountMode);
        }
        if (res.settings?.virtiofs_enabled !== undefined) {
          setVirtiofs(res.settings.virtiofs_enabled as boolean);
        }
      })
      .catch(() => {});
  }, [loadInitial]);

  async function handleMountModeChange(m: MountMode) {
    setMountMode(m);
    try {
      await sandboxSettingsApi.updateSandbox({ workspace_mount_mode: m });
    } catch {
      // 静默
    }
  }

  async function handleVirtiofsChange(v: boolean) {
    setVirtiofs(v);
    try {
      await sandboxSettingsApi.updateSandbox({ virtiofs_enabled: v });
    } catch {
      // 静默
    }
  }

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-3xl mx-auto px-6 py-10">
        {/* 原「返回设置」按钮随 /settings 枢纽页移除;本页入口 = 用户设置抽屉 Security tab 的详细链接 */}
        <h1 className="text-2xl font-bold mb-1">{t("settingsSandbox.title")}</h1>
        <p className="text-sm text-muted-foreground mb-6">{t("settingsSandbox.desc")}</p>

        <Tabs defaultValue="provider">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="provider">Provider</TabsTrigger>
            <TabsTrigger value="mount">{t("settingsSandbox.tabMount")}</TabsTrigger>
            <TabsTrigger value="network">{t("settingsSandbox.tabNetwork")}</TabsTrigger>
          </TabsList>

          {/* ─── Tab 1: Provider ─────────────────────────────── */}
          <TabsContent value="provider" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("settingsSandbox.selectProvider")}</CardTitle>
                <CardDescription>{t("settingsSandbox.selectProviderDesc")}</CardDescription>
              </CardHeader>
              <CardContent>
                <ProviderSelector
                  value={selectedProvider}
                  onChange={(p: ProviderType) => setProvider(p)}
                  capabilities={capabilities}
                  actualProvider={actualProvider ?? undefined}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("settingsSandbox.connectionTest")}</CardTitle>
              </CardHeader>
              <CardContent>
                <SandboxTestButton provider={selectedProvider} />
              </CardContent>
            </Card>
          </TabsContent>

          {/* ─── Tab 2: 工作区挂载 ───────────────────────────── */}
          <TabsContent value="mount" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("settingsSandbox.mountMode")}</CardTitle>
                <CardDescription>{t("settingsSandbox.mountModeDesc")}</CardDescription>
              </CardHeader>
              <CardContent>
                <MountModeSelector value={mountMode} onChange={handleMountModeChange} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">VirtioFS</CardTitle>
              </CardHeader>
              <CardContent>
                <VirtiofsToggle
                  value={virtiofs}
                  onChange={handleVirtiofsChange}
                  available={selectedProvider === "e2b" || selectedProvider === "auto"}
                />
              </CardContent>
            </Card>

            <Alert>
              <AlertDescription>{t("settingsSandbox.mountAlert")}</AlertDescription>
            </Alert>
          </TabsContent>

          {/* ─── Tab 3: 网络与配额 ───────────────────────────── */}
          <TabsContent value="network" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("settingsSandbox.networkPolicy")}</CardTitle>
                <CardDescription>{t("settingsSandbox.networkPolicyDesc")}</CardDescription>
              </CardHeader>
              <CardContent>
                <NetworkPolicyViewer policy={policy} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("settingsSandbox.quotaUsage")}</CardTitle>
              </CardHeader>
              <CardContent>
                <QuotaIndicator usage={quotaUsage} />
              </CardContent>
            </Card>

            <Alert>
              <AlertDescription>{t("settingsSandbox.gracePeriodAlert")}</AlertDescription>
            </Alert>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
