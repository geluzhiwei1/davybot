# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""NER model-based knowledge extraction

Uses professional NER models (spaCy, HuggingFace) for entity extraction.
Best quality but requires model download and loading time.
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

from dawei.knowledge.extraction.base import (
    ExtractionStrategy,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)

logger = logging.getLogger(__name__)


class NERModelExtractor(ExtractionStrategy):
    """Professional NER model-based extraction

    Uses spaCy or HuggingFace models for high-quality extraction.
    Slowest startup but fast execution and best accuracy.

    Config:
        model_name: Model to use
            - "zh_core_web_sm": Chinese small model (spaCy)
            - "en_core_web_sm": English small model (spaCy)
            - "zh_core_web_lg": Chinese large model (spaCy)
            - None: Auto-detect based on text
        library: "spacy" or "transformers"
        device: "cpu" or "cuda"
        relation_extraction: bool (whether to extract relations)
    """

    strategy_name = "ner_model"

    # spaCy entity type mappings
    SPACY_ENTITY_MAP = {
        "PERSON": "PERSON",
        "ORG": "ORG",
        "GPE": "LOCATION",  # Geopolitical entity
        "LOC": "LOCATION",
        "PRODUCT": "TECH",
        "EVENT": "CONCEPT",
        "WORK_OF_ART": "CONCEPT",
        "LAW": "CONCEPT",
        "LANGUAGE": "TECH",
        "DATE": "TIME",
        "TIME": "TIME",
        "PERCENT": "NUMBER",
        "MONEY": "NUMBER",
        "QUANTITY": "NUMBER",
        "CARDINAL": "NUMBER",
        "ORDINAL": "NUMBER",
    }

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)
        # Load domain profile: use domain-specific model if configured
        profile = config.get("domain_profile")
        if profile and profile.ner_model:
            self.model_name = profile.ner_model
            logger.info(f"NERModelExtractor using domain NER model: {self.model_name}")
        else:
            self.model_name = self.config.get("model_name", None)
        self.library = self.config.get("library", "spacy")
        self.device = self.config.get("device", "cpu")
        self.extract_relations = self.config.get("relation_extraction", True)

        # Lazy load model
        self._nlp = None

        logger.info(f"NERModelExtractor initialized: model={self.model_name}, library={self.library}")

    def _load_model(self):
        """Lazy load NER model"""
        if self._nlp is not None:
            return

        try:
            if self.library == "spacy":
                import spacy

                # Determine model to use
                model = self.model_name or "zh_core_web_sm"

                try:
                    self._nlp = spacy.load(model)
                    logger.info(f"Loaded spaCy model: {model}")
                except OSError:
                    # Model not installed, try to download
                    logger.warning(f"spaCy model '{model}' not found, attempting download...")
                    import subprocess

                    subprocess.run(["python", "-m", "spacy", "download", model], check=True)
                    self._nlp = spacy.load(model)
                    logger.info(f"Downloaded and loaded spaCy model: {model}")

            else:
                raise ValueError(f"Unsupported library: {self.library}")

        except ImportError:
            logger.error(f"Library '{self.library}' not installed. Install with: pip install {self.library}")
            raise
        except Exception as e:
            logger.error(f"Failed to load NER model: {e}")
            raise

    async def extract(self, text: str, **kwargs) -> ExtractionResult:
        """Extract entities and relations using NER model

        Args:
            text: Text to extract from
            **kwargs: Additional parameters

        Returns:
            ExtractionResult
        """
        # Lazy load model
        self._load_model()

        entities = []
        relations = []

        try:
            # Process text with spaCy
            doc = self._nlp(text)

            # Extract entities
            seen_entities = {}  # Deduplicate by text

            for ent in doc.ents:
                entity_name = ent.text.strip()

                # Skip very short entities
                if len(entity_name) < 2:
                    continue

                # Map entity type
                entity_type = self.SPACY_ENTITY_MAP.get(ent.label_, "OTHER")

                # Deduplicate
                if entity_name not in seen_entities:
                    seen_entities[entity_name] = {
                        "type": entity_type,
                        "count": 1,
                        "properties": {
                            "label": ent.label_,
                            "start": ent.start_char,
                            "end": ent.end_char,
                        },
                    }
                else:
                    seen_entities[entity_name]["count"] += 1

            # Create ExtractedEntity objects
            for name, data in seen_entities.items():
                entities.append(
                    ExtractedEntity(
                        name=name,
                        type=data["type"],
                        properties=data["properties"],
                        confidence=0.9,  # High confidence for professional models
                        mention_count=data["count"],
                    )
                )

            # Extract relations (dependency-based)
            if self.extract_relations:
                relations = self._extract_dependency_relations(doc, entities)

            # Attach source provenance from kwargs
            chunk_id = kwargs.get("chunk_id")
            document_id = kwargs.get("document_id")
            page_number = kwargs.get("page_number")

            for entity in entities:
                if entity.source_chunk_id is None and chunk_id:
                    entity.source_chunk_id = chunk_id
                if entity.source_document_id is None and document_id:
                    entity.source_document_id = document_id
                if entity.source_page_number is None and page_number is not None:
                    entity.source_page_number = page_number

            for relation in relations:
                if relation.source_chunk_id is None and chunk_id:
                    relation.source_chunk_id = chunk_id
                if relation.source_document_id is None and document_id:
                    relation.source_document_id = document_id
                if relation.source_page_number is None and page_number is not None:
                    relation.source_page_number = page_number

            result = ExtractionResult(
                entities=entities,
                relations=relations,
                metadata={
                    "strategy": self.strategy_name,
                    "model": self.model_name or "auto",
                    "library": self.library,
                    "entity_count": len(entities),
                    "relation_count": len(relations),
                },
            )
            logger.debug(f"NER extraction: {len(entities)} entities, {len(relations)} relations")
            return result

        except Exception as e:
            logger.error(f"NER extraction failed: {e}", exc_info=True)
            return ExtractionResult(entities=[], relations=[], metadata={"error": str(e)})

    def _extract_dependency_relations(self, doc, entities: List[ExtractedEntity]) -> List[ExtractedRelation]:
        """Extract relations based on dependency parsing

        Args:
            doc: spaCy Doc object
            entities: List of extracted entities

        Returns:
            List of ExtractedRelation
        """
        relations = []
        entity_names = {e.name for e in entities}

        # Simple dependency-based relation extraction
        for token in doc:
            # Check if token is an entity
            if token.text in entity_names:
                # Get head (governor) of this token
                head = token.head

                # Check if head is also an entity
                if head.text in entity_names and head.text != token.text:
                    # Determine relation type based on dependency
                    rel_type = self._map_dependency_to_relation(token.dep_)

                    relations.append(
                        ExtractedRelation(
                            from_entity=token.text,
                            to_entity=head.text,
                            relation_type=rel_type,
                            properties={
                                "dependency": token.dep_,
                                "source": "dependency_parsing",
                            },
                            confidence=0.75,
                            mention_count=1,
                        )
                    )

        return relations

    def _map_dependency_to_relation(self, dep: str) -> str:
        """Map spaCy dependency label to relation type

        Args:
            dep: Dependency label

        Returns:
            Relation type string
        """
        mapping = {
            "nsubj": "defines",
            "dobj": "acts_on",
            "pobj": "related_to",
            "compound": "part_of",
            "amod": "describes",
            "nmod": "modifies",
            "prep": "related_to",
        }
        return mapping.get(dep, "related_to")

    async def extract_batch(self, texts: List[str], **kwargs) -> List[ExtractionResult]:
        """Extract from multiple texts efficiently

        spaCy supports batch processing for better performance.

        Args:
            texts: List of texts
            **kwargs: Additional parameters

        Returns:
            List of ExtractionResult
        """
        self._load_model()

        results = []
        batch_size = self.config.get("batch_size", 50)

        # Use spaCy's pipe for efficient batch processing
        docs = self._nlp.pipe(texts, batch_size=batch_size)

        for doc in docs:
            # Extract entities from doc
            entities = []
            seen_entities = {}

            for ent in doc.ents:
                entity_name = ent.text.strip()
                if len(entity_name) < 2:
                    continue

                entity_type = self.SPACY_ENTITY_MAP.get(ent.label_, "OTHER")

                if entity_name not in seen_entities:
                    seen_entities[entity_name] = {"type": entity_type, "count": 1, "properties": {"label": ent.label_}}
                else:
                    seen_entities[entity_name]["count"] += 1

            for name, data in seen_entities.items():
                entities.append(
                    ExtractedEntity(
                        name=name,
                        type=data["type"],
                        properties=data["properties"],
                        confidence=0.9,
                        mention_count=data["count"],
                    )
                )

            # Extract relations if enabled
            relations = []
            if self.extract_relations:
                relations = self._extract_dependency_relations(doc, entities)

            results.append(ExtractionResult(entities=entities, relations=relations, metadata={"strategy": self.strategy_name}))

        return results
