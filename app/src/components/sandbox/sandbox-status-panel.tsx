/**
 * SandboxStatusPanel — 当前会话状态 + 重连倒计时 (§14.3)
 * 订阅 sandboxStore
 */
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "react-i18next";
import { useSandboxStore } from "@/lib/stores/sandbox-store";
import { ReconnectBanner } from "./reconnect-banner";
import { QuotaIndicator } from "./quota-indicator";
import type { SandboxStatus } from "@/lib/types/sandbox";

const STATUS_VARIANT: Record<SandboxStatus, "default" | "secondary" | "destructive" | "outline"> = {
  uninitialized: "outline",
  initializing: "secondary",
  active: "default",
  paused: "secondary",
  queued: "secondary",
  reconnecting: "secondary",
  destroyed: "destructive",
  error: "destructive",
};

const STATUS_COLORS: Record<SandboxStatus, string> = {
  uninitialized: "bg-gray-400",
  initializing: "bg-yellow-400",
  active: "bg-green-500",
  paused: "bg-yellow-500",
  queued: "bg-blue-400",
  reconnecting: "bg-orange-400",
  destroyed: "bg-red-500",
  error: "bg-red-500",
};

export function SandboxStatusPanel() {
  const { t } = useTranslation("sandbox");
  const status = useSandboxStore((s) => s.status);
  const quotaUsage = useSandboxStore((s) => s.quotaUsage);
  const actualProvider = useSandboxStore((s) => s.actualProvider);

  return (
    <div className="space-y-3">
      <ReconnectBanner />

      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${STATUS_COLORS[status]} ${
            status === "active" || status === "initializing" ? "animate-pulse" : ""
          }`}
          aria-label={t(`status.${status}`)}
        />
        <Badge variant={STATUS_VARIANT[status]}>{t(`status.${status}`)}</Badge>
        {actualProvider && <Badge variant="outline">{actualProvider}</Badge>}
      </div>

      <QuotaIndicator usage={quotaUsage} />
    </div>
  );
}
