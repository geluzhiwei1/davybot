"""Health monitoring and aggregation for channels.

Provides utilities for:
- Aggregating health status from multiple channels
- Computing overall system health
- Generating health reports
- Alerting on unhealthy channels
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .channel import BaseChannel, ChannelHealth

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Aggregated health report for all channels."""

    timestamp: datetime = field(default_factory=datetime.now)
    channels: dict[str, ChannelHealth] = field(default_factory=dict)
    overall_healthy: bool = True
    unhealthy_channels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_healthy": self.overall_healthy,
            "unhealthy_channels": self.unhealthy_channels,
            "channels": {
                name: {
                    "healthy": health.healthy,
                    "message": health.message,
                    "latency_ms": health.latency_ms,
                    "metadata": health.metadata,
                }
                for name, health in self.channels.items()
            },
            "metadata": self.metadata,
        }


@dataclass
class HealthAlert:
    """Alert for unhealthy channel."""

    channel_type: str
    healthy: bool
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    consecutive_failures: int = 0


AlertCallback = Callable[[HealthAlert], Awaitable[None]]


class HealthMonitor:
    """Monitors health of multiple channels and generates alerts.

    Features:
    - Periodic health checks
    - Consecutive failure tracking
    - Configurable alert thresholds
    - Callback-based alerting
    - Health history tracking
    """

    def __init__(
        self,
        channels: dict[str, BaseChannel],
        check_interval_s: float = 60.0,
        alert_threshold: int = 3,
    ) -> None:
        """Initialize the health monitor.

        Args:
            channels: Dict of channel_type -> channel instance
            check_interval_s: Seconds between health checks
            alert_threshold: Consecutive failures before alerting
        """
        self._channels = channels
        self._check_interval_s = check_interval_s
        self._alert_threshold = alert_threshold
        self._running = False
        self._monitor_task: asyncio.Task[None] | None = None
        self._failure_counts: dict[str, int] = {}
        self._last_failure_time: dict[str, datetime] = {}
        self._last_health_time: dict[str, datetime] = {}
        self._health_history: dict[str, list[ChannelHealth]] = {}
        self._max_history = 100
        self._alert_callbacks: list[AlertCallback] = []

    def add_alert_callback(self, callback: AlertCallback) -> None:
        """Add a callback for health alerts.

        Args:
            callback: Async function called when alerts are triggered
        """
        self._alert_callbacks.append(callback)

    def remove_alert_callback(self, callback: AlertCallback) -> None:
        """Remove an alert callback."""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)

    async def start(self) -> None:
        """Start the health monitor."""
        if self._running:
            logger.warning("HealthMonitor already running")
            return

        logger.info(f"Starting health monitor (interval={self._check_interval_s}s)")
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the health monitor."""
        if not self._running:
            return

        logger.info("Stopping health monitor")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self) -> None:
        """Periodic health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval_s)
                await self._check_all_channels()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")

    async def _check_all_channels(self) -> None:
        """Check health of all channels and generate alerts."""
        for channel_type, channel in self._channels.items():
            try:
                health = await channel.health_check()
                await self._process_health_result(channel_type, health)
            except Exception as e:
                logger.error(f"Health check failed for {channel_type}: {e}")
                # Mark as unhealthy
                await self._process_health_result(
                    channel_type,
                    ChannelHealth(
                        healthy=False,
                        message=f"Health check exception: {e}",
                    ),
                )

    async def _process_health_result(
        self,
        channel_type: str,
        health: ChannelHealth,
    ) -> None:
        """Process a health check result and generate alerts if needed."""
        # Record health history
        if channel_type not in self._health_history:
            self._health_history[channel_type] = []

        self._health_history[channel_type].append(health)
        if len(self._health_history[channel_type]) > self._max_history:
            self._health_history[channel_type] = self._health_history[channel_type][
                -self._max_history :
            ]

        self._last_health_time[channel_type] = datetime.now()

        # Check if healthy
        if health.healthy:
            # Reset failure count on success
            if channel_type in self._failure_counts:
                logger.info(f"Channel {channel_type} recovered")
                del self._failure_counts[channel_type]

            # Send recovery alert
            if channel_type in self._last_failure_time:
                await self._send_alert(
                    HealthAlert(
                        channel_type=channel_type,
                        healthy=True,
                        message="Channel recovered",
                    )
                )
                del self._last_failure_time[channel_type]
        else:
            # Increment failure count
            self._failure_counts[channel_type] = (
                self._failure_counts.get(channel_type, 0) + 1
            )
            self._last_failure_time[channel_type] = datetime.now()

            # Check if we should alert
            count = self._failure_counts[channel_type]
            if count >= self._alert_threshold:
                logger.warning(
                    f"Channel {channel_type} unhealthy for {count} consecutive checks: "
                    f"{health.message}"
                )
                await self._send_alert(
                    HealthAlert(
                        channel_type=channel_type,
                        healthy=False,
                        message=health.message,
                        consecutive_failures=count,
                    )
                )

    async def _send_alert(self, alert: HealthAlert) -> None:
        """Send alert to all registered callbacks."""
        for callback in self._alert_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")

    async def get_health_report(self) -> HealthReport:
        """Generate a comprehensive health report.

        Returns:
            HealthReport with status of all channels
        """
        channels_health = {}
        unhealthy = []

        for channel_type, channel in self._channels.items():
            try:
                health = await channel.health_check()
                channels_health[channel_type] = health
                if not health.healthy:
                    unhealthy.append(channel_type)
            except Exception as e:
                channels_health[channel_type] = ChannelHealth(
                    healthy=False,
                    message=f"Health check error: {e}",
                )
                unhealthy.append(channel_type)

        return HealthReport(
            channels=channels_health,
            overall_healthy=len(unhealthy) == 0,
            unhealthy_channels=unhealthy,
        )

    def get_health_history(
        self,
        channel_type: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, list[ChannelHealth]]:
        """Get health history for channels.

        Args:
            channel_type: Specific channel to get history for (None = all)
            since: Only include entries since this time (None = all)

        Returns:
            Dict mapping channel_type to list of health results
        """
        if since is None:
            # Return all history
            if channel_type:
                return {channel_type: self._health_history.get(channel_type, [])}
            return self._health_history.copy()

        # Filter by time
        result = {}
        for ch_type, history in self._health_history.items():
            if channel_type and ch_type != channel_type:
                continue

            filtered = [
                h for h in history if h.metadata and h.metadata.get("timestamp", datetime.min) >= since
            ]
            if filtered:
                result[ch_type] = filtered

        return result

    @property
    def is_running(self) -> bool:
        """Check if the monitor is running."""
        return self._running

    @property
    def failure_counts(self) -> dict[str, int]:
        """Get current failure counts for all channels."""
        return self._failure_counts.copy()


async def aggregate_channel_health(
    channels: dict[str, BaseChannel],
) -> HealthReport:
    """Aggregate health status from multiple channels (one-time check).

    Args:
        channels: Dict of channel_type -> channel instance

    Returns:
        HealthReport with status of all channels
    """
    channels_health = {}
    unhealthy = []

    for channel_type, channel in channels.items():
        try:
            health = await channel.health_check()
            channels_health[channel_type] = health
            if not health.healthy:
                unhealthy.append(channel_type)
        except Exception as e:
            channels_health[channel_type] = ChannelHealth(
                healthy=False,
                message=f"Health check error: {e}",
            )
            unhealthy.append(channel_type)

    return HealthReport(
        channels=channels_health,
        overall_healthy=len(unhealthy) == 0,
        unhealthy_channels=unhealthy,
    )
