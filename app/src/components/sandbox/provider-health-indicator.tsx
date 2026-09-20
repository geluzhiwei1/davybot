/**
 * ProviderHealthIndicator — Provider 列表 + 健康状态点 (§14.3)
 * 内部 fetch
 */
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { sandboxProviderApi } from "@/lib/api/sandbox";
import type { ProviderHealth } from "@/lib/types/sandbox";

export function ProviderHealthIndicator() {
  const { t } = useTranslation("sandbox");
  const [providers, setProviders] = useState<ProviderHealth[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function fetchHealth() {
      try {
        const res = await sandboxProviderApi.listProviders();
        if (mounted) setProviders(res.providers);
      } catch {
        // 静默失败
      } finally {
        if (mounted) setLoading(false);
      }
    }

    fetchHealth();
    const timer = setInterval(fetchHealth, 30_000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);

  if (loading) {
    return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />;
  }

  if (providers.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {providers.map((p) => (
        <div key={p.provider} className="flex items-center gap-1.5">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              p.available ? "bg-green-500" : "bg-red-500"
            }`}
            aria-label={p.available ? t("health.available") : t("health.unavailable")}
          />
          <Badge variant="outline" className="text-xs">
            {p.provider}
            {p.latency_ms ? ` · ${p.latency_ms}ms` : ""}
          </Badge>
        </div>
      ))}
    </div>
  );
}
