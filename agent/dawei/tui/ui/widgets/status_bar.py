# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""StatusBar Widget

Displays Agent status, mode, PDCA cycle info, and other runtime information.
"""

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

    def update_text(self) -> None:
        """Update the status text"""
        model_display = self.model or _("N/A")
        status_emoji = self._get_status_emoji(self.status)

        # Build base status
        text = f"{status_emoji} [bold]{_('Status')}:[/bold] {self.status} | [bold]{_('Mode')}:[/bold] {self.mode} | [bold]{_('Model')}:[/bold] {model_display}"

        # Add PDCA info if active
        if self.pdca_active:
            phase_emoji = self._get_phase_emoji(self.pdca_phase)
            domain_emoji = self._get_domain_emoji(self.pdca_domain)
            pdca_info = f" | {phase_emoji} [bold]PDCA:[/bold] {self.pdca_phase.upper()} ({domain_emoji}{self.pdca_domain}) {self.pdca_completion:.0f}%"
            text += pdca_info

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
        print(f"[DEBUG] StatusBar.set_mode: {mode!r}")
        self.mode = mode

    def set_model(self, model: str) -> None:
        """Set model

        Args:
            model: New model

        """
        print(f"[DEBUG] StatusBar.set_model: {model!r}")
        # Truncate long model names
        if len(model) > 30:
            model = model[:27] + "..."
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
