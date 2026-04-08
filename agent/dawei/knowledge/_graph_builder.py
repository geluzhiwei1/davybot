# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge graph builder - extract from chunks and merge"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dawei.knowledge.extraction.base import ExtractionStrategy

logger = logging.getLogger(__name__)

# LLM 提取时单次最大文本长度（与 LLMExtractor.max_text_length 对齐）
_MAX_EXTRACT_TEXT_LEN = 4000
# 每批处理多少个合并单元（用于进度日志和错误隔离）
_BATCH_SIZE = 20

# 无需逐 chunk 提取的策略（直接用全文，速度快）
_FULL_TEXT_STRATEGIES = frozenset({"rule_based", "sanctions_hybrid"})


def _merge_chunks_into_units(chunks: list, max_len: int = _MAX_EXTRACT_TEXT_LEN) -> list[dict]:
    """将连续小 chunk 合并为更大的提取单元，减少 LLM 调用次数。

    每个 unit 包含合并后的文本和所有源 chunk 的溯源信息。
    """
    units: list[dict] = []
    buf_text = ""
    buf_chunk_ids: list[str] = []
    buf_page: int | None = None

    def _flush():
        if not buf_text:
            return
        units.append({
            "text": buf_text,
            "chunk_ids": list(buf_chunk_ids),
            "page_number": buf_page,
        })

    for chunk in chunks:
        chunk_text = chunk.content or ""
        # 加一个分隔符
        candidate = (buf_text + "\n\n" + chunk_text) if buf_text else chunk_text

        if len(candidate) > max_len and buf_text:
            # 当前 chunk 放不下，先刷出已有的
            _flush()
            buf_text = chunk_text
            buf_chunk_ids = [chunk.id]
            buf_page = chunk.metadata.get("page_number") if chunk.metadata else None
        else:
            buf_text = candidate
            buf_chunk_ids.append(chunk.id)
            page = chunk.metadata.get("page_number") if chunk.metadata else None
            if page is not None and buf_page is None:
                buf_page = page

    _flush()
    return units


