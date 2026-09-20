/**
 * SandboxSection — 沙箱配置 Section (容器组件)
 *
 * 用于嵌入 settings 页面, 组合多个 sandbox 子组件 (§14.2.1)
 *
 * 组件层级:
 *   SandboxSection (container)
 *     ├─ ProviderHealthIndicator
 *     ├─ ProviderSelector
 *     │    └─ CapabilitiesBadge
 *     ├─ SandboxStatusPanel
 *     │    ├─ ReconnectBanner
 *     │    └─ QuotaIndicator
 *     └─ NetworkPolicyViewer
 */
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, Settings2 } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useSandboxStore } from "@/lib/stores/sandbox-store";
import { sandboxPolicyApi, sandboxProviderApi } from "@/lib/api/sandbox";
import { sandboxSettingsApi } from "@/lib/api/sandbox";

import { ProviderSelector } from "./provider-selector";
import { ProviderHealthIndicator } from "./provider-health-indicator";
import { SandboxStatusPanel } from "./sandbox-status-panel";
import { NetworkPolicyViewer } from "./network-policy-viewer";
import { MountModeSelector } from "./mount-mode-selector";
import { VirtiofsToggle } from "./virtiofs-toggle";
import { SandboxTestButton } from "./sandbox-test-button";

import type { ProviderType, MountMode, NetworkPolicy } from "@/lib/types/sandbox";

export function SandboxSection() {
  const { t } = useTranslation("sandbox");
  const { selectedProvider, capabilities, loadInitial, setProvider, actualProvider } =
    useSandboxStore();

  const [mountMode, setMountMode] = useState<MountMode>("ro");
  const [virtiofs, setVirtiofs] = useState(false);
  const [policy, setPolicy] = useState<NetworkPolicy | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // 部署模式 (local=PC App / saas) — 决定 Provider 选项与 virtiofs 可见性
  // (2026-09-19 简化: local 仅 Docker/Podman, 无 e2b/subprocess)
  const [deploymentMode, setDeploymentMode] = useState<"local" | "saas" | null>(null);

  useEffect(() => {
    loadInitial();
    // 加载部署模式 (拉取失败保持 null → ProviderSelector 显示全量并依赖 availableProviders)
    sandboxProviderApi
      .getDeploymentMode()
      .then((res) => setDeploymentMode(res.mode))
      .catch(() => {});
    // 加载网络策略
    sandboxPolicyApi
      .getPolicy()
      .then((res) => setPolicy(res.policy))
      .catch(() => {});
    // 加载用户 sandbox 设置
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
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>{t("section.title")}</CardTitle>
            <CardDescription>{t("section.description")}</CardDescription>
          </div>
          <ProviderHealthIndicator />
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Provider 选择 */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Provider</h4>
          <ProviderSelector
            value={selectedProvider}
            onChange={(p: ProviderType) => setProvider(p)}
            capabilities={capabilities}
            deploymentMode={deploymentMode ?? undefined}
            actualProvider={actualProvider ?? undefined}
          />
        </div>

        {/* 状态面板 */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">{t("section.currentStatus")}</h4>
          <SandboxStatusPanel />
        </div>

        {/* 网络策略 */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium">{t("section.networkPolicy")}</h4>
          <NetworkPolicyViewer policy={policy} />
        </div>

        {/* 高级配置 (折叠) */}
        <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full">
              <Settings2 className="mr-2 h-4 w-4" />
              {t("section.advanced")}
              <ChevronDown
                className={`ml-2 h-4 w-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 pt-4">
            {/* Provider 测试 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">{t("section.connectionTest")}</h4>
              <SandboxTestButton provider={selectedProvider} />
            </div>

            {/* 挂载模式 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">{t("section.mountMode")}</h4>
              <MountModeSelector value={mountMode} onChange={handleMountModeChange} />
            </div>

            {/* VirtioFS */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">VirtioFS</h4>
              <VirtiofsToggle
                value={virtiofs}
                onChange={handleVirtiofsChange}
                available={
                  // virtiofs 是 CubeSandbox/E2B microVM 特性 — 仅 SaaS 可用
                  deploymentMode === "saas" &&
                  (selectedProvider === "e2b" || selectedProvider === "auto")
                }
                deploymentMode={deploymentMode ?? undefined}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>

        {/* 链接到沙箱高级配置页 */}
        <Button variant="link" size="sm" asChild>
          <Link to="/settings/security/sandbox">{t("section.detailedSettings")}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
