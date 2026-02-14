# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""PDCA Panel Widget

Displays detailed PDCA cycle information including current phase,
domain, completion, and phase transition history.
"""

from typing import ClassVar

from textual.reactive import reactive
from textual.widgets import Static


class PDCAPanel(Static):
    """PDCA cycle information display widget"""

    # PDCA state
    pdca_active = reactive(False)
    current_phase = reactive("")
    domain = reactive("")
    cycle_count = reactive(0)
    completion_percentage = reactive(0.0)
    phase_history: ClassVar[list[str]] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.phase_history = []

    def watch_pdca_active(self, _old_value: bool, _new_value: bool) -> None:
        """Update display when PDCA active state changes"""
        self.update_content()

    def watch_current_phase(self, _old_phase: str, _new_phase: str) -> None:
        """Update display when phase changes"""
        self.update_content()

    def watch_domain(self, _old_domain: str, _new_domain: str) -> None:
        """Update display when domain changes"""
        self.update_content()

    def watch_cycle_count(self, _old_count: int, _new_count: int) -> None:
        """Update display when cycle count changes"""
        self.update_content()

    def watch_completion_percentage(self, _old_completion: float, _new_completion: float) -> None:
        """Update display when completion percentage changes"""
        self.update_content()

    def update_content(self) -> None:
        """Update the panel content"""
        if not self.pdca_active:
            self.update(
                "[dim italic]PDCA cycle not active[/dim italic]\n\n[dim]Orchestrator will automatically start PDCA for complex tasks.[/dim]",
            )
            return

        phase_emoji = self._get_phase_emoji(self.current_phase)
        domain_emoji = self._get_domain_emoji(self.domain)

        # Build panel content
        content = [
            "[bold]PDCA Cycle Active[/bold]",
            "",
            f"{domain_emoji} [bold]Domain:[/bold] {self.domain.upper()}",
            f"{phase_emoji} [bold]Phase:[/bold] {self.current_phase.upper()}",
            f"🔄 [bold]Cycle:[/bold] {self.cycle_count}",
            "",
            self._get_progress_bar(),
            "",
        ]

        # Add phase-specific guidance
        guidance = self._get_phase_guidance(self.current_phase, self.domain)
        if guidance:
            content.extend(
                [
                    "[bold]Phase Guidance:[/bold]",
                    f"[dim]{guidance}[/dim]",
                    "",
                ],
            )

        # Add phase history if available
        if self.phase_history:
            content.extend(
                [
                    "[bold]Phase History:[/bold]",
                    f"[dim]{' → '.join(self.phase_history)}[/dim]",
                    "",
                ],
            )

        self.update("\n".join(content))

    def _get_progress_bar(self) -> str:
        """Get a visual progress bar"""
        filled = int(self.completion_percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)
        return f"[bold]{self.completion_percentage:.0f}%[/bold] {bar}"

    def _get_phase_emoji(self, phase: str) -> str:
        """Get emoji for PDCA phase"""
        phase_emojis = {
            "plan": "📋",
            "do": "⚙️",
            "check": "✓",
            "act": "🚀",
            "orchestrator": "🪃",
        }
        return phase_emojis.get(phase.lower(), "🔄")

    def _get_domain_emoji(self, domain: str) -> str:
        """Get emoji for domain"""
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

    def _get_phase_guidance(self, phase: str, _domain: str) -> str:
        """Get guidance message for the current phase"""
        guidance_map = {
            "plan": "Understanding requirements, exploring context, and creating a plan.",
            "do": "Executing the planned actions systematically.",
            "check": "Verifying results against goals and quality standards.",
            "act": "Standardizing improvements and deciding on next steps.",
            "orchestrator": "Coordinating PDCA cycle across all phases.",
        }
        return guidance_map.get(phase.lower(), "")

    def set_pdca_active(self, active: bool) -> None:
        """Set PDCA active state"""
        self.pdca_active = active

    def set_current_phase(self, phase: str) -> None:
        """Set current PDCA phase"""
        self.current_phase = phase
        if phase and (not self.phase_history or self.phase_history[-1] != phase):
            self.phase_history.append(phase)
            # Keep only last 10 phases
            if len(self.phase_history) > 10:
                self.phase_history = self.phase_history[-10:]

    def set_domain(self, domain: str) -> None:
        """Set domain type"""
        self.domain = domain

    def set_cycle_count(self, count: int) -> None:
        """Set cycle count"""
        self.cycle_count = count

    def set_completion_percentage(self, percentage: float) -> None:
        """Set completion percentage"""
        self.completion_percentage = percentage

    def update_from_status(self, pdca_status: dict | None) -> None:
        """Update panel from PDCA status dict

        Args:
            pdca_status: PDCA status dict

        """
        if not pdca_status:
            self.set_pdca_active(False)
            return

        self.set_pdca_active(pdca_status.get("active", False))

        if self.pdca_active:
            summary = pdca_status.get("summary", {})
            self.set_current_phase(summary.get("current_phase", ""))
            self.set_domain(summary.get("domain", ""))
            self.set_cycle_count(summary.get("cycle_count", 0))
            self.set_completion_percentage(summary.get("completion_percentage", 0))

            # Update phase history
            phase_history = summary.get("phase_history", [])
            if phase_history:
                self.phase_history = phase_history[-10:]

    def reset(self) -> None:
        """Reset panel to initial state"""
        self.set_pdca_active(False)
        self.set_current_phase("")
        self.set_domain("")
        self.set_cycle_count(0)
        self.set_completion_percentage(0.0)
        self.phase_history = []
