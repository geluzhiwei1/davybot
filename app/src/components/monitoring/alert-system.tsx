"use client";
import { AlertTriangle, Bell, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useMonitoringStore } from "@/lib/monitoring-store";
import { cn } from "@/lib/utils";
import type { AlertSeverity } from "@/lib/types/monitoring";

const SEVERITY_COLORS: Record<AlertSeverity, string> = {
  info: "border-l-blue-500",
  warning: "border-l-yellow-500",
  error: "border-l-red-500",
  critical: "border-l-red-700",
};

export function AlertSystem() {
  const { t } = useTranslation("monitoring");
  const alerts = useMonitoringStore((s) => s.alerts);
  const acknowledgeAlert = useMonitoringStore((s) => s.acknowledgeAlert);

  const unacknowledged = alerts.filter((a) => !a.acknowledged);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium flex items-center gap-1.5">
            <Bell className="w-3.5 h-3.5" />
            {t("alert.title")}
            {unacknowledged.length > 0 && (
              <span className="text-[10px] font-normal text-muted-foreground">
                {t("alert.unacknowledged", { count: unacknowledged.length })}
              </span>
            )}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        <div className="space-y-2 max-h-48 overflow-auto scrollbar-thin">
          {alerts.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">{t("alert.empty")}</div>
          ) : (
            alerts
              .slice(-20)
              .reverse()
              .map((alert) => (
                <div
                  key={alert.id}
                  className={cn(
                    "border-l-2 pl-2 py-1.5 pr-1 text-xs flex items-start justify-between gap-2",
                    SEVERITY_COLORS[alert.severity],
                    alert.acknowledged && "opacity-50",
                  )}
                >
                  <div className="min-w-0">
                    <div className="font-medium flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3 shrink-0" />
                      {alert.title}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{alert.message}</div>
                  </div>
                  {!alert.acknowledged && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-5 w-5 p-0 shrink-0"
                      onClick={() => acknowledgeAlert(alert.id)}
                    >
                      <Check className="w-3 h-3" />
                    </Button>
                  )}
                </div>
              ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
