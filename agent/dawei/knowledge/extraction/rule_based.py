# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Rule-based knowledge extraction using patterns and dictionaries

Fast and simple extraction strategy based on:
- Regular expressions for pattern matching
- Dictionaries for known entities
- Heuristic rules for relation detection
"""

import re
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


class RuleBasedExtractor(ExtractionStrategy):
    """Rule-based extraction using patterns and dictionaries

    Strategy:
    1. Extract entities using regex patterns and dictionaries
    2. Detect relations using co-occurrence and patterns
    3. Fast but limited accuracy

    Config:
        tech_dict: List of technology keywords
        org_dict: List of organization names
        relation_patterns: Dict of relation patterns
    """

    strategy_name = "rule_based"

    # Default dictionaries (can be overridden via config)
    DEFAULT_TECH_TERMS = [
        # Programming languages
        "Python",
        "Java",
        "JavaScript",
        "TypeScript",
        "Go",
        "Rust",
        "C++",
        "C#",
        "Ruby",
        "PHP",
        "Swift",
        "Kotlin",
        # Frameworks
        "FastAPI",
        "Flask",
        "Django",
        "Spring",
        "React",
        "Vue",
        "Angular",
        # Databases
        "PostgreSQL",
        "MySQL",
        "MongoDB",
        "Redis",
        "SQLite",
        # Tools
        "Docker",
        "Kubernetes",
        "Git",
        "Linux",
        "Nginx",
        # ML/AI
        "TensorFlow",
        "PyTorch",
        "scikit-learn",
        "pandas",
        "numpy",
        # Concepts
        "机器学习",
        "深度学习",
        "人工智能",
        "知识图谱",
        "RAG",
    ]

    DEFAULT_ORG_PATTERNS = [
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:公司|科技|有限|集团|Corp|Inc|Ltd)",
        r"[A-Z]{2,}",  # Acronyms like API, HTTP
    ]

    DEFAULT_PERSON_PATTERN = r"[\u4e00-\u9fa5]{2,3}"  # Chinese names

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)

        # Load dictionaries
        self.tech_terms = set(self.config.get("tech_dict", self.DEFAULT_TECH_TERMS))
        self.org_dict = set(self.config.get("org_dict", []))

        # Compile patterns
        self.person_pattern = re.compile(self.DEFAULT_PERSON_PATTERN)
        self.org_patterns = [re.compile(p) for p in self.config.get("org_patterns", self.DEFAULT_ORG_PATTERNS)]

        # Relation patterns
        self.relation_patterns = self.config.get(
            "relation_patterns",
            {
                "used_in": [r"(\w+)\s+用于\s+(\w+)", r"(\w+)\s+used\s+in\s+(\w+)"],
                "works_at": [r"(\w+)\s+工作于\s+(\w+)", r"(\w+)\s+works\s+at\s+(\w+)"],
                "part_of": [r"(\w+)\s+属于\s+(\w+)", r"(\w+)\s+is\s+part\s+of\s+(\w+)"],
                "similar_to": [r"(\w+)\s+类似\s+(\w+)", r"(\w+)\s+similar\s+to\s+(\w+)"],
            },
        )

        # Compile relation patterns
        self.compiled_relations = {}
        for rel_type, patterns in self.relation_patterns.items():
            self.compiled_relations[rel_type] = [re.compile(p, re.IGNORECASE) for p in patterns]

        logger.info(f"RuleBasedExtractor initialized with {len(self.tech_terms)} tech terms")

    async def extract(self, text: str, **kwargs) -> ExtractionResult:
        """Extract entities and relations using rules

        Args:
            text: Text to extract from
            **kwargs: Additional parameters (ignored)

        Returns:
            ExtractionResult
        """
        entities = []
        relations = []

        # Extract entities
        tech_entities = self._extract_tech_terms(text)
        org_entities = self._extract_organizations(text)
        person_entities = self._extract_persons(text)

        entities.extend(tech_entities)
        entities.extend(org_entities)
        entities.extend(person_entities)

        # Extract relations
        relations = self._extract_relations(text, entities)

        result = ExtractionResult(
            entities=entities,
            relations=relations,
            metadata={
                "strategy": self.strategy_name,
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
        )

        logger.debug(f"Rule-based extraction: {len(entities)} entities, {len(relations)} relations")
        return result

    def _extract_tech_terms(self, text: str) -> List[ExtractedEntity]:
        """Extract technology terms"""
        entities = []

        for term in self.tech_terms:
            if term in text:
                # Count mentions
                count = text.count(term)

                entities.append(
                    ExtractedEntity(
                        name=term,
                        type="TECH",
                        properties={
                            "category": self._categorize_tech_term(term),
                            "mentions": count,
                        },
                        confidence=0.9,
                        mention_count=count,
                    )
                )

        return entities

    def _extract_organizations(self, text: str) -> List[ExtractedEntity]:
        """Extract organization names"""
        entities = []

        # Check org dictionary
        for org in self.org_dict:
            if org in text:
                entities.append(
                    ExtractedEntity(
                        name=org,
                        type="ORG",
                        properties={"source": "dictionary"},
                        confidence=0.95,
                        mention_count=text.count(org),
                    )
                )

        # Apply patterns
        for pattern in self.org_patterns:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, str):
                    org_name = match
                else:
                    org_name = match[0] if match else ""

                if org_name and len(org_name) > 2:
                    entities.append(
                        ExtractedEntity(
                            name=org_name,
                            type="ORG",
                            properties={"source": "pattern"},
                            confidence=0.7,
                            mention_count=text.count(org_name),
                        )
                    )

        return entities

    def _extract_persons(self, text: str) -> List[ExtractedEntity]:
        """Extract person names (Chinese)"""
        entities = []

        matches = self.person_pattern.findall(text)
        seen = set()

        for match in matches:
            if match not in seen and len(match) >= 2:
                seen.add(match)
                entities.append(
                    ExtractedEntity(
                        name=match,
                        type="PERSON",
                        properties={},
                        confidence=0.6,  # Lower confidence for generic pattern
                        mention_count=text.count(match),
                    )
                )

        return entities

    def _extract_relations(self, text: str, entities: List[ExtractedEntity]) -> List[ExtractedRelation]:
        """Extract relations using patterns"""
        relations = []
        entity_names = {e.name for e in entities}

        # Try each relation pattern
        for rel_type, patterns in self.compiled_relations.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                for match in matches:
                    if len(match) >= 2:
                        from_entity = match[0]
                        to_entity = match[1]

                        # Only create relation if both entities exist
                        if from_entity in entity_names and to_entity in entity_names:
                            relations.append(
                                ExtractedRelation(
                                    from_entity=from_entity,
                                    to_entity=to_entity,
                                    relation_type=rel_type,
                                    properties={"source": "pattern"},
                                    confidence=0.7,
                                    mention_count=1,
                                )
                            )

        # Co-occurrence relations (entities appearing close together)
        relations.extend(self._extract_cooccurrence_relations(text, entities))

        return relations

    def _extract_cooccurrence_relations(self, text: str, entities: List[ExtractedEntity]) -> List[ExtractedRelation]:
        """Extract relations based on entity co-occurrence"""
        relations = []

        # Simple approach: if two entities appear in same sentence/paragraph
        sentences = re.split(r"[。！？.!?]", text)

        for sentence in sentences:
            entities_in_sentence = [e for e in entities if e.name in sentence]

            # Create relations between entities in same sentence
            for i, e1 in enumerate(entities_in_sentence):
                for e2 in entities_in_sentence[i + 1 :]:
                    # Avoid duplicate relations
                    relations.append(
                        ExtractedRelation(
                            from_entity=e1.name,
                            to_entity=e2.name,
                            relation_type="co_occurs",
                            properties={
                                "context": sentence[:100],
                                "source": "cooccurrence",
                            },
                            confidence=0.5,  # Lower confidence
                            mention_count=1,
                        )
                    )

        return relations

    def _categorize_tech_term(self, term: str) -> str:
        """Categorize technology term"""
        categories = {
            "Python": "language",
            "Java": "language",
            "JavaScript": "language",
            "FastAPI": "framework",
            "Django": "framework",
            "PostgreSQL": "database",
            "MongoDB": "database",
            "Docker": "tool",
            "Kubernetes": "tool",
            "TensorFlow": "ml_framework",
        }
        return categories.get(term, "unknown")
