# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Domain profiles for knowledge graph extraction"""

from .base import DomainProfile
from .general import GeneralProfile
from .labor_compliance import LaborComplianceProfile
from .legal import LegalProfile
from .medical import MedicalProfile
from .research import ResearchProfile
from .sanctions import SanctionsProfile
from .registry import DomainRegistry

__all__ = [
    "DomainProfile",
    "GeneralProfile",
    "LaborComplianceProfile",
    "LegalProfile",
    "MedicalProfile",
    "ResearchProfile",
    "SanctionsProfile",
    "DomainRegistry",
]
