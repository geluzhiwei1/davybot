"use client";
import { Bot, Clock, Loader2, CheckCircle2, XCircle, Pause, Wrench, Brain } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useParallelTasksStore, getTasksStats } from "@/lib/parallel-tasks-store";
import { cn } from "@/lib/utils";
import type { ParallelTaskState } from "@/lib/types/parallel-tasks";

const STATE_CONFIG: Record<ParallelTaskState, { color: string; icon: React.ReactNode }> = {
  RUNNING: {
    color: "bg-green-500/10 text-green-600 border-green-500/20",
    icon: <Loader2 className="w-3 h-3 animate-spin" />,
  },
  PENDING: {
    color: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
    icon: <Clock className="w-3 h-3" />,
  },
  PAUSED: {
    color: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    icon: <Pause className="w-3 h-3" />,
  },
  COMPLETED: {
    color: "bg-green-500/10 text-green-600 border-green-500/20",
    icon: <CheckCircle2 className="w-3 h-3" />,
  },
  FAILED: {
    color: "bg-red-500/10 text-red-600 border-red-500/20",
    icon: <XCircle className="w-3 h-3" />,
  },
  CANCELLED: {
    color: "bg-gray-500/10 text-gray-600 border-gray-500/20",
    icon: <XCircle className="w-3 h-3" />,
  },
  SKIPPED: {
    color: "bg-gray-500/10 text-gray-500 border-gray-500/20",
    icon: <Clock className="w-3 h-3" />,
  },
};

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

export function AgentsOverview() {
  const { t } = useTranslation("monitoring");
  const parallelTasks = useParallelTasksStore((s) => s.parallelTasks);
  const stats = getTasksStats({ parallelTasks });

  const taskList = Array.from(parallelTasks.values()).sort(
    (a, b) => b.priority - a.priority || b.createdAt - a.createdAt,
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">{t("agents.title")}</h3>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{t("agents.active", { count: stats.active })}</span>
          <span>{t("agents.completed", { count: stats.completed })}</span>
          <span>{t("agents.failed", { count: stats.failed })}</span>
        </div>
      </div>

      {taskList.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-sm text-muted-foreground border border-dashed rounded-lg">
          {t("agents.empty")}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {taskList.map((task) => {
            const config = STATE_CONFIG[task.state];
            return (
              <Card key={task.id} className="py-0">
                <CardHeader className="pb-2 pt-3 px-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-xs font-medium truncate flex items-center gap-1.5">
                      <Bot className="w-3.5 h-3.5 shrink-0" />
                      {task.name}
                    </CardTitle>
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px] px-1.5 py-0 flex items-center gap-1",
                        config.color,
                      )}
                    >
                      {config.icon}
                      {task.state}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="px-3 pb-3 space-y-2">
                  <Progress value={task.progress} className="h-1.5" />
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>{task.progress}%</span>
                    {task.startedAt && <span>{formatDuration(Date.now() - task.startedAt)}</span>}
                  </div>
                  {task.metrics && (task.metrics.toolCalls > 0 || task.metrics.llmCalls > 0) && (
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                      {task.metrics.toolCalls > 0 && (
                        <span className="flex items-center gap-0.5">
                          <Wrench className="w-2.5 h-2.5" />
                          {task.metrics.toolCalls}
                        </span>
                      )}
                      {task.metrics.llmCalls > 0 && (
                        <span className="flex items-center gap-0.5">
                          <Brain className="w-2.5 h-2.5" />
                          {task.metrics.llmCalls}
                        </span>
                      )}
                      {task.metrics.tokensUsed > 0 && (
                        <span className="text-muted-foreground/70">
                          {(task.metrics.tokensUsed / 1000).toFixed(1)}k tokens
                        </span>
                      )}
                    </div>
                  )}
                  {task.output.length > 0 && (
                    <p className="text-[10px] text-muted-foreground truncate">
                      {task.output[task.output.length - 1]}
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
