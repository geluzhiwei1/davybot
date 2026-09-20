/**
 * LLMProvidersDrawer — LLM provider and model configuration.
 * Shows available providers with pricing, auto mode toggle, and credits balance.
 */
import { useEffect, useState, useCallback } from "react";
import { Cpu, Zap, Wallet, RefreshCw, ExternalLink } from "lucide-react";
import { toastError } from "@/lib/api/client.js";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/lib/auth-store";
import { AppDrawer } from "./app-drawer";
import { useStore, type LLMModel } from "@/lib/store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getPreferences,
  updatePreferences,
  getCreditsBalance,
  type UserPreferences as GWPreferences,
  type CreditsBalance,
} from "@/lib/llm-gateway-service";

const STRATEGY_LABEL_KEYS: Record<string, string> = {
  balanced: "llmDrawer.strategy.balanced",
  cost_first: "llmDrawer.strategy.cost_first",
  quality_first: "llmDrawer.strategy.quality_first",
  fast_first: "llmDrawer.strategy.fast_first",
};

export function LLMProvidersDrawer() {
  const { t } = useTranslation("drawersUi");
  const models = useStore((s) => s.models);

  return (
    <AppDrawer
      id="llm"
      title={t("llmDrawer.title")}
      description={t("llmDrawer.description")}
      icon={Cpu}
      badge={t("llmDrawer.badge", { count: models.length })}
      width="w-full sm:w-[440px] sm:max-w-[480px]"
    >
      <div className="p-4 space-y-3">
        <CreditsBar />
        <AutoModeSection />
        <ModelList />
      </div>
    </AppDrawer>
  );
}

