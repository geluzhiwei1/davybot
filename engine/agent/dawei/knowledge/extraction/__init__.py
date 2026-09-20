# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge Graph Extraction Strategies

Provides multiple extraction strategies for building knowledge graphs from documents:
- RuleBasedExtractor: Pattern-based extraction (fast, simple)
- LLMExtractor: LLM-based extraction (accurate, flexible)
- NERModelExtractor: Professional NER models (best quality)

Usage:
    from dawei.knowledge.extraction import ExtractionFactory, ExtractionStrategyType

    # Create extractor
    extractor = ExtractionFactory.create(ExtractionStrategyType.LLM)

    # Extract from text
    result = await extractor.extract("张三在Python公司工作")
"""

from dawei.knowledge.extraction.base import (
    ExtractionStrategy,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)
from dawei.knowledge.extraction.rule_based import RuleBasedExtractor
from dawei.knowledge.extraction.llm_extractor import LLMExtractor
from dawei.knowledge.extraction.ner_extractor import NERModelExtractor
from dawei.knowledge.extraction.factory import (
    ExtractionFactory,
    ExtractionStrategyType,
    ExtractionConfig,
    extract_from_text,
    extract_from_batch,
)

__all__ = [
    # Base classes
    "ExtractionStrategy",
    "ExtractionResult",
    "ExtractedEntity",
    "ExtractedRelation",
    # Concrete strategies
    "RuleBasedExtractor",
    "LLMExtractor",
    "NERModelExtractor",
    # Factory and configuration
    "ExtractionFactory",
    "ExtractionStrategyType",
    "ExtractionConfig",
    # Convenience functions
    "extract_from_text",
    "extract_from_batch",
]
