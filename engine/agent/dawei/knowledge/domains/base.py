# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Domain profile base class for domain-specific knowledge graph extraction"""

from typing import Dict, List


class DomainProfile:
    """Base class for domain profiles.

    Each domain (legal, medical, research, etc.) defines its own:
    - entity_types: what kinds of entities to extract
    - relation_types: what kinds of relations to extract
    - dictionaries: domain-specific terminology for rule-based matching
    - patterns: regex patterns for rule-based matching
    - dictionary_entity_map: optional dictionary category -> entity type
    - pattern_entity_map: optional pattern category -> entity type
    - extraction_prompt: customized LLM prompt for this domain
    - ner_model: domain-specific NER model name
    """

    name: str = "general"
    display_name: str = "通用"
    description: str = ""

    # Domain definitions
    entity_types: Dict[str, str] = {}        # type_code -> display_name
    relation_types: Dict[str, str] = {}      # type_code -> display_name
    dictionaries: Dict[str, List[str]] = {}  # category -> terms
    patterns: Dict[str, List[str]] = {}      # category -> regex patterns
    dictionary_entity_map: Dict[str, str] = {}  # dictionary category -> entity type
    pattern_entity_map: Dict[str, str] = {}     # pattern category -> entity type

    # Extraction configuration
    extraction_prompt: str = ""              # empty = use default prompt
    ner_model: str | None = None             # None = use default model

    def get_entity_types_prompt(self) -> str:
        """Generate entity types description for LLM prompt"""
        if not self.entity_types:
            return ""
        items = [f"{k}({v})" for k, v in self.entity_types.items()]
        return " / ".join(items)

    def get_relation_types_prompt(self) -> str:
        """Generate relation types description for LLM prompt"""
        if not self.relation_types:
            return ""
        items = [f"{k}({v})" for k, v in self.relation_types.items()]
        return " / ".join(items)

    def get_dictionary_entity_type(self, category: str) -> str | None:
        """Get entity type for a dictionary category"""
        return self.dictionary_entity_map.get(category)

    def get_pattern_entity_type(self, category: str) -> str | None:
        """Get entity type for a pattern category"""
        return self.pattern_entity_map.get(category)

    def get_all_dictionary_terms(self) -> set[str]:
        """Get all dictionary terms as a flat set"""
        terms: set[str] = set()
        for term_list in self.dictionaries.values():
            terms.update(term_list)
        return terms
