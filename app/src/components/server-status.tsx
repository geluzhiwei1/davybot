import { useTranslation } from "react-i18next";
import { Wifi, WifiOff, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type ConnectionStatus = "connected" | "disconnected" | "connecting";

interface ServerStatusProps {
  status?: ConnectionStatus;
  agentStatus?: "running" | "idle" | "offline";
  activeTasks?: number;
  latency?: number;
}

export function ServerStatus({
  status = "disconnected",
  agentStatus = "offline",
  activeTasks = 0,
  latency,
}: ServerStatusProps) {
  const { t } = useTranslation("commonUi");
  const statusConfig: Record<
    ConnectionStatus,
    { icon: typeof Wifi; color: string; label: string }
  > = {
    connected: { icon: Wifi, color: "text-green-500", label: t("serverStatus.connected") },
    disconnected: { icon: WifiOff, color: "text-red-500", label: t("serverStatus.disconnected") },
    connecting: { icon: Loader2, color: "text-yellow-500", label: t("serverStatus.connecting") },
  };

  const { icon: StatusIcon, color, label } = statusConfig[status];
  const agentLabel =
    agentStatus === "running"
      ? t("serverStatus.agent.running")
      : agentStatus === "idle"
        ? t("serverStatus.agent.idle")
        : t("serverStatus.agent.offline");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-accent transition-colors">
          <StatusIcon
            className={`h-3.5 w-3.5 ${color} ${status === "connecting" ? "animate-spin" : ""}`}
          />
          <span className="text-xs text-muted-foreground">{label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64" align="end">
        <div className="space-y-3">
          <div className="text-sm font-medium">{t("serverStatus.title")}</div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{t("serverStatus.connection")}</span>
              <Badge variant={status === "connected" ? "default" : "secondary"} className="text-xs">
                {label}
              </Badge>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Agent</span>
              <Badge
                variant={
                  agentStatus === "running"
                    ? "default"
                    : agentStatus === "idle"
                      ? "secondary"
                      : "outline"
                }
                className="text-xs"
              >
                {agentLabel}
              </Badge>
            </div>

            {activeTasks > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {t("serverStatus.activeTasks")}
                </span>
                <span className="text-xs font-medium">{activeTasks}</span>
              </div>
            )}

            {latency !== undefined && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{t("serverStatus.latency")}</span>
                <span className="text-xs font-medium">{latency}ms</span>
              </div>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
