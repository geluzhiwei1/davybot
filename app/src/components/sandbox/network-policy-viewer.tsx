/**
 * NetworkPolicyViewer — 只读网络策略摘要 (§14.3)
 * 展示型
 */
import { Badge } from "@/components/ui/badge";
import { Globe, ShieldCheck, ShieldX } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { NetworkPolicy } from "@/lib/types/sandbox";

export function NetworkPolicyViewer({ policy }: { policy: NetworkPolicy | null }) {
  const { t } = useTranslation("sandboxUi");
  if (!policy) {
    return <p className="text-sm text-muted-foreground">{t("networkPolicy.loading")}</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {policy.default_action === "deny" ? (
          <Badge variant="default" className="gap-1">
            <ShieldX className="h-3 w-3" /> {t("networkPolicy.defaultDeny")}
          </Badge>
        ) : (
          <Badge variant="secondary" className="gap-1">
            <ShieldCheck className="h-3 w-3" /> {t("networkPolicy.defaultAllow")}
          </Badge>
        )}
        <Badge variant="outline" className="gap-1">
          <Globe className="h-3 w-3" /> v{policy.version}
        </Badge>
      </div>

      {policy.allowed_domains.length > 0 && (
        <div>
          <p className="mb-1 text-sm font-medium">{t("networkPolicy.allowedDomains")}</p>
          <div className="flex flex-wrap gap-1">
            {policy.allowed_domains.map((d) => (
              <Badge key={d} variant="outline" className="text-xs">
                {d}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {policy.denied_domains.length > 0 && (
        <div>
          <p className="mb-1 text-sm font-medium">{t("networkPolicy.deniedDomains")}</p>
          <div className="flex flex-wrap gap-1">
            {policy.denied_domains.map((d) => (
              <Badge key={d} variant="destructive" className="text-xs">
                {d}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
