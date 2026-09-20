"use client";
import { CheckSquare, Square, CircleDot } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useTodoStore } from "@/lib/todo-store";
import { cn } from "@/lib/utils";
import type { TodoStatus } from "@/lib/types/todos";

const STATUS_ICONS: Record<TodoStatus, React.ReactNode> = {
  PENDING: <Square className="w-3.5 h-3.5 text-gray-400" />,
  IN_PROGRESS: <CircleDot className="w-3.5 h-3.5 text-blue-500" />,
  COMPLETED: <CheckSquare className="w-3.5 h-3.5 text-green-500" />,
};

const PRIORITY_COLORS: Record<string, string> = {
  low: "text-gray-400",
  medium: "text-blue-400",
  high: "text-yellow-400",
  critical: "text-red-400",
};

export function TodosPanel() {
  const { t } = useTranslation("monitoring");
  const todos = useTodoStore((s) => s.todos);
  const filterStatus = useTodoStore((s) => s.filterStatus);
  const setFilterStatus = useTodoStore((s) => s.setFilterStatus);
  const setTodoStatus = useTodoStore((s) => s.setTodoStatus);
  const getStatistics = useTodoStore((s) => s.getStatistics);

  const stats = getStatistics();
  const filtered = filterStatus === "all" ? todos : todos.filter((t) => t.status === filterStatus);

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium flex items-center gap-1.5">
            <CheckSquare className="w-3.5 h-3.5" />
            {t("todos.title")}
          </CardTitle>
          <div className="text-[10px] text-muted-foreground">
            {t("todos.stats", {
              completed: stats.completed,
              total: stats.total,
              rate: stats.completionRate.toFixed(0),
            })}
          </div>
        </div>
        <div className="flex items-center gap-1 pt-1">
          {(["all", "PENDING", "IN_PROGRESS", "COMPLETED"] as const).map((status) => (
            <Button
              key={status}
              variant={filterStatus === status ? "secondary" : "ghost"}
              size="sm"
              className="h-5 px-1.5 text-[10px]"
              onClick={() => setFilterStatus(status)}
            >
              {t(`todos.filter.${status}`)}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        <div className="space-y-1 max-h-48 overflow-auto scrollbar-thin">
          {filtered.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">{t("todos.empty")}</div>
          ) : (
            filtered.map((todo) => (
              <div
                key={todo.id}
                className="flex items-center gap-2 py-1 px-1 rounded hover:bg-muted/30 text-xs"
              >
                <button
                  onClick={() => {
                    const next: TodoStatus = todo.status === "COMPLETED" ? "PENDING" : "COMPLETED";
                    setTodoStatus(todo.id, next);
                  }}
                >
                  {STATUS_ICONS[todo.status]}
                </button>
                <span
                  className={cn(
                    "flex-1 truncate",
                    todo.status === "COMPLETED" && "line-through text-muted-foreground",
                  )}
                >
                  {todo.title}
                </span>
                {todo.priority !== "low" && (
                  <span className={cn("text-[10px] font-medium", PRIORITY_COLORS[todo.priority])}>
                    {todo.priority}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
