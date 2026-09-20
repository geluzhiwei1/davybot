/**
 * QuotaIndicator — n/N 沙箱 + 内存条 (§14.3)
 * 展示型
 */
import { Progress } from "@/components/ui/progress";
import { useTranslation } from "react-i18next";
import type { QuotaUsage } from "@/lib/types/sandbox";

function pct(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, (used / limit) * 100);
}

function fmtMem(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

export function QuotaIndicator({ usage }: { usage: QuotaUsage | null }) {
  const { t } = useTranslation("sandboxUi");
  if (!usage) {
    return <p className="text-sm text-muted-foreground">{t("quota.loading")}</p>;
  }

  const sessionPct = pct(usage.sessions.used, usage.sessions.limit);
  const memPct = pct(usage.memory_mb.used, usage.memory_mb.limit);
  const ratePct = pct(usage.rate_per_min.used, usage.rate_per_min.limit);

  return (
    <div className="space-y-3" role="region" aria-label={t("quota.region")}>
      {/* Sessions */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span>{t("quota.sessions")}</span>
          <span className={sessionPct >= 90 ? "font-bold text-destructive" : ""}>
            {usage.sessions.used} / {usage.sessions.limit}
          </span>
        </div>
        <Progress
          value={sessionPct}
          aria-valuenow={usage.sessions.used}
          aria-valuemax={usage.sessions.limit}
        />
      </div>

      {/* Memory */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span>{t("quota.memory")}</span>
          <span className={memPct >= 90 ? "font-bold text-destructive" : ""}>
            {fmtMem(usage.memory_mb.used)} / {fmtMem(usage.memory_mb.limit)}
          </span>
        </div>
        <Progress
          value={memPct}
          aria-valuenow={usage.memory_mb.used}
          aria-valuemax={usage.memory_mb.limit}
        />
      </div>

      {/* Rate */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span>{t("quota.rate")}</span>
          <span className={ratePct >= 90 ? "font-bold text-destructive" : ""}>
            {usage.rate_per_min.used} / {usage.rate_per_min.limit}
          </span>
        </div>
        <Progress
          value={ratePct}
          aria-valuenow={usage.rate_per_min.used}
          aria-valuemax={usage.rate_per_min.limit}
        />
      </div>
    </div>
  );
}
