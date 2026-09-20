/**
 * Personal Module Subscription — 个人用户订阅管理
 *
 * 場景：用戶以「個人身份」登入（無租戶上下文）時，按 opt-in 訂閱自己需要的模塊。
 * 與租戶的雙層模型（authorized + enabled）並行 — 個人用戶**只有 enabled 層**：
 *   - 空 = 從未訂閱 → 全量啟用（向後兼容）
 *   - 非空 = 用戶明確訂閱
 *
 * pinned 模塊（首頁 / 工作區 / 知識 / 記憶 / 用戶設置）始終保留，
 * 不可被取消；前端 checkbox 鎖定禁用，但保留視覺便於了解。
 */
import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useMemo } from "react";
import { Loader2, Lock, Save, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { SUPPORT_API_URL } from "@/lib/env";
import { CapabilityGate } from "@/components/capability-gate";
import { useAuthStore } from "@/lib/auth-store";
import { useTranslation } from "react-i18next";
import i18n from "@/lib/i18n";

export const Route = createFileRoute("/settings/modules")({
  head: () => ({ meta: [{ title: i18n.t("routesB:settingsModules.metaTitle") }] }),
  component: PersonalModulesPage,
});

interface ModuleItem {
  key: string;
  group: string;
  group_title: string;
  title: string;
  route: string;
  icon: string;
  order: number;
  badge?: string | null;
  subgroup?: string | null;
  description?: string;
  pinned?: boolean;
  visible?: boolean;
}

interface ModuleGroup {
  key: string;
  group_title: string;
  items: ModuleItem[];
}

interface MyModulesResponse {
  enabled_modules: string[];
  all_modules: ModuleItem[];
  has_custom_subscription: boolean;
}

// 能力门 (多模式统一方案 §L4): 无 market capability → 显式空态而非空转
function PersonalModulesPage() {
  return (
    <CapabilityGate section="modules">
      <PersonalModulesPageInner />
    </CapabilityGate>
  );
}

function PersonalModulesPageInner() {
  const { t } = useTranslation("routesB");
  const accessToken = useAuthStore((s) => s.accessToken);
  const refreshAccessToken = useAuthStore((s) => s.refreshAccessToken);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [allModules, setAllModules] = useState<ModuleItem[]>([]);
  const [hasCustomSubscription, setHasCustomSubscription] = useState(false);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());

  /** 認證 fetch — 401 時自動 refresh 後重試一次。 */
  async function authedFetch(url: string, init?: RequestInit): Promise<Response> {
    const doFetch = (tok: string | null) =>
      fetch(url, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
          ...(init?.headers ?? {}),
        },
      });
    let res = await doFetch(accessToken);
    if (res.status === 401) {
      const ok = await refreshAccessToken();
      if (ok) {
        const newTok = useAuthStore.getState().accessToken;
        res = await doFetch(newTok);
      }
    }
    return res;
  }

  async function loadData() {
    setLoading(true);
    try {
      const res = await authedFetch(`${SUPPORT_API_URL}/v1/me/modules`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: MyModulesResponse = await res.json();
      setAllModules(data.all_modules ?? []);
      setHasCustomSubscription(data.has_custom_subscription);
      setEnabled(new Set(data.enabled_modules ?? []));
    } catch (e) {
      toast.error(t("settingsModules.loadFailed"), { description: String(e) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 分組渲染。 */
  const groups = useMemo<ModuleGroup[]>(() => {
    const map = new Map<string, ModuleGroup>();
    for (const m of allModules) {
      if (!map.has(m.group)) {
        map.set(m.group, { key: m.group, group_title: m.group_title, items: [] });
      }
      map.get(m.group)!.items.push(m);
    }
    // 模塊按 order 排序；分組按首個模塊的 group 名穩定排序
    for (const g of map.values()) {
      g.items.sort((a, b) => a.order - b.order);
    }
    return Array.from(map.values()).sort((a, b) => {
      const ao = a.items[0]?.order ?? 0;
      const bo = b.items[0]?.order ?? 0;
      return ao - bo;
    });
  }, [allModules]);

  function toggleItem(key: string, checked: boolean) {
    const next = new Set(enabled);
    if (checked) next.add(key);
    else next.delete(key);
    setEnabled(next);
  }

  function countChecked(g: ModuleGroup): number {
    return g.items.filter((it) => enabled.has(it.key)).length;
  }

  function isGroupAllChecked(g: ModuleGroup): boolean {
    return g.items.length > 0 && g.items.every((it) => enabled.has(it.key) || it.pinned);
  }

  function toggleGroup(g: ModuleGroup, checked: boolean) {
    const next = new Set(enabled);
    for (const it of g.items) {
      if (it.pinned) {
        next.add(it.key); // pinned 始終保留
        continue;
      }
      if (checked) next.add(it.key);
      else next.delete(it.key);
    }
    setEnabled(next);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const res = await authedFetch(`${SUPPORT_API_URL}/v1/me/modules`, {
        method: "PUT",
        body: JSON.stringify({ enabled_modules: Array.from(enabled) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      // 刷新 /me 以更新 effectiveModules（前端 sidebar 即時更新）
      await useAuthStore.getState().loadFromStorage();
      toast.success(t("settingsModules.saved"));
    } catch (e) {
      toast.error(t("settingsModules.saveFailed"), { description: String(e) });
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    if (!confirm(t("settingsModules.resetConfirm"))) return;
    // 「恢复全量」= 訂閱所有非 pinned 模塊（empty 訂閱現在 = 僅 pinned，可見變少）
    // 注意：取消所有勾選 ≠ 全量 — 取消會回到「僅 pinned」狀態。
    const allKeys = allModules.filter((m) => !m.pinned).map((m) => m.key);
    const next = new Set(allKeys);
    setEnabled(next);
    setSaving(true);
    try {
      const res = await authedFetch(`${SUPPORT_API_URL}/v1/me/modules`, {
        method: "PUT",
        body: JSON.stringify({ enabled_modules: Array.from(next) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data: MyModulesResponse = await res.json();
      setEnabled(new Set(data.enabled_modules ?? []));
      setHasCustomSubscription(data.has_custom_subscription);
      await useAuthStore.getState().loadFromStorage();
      toast.success(t("settingsModules.resetDone"));
    } catch (e) {
      toast.error(t("settingsModules.resetFailed"), { description: String(e) });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl py-6 px-4">
      <Card className="mb-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            {t("settingsModules.title")}
          </CardTitle>
          <CardDescription>
            {t("settingsModules.descLine1")}
            <strong className="ml-1">{t("settingsModules.descUncheck")}</strong>
            {t("settingsModules.descLine2")}
            {t("settingsModules.descLine3")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!hasCustomSubscription && (
            <Alert>
              <Sparkles className="h-4 w-4" />
              <AlertTitle>{t("settingsModules.noSubscriptionTitle")}</AlertTitle>
              <AlertDescription>{t("settingsModules.noSubscriptionDesc")}</AlertDescription>
            </Alert>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={handleReset} disabled={saving}>
              <RotateCcw className="w-4 h-4 mr-2" />
              {t("settingsModules.subscribeAll")}
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              {t("settingsModules.saveSettings")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {groups.map((g) => (
          <Card key={g.key}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Checkbox
                    checked={isGroupAllChecked(g)}
                    onCheckedChange={(v) => toggleGroup(g, v === true)}
                  />
                  {g.group_title}
                </CardTitle>
                <span className="text-xs text-muted-foreground">
                  {countChecked(g)}/{g.items.length}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {g.items.map((it) => {
                const checked = enabled.has(it.key);
                const row = (
                  <label
                    key={it.key}
                    className={`flex items-center gap-2 text-sm py-1 ${it.pinned ? "opacity-70" : ""}`}
                  >
                    <Checkbox
                      checked={checked}
                      disabled={it.pinned}
                      onCheckedChange={(v) => toggleItem(it.key, v === true)}
                    />
                    <span>{it.title}</span>
                    {it.pinned && (
                      <Badge variant="outline" className="text-[10px] py-0 px-1">
                        {t("settingsModules.pinned")}
                      </Badge>
                    )}
                    {it.badge && (
                      <Badge variant="secondary" className="text-[10px] py-0 px-1">
                        {it.badge}
                      </Badge>
                    )}
                    {it.pinned && <Lock className="w-3 h-3 text-muted-foreground ml-auto" />}
                  </label>
                );

                if (it.pinned) {
                  return (
                    <Tooltip key={it.key}>
                      <TooltipTrigger asChild>{row}</TooltipTrigger>
                      <TooltipContent>{t("settingsModules.pinnedTooltip")}</TooltipContent>
                    </Tooltip>
                  );
                }
                return row;
              })}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
