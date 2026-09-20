/**
 * CapabilitiesBadge — 隔离级别 / 冷启动 / 超时徽章 (§14.3)
 * 展示型, 无状态
 */
import { Badge } from "@/components/ui/badge";
import { Shield, Zap, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SandboxCapabilities, IsolationLevel } from "@/lib/types/sandbox";

const ISOLATION_VARIANT: Record<
  IsolationLevel,
  "default" | "secondary" | "destructive" | "outline"
> = {
  none: "destructive",
  process: "secondary",
  container: "default",
  hardware: "default",
};

export function CapabilitiesBadge({ capabilities }: { capabilities: SandboxCapabilities }) {
  const { t } = useTranslation("sandbox");
  return (
    <div className="flex flex-wrap gap-2">
      <Badge variant={ISOLATION_VARIANT[capabilities.isolation_level]} className="gap-1">
        <Shield className="h-3 w-3" />
        {t(`capabilities.isolation.${capabilities.isolation_level}`)}
      </Badge>
      <Badge variant="outline" className="gap-1">
        <Zap className="h-3 w-3" />
        {t("capabilities.coldStart", { ms: capabilities.cold_start_ms })}
      </Badge>
      <Badge variant="outline" className="gap-1">
        <Clock className="h-3 w-3" />
        {t("capabilities.timeout", { seconds: capabilities.max_timeout_s })}
      </Badge>
    </div>
  );
}
