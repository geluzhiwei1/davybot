import { useEffect, useRef } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useStore } from "@/lib/store";
import { useTabsStore } from "@/lib/tabs-store";
import { ChatView } from "@/components/chat-view";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";

export const Route = createFileRoute("/temp/$taskId")({
  component: TempTaskPage,
});

function TempTaskPage() {
  const { t } = useTranslation("routesB");
  const { taskId } = Route.useParams();
  const task = useStore((s) => s.tasks.find((t) => t.id === taskId));
  const openTab = useTabsStore((s) => s.openTab);
  const tabRegistered = useRef(false);

  // Register this task as a tab — run once when task becomes available
  useEffect(() => {
    if (task && !tabRegistered.current) {
      tabRegistered.current = true;
      openTab({
        key: `/temp/${taskId}`,
        title: task.title || t("tempTask.defaultTitle"),
        type: "temp-task",
        taskId,
      });
    }
  }, [task, taskId, openTab]);

  if (!task) {
    return (
      <div className="flex-1 flex items-center justify-center text-center p-6">
        <div>
          <p className="text-muted-foreground mb-3">{t("tempTask.notFound")}</p>
          <Button asChild>
            <Link to="/">{t("tempTask.backHome")}</Link>
          </Button>
        </div>
      </div>
    );
  }

  return <ChatView task={task} />;
}
