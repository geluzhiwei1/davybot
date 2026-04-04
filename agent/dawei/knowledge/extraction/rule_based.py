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
        # Chinese company suffixes
        r"[^\s,。，]{2,20}(?:公司|科技|集团|有限责任公司|股份有限公司|合伙企业|基金会|协会|委员会|研究院)",
        # Western company suffixes
        r"\b[A-Z][A-Za-z0-9&'\- ]{1,60}\s+(?:Corp(?:oration)?|Inc(?:orporated)?|Ltd|LLC|LLP|PLC|GmbH|S\.A\.|B\.V\.|AG|NV|SE|Foundation|Institute|Authority|Group|Holdings|Partners)\b",
    ]

    # NOTE: Chinese person name extraction via regex is disabled.
    # Pattern r"[\u4e00-\u9fa5]{2,4}" matches ANY 2-4 Chinese chars,
    # producing massive false positives (e.g. "的详情", "请浏览", "与服务合").
    # Chinese NER requires a proper model (spacy/LLM), not a naive regex.
    # Western names: "First Last" or "Title + Name" (Title-cased, 2-4 tokens)
    PERSON_PATTERN_WESTERN = (
        r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?|Sir|Dame|Lord|Lady)\s+"
        r"[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,3}\b"
        r"|"
        r"\b[A-Z][a-z]{1,20}(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]{1,20}\b"
    )

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)

        # Load domain profile if available
        profile = self.config.get("domain_profile")
        self._domain_profile = profile
        self.entity_type_map = profile.entity_types if profile else {"TECH": "技术"}

        if profile:
            self.dictionary_entries = self._build_dictionary_entries(profile)
            self.domain_patterns = self._compile_domain_patterns(profile)
        else:
            self.dictionary_entries = [
                {
                    "term": term,
                    "type": "TECH",
                    "category": self._categorize_tech_term(term),
                }
                for term in self.DEFAULT_TECH_TERMS
            ]
            self.domain_patterns = {}

        self.org_dict = set(self.config.get("org_dict", []))

        # Compile patterns
        self.person_pattern_western = re.compile(self.PERSON_PATTERN_WESTERN)
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

        logger.info(
            "RuleBasedExtractor initialized with %s dictionary terms and %s domain pattern categories",
            len(self.dictionary_entries),
            len(self.domain_patterns),
        )

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
        dictionary_entities = self._extract_dictionary_entities(text)
        pattern_entities = self._extract_pattern_entities(text)
        org_entities = self._extract_organizations(text)
        person_entities = self._extract_persons(text)

        entities.extend(dictionary_entities)
        entities.extend(pattern_entities)
        entities.extend(org_entities)
        entities.extend(person_entities)
        entities = self._deduplicate_entities(entities)

        # Extract relations
        relations = self._extract_relations(text, entities)

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
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
        )

        logger.debug(f"Rule-based extraction: {len(entities)} entities, {len(relations)} relations")
        return result

    def _build_dictionary_entries(self, profile) -> List[Dict[str, str]]:
        """Build dictionary entries with resolved entity types"""
        entries = []

        for category, terms in profile.dictionaries.items():
            entity_type = self._resolve_dictionary_entity_type(profile, category)
            if not entity_type:
                continue

            for term in terms:
                entries.append(
                    {
                        "term": term,
                        "type": entity_type,
                        "category": category,
                    }
                )

        return entries

    def _compile_domain_patterns(self, profile) -> Dict[str, Dict[str, Any]]:
        """Compile domain regex patterns with mapped entity types"""
        compiled = {}

        for category, patterns in profile.patterns.items():
            entity_type = self._resolve_pattern_entity_type(profile, category)
            if not entity_type:
                continue

            compiled[category] = {
                "type": entity_type,
                "patterns": [re.compile(pattern, re.IGNORECASE) for pattern in patterns],
            }

        return compiled

    def _resolve_dictionary_entity_type(self, profile, category: str) -> str | None:
        """Resolve dictionary category to entity type"""
        entity_type = profile.get_dictionary_entity_type(category)
        if entity_type:
            return entity_type
        return self._infer_entity_type_from_category(category, profile.entity_types)

    def _resolve_pattern_entity_type(self, profile, category: str) -> str | None:
        """Resolve pattern category to entity type"""
        entity_type = profile.get_pattern_entity_type(category)
        if entity_type:
            return entity_type
        return self._infer_entity_type_from_category(category, profile.entity_types)

    def _infer_entity_type_from_category(self, category: str, entity_types: Dict[str, str]) -> str | None:
        """Infer entity type from dictionary/pattern category name"""
        normalized = category.strip().upper()
        candidates = [normalized]

        if normalized.endswith("IES"):
            candidates.append(normalized[:-3] + "Y")
        if normalized.endswith("S"):
            candidates.append(normalized[:-1])

        synonyms = {
            "DRUGS": "DRUG",
            "METHODS": "METHOD",
            "DATASETS": "DATASET",
            "OFFENSES": "CRIME",
            "CRIMES": "CRIME",
            "COURTS": "COURT",
            "AGENCIES": "AGENCY",
            "INSTITUTIONS": "INSTITUTION",
            "ORGANIZATIONS": "ORG",
            "ORGS": "ORG",
            "JURISDICTIONS": "JURISDICTION",
            "CONTRACTS": "CONTRACT",
            "CLAUSES": "CLAUSE",
            "ARTICLES": "ARTICLE",
            "LAWS": "LAW",
            "CASES": "CASE",
            "AUTHORS": "AUTHOR",
            "TOOLS": "TOOL",
            "LAW_NAME": "LAW",
            "CASE_NO": "CASE",
            "ARTICLE_NO": "ARTICLE",
            "PROVISION_REF": "ARTICLE",
            "TRIBUNAL_NAME": "COURT",
        }
        synonym = synonyms.get(normalized)
        if synonym:
            candidates.append(synonym)

        for candidate in candidates:
            if candidate in entity_types:
                return candidate

        return None

    def _extract_dictionary_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract entities from configured dictionaries"""
        entities = []

        for entry in self.dictionary_entries:
            count = self._count_term_matches(text, entry["term"])
            if count == 0:
                continue

            entities.append(
                ExtractedEntity(
                    name=entry["term"],
                    type=entry["type"],
                    properties={
                        "category": entry["category"],
                        "source": "dictionary",
                        "mentions": count,
                    },
                    confidence=0.9,
                    mention_count=count,
                )
            )

        return entities

    def _extract_pattern_entities(self, text: str) -> List[ExtractedEntity]:
        """Extract entities from domain-specific regex patterns"""
        entities = []

        for category, config in self.domain_patterns.items():
            for pattern in config["patterns"]:
                for match in pattern.finditer(text):
                    entity_name = match.group(0).strip()
                    if len(entity_name) < 2:
                        continue

                    entities.append(
                        ExtractedEntity(
                            name=entity_name,
                            type=config["type"],
                            properties={
                                "category": category,
                                "source": "pattern",
                                "pattern": pattern.pattern,
                            },
                            confidence=0.85,
                            mention_count=self._count_term_matches(text, entity_name) or 1,
                        )
                    )

        return entities

    def _deduplicate_entities(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Deduplicate entities while preserving strongest metadata"""
        deduplicated: Dict[tuple[str, str], ExtractedEntity] = {}

        for entity in entities:
            key = (entity.name, entity.type)
            if key not in deduplicated:
                deduplicated[key] = entity
                continue

            existing = deduplicated[key]
            existing.mention_count = max(existing.mention_count, entity.mention_count)
            existing.confidence = max(existing.confidence, entity.confidence)
            existing.properties.update(entity.properties)

        return list(deduplicated.values())

    def _count_term_matches(self, text: str, term: str) -> int:
        """Count matches with safer boundaries for Latin-script terms"""
        if not term:
            return 0

        if re.search(r"[A-Za-z]", term):
            pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            return len(pattern.findall(text))

        return text.count(term)

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
        """Extract person names (Western scripts only via regex)

        Chinese person name extraction is NOT supported by regex —
        r"[\\u4e00-\\u9fa5]{2,4}" matches any 2-4 Chinese chars and
        produces massive false positives. Use LLM or NER strategy instead.
        """
        entities = []
        seen: set[str] = set()

        # Western names only (Title-cased with optional honorific)
        for match in self.person_pattern_western.finditer(text):
            name = match.group(0).strip()
            if name not in seen and len(name) >= 4:
                seen.add(name)
                entities.append(
                    ExtractedEntity(
                        name=name,
                        type="PERSON",
                        properties={"script": "latin"},
                        confidence=0.6,
                        mention_count=self._count_term_matches(text, name),
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
