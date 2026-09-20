import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { workspaceApi } from "@/lib/api-client";
import { setPendingAutoStart } from "@/lib/pending-auto-start";
import i18n from "@/lib/i18n";

/**
 * Shared "新聊天 / 快速开始" flow.
 *
 * Creates a temp workspace (no path / no capability config), then an empty task
 * inside it, then navigates to that task's detail page. Fallback: if temp
 * workspace creation fails, creates a null-workspace temp task instead.
 *
 * Used by both the homepage and the 工作区 page so the two entry points can
 * never diverge.
 *
 * @param initialPrompt Optional opening message. When provided (a non-empty
 *   string), it is staged via setPendingAutoStart so ChatView auto-sends it as
 *   the first message once the WS connects — same mechanism the compliance
 *   对话引导 launcher uses. Coerced to string so passing this hook straight as
 *   an onClick (which would hand it a MouseEvent) stays a no-op auto-start.
 */
export function useQuickChat() {
  const navigate = useNavigate();
  const getOrCreateEmptyTask = useStore((s) => s.getOrCreateEmptyTask);
  const fetchWorkspaces = useStore((s) => s.fetchWorkspaces);
  const [creating, setCreating] = useState(false);

  const startChat = async (initialPrompt?: string) => {
    const prompt = typeof initialPrompt === "string" ? initialPrompt.trim() : "";
    setCreating(true);
    try {
      const tempWsRes = await workspaceApi.createTemp(
        i18n.t("quickChat.tempWorkspaceName", { ns: "hooksUi" }),
      );
      const tempWsId = tempWsRes.workspace.id;
      await fetchWorkspaces();
      const t = await getOrCreateEmptyTask({ workspaceId: tempWsId });
      if (prompt) setPendingAutoStart(t.id, prompt);
      navigate({
        to: "/workspace/$workspaceId/task/$taskId",
        params: { workspaceId: tempWsId, taskId: t.id },
      });
    } catch (e: unknown) {
      console.error("Failed to create temp workspace:", e);
      // Fallback: create a task with no workspace (legacy null-workspace temp task)
      const t = await getOrCreateEmptyTask({ workspaceId: null });
      if (prompt) setPendingAutoStart(t.id, prompt);
      navigate({ to: "/temp/$taskId", params: { taskId: t.id } });
    } finally {
      setCreating(false);
    }
  };

  return { startChat, creating };
}
