# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Base extraction strategy interface"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel


class ExtractedEntity(BaseModel):
    """Extracted entity from text"""

    name: str
    type: str  # PERSON, ORG, TECH, CONCEPT, etc.
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    mention_count: int = 1

    # Source provenance — which chunk/document this entity was extracted from
    source_chunk_id: str | None = None
    source_document_id: str | None = None
    source_page_number: int | None = None


class ExtractedRelation(BaseModel):
    """Extracted relation between entities"""

    from_entity: str
    to_entity: str
    relation_type: str  # works_at, used_in, cites, is_a, etc.
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    mention_count: int = 1

    # Source provenance
    source_chunk_id: str | None = None
    source_document_id: str | None = None
    source_page_number: int | None = None


@dataclass
class ExtractionResult:
    """Result of knowledge extraction from a text chunk"""

    entities: List[ExtractedEntity]
    relations: List[ExtractedRelation]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.entities) + len(self.relations)


class ExtractionStrategy(ABC):
    """Abstract base class for extraction strategies

    All extraction strategies must inherit from this class and implement
    the extract() method.
    """

    strategy_name: str = "base"

    def __init__(self, config: Dict[str, Any] | None = None):
        """Initialize extraction strategy

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}

    @abstractmethod
    async def extract(self, text: str, **kwargs) -> ExtractionResult:
        """Extract entities and relations from text

        Args:
            text: Text to extract from
            **kwargs: Additional parameters (chunk_id, document_id, etc.)

        Returns:
            ExtractionResult with entities and relations
        """
        pass

    async def extract_batch(self, texts: List[str], **kwargs) -> List[ExtractionResult]:
        """Extract from multiple texts (default implementation)

        Args:
            texts: List of texts to extract from
            **kwargs: Additional parameters

        Returns:
            List of ExtractionResult
        """
        results = []
        for text in texts:
            result = await self.extract(text, **kwargs)
            results.append(result)
        return results

    def merge_results(self, results: List[ExtractionResult]) -> ExtractionResult:
        """Merge multiple extraction results

        Args:
            results: List of ExtractionResult to merge

        Returns:
            Merged ExtractionResult
        """
        all_entities: Dict[str, ExtractedEntity] = {}
        all_relations: Dict[str, ExtractedRelation] = {}

        for result in results:
            # Merge entities (deduplicate by name)
            for entity in result.entities:
                if entity.name in all_entities:
                    # Update existing entity
                    existing = all_entities[entity.name]
                    existing.mention_count += entity.mention_count
                    # Average confidence
                    existing.confidence = (existing.confidence + entity.confidence) / 2
                    # Merge properties
                    existing.properties.update(entity.properties)

                    # Merge source provenance
                    if entity.source_document_id and entity.source_document_id not in (
                        existing.source_document_id or ""
                    ):
                        if existing.source_document_id:
                            # Keep first, already have one
                            pass
                        else:
                            existing.source_document_id = entity.source_document_id
                    if entity.source_chunk_id and entity.source_chunk_id not in (
                        existing.source_chunk_id or ""
                    ):
                        if existing.source_chunk_id:
                            pass
                        else:
                            existing.source_chunk_id = entity.source_chunk_id
                    if (
                        entity.source_page_number is not None
                        and existing.source_page_number is None
                    ):
                        existing.source_page_number = entity.source_page_number
                else:
                    all_entities[entity.name] = entity

            # Merge relations (deduplicate by from_entity+to_entity+relation_type)
            for relation in result.relations:
                key = f"{relation.from_entity}|{relation.to_entity}|{relation.relation_type}"
                if key in all_relations:
                    # Update existing relation
                    existing = all_relations[key]
                    existing.mention_count += relation.mention_count
                    existing.confidence = (existing.confidence + relation.confidence) / 2
                    existing.properties.update(relation.properties)

                    # Merge source provenance for relations
                    if relation.source_document_id and not existing.source_document_id:
                        existing.source_document_id = relation.source_document_id
                    if relation.source_chunk_id and not existing.source_chunk_id:
                        existing.source_chunk_id = relation.source_chunk_id
                    if relation.source_page_number is not None and existing.source_page_number is None:
                        existing.source_page_number = relation.source_page_number
                else:
                    all_relations[key] = relation

        return ExtractionResult(
            entities=list(all_entities.values()),
            relations=list(all_relations.values()),
        )

    def get_strategy_name(self) -> str:
        """Get strategy name"""
        return self.strategy_name

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return self.config.copy()
