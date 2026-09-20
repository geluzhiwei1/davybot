/**
 * ProviderSelector — Provider radio + 描述 (§14.3)
 * 状态归属: 父组件 (Settings 页)
 */
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { useTranslation } from "react-i18next";
import { CapabilitiesBadge } from "./capabilities-badge";
import type { ProviderType, SandboxCapabilities } from "@/lib/types/sandbox";

interface ProviderSelectorProps {
  value: ProviderType;
  onChange: (p: ProviderType) => void;
  capabilities?: SandboxCapabilities | null;
  availableProviders?: ProviderType[];
  deploymentMode?: "local" | "saas";
  actualProvider?: ProviderType | null;
}

export function ProviderSelector({
  value,
  onChange,
  capabilities,
  availableProviders,
  deploymentMode,
}: ProviderSelectorProps) {
  const { t } = useTranslation("sandbox");
  const allProviders: ProviderType[] = ["auto", "subprocess", "docker", "e2b"];
  // 模式收敛 (2026-09-19 desktop 沙箱简化, 与后端 provider_factory 守卫一致):
  // - local (PC App): 仅 docker (Podman 兼容) + auto
  // - saas:          仅 e2b (CubeSandbox) + auto
  // - 未知模式: 全量, 由 availableProviders (后端 /providers) 兜底过滤
  const visibleProviders = allProviders.filter((p) => {
    if (
      availableProviders &&
      availableProviders.length > 0 &&
      !availableProviders.includes(p) &&
      p !== "auto"
    ) {
      return false;
    }
    if (deploymentMode === "local" && (p === "subprocess" || p === "e2b")) return false;
    if (deploymentMode === "saas" && (p === "subprocess" || p === "docker")) return false;
    return true;
  });

  return (
    <div className="space-y-3">
      <RadioGroup
        value={value}
        onValueChange={(v) => onChange(v as ProviderType)}
        className="gap-3"
      >
        {visibleProviders.map((p) => (
          <div
            key={p}
            className="flex items-start gap-3 rounded-lg border p-3 has-[:checked]:border-primary has-[:checked]:bg-primary/5"
          >
            <RadioGroupItem value={p} id={`provider-${p}`} className="mt-1" />
            <div className="flex-1 space-y-1">
              <Label htmlFor={`provider-${p}`} className="cursor-pointer font-medium">
                {t(`provider.${p}.label`)}
              </Label>
              <p className="text-sm text-muted-foreground">{t(`provider.${p}.description`)}</p>
              {value === p && capabilities && (
                <div className="pt-1">
                  <CapabilitiesBadge capabilities={capabilities} />
                </div>
              )}
            </div>
          </div>
        ))}
      </RadioGroup>
    </div>
  );
}
