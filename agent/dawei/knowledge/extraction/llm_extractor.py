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

        # Lazy init LLM service
        self._llm_service = None

        logger.info(f"LLMExtractor initialized")

    @property
    def llm_service(self):
        """Lazy load LLM service"""
        if self._llm_service is None:
            try:
                from dawei.llm_api.llm_provider import LLMProviderManager

                self._llm_service = LLMProviderManager()
                logger.info("LLM service loaded successfully")
            except ImportError as e:
                logger.error(f"Failed to import LLM service: {e}")
                raise
        return self._llm_service

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
        prompt = self.DEFAULT_PROMPT.format(text=text)

        try:
            # Import message types
            from dawei.entity.lm_messages import UserMessage, MessageRole

            # Create message
            messages = [UserMessage(role=MessageRole.USER, content=prompt)]

            # Call LLM service
            logger.info("Calling LLM for knowledge extraction...")
            response = await self.llm_service.create_message(messages)

            # Extract response content
            if hasattr(response, "content"):
                content = response.content
            elif isinstance(response, dict):
                content = response.get("content", "")
            else:
                content = str(response)

            logger.info(f"LLM response received: {len(content)} chars")

            # Parse response
            result = self._parse_llm_response(content)

            # Add metadata
            result.metadata.update(
                {
                    "strategy": self.strategy_name,
                    "text_length": len(text),
                    "chunk_id": kwargs.get("chunk_id"),
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
