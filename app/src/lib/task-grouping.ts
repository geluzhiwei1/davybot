/**
 * 任务列表嵌套分组（2026-09-24）：
 * 编排器自动创建的子任务会话（taskType === "subtask"）不再与用户创建的任务
 * 平铺并列 —— 按 parentConversationId 折叠进父任务行内渲染。
 * 归属失败的子任务（父会话已删除/后端未标注）保持平铺，绝不丢数据。
 */
import type { Task } from "@/lib/store";

export interface TaskGroup {
  /** 用户创建的任务（顶层行） */
  parent: Task;
  /** 折叠在该父任务下的子任务会话（按 createdAt 升序，与执行顺序一致） */
  children: Task[];
}

export function groupTasksByParent(tasks: Task[]): {
  groups: TaskGroup[];
  /** 无法归属到任何在列父任务的子任务会话（平铺兜底） */
  orphans: Task[];
} {
  const ids = new Set(tasks.map((t) => t.id));
  const childrenByParent = new Map<string, Task[]>();
  const groups: TaskGroup[] = [];
  const orphans: Task[] = [];

  for (const t of tasks) {
    if (t.taskType !== "subtask") {
      groups.push({ parent: t, children: [] });
      continue;
    }
    const pid = t.parentConversationId;
    if (pid && ids.has(pid)) {
      const arr = childrenByParent.get(pid);
      if (arr) arr.push(t);
      else childrenByParent.set(pid, [t]);
    } else {
      orphans.push(t);
    }
  }
  for (const g of groups) {
    g.children = (childrenByParent.get(g.parent.id) ?? []).sort(
      (a, b) => a.createdAt - b.createdAt,
    );
  }
  return { groups, orphans };
}