/** 积分余额展示条 — 按当前身份查询：租户会话查租户余额，个人会话查个人余额 */
function CreditsBar() {
  const { t } = useTranslation("drawersUi");
  const [balance, setBalance] = useState<CreditsBalance | null>(null);
  const [loading, setLoading] = useState(false);
  // is_current 由后端根据 JWT tid 标记；有标记 = 租户会话
  const tenantName = useAuthStore(
    (s) => s.availableTenants.find((t) => t.is_current)?.tenant_name ?? null,
  );
  const scope: "user" | "tenant" = tenantName ? "tenant" : "user";

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const b = await getCreditsBalance(scope);
      setBalance(b);
    } catch (e) {
      console.error("[LLMDrawer] getCreditsBalance failed:", e);
      toastError(t("llmDrawer.credits.loadFailed"), e);
    } finally {
      setLoading(false);
    }
  }, [scope, t]);

  useEffect(() => {
    setBalance(null); // 身份切换时先清空旧余额，避免闪现错值
    refresh();
  }, [refresh]);

  return (
    <div className="rounded-lg border border-border/60 px-3 py-2.5 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Wallet className="w-4 h-4 text-brand" />
        <span className="text-sm font-medium">{t("llmDrawer.credits.title")}</span>
        {scope === "tenant" && (
          <Badge variant="secondary" className="text-[9px] px-1.5">
            {t("llmDrawer.credits.tenant", { name: tenantName })}
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-brand">
          {balance ? balance.balance.toFixed(2) : "—"}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
        </Button>
        <a
          href={`${window.location.origin}/support/ui/user/dashboard`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-brand/10 text-brand hover:bg-brand/20 transition"
        >
          {t("llmDrawer.credits.recharge")} <ExternalLink className="w-2.5 h-2.5" />
        </a>
      </div>
    </div>
  );
}

/** Auto Mode 切换 + 策略选择 */
function AutoModeSection() {
  const { t } = useTranslation("drawersUi");
  const [prefs, setPrefs] = useState<GWPreferences | null>(null);
  const [saving, setSaving] = useState(false);

  const loadPrefs = useCallback(async () => {
    try {
      const p = await getPreferences();
      setPrefs(p);
    } catch (e) {
      console.error("[LLMDrawer] getPreferences failed:", e);
      toastError(t("llmDrawer.prefs.loadFailed"), e);
    }
  }, [t]);

  useEffect(() => {
    loadPrefs();
  }, [loadPrefs]);

  const toggleAutoMode = async (enabled: boolean) => {
    if (!prefs) return;
    setSaving(true);
    try {
      await updatePreferences({ auto_mode_enabled: enabled });
      setPrefs({ ...prefs, auto_mode_enabled: enabled });
    } catch (e) {
      console.error("[LLMDrawer] updatePreferences failed:", e);
      toastError(t("llmDrawer.prefs.saveFailed"), e);
    } finally {
      setSaving(false);
    }
  };

  const changeStrategy = async (strategy: string) => {
    if (!prefs) return;
    setSaving(true);
    try {
      await updatePreferences({
        auto_mode_strategy: strategy as GWPreferences["auto_mode_strategy"],
      });
      setPrefs({ ...prefs, auto_mode_strategy: strategy as GWPreferences["auto_mode_strategy"] });
    } catch (e) {
      console.error("[LLMDrawer] updatePreferences failed:", e);
      toastError(t("llmDrawer.prefs.saveFailed"), e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-border/60 px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-yellow-500" />
          <span className="text-sm font-medium">Auto Mode</span>
        </div>
        <Switch
          checked={prefs?.auto_mode_enabled ?? false}
          onCheckedChange={toggleAutoMode}
          disabled={saving}
        />
      </div>
      {prefs?.auto_mode_enabled && (
        <div className="flex items-center gap-2 pl-6">
          <span className="text-[11px] text-muted-foreground">
            {t("llmDrawer.autoMode.strategy")}
          </span>
          <Select value={prefs.auto_mode_strategy} onValueChange={changeStrategy} disabled={saving}>
            <SelectTrigger className="h-7 text-xs w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(STRATEGY_LABEL_KEYS).map(([key, labelKey]) => (
                <SelectItem key={key} value={key} className="text-xs">
                  {t(labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground pl-6">
        {t("llmDrawer.autoMode.strategyHint")}
      </p>
    </div>
  );
}

/** 模型列表：官方模型与本地模型分区展示，各自按 provider 分组（不合并） */
function ModelList() {
  const { t } = useTranslation("drawersUi");
  const models = useStore((s) => s.models);

  if (models.length === 0) {
    return (
      <div>
        <h3 className="text-xs font-medium text-muted-foreground mb-2 px-1">
          {t("llmDrawer.models.title")}
        </h3>
        <div className="text-center py-4 text-xs text-muted-foreground border border-dashed border-border rounded-lg">
          {t("llmDrawer.models.empty")}
        </div>
      </div>
    );
  }

  // 按来源拆分：官方（网关/系统内置，按积分计费）与本地（自配 Key），各自独立分区
  const official = models.filter((m) => m.source === "official");
  const local = models.filter((m) => m.source !== "official");

  return (
    <div>
      <div className="flex items-center justify-between mb-1 px-1">
        <h3 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
          <Cpu className="w-3 h-3" /> {t("llmDrawer.models.title")}
        </h3>
        <span className="text-[10px] text-muted-foreground">
          {t("llmDrawer.models.countSummary", { count: models.length })}
          {official.length > 0 && (
            <span className="text-brand">
              {t("llmDrawer.models.officialCount", { count: official.length })}
            </span>
          )}
          {local.length > 0 && (
            <span>{t("llmDrawer.models.localCount", { count: local.length })}</span>
          )}
        </span>
      </div>
      <p className="text-[11px] text-muted-foreground mb-2 px-1">{t("llmDrawer.models.note")}</p>
      <div className="space-y-3 max-h-[360px] overflow-y-auto scrollbar-thin">
        {official.length > 0 && (
          <ModelSection
            title={t("llmDrawer.models.officialSection")}
            hint={t("llmDrawer.models.officialHint")}
            models={official}
          />
        )}
        {local.length > 0 && (
          <ModelSection
            title={t("llmDrawer.models.localSection")}
            hint={t("llmDrawer.models.localHint")}
            models={local}
          />
        )}
      </div>
    </div>
  );
}

/** 一个来源分区（官方/本地），标题下按 provider 分组渲染卡片 */
function ModelSection({
  title,
  hint,
  models,
}: {
  title: string;
  hint: string;
  models: LLMModel[];
}) {
  const { t } = useTranslation("drawersUi");
  // Group models by provider within this section
  const providerMap = new Map<string, LLMModel[]>();
  for (const m of models) {
    const provider = m.provider ?? "default";
    if (!providerMap.has(provider)) providerMap.set(provider, []);
    providerMap.get(provider)!.push(m);
  }

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5 px-1">
        <span className="text-xs font-semibold">{title}</span>
        <span className="text-[10px] text-muted-foreground">{hint}</span>
      </div>
      <div className="space-y-2">
        {Array.from(providerMap.entries()).map(([provider, pModels]) => (
          <div key={provider} className="rounded-lg border border-border/60 px-3 py-2">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm font-medium">{provider}</span>
              <span className="text-[10px] text-muted-foreground">
                {t("llmDrawer.models.providerCount", { count: pModels.length })}
              </span>
            </div>
            <div className="space-y-1">
              {pModels.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between text-[11px] px-1 py-0.5 rounded hover:bg-muted/40"
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="truncate font-medium">{m.name || m.id}</span>
                    {m.supportsVision && (
                      <Badge variant="outline" className="text-[8px] px-1 py-0 h-3.5">
                        Vision
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 text-muted-foreground">
                    {m.pricing ? (
                      <>
                        <span>
                          {m.pricing.inputRate}/{m.pricing.outputRate}
                        </span>
                        <span className="text-[9px]">{t("llmDrawer.models.creditsPer1K")}</span>
                      </>
                    ) : (
                      <span className="text-[9px]">{t("llmDrawer.models.free")}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
