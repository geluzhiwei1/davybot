"use client";
import { Cpu, MemoryStick, HardDrive, Wifi } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useMonitoringStore } from "@/lib/monitoring-store";
import { cn } from "@/lib/utils";

function HealthBar({
  label,
  value,
  icon,
  unit = "%",
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  unit?: string;
}) {
  const color = value > 80 ? "text-red-500" : value > 60 ? "text-yellow-500" : "text-green-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-muted-foreground flex items-center gap-1">
          {icon} {label}
        </span>
        <span className={cn("font-medium", color)}>
          {value.toFixed(1)}
          {unit}
        </span>
      </div>
      <Progress value={value} className="h-1.5" />
    </div>
  );
}

export function SystemHealth() {
  const { t } = useTranslation("monitoring");
  const metrics = useMonitoringStore((s) => s.systemMetrics);
  const isConnected = useMonitoringStore((s) => s.isConnected);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5" />
            {t("systemHealth.title")}
          </CardTitle>
          <div
            className={cn("w-2 h-2 rounded-full", isConnected ? "bg-green-500" : "bg-red-500")}
          />
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3 space-y-3">
        {!metrics ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            {t("systemHealth.waiting")}
          </div>
        ) : (
          <>
            <HealthBar label="CPU" value={metrics.cpuUsage} icon={<Cpu className="w-3 h-3" />} />
            <HealthBar
              label={t("systemHealth.memory")}
              value={metrics.memoryUsage}
              icon={<MemoryStick className="w-3 h-3" />}
            />
            <HealthBar
              label={t("systemHealth.disk")}
              value={metrics.diskUsage}
              icon={<HardDrive className="w-3 h-3" />}
            />
            <HealthBar
              label={t("systemHealth.networkLatency")}
              value={Math.min(metrics.networkLatency / 10, 100)}
              icon={<Wifi className="w-3 h-3" />}
              unit={`ms (${metrics.networkLatency.toFixed(0)})`}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
