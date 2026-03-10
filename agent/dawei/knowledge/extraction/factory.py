# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Extraction strategy factory and configuration

Provides easy access to different extraction strategies with
automatic fallback and strategy selection.
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional

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
    """Configuration for extraction strategy

    Example:
        config = ExtractionConfig(
            strategy=ExtractionStrategyType.LLM,
            llm_config={"temperature": 0.0, "max_tokens": 2000},
        )
        extractor = ExtractionFactory.create(config)
    """

    def __init__(
        self,
        strategy: ExtractionStrategyType | str = ExtractionStrategyType.RULE_BASED,
        strategy_config: Dict[str, Any] | None = None,
    ):
        """Initialize extraction configuration

        Args:
            strategy: Strategy type to use
            strategy_config: Optional configuration for the specific strategy
        """
        if isinstance(strategy, str):
            strategy = ExtractionStrategyType(strategy)

        self.strategy = strategy
        self.strategy_config = strategy_config or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy": self.strategy.value,
            "strategy_config": self.strategy_config,
        }


class ExtractionFactory:
    """Factory for creating extraction strategies

    Usage:
        # Create rule-based extractor
        extractor = ExtractionFactory.create(ExtractionStrategyType.RULE_BASED)

        # Create LLM extractor with custom config
        extractor = ExtractionFactory.create(
            ExtractionStrategyType.LLM,
            config={"temperature": 0.0}
        )

        # Auto-select (tries LLM -> NER -> Rule)
        extractor = ExtractionFactory.create(ExtractionStrategyType.AUTO)
    """

    # Strategy registry
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
    ) -> ExtractionStrategy:
        """Create an extraction strategy instance

        Args:
            strategy: Strategy type to create
            config: Optional configuration dictionary

        Returns:
            ExtractionStrategy instance

        Raises:
            ValueError: If strategy type is invalid
        """
        if isinstance(strategy, str):
            strategy = ExtractionStrategyType(strategy)

        # Handle AUTO strategy
        if strategy == ExtractionStrategyType.AUTO:
            strategy = cls._auto_select_strategy()

        # Get strategy class
        strategy_class = cls._strategies.get(strategy)

        if strategy_class is None:
            raise ValueError(f"Unknown strategy type: {strategy}. Available: {list(cls._strategies.keys())}")

        # Create instance
        logger.info(f"Creating extraction strategy: {strategy.value}")
        return strategy_class(config=config or {})

    @classmethod
    def create_from_config(cls, config: ExtractionConfig) -> ExtractionStrategy:
        """Create extractor from ExtractionConfig

        Args:
            config: ExtractionConfig instance

        Returns:
            ExtractionStrategy instance
        """
        return cls.create(
            strategy=config.strategy,
            config=config.strategy_config,
        )

    @classmethod
    def register_strategy(
        cls,
        strategy_type: ExtractionStrategyType,
        strategy_class: type,
    ):
        """Register a custom extraction strategy

        Args:
            strategy_type: Strategy type enum
            strategy_class: Strategy class (must inherit from ExtractionStrategy)
        """
        if not issubclass(strategy_class, ExtractionStrategy):
            raise TypeError(f"Strategy class must inherit from ExtractionStrategy: {strategy_class}")

        cls._strategies[strategy_type] = strategy_class
        logger.info(f"Registered custom strategy: {strategy_type.value}")

    @classmethod
    def _auto_select_strategy(cls) -> ExtractionStrategyType:
        """Auto-select best available strategy

        Priority:
        1. LLM (most accurate)
        2. NER_MODEL (professional quality)
        3. RULE_BASED (always available)

        Returns:
            Selected strategy type
        """
        # Check if LLM is available
        try:
            from dawei.llm_api.client import LLMClient

            client = LLMClient.get_instance()
            if client is not None:
                logger.info("Auto-selected: LLM strategy")
                return ExtractionStrategyType.LLM
        except Exception:
            logger.debug("LLM not available")

        # Check if NER models are available
        try:
            import spacy

            logger.info("Auto-selected: NER model strategy")
            return ExtractionStrategyType.NER_MODEL
        except ImportError:
            logger.debug("spaCy not available")

        # Fallback to rule-based
        logger.info("Auto-selected: Rule-based strategy (fallback)")
        return ExtractionStrategyType.RULE_BASED

    @classmethod
    def list_available_strategies(cls) -> list[str]:
        """List all available strategy types

        Returns:
            List of strategy type names
        """
        return [s.value for s in cls._strategies.keys()]


# Convenience functions


async def extract_from_text(
    text: str,
    strategy: ExtractionStrategyType | str = ExtractionStrategyType.AUTO,
    config: Dict[str, Any] | None = None,
) -> ExtractionResult:
    """Convenience function to extract entities/relations from text

    Args:
        text: Text to extract from
        strategy: Strategy to use (default: AUTO)
        config: Optional strategy configuration

    Returns:
        ExtractionResult

    Example:
        result = await extract_from_text(
            "张三在Python公司工作，使用FastAPI框架",
            strategy=ExtractionStrategyType.LLM
        )
        print(f"Found {len(result.entities)} entities")
    """
    extractor = ExtractionFactory.create(strategy, config)
    return await extractor.extract(text)


async def extract_from_batch(
    texts: list[str],
    strategy: ExtractionStrategyType | str = ExtractionStrategyType.AUTO,
    config: Dict[str, Any] | None = None,
) -> list[ExtractionResult]:
    """Convenience function to extract from multiple texts

    Args:
        texts: List of texts to extract from
        strategy: Strategy to use
        config: Optional strategy configuration

    Returns:
        List of ExtractionResult
    """
    extractor = ExtractionFactory.create(strategy, config)
    return await extractor.extract_batch(texts)
