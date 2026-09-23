# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""StatusBar Widget

Single-line Claude-Code style status bar: status │ mode │ model │ PDCA.
Rich ``Text`` with ellipsis overflow handles CJK-safe width truncation
(char-count slicing like ``model[:27]`` corrupts double-width text).
"""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from dawei.tui.i18n import _


class StatusBar(Static):
    """Agent status display widget"""

    status = reactive("Idle")
    mode = reactive("orchestrator")
    model = reactive("")

    # PDCA state
    pdca_active = reactive(False)
    pdca_phase = reactive("")
    pdca_domain = reactive("")
    pdca_completion = reactive(0)

    # C24：子任务缩略段（空串 = 无活动子任务，整段隐藏；有失败整段警示色）
    subtask_summary = reactive("")
    subtask_has_failure = reactive(False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_text()

    def watch_status(self, _old_status: str, _new_status: str) -> None:
        """Update status display when status changes

        Args:
            old_status: Old status value
            new_status: New status value

        """
        self.update_text()

    def watch_mode(self, _old_mode: str, _new_mode: str) -> None:
        """Update status display when mode changes

        Args:
            old_mode: Old mode value
            new_mode: New mode value

        """
        self.update_text()

    def watch_model(self, _old_model: str, _new_model: str) -> None:
        """Update status display when model changes

        Args:
            old_model: Old model value
            new_model: New model value

        """
        self.update_text()

    def watch_pdca_active(self, _old_value: bool, _new_value: bool) -> None:
        """Update status display when PDCA active state changes

        Args:
            old_value: Old PDCA active value
            new_value: New PDCA active value

        """
        self.update_text()

    def watch_pdca_phase(self, _old_phase: str, _new_phase: str) -> None:
        """Update status display when PDCA phase changes

        Args:
            old_phase: Old PDCA phase value
            new_phase: New PDCA phase value

        """
        self.update_text()

    def watch_pdca_domain(self, _old_domain: str, _new_domain: str) -> None:
        """Update status display when PDCA domain changes

        Args:
            old_domain: Old PDCA domain value
            new_domain: New PDCA domain value

        """
        self.update_text()

    def watch_pdca_completion(self, _old_completion: float, _new_completion: float) -> None:
        """Update status display when PDCA completion changes

        Args:
            old_completion: Old PDCA completion value
            new_completion: New PDCA completion value

        """
        self.update_text()

    def watch_subtask_summary(self, _old: str, _new: str) -> None:
        """C24：子任务缩略段变化时重绘"""
        self.update_text()

    def watch_subtask_has_failure(self, _old: bool, _new: bool) -> None:
        """C24：失败警示色变化时重绘"""
        self.update_text()

    def update_text(self) -> None:
        """Update the status text (single line; ellipsis handles overflow)."""
        model_display = self.model or _("N/A")
        status_emoji = self._get_status_emoji(self.status)

        # Plain Text segments (markup-injection safe); no_wrap + ellipsis
        # truncate to the bar's actual cell width, CJK-safe.
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{status_emoji} {self.status}", style="bold")
        text.append(f" │ {self.mode}")
        text.append(f" │ {model_display}", style="cyan")

        if self.pdca_active:
            phase_emoji = self._get_phase_emoji(self.pdca_phase)
            text.append(
                f" │ {phase_emoji} PDCA {self.pdca_phase.upper()} {self.pdca_completion:.0f}%",
                style="yellow",
            )

        # C24：子任务常驻缩略段（无活动子任务时整段隐藏）
        if self.subtask_summary:
            text.append(
                f" │ {self.subtask_summary}",
                style="bold red" if self.subtask_has_failure else "green",
            )

        self.update(text)

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status

        Args:
            status: Status string

        Returns:
            Emoji string

        """
        status_lower = status.lower()
        if "running" in status_lower or "processing" in status_lower:
            return "⚙️"
        if "idle" in status_lower or "ready" in status_lower:
            return "✓"
        if "error" in status_lower:
            return "❌"
        return "ℹ️"

    def _get_phase_emoji(self, phase: str) -> str:
        """Get emoji for PDCA phase

        Args:
            phase: Phase string

        Returns:
            Emoji string

        """
        phase_emojis = {
            "plan": "📋",
            "do": "⚙️",
            "check": "✓",
            "act": "🚀",
            "orchestrator": "🪃",
        }
        return phase_emojis.get(phase.lower(), "🔄")

    def _get_domain_emoji(self, domain: str) -> str:
        """Get emoji for domain

        Args:
            domain: Domain string

        Returns:
            Emoji string

        """
        domain_emojis = {
            "software": "💻",
            "data": "📊",
            "writing": "✍️",
            "research": "🔬",
            "business": "🏢",
            "education": "🎓",
            "operations": "🔧",
            "marketing": "📣",
            "general": "📌",
        }
        return domain_emojis.get(domain.lower(), "")

    def set_status(self, status: str) -> None:
        """Set status

        Args:
            status: New status

        """
        self.status = status

    def set_mode(self, mode: str) -> None:
        """Set mode

        Args:
            mode: New mode

        """
        self.mode = mode

    def set_model(self, model: str) -> None:
        """Set model

        Args:
            model: New model

        """
        # No char-count truncation: update_text() ellipsis-truncates to the
        # actual render width (char slicing mis-measures double-width CJK).
        self.model = model

    def set_pdca_active(self, active: bool) -> None:
        """Set PDCA active state

        Args:
            active: Whether PDCA is active

        """
        self.pdca_active = active

    def set_pdca_phase(self, phase: str) -> None:
        """Set PDCA phase

        Args:
            phase: PDCA phase (plan/do/check/act/orchestrator)

        """
        self.pdca_phase = phase

    def set_pdca_domain(self, domain: str) -> None:
        """Set PDCA domain

        Args:
            domain: Domain type

        """
        self.pdca_domain = domain

    def set_pdca_completion(self, completion: float) -> None:
        """Set PDCA completion percentage

        Args:
            completion: Completion percentage (0-100)

        """
        self.pdca_completion = completion

    def update_pdca_status(self, pdca_status: dict | None) -> None:
        """Update all PDCA status from a dict

        Args:
            pdca_status: PDCA status dict with active, phase, domain, completion

        """
        if not pdca_status:
            self.set_pdca_active(False)
            return

        self.set_pdca_active(pdca_status.get("active", False))
        if self.pdca_active:
            summary = pdca_status.get("summary", {})
            self.set_pdca_phase(summary.get("current_phase", ""))
            self.set_pdca_domain(summary.get("domain", ""))
            self.set_pdca_completion(summary.get("completion_percentage", 0))

    def set_subtask_summary(self) -> None:
        """C24：从 app.agent_bridge.subtask_states 计算缩略段

        形如 `子任务 4/6 ✓3 ✗1 · 新加坡(3/5)`（末段 = 最活跃项 todo 步数，
        空间由 ellipsis 裁剪）。无活动子任务时整段隐藏（summary 置空）。
        异常安全：计算失败保持旧值（纯 UI 态）。
        """
        try:
            bridge = getattr(self.app, "agent_bridge", None)
            states = getattr(bridge, "subtask_states", None) or {}
            if not states:
                self.subtask_summary = ""
                self.subtask_has_failure = False
                return
            terminal = {"completed", "failed", "aborted", "cancelled"}
            items = list(states.values())
            total = len(items)
            done = sum(1 for s in items if str(s.get("status", "")) in terminal)
            completed = sum(1 for s in items if str(s.get("status", "")) == "completed")
            failed = sum(1 for s in items if str(s.get("status", "")) in ("failed", "aborted", "cancelled"))
            summary = f"子任务 {done}/{total}"
            if completed:
                summary += f" ✓{completed}"
            if failed:
                summary += f" ✗{failed}"
            # 空间允许时追加最活跃项步数（首个带 todos 的非终态项）
            if done < total:
                for s in items:
                    if str(s.get("status", "")) in terminal:
                        continue
                    todos = s.get("todos") or {}
                    if todos.get("total"):
                        ident = str(s.get("item_identity") or "")[:8]
                        summary += f" · {ident}({todos.get('completed', 0)}/{todos.get('total', 0)})"
                        break
            self.subtask_summary = summary
            self.subtask_has_failure = failed > 0
        except Exception:  # noqa: BLE001 — 纯 UI 态，计算失败保持旧值
            pass
