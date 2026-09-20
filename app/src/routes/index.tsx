import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { useQuickChat } from "@/hooks/use-quick-chat";
import { usePinnedStore } from "@/lib/pinned-store";
import { resolveIcon } from "@/lib/icon-map";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ArrowRight, Loader2, FolderOpen, Sparkles, Pin } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

export const Route = createFileRoute("/")({
  component: HomePage,
});

function greeting(t: TFunction): string {
  const h = new Date().getHours();
  if (h < 6) return t("index.greetingDawn");
  if (h < 12) return t("index.greetingMorning");
  if (h < 14) return t("index.greetingNoon");
  if (h < 18) return t("index.greetingAfternoon");
  return t("index.greetingEvening");
}

function HomePage() {
  const { t } = useTranslation("routesA");
  const tasks = useStore((s) => s.tasks);
  const workspaces = useStore((s) => s.workspaces);
  const { startChat, creating } = useQuickChat();
  const [quickText, setQuickText] = useState("");
  const pinnedItems = usePinnedStore((s) => s.pinned);
  const unpin = usePinnedStore((s) => s.unpin);

  // 按 updatedAt 降序排列后取前 5 条，确保显示真正最近更新的任务
  const recentTasks = [...tasks].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 5);

  const canStart = !!quickText.trim() && !creating;

  const handleQuickStart = () => {
    if (!canStart) return;
    startChat(quickText.trim());
  };

  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin">
      <div className="max-w-5xl mx-auto px-4 py-8 md:px-6 md:py-10">
        {/* Hero — 品牌 + 快速开始 */}
        <div className="mb-10">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
            <span className="text-gradient-brand">NormNomos</span>
            <span className="text-foreground"> · {t("index.heroTagline")}</span>
          </h1>
          <p className="text-muted-foreground mt-3 max-w-2xl">{t("index.heroDesc")}</p>
          <div className="mt-6 flex items-center gap-4 flex-wrap">
            <span className="text-xs text-muted-foreground">
              {greeting(t)} 👋 · {t("index.workspacesCount", { count: workspaces.length })} ·{" "}
              {t("index.tasksCount", { count: tasks.length })}
            </span>
          </div>
        </div>

        {/* 快速开启智能体 — 直接开启一个新聊天 */}
        <section className="mb-10">
          <div className="bg-gradient-card border border-border rounded-2xl p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-brand" />
              <h2 className="text-sm font-semibold">{t("index.quickStartTitle")}</h2>
              <span className="text-xs text-muted-foreground">{t("index.quickStartHint")}</span>
            </div>
            {/* <sm 输入与按钮纵向堆叠(移动端方案 Phase 3.1),≥sm 恢复横排 */}
            <div className="flex flex-col sm:flex-row sm:items-end gap-2">
              <Textarea
                value={quickText}
                onChange={(e) => setQuickText(e.target.value)}
                onKeyDown={(e) => {
                  // Enter 发送、Shift+Enter 换行（与聊天输入框一致）
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleQuickStart();
                  }
                }}
                placeholder={t("index.quickStartPlaceholder")}
                rows={2}
                disabled={creating}
                className="resize-none flex-1 text-sm min-h-[44px]"
              />
              <Button
                onClick={handleQuickStart}
                disabled={!canStart}
                className="bg-gradient-brand text-brand-foreground gap-1.5 shrink-0 w-full sm:w-auto"
              >
                {creating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ArrowRight className="w-4 h-4" />
                )}
                {t("index.startNow")}
              </Button>
            </div>
          </div>
        </section>

        {/* 快捷入口 — pinned menu items */}
        {pinnedItems.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center gap-2 mb-3">
              <Pin className="w-3.5 h-3.5 text-brand" fill="currentColor" />
              <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                {t("index.pinnedSection")}
              </h2>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {pinnedItems.map((item) => {
                const Icon = resolveIcon(item.icon);
                return (
                  <div
                    key={item.key}
                    className="group relative bg-gradient-card border border-border rounded-xl p-4 flex items-center gap-3 hover:border-brand/40 transition"
                  >
                    <Link to={item.route} className="flex items-center gap-3 flex-1 min-w-0">
                      <div className="w-9 h-9 rounded-lg bg-brand/10 border border-brand/20 flex items-center justify-center shrink-0">
                        <Icon className="w-4 h-4 text-brand" />
                      </div>
                      <span className="text-sm font-medium truncate">{item.title}</span>
                    </Link>
                    <button
                      type="button"
                      onClick={() => unpin(item.key)}
                      className="shrink-0 rounded p-1 text-muted-foreground hover:text-destructive transition opacity-0 group-hover:opacity-100"
                      title={t("index.unpin")}
                    >
                      <Pin className="w-3 h-3" fill="currentColor" />
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* 继续工作 — compact recent tasks */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
              {t("index.continueWorking")}
            </h2>
            <Link
              to="/workspaces"
              className="text-xs text-muted-foreground hover:text-brand inline-flex items-center gap-1"
            >
              {t("index.viewAll")} <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {recentTasks.length === 0 ? (
            <div className="text-sm text-muted-foreground bg-card/40 border border-dashed border-border rounded-2xl p-10 text-center">
              {t("index.noTasks")}
            </div>
          ) : (
            <div className="space-y-2">
              {recentTasks.map((task) => (
                <Link
                  key={task.id}
                  to={task.workspaceId ? "/workspace/$workspaceId/task/$taskId" : "/temp/$taskId"}
                  params={
                    task.workspaceId
                      ? { workspaceId: task.workspaceId, taskId: task.id }
                      : { taskId: task.id }
                  }
                  className="flex items-center gap-3 bg-card/40 hover:bg-card border border-border rounded-xl p-3 transition group"
                >
                  <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
                    {task.workspaceId ? (
                      <FolderOpen className="w-4 h-4 text-brand" />
                    ) : (
                      <Sparkles className="w-4 h-4 text-brand" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{task.title}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {task.workspaceId
                        ? workspaces.find((w) => w.id === task.workspaceId)?.name ||
                          t("index.workspace")
                        : t("index.tempTask")}
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition shrink-0" />
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
