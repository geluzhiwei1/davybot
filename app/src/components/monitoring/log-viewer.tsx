"use client";
import { useRef, useEffect, useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ScrollText, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useMonitoringStore } from "@/lib/monitoring-store";
import { cn } from "@/lib/utils";

const LEVEL_COLORS: Record<string, string> = {
  debug: "text-gray-400",
  info: "text-blue-400",
  warn: "text-yellow-400",
  error: "text-red-400",
};

const LEVEL_BG: Record<string, string> = {
  debug: "",
  info: "",
  warn: "bg-yellow-500/5",
  error: "bg-red-500/5",
};

export function LogViewer() {
  const { t } = useTranslation("monitoring");
  const logs = useMonitoringStore((s) => s.logs);
  const clearLogs = useMonitoringStore((s) => s.clearLogs);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>("all");

  const filteredLogs = useMemo(() => {
    if (levelFilter === "all") return logs;
    return logs.filter((l) => l.level === levelFilter);
  }, [logs, levelFilter]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll]);

  const counts = useMemo(() => {
    const c = { debug: 0, info: 0, warn: 0, error: 0 };
    logs.forEach((l) => {
      c[l.level]++;
    });
    return c;
  }, [logs]);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium flex items-center gap-1.5">
            <ScrollText className="w-3.5 h-3.5" />
            {t("log.title")}
            <span className="text-muted-foreground font-normal">({logs.length})</span>
          </CardTitle>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px]"
              onClick={() => setAutoScroll(!autoScroll)}
            >
              {autoScroll ? t("log.autoScroll") : t("log.manual")}
            </Button>
            <Button variant="ghost" size="sm" className="h-6 px-1.5" onClick={clearLogs}>
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-1 pt-1">
          {["all", "error", "warn", "info", "debug"].map((level) => (
            <Button
              key={level}
              variant={levelFilter === level ? "secondary" : "ghost"}
              size="sm"
              className="h-5 px-1.5 text-[10px]"
              onClick={() => setLevelFilter(level)}
            >
              {level === "all" ? t("log.all") : level}
              {level !== "all" && counts[level as keyof typeof counts] > 0 && (
                <Badge variant="secondary" className="ml-0.5 text-[8px] px-1 py-0 min-w-0">
                  {counts[level as keyof typeof counts]}
                </Badge>
              )}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        <div
          ref={scrollRef}
          className="h-48 overflow-auto font-mono text-[10px] space-y-0.5 scrollbar-thin"
        >
          {filteredLogs.length === 0 ? (
            <div className="text-muted-foreground text-center py-8">{t("log.empty")}</div>
          ) : (
            filteredLogs.map((log) => (
              <div
                key={log.id}
                className={cn("flex gap-2 py-0.5 px-1 rounded", LEVEL_BG[log.level])}
              >
                <span className="text-muted-foreground shrink-0 w-16">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span
                  className={cn("w-10 shrink-0 uppercase font-medium", LEVEL_COLORS[log.level])}
                >
                  {log.level}
                </span>
                <span className="text-muted-foreground shrink-0 w-20 truncate">{log.source}</span>
                <span className="truncate">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
