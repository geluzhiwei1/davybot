"use client";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, Loader2, XCircle, SkipForward, Ban } from "lucide-react";
import type { TaskGraphExecution, NodeStatus } from "@/lib/types/monitoring";

const NODE_ICONS: Record<NodeStatus, React.ReactNode> = {
  PENDING: <Circle className="w-3.5 h-3.5 text-gray-400" />,
  RUNNING: <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />,
  COMPLETED: <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />,
  FAILED: <XCircle className="w-3.5 h-3.5 text-red-500" />,
  SKIPPED: <SkipForward className="w-3.5 h-3.5 text-gray-400" />,
  CANCELLED: <Ban className="w-3.5 h-3.5 text-gray-400" />,
};

const NODE_COLORS: Record<NodeStatus, string> = {
  PENDING: "border-gray-300 bg-gray-50",
  RUNNING: "border-blue-300 bg-blue-50",
  COMPLETED: "border-green-300 bg-green-50",
  FAILED: "border-red-300 bg-red-50",
  SKIPPED: "border-gray-200 bg-gray-50",
  CANCELLED: "border-gray-200 bg-gray-50",
};

interface TaskGraphSimpleProps {
  execution: TaskGraphExecution | null;
}

export function TaskGraphSimple({ execution }: TaskGraphSimpleProps) {
  const { t } = useTranslation("monitoring");
  if (!execution) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground border border-dashed rounded-lg">
        {t("taskGraph.empty")}
      </div>
    );
  }

  const nodes = Object.values(execution.nodes);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium">{execution.name}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              {t("taskGraph.completedOf", {
                completed: nodes.filter((n) => n.status === "COMPLETED").length,
                total: nodes.length,
              })}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        <div className="grid grid-cols-3 gap-2">
          {nodes.map((node) => (
            <div
              key={node.id}
              className={cn(
                "flex items-center gap-2 p-2 rounded-md border text-xs transition-colors",
                NODE_COLORS[node.status],
              )}
            >
              {NODE_ICONS[node.status]}
              <div className="min-w-0 flex-1">
                <div className="font-medium truncate">{node.label}</div>
                <div className="text-[10px] text-muted-foreground">
                  {node.status === "RUNNING" && `${node.progress}%`}
                  {node.status === "COMPLETED" && t("taskGraph.done")}
                  {node.status === "FAILED" && t("taskGraph.failed")}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
