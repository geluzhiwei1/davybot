import { createFileRoute, redirect } from "@tanstack/react-router";

// 简单任务已合并进工作区页（/workspaces），统一管理。
// 保留该路由用于兼容旧链接 / 书签，访问时重定向到工作区页。
export const Route = createFileRoute("/regular-tasks")({
  beforeLoad: () => {
    throw redirect({ to: "/workspaces" });
  },
});
