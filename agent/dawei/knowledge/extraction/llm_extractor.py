# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""LLM-based knowledge extraction

Uses Large Language Models to extract entities and relations from text.
Most accurate but slower and requires LLM API access.
"""

import json
import logging
from typing import List, Dict, Any

from dawei.knowledge.extraction.base import (
    ExtractionStrategy,
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
)

logger = logging.getLogger(__name__)


class LLMExtractor(ExtractionStrategy):
    """LLM-based extraction strategy

    Uses LLM to understand context and extract entities/relations.
    High accuracy but slower and requires API costs.

    Config:
        max_text_length: Maximum text length to send to LLM (default: 4000)
    """

    strategy_name = "llm"

    DEFAULT_PROMPT = """你是一个专业的知识图谱构建助手。请从以下文本中提取实体和关系。

文本内容：
{text}

请严格按照以下JSON格式返回，不要添加任何其他内容：

{{
    "entities": [
        {{"name": "实体名称", "type": "类型(PERSON/ORG/TECH/CONCEPT/OTHER)", "properties": {{"key": "value"}}}}
    ],
    "relations": [
        {{"from_entity": "实体1", "to_entity": "实体2", "relation_type": "关系类型(works_at/used_in/part_of/similar_to/cites/defines/OTHER)", "properties": {{}}}}
    ]
}}

注意：
1. 实体类型：PERSON(人物), ORG(组织/公司), TECH(技术/工具), CONCEPT(概念), OTHER(其他)
2. 关系类型：works_at(工作于), used_in(用于), part_of(属于), similar_to(类似), cites(引用), defines(定义), OTHER(其他)
3. 只提取文本中明确提到的实体和关系
4. 如果某个字段不确定，可以留空或使用OTHER
5. properties是可选的，用于存储额外信息
"""

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(config)
        self.max_text_length = self.config.get("max_text_length", 4000)

        # Load domain profile
        profile = self.config.get("domain_profile")
        if profile and profile.extraction_prompt:
            self.prompt_template = profile.extraction_prompt
        else:
            self.prompt_template = self.DEFAULT_PROMPT

        # Lazy init LLM service
        self._llm_service = None
        self._domain_profile = profile
        logger.info(f"LLMExtractor initialized, domain={profile.name if profile else 'general'}")

    @property
    def llm_service(self):
        """Lazy load LLM service"""
        if self._llm_service is None:
            try:
                from dawei.llm_api.llm_provider import LLMProvider

                self._llm_service = LLMProvider()
                logger.info("LLM service loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load LLM service: {e}")
                raise
        return self._llm_service

    def _get_entity_types_str(self) -> str:
        profile = self.config.get("domain_profile")
        return profile.get_entity_types_prompt() if profile else ""

    def _get_relation_types_str(self) -> str:
        profile = self.config.get("domain_profile")
        return profile.get_relation_types_prompt() if profile else ""

    async def extract(self, text: str, **kwargs) -> ExtractionResult:
        """Extract entities and relations using LLM

        Args:
            text: Text to extract from
            **kwargs: Additional parameters (chunk_id, document_id)

        Returns:
            ExtractionResult
        """
        # Truncate text if too long
        if len(text) > self.max_text_length:
            text = text[: self.max_text_length] + "..."
            logger.warning(f"Text truncated to {self.max_text_length} chars for LLM extraction")

        # Prepare prompt
        prompt = self.prompt_template.format(
            text=text,
            entity_types=self._get_entity_types_str() or "",
            relation_types=self._get_relation_types_str() or "",
        )

        try:
            # Import message types
            from dawei.entity.lm_messages import UserMessage, MessageRole

            # Create message
            messages = [UserMessage(role=MessageRole.USER, content=prompt)]

            # Call LLM service
            logger.info("Calling LLM for knowledge extraction...")
            llm_result = await self.llm_service.process_message(messages)

            # Extract response content
            content = llm_result.get("content") or ""

            logger.info(f"LLM response received: {len(content)} chars")

            # Parse response
            result = self._parse_llm_response(content)

            # Attach source provenance from kwargs
            chunk_id = kwargs.get("chunk_id")
            document_id = kwargs.get("document_id")
            page_number = kwargs.get("page_number")

            for entity in result.entities:
                if entity.source_chunk_id is None and chunk_id:
                    entity.source_chunk_id = chunk_id
                if entity.source_document_id is None and document_id:
                    entity.source_document_id = document_id
                if entity.source_page_number is None and page_number is not None:
                    entity.source_page_number = page_number

            for relation in result.relations:
                if relation.source_chunk_id is None and chunk_id:
                    relation.source_chunk_id = chunk_id
                if relation.source_document_id is None and document_id:
                    relation.source_document_id = document_id
                if relation.source_page_number is None and page_number is not None:
                    relation.source_page_number = page_number

            # Add metadata
            result.metadata.update(
                {
                    "strategy": self.strategy_name,
                    "text_length": len(text),
                    "chunk_id": chunk_id,
                }
            )

            logger.info(f"LLM extraction completed: {len(result.entities)} entities, {len(result.relations)} relations")
            return result

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}", exc_info=True)
            # Return empty result on failure
            return ExtractionResult(entities=[], relations=[], metadata={"error": str(e), "strategy": self.strategy_name})

    def _parse_llm_response(self, response: str) -> ExtractionResult:
        """Parse LLM response into ExtractionResult

        Args:
            response: Raw LLM response text

        Returns:
            ExtractionResult
        """
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response.strip()

            # Remove markdown code blocks if present
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                start_idx = 0
                for i, line in enumerate(lines):
                    if not line.strip().startswith("```") and line.strip():
                        start_idx = i
                        break
                end_idx = len(lines)
                for i in range(start_idx, len(lines)):
                    if lines[i].strip().startswith("```"):
                        end_idx = i
                        break
                json_str = "\n".join(lines[start_idx:end_idx])

            # Parse JSON
            data = json.loads(json_str)

            # Parse entities
            entities = []
            for entity_data in data.get("entities", []):
                entities.append(
                    ExtractedEntity(
                        name=entity_data.get("name", ""),
                        type=entity_data.get("type", "OTHER"),
                        properties=entity_data.get("properties", {}),
                        confidence=0.85,
                        mention_count=1,
                    )
                )

            # Parse relations
            relations = []
            for rel_data in data.get("relations", []):
                relations.append(
                    ExtractedRelation(
                        from_entity=rel_data.get("from_entity", ""),
                        to_entity=rel_data.get("to_entity", ""),
                        relation_type=rel_data.get("relation_type", "OTHER"),
                        properties=rel_data.get("properties", {}),
                        confidence=0.80,
                        mention_count=1,
                    )
                )

            return ExtractionResult(
                entities=entities,
                relations=relations,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Response content: {response[:500]}")
            return ExtractionResult(entities=[], relations=[])
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return ExtractionResult(entities=[], relations=[])

    async def extract_batch(self, texts: List[str], **kwargs) -> List[ExtractionResult]:
        """Extract from multiple texts sequentially

        Args:
            texts: List of texts to extract from
            **kwargs: Additional parameters

        Returns:
            List of ExtractionResult
        """
        results = []
        for i, text in enumerate(texts):
            logger.info(f"Processing text {i + 1}/{len(texts)}")
            result = await self.extract(text, **kwargs)
            results.append(result)
        return results
