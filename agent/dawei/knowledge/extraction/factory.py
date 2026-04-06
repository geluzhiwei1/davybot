# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Extraction strategy factory and configuration

Provides easy access to different extraction strategies with
automatic fallback and strategy selection.
"""

import logging
from enum import Enum
from typing import Dict, Any

from dawei.knowledge.extraction.base import (
    ExtractionStrategy,
    ExtractionResult,
)
from dawei.knowledge.extraction.rule_based import RuleBasedExtractor
from dawei.knowledge.extraction.llm_extractor import LLMExtractor
from dawei.knowledge.extraction.ner_extractor import NERModelExtractor

logger = logging.getLogger(__name__)


class ExtractionStrategyType(str, Enum):
    """Available extraction strategy types"""

    RULE_BASED = "rule_based"  # Fast, simple, pattern-based
    LLM = "llm"  # Accurate, flexible, LLM-based
    NER_MODEL = "ner_model"  # Professional NER models
    AUTO = "auto"  # Auto-select based on availability


class ExtractionConfig:
    """Configuration for extraction strategy"""

    def __init__(
        self,
        strategy: ExtractionStrategyType | str = ExtractionStrategyType.RULE_BASED,
        strategy_config: Dict[str, Any] | None = None,
    ):
        if isinstance(strategy, str):
            strategy = ExtractionStrategyType(strategy)
        self.strategy = strategy
        self.strategy_config = strategy_config or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "strategy_config": self.strategy_config,
        }


class ExtractionFactory:
    """Factory for creating extraction strategies"""

    _strategies: Dict[ExtractionStrategyType, type] = {
        ExtractionStrategyType.RULE_BASED: RuleBasedExtractor,
        ExtractionStrategyType.LLM: LLMExtractor,
        ExtractionStrategyType.NER_MODEL: NERModelExtractor,
    }

    @classmethod
    def create(
        cls,
        strategy: ExtractionStrategyType | str = ExtractionStrategyType.RULE_BASED,
        config: Dict[str, Any] | None = None,
        domain: str | None = None,
        llm_config_name: str | None = None,
    ) -> ExtractionStrategy:
        """Create an extraction strategy instance

        Args:
            strategy: Strategy type to create
            config: Optional configuration dictionary
            domain: Optional domain name for domain-specific extraction

        Returns:
            ExtractionStrategy instance
        """
        if isinstance(strategy, str):
            strategy = ExtractionStrategyType(strategy)

        if strategy == ExtractionStrategyType.AUTO:
            strategy = cls._auto_select_strategy()

        strategy_class = cls._strategies.get(strategy)
        if strategy_class is None:
            raise ValueError(f"Unknown strategy type: {strategy}. Available: {list(cls._strategies.keys())}")

        # Inject domain profile into config
        if domain:
            from dawei.knowledge.domains.registry import DomainRegistry

            profile = DomainRegistry.get(domain)
            if profile:
                config = dict(config) if config else {}
                config["domain_profile"] = profile

        # Inject llm_config_name for LLM strategy
        if llm_config_name and strategy in (
            ExtractionStrategyType.LLM,
            ExtractionStrategyType.AUTO,
        ):
            config = dict(config) if config else {}
            config["llm_config_name"] = llm_config_name

        logger.info(f"Creating extraction strategy: {strategy.value}, domain={domain or 'general'}, llm_config={llm_config_name or 'default'}")
        return strategy_class(config=config or {})

    @classmethod
    def create_from_config(cls, config: ExtractionConfig) -> ExtractionStrategy:
        return cls.create(strategy=config.strategy, config=config.strategy_config)

    @classmethod
    def register_strategy(cls, strategy_type: ExtractionStrategyType, strategy_class: type):
        if not issubclass(strategy_class, ExtractionStrategy):
            raise TypeError(f"Strategy class must inherit from ExtractionStrategy: {strategy_class}")
        cls._strategies[strategy_type] = strategy_class
        logger.info(f"Registered custom strategy: {strategy_type.value}")

    @classmethod
    def _auto_select_strategy(cls) -> ExtractionStrategyType:
        try:
            from dawei.llm_api.client import LLMClient
            client = LLMClient.get_instance()
            if client is not None:
                return ExtractionStrategyType.LLM
        except Exception:
            pass

        try:
            import spacy
            return ExtractionStrategyType.NER_MODEL
        except ImportError:
            pass

        return ExtractionStrategyType.RULE_BASED

    @classmethod
    def list_available_strategies(cls) -> list[str]:
        return [s.value for s in cls._strategies.keys()]


async def extract_from_text(
    text: str,
    strategy: ExtractionStrategyType | str = ExtractionStrategyType.AUTO,
    config: Dict[str, Any] | None = None,
) -> ExtractionResult:
    extractor = ExtractionFactory.create(strategy, config)
    return await extractor.extract(text)


async def extract_from_batch(
    texts: list[str],
    strategy: ExtractionStrategyType | str = ExtractionStrategyType.AUTO,
    config: Dict[str, Any] | None = None,
) -> list[ExtractionResult]:
    extractor = ExtractionFactory.create(strategy, config)
    return await extractor.extract_batch(texts)
