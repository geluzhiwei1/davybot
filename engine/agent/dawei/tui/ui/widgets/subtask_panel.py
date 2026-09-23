# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""SubtaskPanel Widget（C24）

子任务面板：side_drawer 第 4 面板。数据源 = agent_bridge.subtask_states
（C23 状态 dict，由 SUBTASK_* 事件记账）。渲染：batch 分组 + 状态着色 +
running 项 todo 步级行（C25 subtask_progress 数据）。
纯 UI 态 —— 不写入任何会话历史。
"""

from textual.widgets import Static

from dawei.tui.i18n import _

# 终态集合（与 TaskGraph._TERMINAL_STATUSES 对齐）
_TERMINAL = {"completed", "failed", "aborted", "cancelled"}


class SubtaskPanel(Static):
    """Subtask display widget (batch-grouped, status-colored, todo-stepped)"""

    def __init__(self, max_items: int = 30, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_items = max_items
        self.update(f"[dim]{_('Subtasks...')}[/dim]")

    def refresh_from_bridge(self) -> None:
        """从 app.agent_bridge.subtask_states 重绘（app 未挂载/无 bridge 时静默跳过）"""
        try:
            bridge = getattr(self.app, "agent_bridge", None)
            states = getattr(bridge, "subtask_states", None) or {}
            self.render_states(states)
        except Exception:  # noqa: BLE001 — 纯 UI 态，渲染失败只保持旧内容
            pass

    def render_states(self, states: dict) -> None:
        """渲染状态 dict（空 dict 显示占位符）"""
        try:
            if not states:
                self.update(f"[dim]{_('Subtasks...')}[/dim]")
                return
            # batch 分组：batch_id 缺失（new_task 单发）归 "_" 组不显示组头
            groups: dict[str, list[tuple[str, dict]]] = {}
            for sid, s in states.items():
                groups.setdefault(str(s.get("batch_id") or "_"), []).append((sid, s))
            lines = [f"[bold]{_('Subtasks:')}[/bold]"]
            rendered = 0
            for batch_id, items in groups.items():
                if rendered >= self.max_items:
                    break
                if batch_id != "_":
                    done = sum(1 for _, s in items if str(s.get("status", "")) in _TERMINAL)
                    lines.append(f"[bold cyan]批次 {batch_id[:8]} ({done}/{len(items)})[/bold cyan]")
                for sid, s in items:
                    if rendered >= self.max_items:
                        lines.append("  …")
                        break
                    lines.append(self._render_item(sid, s))
                    rendered += 1
            self.update("\n".join(lines))
        except Exception:  # noqa: BLE001 — 渲染失败保持旧内容
            pass

    def _render_item(self, sid: str, s: dict) -> str:
        """单个子任务行：状态图标 + identity + todo 步级（running 项）"""
        status = str(s.get("status", "") or "unknown")
        ident = str(s.get("item_identity") or sid[:8])
        if status == "completed":
            icon, color = "✓", "green"
        elif status in ("failed", "aborted", "cancelled"):
            icon, color = "✗", "red"
        elif status in ("running", "started", "in_progress", "pending"):
            icon, color = "▶", "yellow"
        else:
            icon, color = "·", "dim"
        line = f"  [{color}]{icon}[/{color}] {ident[:40]}"
        todos = s.get("todos") or {}
        if todos.get("total"):
            try:
                completed = int(todos.get("completed", 0))
                total = int(todos.get("total", 0))
                line += f" {self._progress_bar(completed, total)}"
            except (TypeError, ValueError):
                pass
            if todos.get("current"):
                line += f" · {str(todos['current'])[:40]}"
        return line

    @staticmethod
    def _progress_bar(completed: int, total: int, width: int = 5) -> str:
        """手写进度条：▓▓▓░░ 3/5"""
        total = max(total, 1)
        filled = min(round(completed / total * width), width)
        return "▓" * filled + "░" * (width - filled) + f" {completed}/{total}"