async def build_document_graph(
    graph_store,
    document,  # Document object
    chunks: list,  # List[DocumentChunk] — used as extraction input only
    extractor,  # ExtractionStrategy
    base_id: str,
    extraction_strategy: str,
    file_name: str,
) -> tuple[int, int]:
    """Build knowledge graph by extracting from ALL chunks and merging.

    Chunks feed into LLM extraction but are NOT stored as graph nodes.
    The graph is a pure semantic layer: document -> entities -> relations.
    Chunk-level provenance is kept in entity properties (source_chunks).

    For fast strategies (rule_based, sanctions_hybrid), the full document
    text is passed directly to the extractor instead of chunk-by-chunk,
    avoiding thousands of individual extraction calls.

    Returns:
        (total_entities, total_relations) count
    """
    from dawei.knowledge.models import GraphEntity, GraphRelation

    total_entities = 0
    total_relations = 0

    # 1. Document entity
    doc_entity = GraphEntity(
        id=f"doc_{document.id}",
        type="document",
        name=file_name,
        description=f"Document: {file_name}",
        properties={
            "file_size": document.metadata.file_size,
            "file_type": document.metadata.file_type,
        },
        base_id=base_id,
    )
    await graph_store.add_entity(doc_entity)
    total_entities += 1

    # 2. Build extraction units
    #    For rule-based / sanctions_hybrid: use full document text (fast, no LLM)
    #    For LLM / NER: merge chunks into ~4000 char units
    if extraction_strategy in _FULL_TEXT_STRATEGIES:
        full_text = "\n\n".join(c.content for c in chunks if c.content)
        units = [{
            "text": full_text,
            "chunk_ids": [c.id for c in chunks],
            "page_number": chunks[0].metadata.get("page_number") if chunks and chunks[0].metadata else None,
        }]
    else:
        units = _merge_chunks_into_units(chunks, max_len=_MAX_EXTRACT_TEXT_LEN)

    total_units = len(units)
    logger.info(
        f"Extraction plan for {file_name}: "
        f"{len(chunks)} chunks -> {total_units} extraction units (strategy: {extraction_strategy})"
    )

    # 3. Extract from every unit
    chunk_results = []

    for batch_start in range(0, total_units, _BATCH_SIZE):
        batch_end = min(batch_start + _BATCH_SIZE, total_units)
        batch = units[batch_start:batch_end]
        batch_idx = batch_start // _BATCH_SIZE + 1
        total_batches = (total_units + _BATCH_SIZE - 1) // _BATCH_SIZE

        for i, unit in enumerate(batch):
            try:
                result = await extractor.extract(
                    unit["text"],
                    chunk_id=unit["chunk_ids"][0],  # primary chunk id
                    document_id=document.id,
                    page_number=unit["page_number"],
                )

                # Attach all source chunk ids to entities
                for entity in result.entities:
                    if len(unit["chunk_ids"]) > 1:
                        entity.source_chunk_id = unit["chunk_ids"][0]
                for rel in result.relations:
                    if len(unit["chunk_ids"]) > 1:
                        rel.source_chunk_id = unit["chunk_ids"][0]

                if result.entities:
                    chunk_results.append(result)
            except Exception as e:
                unit_idx = batch_start + i + 1
                logger.warning(f"Failed to extract from unit {unit_idx}/{total_units} in {file_name}: {e}")

        logger.info(
            f"Extracted {batch_idx}/{total_batches} for {file_name}: "
            f"{len(chunk_results)} units with entities so far"
        )

    if not chunk_results:
        logger.warning(f"No entities extracted from any unit in {file_name}")
        return total_entities, total_relations

    # 4. Merge all extraction results (deduplicate)
    merged = extractor.merge_results(chunk_results)
    logger.info(
        f"Merged extraction from {len(chunk_results)} units: "
        f"{len(merged.entities)} unique entities, {len(merged.relations)} relations"
    )

    # 5. Add extracted entities + doc->entity "mentions" relations
    entity_id_map: dict[str, str] = {}

    for entity in merged.entities:
        entity_id = f"entity_{hash(entity.name)}_{base_id}"

        if entity.name not in entity_id_map:
            entity_id_map[entity.name] = entity_id

            graph_entity = GraphEntity(
                id=entity_id,
                type=entity.type,
                name=entity.name,
                description=entity.properties.get("description", ""),
                properties={
                    **entity.properties,
                    "confidence": entity.confidence,
                    "source": "extraction",
                    "source_documents": [entity.source_document_id] if entity.source_document_id else [],
                    "source_chunks": [entity.source_chunk_id] if entity.source_chunk_id else [],
                    "source_pages": [entity.source_page_number] if entity.source_page_number is not None else [],
                },
                base_id=base_id,
            )
            await graph_store.add_entity(graph_entity)
            total_entities += 1

        # Document mentions entity
        mentions_relation = GraphRelation(
            id=f"rel_{doc_entity.id}_{entity_id_map[entity.name]}",
            from_entity=doc_entity.id,
            to_entity=entity_id_map[entity.name],
            relation_type="mentions",
            properties={
                "confidence": entity.confidence,
                "strategy": extraction_strategy,
            },
            base_id=base_id,
        )
        await graph_store.add_relation(mentions_relation)
        total_relations += 1

    # 6. Add extracted relations between entities
    for relation in merged.relations:
        from_id = entity_id_map.get(relation.from_entity)
        to_id = entity_id_map.get(relation.to_entity)

        if from_id and to_id:
            graph_relation = GraphRelation(
                id=f"rel_{from_id}_{to_id}_{relation.relation_type}",
                from_entity=from_id,
                to_entity=to_id,
                relation_type=relation.relation_type,
                properties={
                    **relation.properties,
                    "confidence": relation.confidence,
                    "strategy": extraction_strategy,
                },
                base_id=base_id,
            )
            await graph_store.add_relation(graph_relation)
            total_relations += 1

    logger.info(
        f"Graph built for {file_name}: {total_entities} entities, {total_relations} relations "
        f"(strategy: {extraction_strategy})"
    )
    return total_entities, total_relations
