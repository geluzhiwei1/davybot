# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Evolution Feature - PDCA Continuous Improvement System

This package implements the Evolution feature that enables workspaces to continuously
improve through automated PDCA (Plan-Do-Check-Act) cycles.
"""

from dawei.evolution.evolution_lock import EvolutionLock
from dawei.evolution.evolution_manager import EvolutionCycleManager
from dawei.evolution.evolution_scheduler import EvolutionScheduler, evolution_scheduler
from dawei.evolution.evolution_storage import EvolutionStorage
from dawei.evolution.exceptions import (
    EvolutionAlreadyRunningError,
    EvolutionError,
    EvolutionPhaseError,
    EvolutionStateError,
    EvolutionStorageError,
)

__all__ = [
    "EvolutionError",
    "EvolutionAlreadyRunningError",
    "EvolutionStateError",
    "EvolutionPhaseError",
    "EvolutionStorageError",
    "EvolutionLock",
    "EvolutionStorage",
    "EvolutionCycleManager",
    "EvolutionScheduler",
    "evolution_scheduler",
]
