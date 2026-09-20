"use client";
import { DollarSign, Zap, ArrowUpDown, Coins } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMonitoringStore } from "@/lib/monitoring-store";

export function CostTracker() {
  const { t } = useTranslation("monitoring");
  const costData = useMonitoringStore((s) => s.costData);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <CardTitle className="text-xs font-medium flex items-center gap-1.5">
          <Coins className="w-3.5 h-3.5" />
          {t("cost.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-3 pb-3 space-y-3">
        {!costData ? (
          <div className="text-xs text-muted-foreground text-center py-4">{t("cost.waiting")}</div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                  <Zap className="w-3 h-3" /> {t("cost.totalTokens")}
                </div>
                <div className="text-lg font-semibold">{costData.totalTokens.toLocaleString()}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                  <DollarSign className="w-3 h-3" /> {t("cost.totalCost")}
                </div>
                <div className="text-lg font-semibold">${costData.totalCost.toFixed(4)}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground">{t("cost.inputTokens")}</div>
                <div className="text-sm font-medium">{costData.inputTokens.toLocaleString()}</div>
              </div>
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground">{t("cost.outputTokens")}</div>
                <div className="text-sm font-medium">{costData.outputTokens.toLocaleString()}</div>
              </div>
            </div>
            {Object.keys(costData.modelBreakdown).length > 0 && (
              <div className="space-y-1.5 pt-2 border-t">
                <div className="text-[10px] text-muted-foreground flex items-center gap-1">
                  <ArrowUpDown className="w-3 h-3" /> {t("cost.modelBreakdown")}
                </div>
                {Object.entries(costData.modelBreakdown).map(([model, data]) => (
                  <div key={model} className="flex items-center justify-between text-[10px]">
                    <span className="text-muted-foreground truncate">{model}</span>
                    <span>
                      {data.tokens.toLocaleString()} tokens / ${data.cost.toFixed(4)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
