# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Domain profile registry — lookup and list available domain profiles"""

from typing import Dict

from .base import DomainProfile
from .general import GeneralProfile
from .labor_compliance import LaborComplianceProfile
from .legal import LegalProfile
from .medical import MedicalProfile
from .research import ResearchProfile
from .sanctions import SanctionsProfile


class DomainRegistry:
    """Registry for domain profiles"""

    _profiles: Dict[str, type] = {}

    @classmethod
    def _init_defaults(cls) -> None:
        if not cls._profiles:
            cls._profiles = {}
            for profile_cls in [GeneralProfile, LaborComplianceProfile, LegalProfile, MedicalProfile, ResearchProfile, SanctionsProfile]:
                cls._profiles[profile_cls.name] = profile_cls

    @classmethod
    def register(cls, profile_class: type) -> None:
        """Register a domain profile class"""
        if not issubclass(profile_class, DomainProfile):
            raise TypeError(f"Must inherit DomainProfile: {profile_class}")
        cls._profiles[profile_class.name] = profile_class

    @classmethod
    def get(cls, domain: str) -> DomainProfile | None:
        """Get a domain profile instance by name"""
        cls._init_defaults()
        profile_class = cls._profiles.get(domain)
        return profile_class() if profile_class else None

    @classmethod
    def list_domains(cls) -> list[dict]:
        """List all available domains"""
        cls._init_defaults()
        return [
            {"name": name, "display_name": cls._profiles[name].display_name}
            for name in cls._profiles
        ]

    @classmethod
    def get_schema(cls, domain: str) -> dict:
        """Get domain schema ( entity_types + relation_types )"""
        cls._init_defaults()
        profile = cls.get(domain)
        if profile:
            return {
                "entity_types": profile.entity_types,
                "relation_types": profile.relation_types,
            }
        return {"entity_types": {}, "relation_types": {}}
