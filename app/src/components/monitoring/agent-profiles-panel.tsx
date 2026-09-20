"use client";
/**
 * AgentProfilesPanel — UI-E Agent Profile 注册表（§6.3）。
 *
 * 数据源：
 * - REST GET /agents/profiles（注册表：内置 + workspace/.dawei/agents/*）
 * - subtask-store workspaceSubtasks → countSubtaskAgents（每 agent 子任务使用数）
 *
 * 与 UI-C 抽屉内摘要条共享同一份 profiles 拉取与匹配语义（findAgentProfile）。
 */
import { useEffect, useMemo, useState } from "react";
import { Bot, Loader2, RefreshCw, Sparkles, Wrench } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import { subtaskApi } from "@/lib/api/subtask";
import { useSubtaskStore } from "@/lib/subtask-store";
import { countSubtaskAgents } from "@/lib/subtask-thread";
import type { AgentProfileInfo } from "@/lib/types/subtask";
import { wsClient } from "@/lib/ws-client";

interface Props {
  /** 工作区归属；缺省取 wsClient.getWorkspaceId() */
  workspaceId?: string;
}

export function AgentProfilesPanel({ workspaceId }: Props) {
  const { t } = useTranslation("monitoring");
  const buckets = useSubtaskStore((s) => s.workspaceSubtasks);

  const [loading, setLoading] = useState(false);
  const [profiles, setProfiles] = useState<AgentProfileInfo[]>([]);
  const [reloadTick, setReloadTick] = useState(0);

  const wsId = workspaceId ?? wsClient.getWorkspaceId();

  useEffect(() => {
    if (!wsId) return;
    let cancelled = false;
    setLoading(true);
    subtaskApi
      .getAgentProfiles(wsId)
      .then((res) => {
        if (cancelled) return;
        setProfiles(res.profiles ?? []);
      })
      .catch((e: unknown) => {
        if (!cancelled) toast.error(e instanceof Error ? e.message : t("profile.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [wsId, reloadTick]);

  const usage = useMemo(() => (wsId ? countSubtaskAgents(buckets, wsId) : {}), [buckets, wsId]);
  const builtinCount = profiles.filter((p) => p.builtin).length;
  const customCount = profiles.length - builtinCount;

  return (
    <Card className="py-0">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium flex items-center gap-1.5">
            <Bot className="w-3.5 h-3.5" />
            {t("profile.title")}
          </CardTitle>
          <div className="flex items-center gap-1.5">
            {profiles.length > 0 && (
              <Badge variant="outline" className="text-[10px]">
                {t("profile.counts", { builtin: builtinCount, custom: customCount })}
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] gap-1"
              disabled={loading || !wsId}
              onClick={() => setReloadTick((t) => t + 1)}
              title={t("profile.refreshTitle")}
            >
              <RefreshCw className={loading ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
              {t("profile.refresh")}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3">
        {!wsId ? (
          <div className="flex items-center justify-center h-24 text-xs text-muted-foreground border border-dashed rounded-lg">
            {t("profile.noWorkspace")}
          </div>
        ) : loading && profiles.length === 0 ? (
          <div className="flex items-center justify-center gap-2 h-24 text-xs text-muted-foreground">
            <Loader2 className="w-3 h-3 animate-spin" />
            {t("profile.loading")}
          </div>
        ) : profiles.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-xs text-muted-foreground border border-dashed rounded-lg">
            {t("profile.empty")}
          </div>
        ) : (
          <div className="space-y-1.5">
            {profiles.map((p) => (
              <ProfileRow key={p.agent} profile={p} usage={usage[p.agent] ?? 0} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ProfileRow({ profile, usage }: { profile: AgentProfileInfo; usage: number }) {
  const { t } = useTranslation("monitoring");
  return (
    <div className="flex items-center gap-2 p-2 rounded-md border border-border/60 bg-muted/10 text-xs">
      {profile.builtin ? (
        <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
      ) : (
        <Wrench className="w-3.5 h-3.5 text-blue-500 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="font-medium truncate">{profile.agent}</span>
          <Badge variant="outline" className="text-[10px] h-4 px-1.5 shrink-0">
            {profile.builtin ? t("profile.builtin") : t("profile.custom")}
          </Badge>
          {profile.model && (
            <span className="text-[10px] text-muted-foreground truncate">{profile.model}</span>
          )}
          {profile.sandbox_mode && (
            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 shrink-0">
              {profile.sandbox_mode}
            </Badge>
          )}
          {usage > 0 && (
            <Badge variant="default" className="text-[10px] h-4 px-1.5 shrink-0">
              {t("profile.subtasks", { count: usage })}
            </Badge>
          )}
        </div>
        {profile.description && (
          <p className="text-[10px] text-muted-foreground truncate mt-0.5">{profile.description}</p>
        )}
      </div>
    </div>
  );
}
