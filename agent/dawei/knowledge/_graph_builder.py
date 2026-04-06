# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Knowledge graph builder - extract from chunks and merge"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dawei.knowledge.extraction.base import ExtractionStrategy

logger = logging.getLogger(__name__)


async def build_document_graph(
    graph_store,
    document,  # Document object
    chunks: list,  # List[DocumentChunk] — used as extraction input only
    extractor,  # ExtractionStrategy
    base_id: str,
    extraction_strategy: str,
    file_name: str,
) -> tuple[int, int]:
    """Build knowledge graph by extracting per-chunk and merging.

    Chunks feed into LLM extraction but are NOT stored as graph nodes.
    The graph is a pure semantic layer: document → entities → relations.
    Chunk-level provenance is kept in entity properties (source_chunks).

    Flow:
    1. Create document entity in graph
    2. Extract knowledge from each chunk
    3. Merge all extraction results (deduplicate by entity name)
    4. Add extracted entities with doc→entity "mentions" relations
    5. Add extracted relations between entities

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

    # 2. Extract knowledge from each chunk and collect results
    chunk_results = []
    for i, chunk in enumerate(chunks):
        try:
            page_number = chunk.metadata.get("page_number") if chunk.metadata else None
            result = await extractor.extract(
                chunk.content,
                chunk_id=chunk.id,
                document_id=document.id,
                page_number=page_number,
            )
            if result.entities:
                chunk_results.append(result)
                logger.info(
                    f"Chunk {i} extraction: {len(result.entities)} entities, "
                    f"{len(result.relations)} relations"
                )
        except Exception as e:
            logger.warning(f"Failed to extract from chunk {i}: {e}")

    if not chunk_results:
        logger.warning(f"No entities extracted from any chunk in {file_name}")
        return total_entities, total_relations

    # 3. Merge all chunk extraction results (deduplicate)
    merged = extractor.merge_results(chunk_results)
    logger.info(
        f"Merged extraction from {len(chunk_results)} chunks: "
        f"{len(merged.entities)} unique entities, {len(merged.relations)} relations"
    )

    # 4. Add extracted entities + doc→entity "mentions" relations
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

    # 5. Add extracted relations between entities
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
